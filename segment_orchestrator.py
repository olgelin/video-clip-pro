#!/usr/bin/env python3
"""
segment_orchestrator.py — 长视频分段剪辑编排器（调度层，不碰 pipeline.py）

为什么需要：card/pip 是「一段视频进 → 一段成品出」，30 分钟视频喂进去，
语义理解(understand)要把 1 万字+几千短语一次性塞给 LLM，会超时/超 context。

方案：长视频（>= SEG_THRESHOLD）先转录 → 找「句子停顿」切点 → 切成 N 段
（每段 ~TARGET_SEG）→ 每段独立跑 pipeline.py → ffmpeg 合并成一条。

短视频（< SEG_THRESHOLD）：直接透传调 pipeline.py，零变化，零影响。

切点规则：严格切在「相邻字之间停顿 >= MIN_GAP 秒」的地方（自然换气/断句），
绝不把一句话劈两半，保证每段语义完整、边界处不产生断句。

用法（与 pipeline.py 兼容，多一个 --segment 显式开关，默认自动判断）：
  python segment_orchestrator.py 视频.mp4 --mode card [--bgm] [--output out_dir]
"""
from __future__ import annotations
import argparse, json, math, subprocess, sys, time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

# ── 分段参数 ──────────────────────────────────────────
SEG_THRESHOLD = 600.0   # >= 600s(10分钟) 才分段
TARGET_SEG = 600.0      # 每段目标时长 10 分钟
MIN_GAP = 1.5           # 切点停顿阈值：相邻字之间 >= 1.5s 才算「句子边界」
SEARCH_WINDOW = 90.0    # 在理想边界 ±90s 内找最佳停顿点


def ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=30)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def transcribe_for_cuts(path: Path):
    """转录，只拿逐字时间戳（raw_words）用于找停顿切点。复用 faster-whisper large-v3。"""
    from faster_whisper import WhisperModel
    from core.gpu import detect_gpu
    gpu = detect_gpu()
    print(f"  [orchestrator] 转录找切点 (large-v3, {gpu['whisper_device']}) ...")
    t0 = time.time()
    model = WhisperModel("large-v3", device=gpu["whisper_device"], compute_type=gpu["whisper_compute"])
    segments, _info = model.transcribe(str(path), language="zh", beam_size=5, word_timestamps=True)
    raw_words = []
    for seg in segments:
        if seg.words:
            for w in seg.words:
                raw_words.append({"start": round(w.start, 2), "end": round(w.end, 2), "text": w.word.strip()})
    print(f"  [orchestrator] 转录完成 {len(raw_words)} 字, {time.time()-t0:.0f}s")
    return raw_words


def find_cut_points(raw_words, total_dur):
    """在每段理想边界 ±SEARCH_WINDOW 内，找停顿(gap)最大的点作为切点。"""
    # 收集所有 >= MIN_GAP 的停顿
    gaps = []
    for i in range(len(raw_words) - 1):
        gap = raw_words[i + 1]["start"] - raw_words[i]["end"]
        if gap >= MIN_GAP:
            mid = (raw_words[i]["end"] + raw_words[i + 1]["start"]) / 2
            gaps.append((mid, gap))
    n_segs = max(1, int(math.ceil(total_dur / TARGET_SEG)))
    if n_segs <= 1:
        return []
    cut_points = []
    for i in range(1, n_segs):
        ideal = total_dur * i / n_segs
        best = None
        for mid, gap in gaps:
            if abs(mid - ideal) <= SEARCH_WINDOW:
                if best is None or gap > best[1]:
                    best = (mid, gap)
        if best:
            cut_points.append(best[0])
            print(f"  [orchestrator] 切点 {i}: 理想 {ideal:.0f}s → 停顿处 {best[0]:.0f}s (gap {best[1]:.1f}s)")
        else:
            cut_points.append(ideal)
            print(f"  [orchestrator] 切点 {i}: 理想 {ideal:.0f}s 附近无停顿，用理想边界")
    return cut_points


def split_video(path: Path, cut_points, workdir: Path):
    """ffmpeg 按切点切成 N 段（-c copy 快切，切在静音停顿处偏差可忽略）。"""
    bounds = [0.0] + cut_points + [None]
    seg_paths = []
    for i in range(len(bounds) - 1):
        start = bounds[i]
        end = bounds[i + 1]
        seg = workdir / f"_seg_{i:02d}.mp4"
        cmd = ["ffmpeg", "-y", "-ss", f"{start:.2f}"]
        if end is not None:
            cmd += ["-to", f"{end:.2f}"]
        cmd += ["-i", str(path), "-c", "copy", "-avoid_negative_ts", "make_zero", str(seg)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0 or not seg.exists():
            print(f"  [orchestrator] ❌ 切段 {i} 失败: {r.stderr[-200:] if r.stderr else ''}")
            raise RuntimeError(f"切段 {i} 失败")
        seg_paths.append(seg)
    print(f"  [orchestrator] 切成 {len(seg_paths)} 段")
    return seg_paths


def run_pipeline(seg_path: Path, mode: str, out_dir: Path, extra_args: list):
    """对单段调 pipeline.py（透传 mode + 其余参数）。"""
    cmd = [sys.executable, str(SCRIPT_DIR / "pipeline.py"), str(seg_path),
           "--mode", mode, "--output", str(out_dir)] + extra_args
    print(f"  [orchestrator] 跑段 {out_dir.name}: {' '.join(cmd[1:4])} ...")
    r = subprocess.run(cmd, cwd=str(SCRIPT_DIR), timeout=7200)
    if r.returncode != 0:
        print(f"  [orchestrator] ⚠️ 段 {out_dir.name} 失败 (exit {r.returncode})，跳过")
        return None
    final = out_dir / "final_polished.mp4"
    return final if final.exists() else None


def concat_segments(finals: list, final_out: Path):
    """ffmpeg concat 合并所有段的 final_polished.mp4。"""
    list_file = final_out.parent / "_concat_list.txt"
    list_file.write_text("".join(f"file '{Path(f).resolve().as_posix()}'\n" for f in finals), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
           "-c", "copy", str(final_out)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    list_file.unlink(missing_ok=True)
    if r.returncode != 0 or not final_out.exists():
        raise RuntimeError(f"合并失败: {r.stderr[-200:] if r.stderr else ''}")
    return final_out


def main():
    parser = argparse.ArgumentParser(description="长视频分段剪辑编排器（card/pip 前置）")
    parser.add_argument("video", help="输入视频文件")
    parser.add_argument("--mode", choices=["card", "pip"], default="card", help="布局模式")
    parser.add_argument("--output", "-o", help="输出目录")
    parser.add_argument("--segment", action="store_true", help="强制分段（默认自动判断）")
    parser.add_argument("--no-segment", action="store_true", help="强制不分段")
    # 以下参数透传给 pipeline.py
    parser.add_argument("--bgm", action="store_true", help="加 BGM")
    parser.add_argument("--no-bgm", action="store_true", dest="no_bgm", help="禁用 BGM")
    parser.add_argument("--no-2x", action="store_true", dest="no_2x", help="跳过 4K")
    parser.add_argument("--whisper-model", "-m", default="large-v3")
    parser.add_argument("--lang", default="zh")
    args = parser.parse_args()

    video = Path(args.video).resolve()
    if not video.exists():
        print(f"ERROR: 文件不存在 {video}")
        sys.exit(1)

    total_dur = ffprobe_duration(video)
    print(f"\n[orchestrator] 输入: {video.name} ({total_dur:.0f}s / {total_dur/60:.1f} 分钟)")

    out_root = Path(args.output) if args.output else (SCRIPT_DIR / "output" / args.mode / video.stem)

    # 透传参数
    extra = []
    if args.bgm: extra.append("--bgm")
    if args.no_bgm: extra.append("--no-bgm")
    if args.no_2x: extra.append("--no-2x")
    if args.whisper_model: extra += ["--whisper-model", args.whisper_model]
    if args.lang: extra += ["--lang", args.lang]

    # ── 判断是否分段 ──
    do_segment = args.segment
    if args.no_segment:
        do_segment = False
    elif total_dur >= SEG_THRESHOLD:
        do_segment = True

    if not do_segment:
        # 短视频：直接透传调 pipeline.py（零变化）
        print(f"  [orchestrator] 时长 < {SEG_THRESHOLD/60:.0f} 分钟，直接走现有管道（不分段）\n")
        cmd = [sys.executable, str(SCRIPT_DIR / "pipeline.py"), str(video),
               "--mode", args.mode, "--output", str(out_root)] + extra
        subprocess.run(cmd, cwd=str(SCRIPT_DIR))
        return

    # ── 长视频：分段处理 ──
    print(f"  [orchestrator] 时长 >= {SEG_THRESHOLD/60:.0f} 分钟，启动分段剪辑\n")
    workdir = out_root / "_segments"
    workdir.mkdir(parents=True, exist_ok=True)

    raw_words = transcribe_for_cuts(video)
    cut_points = find_cut_points(raw_words, total_dur)
    if not cut_points:
        print("  [orchestrator] 无需分段，直接走完整管道")
        subprocess.run([sys.executable, str(SCRIPT_DIR / "pipeline.py"), str(video),
                        "--mode", args.mode, "--output", str(out_root)] + extra,
                       cwd=str(SCRIPT_DIR))
        return

    seg_paths = split_video(video, cut_points, workdir)

    finals = []
    for i, seg in enumerate(seg_paths):
        seg_out = out_root / f"seg_{i:02d}"
        final = run_pipeline(seg, args.mode, seg_out, extra)
        if final:
            finals.append(final)
        else:
            print(f"  [orchestrator] ⚠️ 段 {i} 失败，已跳过（会反映在最终时长里）")

    if not finals:
        print("  [orchestrator] ❌ 所有段都失败")
        sys.exit(1)

    final_out = out_root / "final_polished.mp4"
    concat_segments(finals, final_out)
    mb = final_out.stat().st_size / (1024 * 1024)
    print(f"\n[orchestrator] ✅ 分段剪辑完成: {final_out} ({mb:.1f} MB, {len(finals)} 段合并)")

    # 清理分段中间文件
    for seg in seg_paths:
        seg.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

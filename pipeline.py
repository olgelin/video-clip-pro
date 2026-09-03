#!/usr/bin/env python3
"""
Video Factory Pro — YAML-driven pipeline entry point.
Transcribe → dual-pass LLM → auto-refine → cut+concat → HyperFrames captions.
Uses core/loader.py + core/provider.py + factory.yaml
"""

import json, os, re, subprocess, sys, time, argparse, traceback, shutil
from pathlib import Path

import yaml
from core import CheckpointManager, QualityGate
from core.provider import Provider, CostTracker
from core.loader import PipelineLoader, StageResult
from core.gpu import detect_gpu, status as gpu_status

SCRIPT_DIR = Path(__file__).parent.resolve()

# ── Dependency check ──────────────────────────────

def check_dependencies():
    """Check all required system dependencies."""
    print("Checking dependencies...")
    all_ok = True
    pyv = sys.version.split()[0]
    print(f"  Python: {pyv}")
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        v = r.stdout.split()[2] if r.stdout else "?"
        print(f"  ffmpeg: {v}")
    except Exception as e:
        print(f"  ffmpeg: NOT FOUND ({str(e)[:30]})")
        all_ok = False
    npx_path = shutil.which("npx") or shutil.which("npx.cmd") or shutil.which("npx.bat")
    if npx_path:
        print("  npx: found")
    else:
        print("  npx: NOT FOUND - install Node.js")
        all_ok = False
    # Check API key
    key = _load_api_key()
    if key:
        masked = key[:6] + "..." + key[-4:] if len(key) > 12 else "set"
        print(f"  API key: {masked}")
    else:
        print("  API key: NOT FOUND (set DEEPSEEK_API_KEY or in call_llm_v2.py)")
        all_ok = False
    return all_ok

def _load_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key: return key
    kp = SCRIPT_DIR / "call_llm_v2.py"
    if kp.exists():
        m = re.search(r"(sk|sks)-[a-zA-Z0-9]+", kp.read_text(encoding="utf-8"))
        if m: return m.group(0)
    return None

# ── Main ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Video Factory Pro — YAML-driven pipeline")
    parser.add_argument("video", nargs="?", help="Input video file path (pip/V23 必填；avatar 模式用 --topic 代替)")
    parser.add_argument("--topic", type=str, help="话题/碎碎念文字输入（avatar-seed / avatar-short 模式用）")
    parser.add_argument("--orientation", choices=["portrait", "landscape"], default="portrait",
                       help="数字人视频方向：portrait 竖屏(默认) / landscape 横屏")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--whisper-model", "-m", default="large-v3", help="Whisper model size (default: large-v3)")
    parser.add_argument("--lang", default="zh", help="Language code (default: zh)")
    parser.add_argument("--doctor", action="store_true", help="Check dependencies without running")
    parser.add_argument("--debug", action="store_true", help="Keep intermediate files")
    parser.add_argument("--no-2x", action="store_true", dest="no_2x", help="Skip 2x upscale (save space)")
    parser.add_argument("--bgm", action="store_true", help="Add AI-generated background music with ducking")
    parser.add_argument("--no-bgm", action="store_true", dest="no_bgm",
                        help="Disable BGM（avatar-short/avatar-seed 默认开 BGM，用此关闭）")
    parser.add_argument("--mode", choices=["fullscreen", "pip", "avatar", "avatar-seed", "avatar-short"], default="fullscreen",
                       help="Layout mode: fullscreen(V23) / pip(画中画) / avatar-seed(碎碎念→数字人) / avatar-short(话题→数字人)")
    args = parser.parse_args()

    if args.doctor:
        ok = check_dependencies()
        print("\n  " + ("ALL OK!" if ok else "SOME CHECKS FAILED!"))
        return

    # 🔴 avatar 系列（seed/short）用 --topic 输入，不走 video 剪切
    is_avatar_topic = args.mode in ("avatar-seed", "avatar-short")
    if is_avatar_topic:
        if not args.topic or not args.topic.strip():
            print(f"ERROR: --mode {args.mode} 需要 --topic \"话题/碎碎念\"")
            sys.exit(1)
        video_path = Path(args.topic.strip())  # 占位，实际走 topic 文字
    else:
        if not args.video:
            parser.print_help()
            sys.exit(1)
        video_path = Path(args.video).resolve()
        if not video_path.exists():
            print(f"ERROR: File not found: {video_path}")
            sys.exit(1)

    # 🔴 统一输出路径：output/<mode>/<标识>/（avatar 用 topic 前 20 字做目录名）
    if is_avatar_topic:
        topic_tag = re.sub(r'[\\/:*?"<>|\s]+', "_", args.topic.strip())[:20]
        output_dir = Path(args.output) if args.output else Path(SCRIPT_DIR, "output", args.mode, topic_tag)
    else:
        output_dir = Path(args.output) if args.output else Path(SCRIPT_DIR, "output", args.mode, video_path.stem)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Init core modules
    checkpoint = CheckpointManager(output_dir)
    cost_tracker = CostTracker(str(output_dir))
    quality = QualityGate(output_dir)
    provider = Provider(cost_tracker)

    # Load pipeline definition
    _mode_yaml = {"fullscreen": "v23", "pip": "pip", "avatar": "avatar",
                  "avatar-seed": "avatar_seed", "avatar-short": "avatar_short"}.get(args.mode, "v23")
    yaml_path = SCRIPT_DIR / "pipeline_defs" / f"{_mode_yaml}.yaml"
    loader = PipelineLoader(provider)
    manifest = loader.load(str(yaml_path))

    print("\n" + "=" * 60)
    print(f"  {manifest.get('description', 'Video Factory Pro')}")
    print("=" * 60)
    print(f"  Input : {args.topic if is_avatar_topic else video_path}")
    print(f"  Output: {output_dir}/")
    print(f"  Stages: {len(manifest.get('stages', []))}")
    print(f"  API   : {provider._load_key()[:8]}...")
    gpu_status()

    # Build context
    context = {
        "video_path": str(video_path),
        "output_dir": str(output_dir),
        "whisper_model": args.whisper_model,
        "lang": args.lang,
        "provider": provider,
        "enable_bgm": args.bgm or (not args.no_bgm and is_avatar_topic),
        "layout_mode": args.mode,
        "no_2x": args.no_2x,
        "topic": args.topic or "",  # 🔴 avatar-seed/short 的文字输入
        "speech_text": args.topic or "",  # 🔴 avatar-seed 的碎碎念原文
        "orientation": args.orientation,  # 🔴 数字人视频方向（duix 形象库选竖/横）
    }

    # Run pipeline
    t0 = time.time()
    try:
        final_ctx = loader.run(manifest, context)

        # Summary
        elapsed = time.time() - t0
        final_path = final_ctx.get("final_polished") or final_ctx.get("final_path") or ""
        original_dur = final_ctx.get("duration", 0)
        final_dur = final_ctx.get("final_dur", 0)

        print()
        print("=" * 60)
        print(f"  DONE! ({elapsed:.0f}s)")
        if original_dur:
            pct = ((original_dur - final_dur) / original_dur * 100) if original_dur > 0 else 0
            print(f"  Original : {original_dur:.1f}s → Final: {final_dur:.1f}s ({pct:.0f}% shorter)")
        if final_path and Path(final_path).exists():
            mb = Path(final_path).stat().st_size / (1024 * 1024)
            print(f"  Output   : {final_path} ({mb:.1f} MB)")
        print(f"  {quality.summary()}")
        print(f"  {provider.cost.summary()}")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR: Pipeline failed: {e}")
        traceback.print_exc()
        # Save partial context
        partial = {"status": "failed", "error": str(e), "output_dir": str(output_dir)}
        (output_dir / "pipeline_error.json").write_text(
            json.dumps(partial, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"  Partial context saved to {output_dir/'pipeline_error.json'}")
        sys.exit(1)

    # Cleanup: 生产模式（非 --debug）只留最终成品，删所有中间产物 → 目录极简
    if not args.debug:
        _cleanup_output(output_dir)


def _cleanup_output(output_dir: Path):
    """极简化：只保留 final_polished.mp4 + final_polished_2x.mp4，删除所有中间产物。"""
    keep_files = {"final_polished.mp4", "final_polished_2x.mp4"}
    # 中间产物目录（全部可重建）
    subdirs = ["checkpoints", "hyperframes", "hf_build_pip", "hf_build", "segments", "renders"]
    for sub in subdirs:
        p = output_dir / sub
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    # 中间产物文件（全部可重建）
    junk_files = ["final.mp4", "transcript.json", "pipeline_context.json", "cost_log.json",
                  "_captions.ass", "_pip_frame.png", "_composed.mp4", "_with_audio.mp4",
                  "_test_composed.mp4", "pipeline_error.json"]
    for name in junk_files:
        p = output_dir / name
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
    # 其余非成品文件也清掉（保留 keep_files）
    for p in output_dir.iterdir():
        if p.is_file() and p.name not in keep_files:
            try:
                p.unlink()
            except Exception:
                pass
    print(f"      中间产物已清理，只留成品（{', '.join(sorted(keep_files))}）")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

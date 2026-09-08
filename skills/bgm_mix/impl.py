"""bgm_mix skill — ACE-Step BGM + ducking + audio mix.

Pipeline position: after hf_build, before upscale.
Only runs when context['enable_bgm'] is True (--bgm flag).

Flow:
  1. ACE-Step generates BGM from transcript + mood caption
  2. Extract speech audio from final video
  3. Compute ducking envelope from EDL segment timestamps
  4. Mix speech + ducked BGM → replace video audio
"""
from __future__ import annotations
import json, subprocess, sys, os, random, re
from pathlib import Path
from core.base import SkillBase

ACESTEP_PYTHON = Path(
    r"E:\Hermes-Agent\workspace\xiaoshan\video-factory\tools\acestep\.venv\Scripts\python.exe"
)
ACESTEP_CLI = Path(r"E:\Hermes-Agent\workspace\xiaoshan\video-factory\tools\acestep\cli.py")


class Bgm_mix(SkillBase):
    name = "bgm_mix"

    def execute(self, context: dict) -> dict:
        if not context.get("enable_bgm"):
            return context

        video_path = Path(context.get("final_polished", "")).resolve()
        edl = context.get("edl", {})
        ranges = edl.get("ranges", [])
        # 🔴 avatar-short/seed 无剪切无 edl，用 storyboard 的场景时间戳做 ducking
        if not ranges:
            scenes = context.get("scenes", [])
            ranges = [{"start": s.get("final_start", 0), "end": s.get("final_end", 0)}
                      for s in scenes if s.get("final_end")]

        if not video_path.is_file() or not ranges:
            print("      [bgm_mix] No video or segments, skipping")
            return context

        output_dir = video_path.parent.resolve()
        bgm_path = output_dir / "bgm.wav"
        mix_path = output_dir / "final_bgm.mp4"

        print(f"\n      [bgm_mix] Generating BGM + ducking mix ...")

        # 1. Generate BGM via ACE-Step
        if not self._gen_bgm(context, output_dir, bgm_path):
            print("      [bgm_mix] BGM generation failed, keeping original")
            return context

        # 2. Compute ducking envelope from segment timeline
        total_dur = self._video_duration(video_path)
        duck_curve = self._ducking_curve(ranges, total_dur)

        # 3. Mix: extract speech, duck BGM, merge
        if self._mix_with_ducking(video_path, bgm_path, duck_curve, mix_path) and mix_path.exists():
            # Replace final_polished with the mixed version
            backup = output_dir / "final_no_bgm.mp4"
            backup.unlink(missing_ok=True)
            video_path.rename(backup)
            mix_path.rename(video_path)
            mb = video_path.stat().st_size / (1024 * 1024)
            print(f"      [bgm_mix] ✅ Mixed with BGM: {video_path} ({mb:.1f} MB)")
            context["bgm_path"] = str(bgm_path)
        else:
            print("      [bgm_mix] Mix failed, keeping original")
            bgm_path.unlink(missing_ok=True)

        return context

    # ── BGM generation ──────────────────────────────────

    def _gen_bgm(self, context: dict, output_dir: Path, bgm_path: Path) -> bool:
        """Call ACE-Step via isolated venv to generate instrumental BGM."""
        if not ACESTEP_PYTHON.exists() or not ACESTEP_CLI.exists():
            print("      [bgm_mix] ACE-Step not available, skipping BGM")
            return False

        # 🔴 歌词来源：优先 lyrics_writer 写好的歌词（映射哲学，[Chorus]/[Verse] 结构），
        # fallback 到口播稿原文（对齐 video-factory：先写歌词→再唱歌生成 BGM）
        lyrics = context.get("lyrics", "")
        if not lyrics:
            words = context.get("words", [])
            transcript = " ".join(w.get("text", "") for w in words) if words else ""
            if not transcript:
                script = context.get("script_data", {})
                sections = script.get("voiceover_sections", []) if isinstance(script, dict) else []
                transcript = " ".join(s.get("content", "") for s in sections)
            if not transcript:
                transcript = context.get("text", "") or context.get("topic", "")
            lyrics = transcript

        # Write lyrics to temp file for ACE-Step --lyrics
        lyrics_file = output_dir / "_bgm_lyrics.txt"
        lyrics_file.write_text(lyrics[:2000], encoding="utf-8")

        # Build mood caption from EDL beats / topic
        caption = self._build_caption(context)

        video_path = context.get("final_polished", "")
        # 🔴 对齐 VF：BGM 时长按歌词长度+随机抖动（在一个范围内变化，不锁死）
        duration = int(self._calc_bgm_duration(lyrics, self._video_duration(Path(video_path))))

        print(f"      [bgm_mix] ACE-Step 抽卡: dur={duration}s, caption=\"{caption[:60]}...\"")

        # 🔴 抽卡：生成 N 首（每次随机 seed），筛废品 + 客观指标打分挑最健康的
        # 267s 长 BGM 每首 ~3 分钟，偶发卡死，抽 3 首足够挑优（4 首边际收益低、卡死概率翻倍）
        N_SAMPLES = 3
        candidates = []
        for i in range(N_SAMPLES):
            cand = output_dir / f"_bgm_cand_{i}.wav"
            if self._run_acestep_once(lyrics_file, cand, duration, caption):
                candidates.append(cand)
        lyrics_file.unlink(missing_ok=True)

        if not candidates:
            print("      [bgm_mix] ACE-Step 全部生成失败")
            return False

        best = self._pick_best(candidates, duration)
        for c in candidates:
            if c != best:
                c.unlink(missing_ok=True)
        best.rename(bgm_path)
        print(f"      [bgm_mix] ✅ 从 {len(candidates)} 首里挑出最好: {bgm_path.stat().st_size // 1024}KB")
        return True

    def _run_acestep_once(self, lyrics_file: Path, output_path: Path, duration: int, caption: str) -> bool:
        """调用 ACE-Step 生成一首 BGM 到 output_path（每次随机 seed）。

        坑（2026-09-08 实测 30min 视频）：ACE-Step 生成 267s 音乐会偶发卡死，且
        subprocess.run(capture_output=True) 用管道捕获输出时，孙进程继承管道写端 →
        超时 kill 主进程后 communicate() 卡在回收管道，TimeoutExpired 永远抛不出来，
        整个 pipeline 被拖死 2 小时。
        解法：stdout/stderr 重定向到文件（不用管道，彻底避开管道阻塞），超时用
        taskkill /T 杀整个进程树（含孙进程），单首卡死跳过不阻塞后续抽卡。
        """
        cmd = [
            str(ACESTEP_PYTHON), str(ACESTEP_CLI),
            "--lyrics", str(lyrics_file),
            "--output", str(output_path),
            "--duration", str(duration),
            "--captions", caption,
        ]
        log_file = output_path.with_suffix(".log")
        logf = open(log_file, "w", encoding="utf-8")
        try:
            proc = subprocess.Popen(
                cmd, stdout=logf, stderr=subprocess.STDOUT,
                cwd=str(ACESTEP_CLI.parent),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                proc.wait(timeout=600)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True, text=True)
                print("      [bgm_mix] 一首卡死超时，已杀进程树")
                output_path.unlink(missing_ok=True)
                return False
            ok = proc.returncode == 0 and output_path.exists()
            if not ok:
                print(f"      [bgm_mix] 一首生成失败 (exit {proc.returncode})")
                output_path.unlink(missing_ok=True)
            return ok
        except Exception as e:
            print(f"      [bgm_mix] 一首出错: {e}")
            output_path.unlink(missing_ok=True)
            return False
        finally:
            logf.close()
            log_file.unlink(missing_ok=True)

    def _pick_best(self, candidates: list, target_dur: float) -> Path:
        """客观指标打分，选最健康的（不是废品 + 有起伏）"""
        scored = []
        for c in candidates:
            s = self._score_bgm(c, target_dur)
            scored.append((s, c))
            print(f"      [bgm_mix] 候选 {c.name}: 分={s}")
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]

    def _score_bgm(self, path: Path, target_dur: float) -> int:
        """用 ffmpeg volumedetect + silencedetect 提取客观指标打分。
        高分 = 不是死静音 + 不削波 + 静音少 + 有正常起伏。"""
        score = 0
        try:
            # 1. 音量检测
            r = subprocess.run(
                ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, text=True, timeout=30,
            )
            mean_vol = max_vol = None
            for line in r.stderr.split("\n"):
                if "mean_volume" in line:
                    try:
                        mean_vol = float(line.split(":")[-1].strip().split(" ")[0])
                    except (ValueError, IndexError):
                        pass
                elif "max_volume" in line:
                    try:
                        max_vol = float(line.split(":")[-1].strip().split(" ")[0])
                    except (ValueError, IndexError):
                        pass

            # 2. 静音检测（连续 3 秒 < -35dB 视为静音）
            r2 = subprocess.run(
                ["ffmpeg", "-i", str(path), "-af", "silencedetect=n=-35dB:d=3", "-f", "null", "-"],
                capture_output=True, text=True, timeout=30,
            )
            silence_dur = 0.0
            for line in r2.stderr.split("\n"):
                if "silence_duration" in line:
                    try:
                        silence_dur += float(line.split(":")[-1].strip())
                    except (ValueError, IndexError):
                        pass

            # 3. 打分
            if mean_vol is not None and mean_vol > -40:
                score += 2  # 不是死静音
            if max_vol is not None and max_vol <= 0:
                score += 1  # 不削波
            if silence_dur < 0.2 * target_dur:
                score += 1  # 静音占比 < 20%
            if mean_vol is not None and max_vol is not None:
                dynamic = max_vol - mean_vol
                if 5 < dynamic < 35:
                    score += 1  # 有正常起伏（不单调）
            return score
        except Exception as e:
            print(f"      [bgm_mix] 打分出错 {path.name}: {e}")
            return 0

    def _build_caption(self, context: dict) -> str:
        """对齐 VF：按场景 mood（中文情绪）映射 music mood。scenes 无 beat 字段（storyboard 只存 mood），
        之前用 s.get("beat") 拿到空串 → caption 永远兜底。改用 mood 字段。"""
        scenes = context.get("scenes", [])
        # 中文 mood → 英文 music mood（语义对齐 vf 的 MOOD_MAP）
        mood_map = {
            "冲击 悬念": "energetic, attention-grabbing",
            "冷静 理性": "building, informative",
            "紧张 对立": "tense, dramatic",
            "冲突 焦虑": "emotional, determined",
            "开阔 希望": "triumphant, inspirational",
        }
        moods = []
        seen = set()
        for s in scenes:
            m = s.get("mood", "")
            if m in mood_map and m not in seen:
                seen.add(m)
                moods.append(mood_map[m])
        # 兜底：card/pip 模式用 edl ranges 的 narrative beat 映射
        if not moods:
            edl = context.get("edl", {})
            ranges = edl.get("ranges", [])
            if ranges:
                beat_map = {
                    "HOOK": "energetic, attention-grabbing",
                    "CONTEXT": "building, informative",
                    "PROBLEM": "tense, dramatic",
                    "STRUGGLE": "emotional, determined",
                    "RESOLUTION": "triumphant, inspirational",
                }
                beats = set(r.get("beat", "").upper() for r in ranges)
                for b in beats:
                    if b in beat_map and beat_map[b] not in moods:
                        moods.append(beat_map[b])
        base = ", ".join(moods[:3]) if moods else "cinematic, engaging"
        return f"{base}, instrumental, 100-120 BPM, background music for narration"

    def _calc_bgm_duration(self, lyrics_text: str, video_dur: float = 0) -> float:
        """对齐 VF bgm_generator 的 _calc_duration_by_lyrics：BGM 时长按歌词长度
        线性映射到固定区间 + 随机抖动（不锁死，不跟视频时长跑）。"""
        _MIN_DURATION = 210  # 3分30秒
        _MAX_DURATION = 280  # 4分40秒
        clean = re.sub(r'\[.*?\]', '', lyrics_text)
        clean = re.sub(r'[^\u4e00-\u9fff]', '', clean)
        char_count = len(clean)
        # 线性映射：200字→210s，500字→280s，中间线性插值
        base = _MIN_DURATION + (char_count - 200) / (500 - 200) * (_MAX_DURATION - _MIN_DURATION)
        base = max(_MIN_DURATION, min(_MAX_DURATION, base))
        # 随机抖动 ±8s（让每首歌时长有变化，不锁死）
        jitter = random.uniform(-8, 8)
        duration = base + jitter
        return round(max(_MIN_DURATION, min(_MAX_DURATION, duration)), 1)

    # ── Ducking & mixing ────────────────────────────────

    def _ducking_curve(self, ranges: list, total_dur: float) -> str:
        """Build ffmpeg volume envelope: BGM dips during speech, rises in gaps.

        Returns a volume expression string like:
          'if(between(t,0,5.1),0.18,if(between(t,5.1,5.8),0.55,...))'
        """
        if not ranges:
            return "0.2"

        # Compute segment positions in final concatenated timeline
        segments = []  # (start, end) in final video
        cursor = 0.0
        for r in ranges:
            dur = r["end"] - r["start"]
            segments.append((cursor, cursor + dur))
            cursor += dur

        # Find gaps between segments
        duck_speech_vol = 0.18   # BGM volume during speech
        duck_gap_vol = 0.55      # BGM volume during gaps/transitions
        fade_ms = 200             # crossfade between levels

        # Build expression: for each segment+gap, nest if(between(...), vol, ...)
        # For simplicity with many segments, use a stepped approach:
        # Create a volume timeline as [time, volume] pairs
        timeline = []
        prev_end = 0.0
        for seg_start, seg_end in segments:
            # Gap before this segment (if any)
            if seg_start > prev_end + 0.05:
                timeline.append((prev_end, duck_gap_vol))
                timeline.append((seg_start, duck_gap_vol))
            # Speech segment
            timeline.append((seg_start, duck_speech_vol))
            timeline.append((seg_end, duck_speech_vol))
            prev_end = seg_end

        # Final gap after last segment
        if prev_end < total_dur:
            timeline.append((prev_end, duck_gap_vol))
            timeline.append((total_dur, duck_gap_vol))

        if len(timeline) < 4:
            return str(duck_speech_vol)

        # Simplify: deduplicate consecutive same-volume entries
        deduped = []
        for t, v in timeline:
            if not deduped or abs(v - deduped[-1][1]) > 0.01:
                deduped.append((t, v))
        # Add final hold
        if deduped and deduped[-1][0] < total_dur:
            deduped.append((total_dur, deduped[-1][1]))

        if len(deduped) < 2:
            return str(duck_speech_vol)

        # Build nested if(between(t, t0, t1), vol, default)
        # Iterate reversed: each (t0, v0) → (next_t, _) becomes one condition
        expr = str(duck_gap_vol)
        for i in range(len(deduped) - 2, -1, -1):
            t0, v0 = deduped[i]
            t1, _ = deduped[i + 1]
            if t1 > t0 + 0.05:
                expr = f"if(between(t,{t0:.2f},{t1:.2f}),{v0},{expr})"

        return expr

    def _mix_with_ducking(
        self, video_path: Path, bgm_path: Path, duck_curve: str, output: Path
    ) -> bool:
        """Extract speech, duck BGM, mix, replace audio in video."""
        tmp_dir = video_path.parent
        speech_audio = tmp_dir / "_speech.wav"
        ducked_bgm = tmp_dir / "_ducked_bgm.wav"
        mixed_audio = tmp_dir / "_mixed.wav"

        try:
            # Extract speech audio from video
            r = subprocess.run([
                "ffmpeg", "-y", "-i", str(video_path),
                "-vn", "-acodec", "pcm_s16le", str(speech_audio),
            ], capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return False

            # Get video duration for BGM trim
            dur = self._video_duration(video_path)

            # Apply ducking: BGM volume envelope + trim to video length + fade in/out
            r = subprocess.run([
                "ffmpeg", "-y",
                "-i", str(bgm_path),
                "-filter_complex",
                f"[0:a]atrim=0:{dur + 1},volume='{duck_curve}':eval=frame,"
                f"afade=t=in:st=0:d=2,afade=t=out:st={dur - 3}:d=3[bgm]",
                "-map", "[bgm]",
                str(ducked_bgm),
            ], capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                print(f"        ducking failed: {r.stderr[-200:]}")
                return False

            # Mix speech + ducked BGM
            r = subprocess.run([
                "ffmpeg", "-y",
                "-i", str(speech_audio),
                "-i", str(ducked_bgm),
                "-filter_complex",
                "[0:a]volume=1.5[speech];"
                "[speech][1:a]amix=inputs=2:duration=first:dropout_transition=3[out]",
                "-map", "[out]",
                str(mixed_audio),
            ], capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return False

            # Replace audio in video
            r = subprocess.run([
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(mixed_audio),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest",
                str(output),
            ], capture_output=True, text=True, timeout=60)
            return r.returncode == 0 and output.exists()

        finally:
            # Cleanup temp files
            for f in (speech_audio, ducked_bgm, mixed_audio):
                f.unlink(missing_ok=True)

    def _video_duration(self, path: Path) -> float:
        r = subprocess.run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ], capture_output=True, text=True, timeout=10)
        try:
            return float(r.stdout.strip())
        except (ValueError, AttributeError):
            return 120.0

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

        print(f"      [bgm_mix] ACE-Step: dur={duration}s, caption=\"{caption[:60]}...\"")

        cmd = [
            str(ACESTEP_PYTHON), str(ACESTEP_CLI),
            "--lyrics", str(lyrics_file),
            "--output", str(bgm_path),
            "--duration", str(duration),
            "--captions", caption,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
                cwd=str(ACESTEP_CLI.parent),
            )
            if result.returncode == 0 and bgm_path.exists():
                print(f"      [bgm_mix] BGM generated: {bgm_path.stat().st_size // 1024}KB")
                lyrics_file.unlink(missing_ok=True)
                return True

            print(f"      [bgm_mix] ACE-Step failed (exit {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-3:]:
                    print(f"        {line}")
        except subprocess.TimeoutExpired:
            print("      [bgm_mix] ACE-Step timeout (10min)")
        except Exception as e:
            print(f"      [bgm_mix] ACE-Step error: {e}")

        lyrics_file.unlink(missing_ok=True)
        return False

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
        # 兜底：fullscreen/pip 模式用 edl ranges 的 narrative beat 映射
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

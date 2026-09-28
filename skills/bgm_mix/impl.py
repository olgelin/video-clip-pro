"""bgm_mix skill — YuE2 BGM + ducking + audio mix.

Pipeline position: after hf_build, before upscale.
Only runs when context['enable_bgm'] is True (--bgm flag).

Flow:
  1. YuE2 generates BGM from transcript + mood caption (cot=full)
  2. Extract speech audio from final video
  3. Compute ducking envelope from EDL segment timestamps
  4. Mix speech + ducked BGM → replace video audio
"""
from __future__ import annotations
import json, subprocess, sys, os, random, re, uuid, time
import urllib.request
from pathlib import Path
from core.base import SkillBase

# YuE2（audio.cpp，音乐主力：器乐编曲/旋律/情感强于 Music3）
AUDIOCPP_CLI = "E:/YuE2/audio_cpp/audiocpp_cli.exe"
YUE2_MODELS = "E:/YuE2/models"

# MiniMax Music3（ComfyUI 原生节点，YuE2 失败时兜底）
COMFY_URL = "http://127.0.0.1:8188"
MINIMAX_UNET = "minimax_music3_dit_int8_convrot.safetensors"
MINIMAX_CLIP = "minimax_music3_text_encoder_pruned_int8_convrot.safetensors"
MINIMAX_VAE = "minimax_music3_dav.safetensors"


def _call_minimax_music3(caption: str, lyrics: str, output_path: str,
                         duration: float = 300) -> dict:
    """通过 ComfyUI 调用 MiniMax Music3 生成完整歌曲（带歌词）。

    caption: 三段式音乐风格描述（Global Metadata / Vocal Details / Arrangement）
    lyrics: 歌词（带结构标签）；纯音乐可为空或 [Instrumental]
    duration: 目标时长上限（秒），Music3 实际时长由歌词内容密度决定
    """
    seed = random.randint(0, 1000000)
    workflow = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": MINIMAX_UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": MINIMAX_CLIP, "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": MINIMAX_VAE}},
        "4": {"class_type": "MiniMaxMusic3TextEncode", "inputs": {
            "clip": ["2", 0], "caption": caption, "lyrics": lyrics,
            "seed": seed, "max_duration": float(duration), "cfg_scale": 1.7, "top_k": 50,
        }},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "6": {"class_type": "EmptyMiniMaxMusic3LatentAudio", "inputs": {"seconds": ["4", 1], "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "seed": seed, "steps": 30, "cfg": 1.7,
            "sampler_name": "euler", "scheduler": "simple",
            "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0], "denoise": 1.0,
        }},
        "8": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveAudio", "inputs": {"audio": ["8", 0], "filename_prefix": "bgm_minimax"}},
    }
    try:
        payload = json.dumps({"prompt": workflow, "client_id": str(uuid.uuid4())}).encode("utf-8")
        req = urllib.request.Request(f"{COMFY_URL}/prompt", data=payload,
                                     headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=60)
        r = json.loads(resp.read().decode())
        prompt_id = r.get("prompt_id")
        if not prompt_id:
            return {"error": f"ComfyUI 提交失败: {json.dumps(r.get('node_errors', {}))[:200]}"}
        start = time.time()
        timeout = max(600, int(duration * 4))
        while time.time() - start < timeout:
            time.sleep(5)
            try:
                hreq = urllib.request.Request(f"{COMFY_URL}/history/{prompt_id}")
                h = json.loads(urllib.request.urlopen(hreq, timeout=15).read().decode())
            except Exception:
                continue
            entry = h.get(prompt_id, {})
            status = entry.get("status", {}).get("status_str", "")
            if status == "success":
                for node_out in entry.get("outputs", {}).values():
                    for audio in node_out.get("audio", []):
                        filename = audio.get("filename")
                        subfolder = audio.get("subfolder", "")
                        ftype = audio.get("type", "output")
                        url = f"{COMFY_URL}/view?filename={filename}&subfolder={subfolder}&type={ftype}"
                        data = urllib.request.urlopen(urllib.request.Request(url), timeout=120).read()
                        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(data)
                        return {"success": True, "path": output_path, "duration": duration, "seed": seed}
                return {"error": "生成成功但无 audio 输出"}
            elif status in ("error", "failed"):
                return {"error": f"ComfyUI 生成失败: {json.dumps(entry.get('status', {}))[:300]}"}
        return {"error": f"ComfyUI 超时 ({timeout}s)"}
    except Exception as e:
        return {"error": f"MiniMax Music3 调用异常: {e}"}


def _call_yue2(lyrics: str, caption: str, output_path: str,
               duration: float = 300, seed: int = None) -> dict:
    """通过 audio.cpp CLI 调用 YuE2 生成音乐（cot=full 完整规划，先写 ABC 乐谱再渲染）。

    YuE2 是音乐主力（器乐编曲/旋律/情感强于 Music3，中文咬字略差）。
    caption: style 一段式（YuE2 的 style 参数，不是 Music3 三段式）
    duration: 保留参数兼容（YuE2 时长由歌词 + cot=full 结构决定）
    """
    if seed is None:
        seed = random.randint(0, 1000000)

    cmd = [
        AUDIOCPP_CLI,
        "--task", "gen", "--family", "yue2",
        "--model", YUE2_MODELS,
        "--backend", "cuda", "--threads", "8",
        "--text", lyrics,
        "--request-option", f"style={caption}",
        "--request-option", "cot=full",
        "--request-option", f"seed={seed}",
        "--request-option", "num_inference_steps=8",
        "--session-option", "yue2.model_gguf=yue2-3b-bf16.gguf",
        "--session-option", "yue2.vae_gguf=yue2-vae-f32.gguf",
        "--out", output_path,
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return {"success": True, "path": output_path, "duration": duration, "seed": seed}
        return {"error": f"YuE2 生成失败: {(r.stderr or r.stdout)[-300:]}"}
    except Exception as e:
        return {"error": f"YuE2 调用异常: {e}"}


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
        """首选 YuE2 生成完整歌曲（cot=full），失败降级 MiniMax Music3。"""
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

        # ── 首选 YuE2（音乐主力：器乐编曲/旋律/情感强于 Music3）──
        yue2_caption = context.get("yue2_caption") or self._build_caption(context)
        print(f"      [bgm_mix] YuE2 生成: caption=\"{yue2_caption[:50]}...\"")
        result = _call_yue2(lyrics, yue2_caption, str(bgm_path))
        if not result.get("error"):
            print(f"      [bgm_mix] ✅ YuE2 完成: {bgm_path.stat().st_size // 1024}KB")
            return True

        # ── 降级 MiniMax Music3（备用）──
        print(f"      [bgm_mix] ⚠️ YuE2 失败，降级 Music3: {result['error'][:80]}")
        music_caption = context.get("music_caption", "") or self._build_caption(context)
        result2 = _call_minimax_music3(music_caption, lyrics, str(bgm_path), duration=300)
        if not result2.get("error"):
            print(f"      [bgm_mix] ✅ Music3 完成: {bgm_path.stat().st_size // 1024}KB")
            return True
        print(f"      [bgm_mix] ❌ Music3 也失败: {result2['error'][:80]}")
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

            # Mix speech + ducked BGM（两输入都强制立体声，BGM 双声道别被 amix 降成单声道）
            r = subprocess.run([
                "ffmpeg", "-y",
                "-i", str(speech_audio),
                "-i", str(ducked_bgm),
                "-filter_complex",
                "[0:a]volume=1.5,aformat=channel_layouts=stereo[speech];"
                "[1:a]aformat=channel_layouts=stereo[bgm];"
                "[speech][bgm]amix=inputs=2:duration=first:dropout_transition=3[out]",
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
                "-c:a", "aac", "-b:a", "320k",
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

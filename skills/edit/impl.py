"""Edit skill — Cut + crossfade concatenate + loudnorm audio."""
from __future__ import annotations
import json, subprocess, shutil
from pathlib import Path
from core.base import SkillBase
from core.gpu import ffmpeg_encode_args, detect_gpu


class Edit(SkillBase):
    name = "edit"

    def execute(self, context: dict) -> dict:
        edl = context.get("edl") or context.get("draft_edl", {"ranges": []})
        video_path = Path(context["video_path"])
        output_dir = Path(context.get("output_dir", "test_output"))
        ranges = edl.get("ranges", [])

        gpu = detect_gpu()

        # Post-process: merge small segments, enforce constraints
        ranges = self._postprocess(ranges)
        # 🔴 修复：回写 postprocess 后的 ranges 到 edl，保证后续 storyboard 用同一份剪辑边界
        edl["ranges"] = ranges

        # Cut segments
        seg_dir = output_dir / "segments"
        seg_dir.mkdir(parents=True, exist_ok=True)
        seg_files = []
        print(f"\n[5/7] Cutting {len(ranges)} segment(s) ...")
        for i, r in enumerate(ranges):
            seg_path = seg_dir / f"seg_{i:03d}.mp4"
            start, end = r["start"], r["end"]
            dur = end - start
            beat = r.get("beat", "")
            title = r.get("title", "")[:30]
            print(f"  [{i+1}/{len(ranges)}] {start:.2f}-{end:.2f} ({dur:.2f}s) {beat} {title}")

            # GPU re-encode for frame-accurate cuts (no keyframe drift)
            enc_args = ffmpeg_encode_args(gpu)
            cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(video_path),
                   "-t", f"{dur:.3f}"] + enc_args + [str(seg_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0 and seg_path.stat().st_size > 0:
                seg_files.append(seg_path)

        if not seg_files:
            raise RuntimeError("No segments extracted")

        # Simple concat (crossfade unreliable with VFR sources)
        print(f"\n[6/7] Concatenating {len(seg_files)} segment(s) ...")
        final = output_dir / "final.mp4"
        final_tmp = output_dir / "final_tmp.mp4"

        if len(seg_files) >= 2:
            concat_file = output_dir / "_concat.txt"
            with open(concat_file, "w") as f:
                for sf in seg_files:
                    f.write(f"file '{Path(sf).resolve().as_posix()}'\n")
            enc_args = ffmpeg_encode_args(gpu)
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file)]
                + enc_args + [str(final_tmp)],
                capture_output=True, text=True, timeout=300)
            if concat_file.exists():
                concat_file.unlink()
        else:
            shutil.copy2(str(seg_files[0]), str(final_tmp))

        # Loudnorm audio
        self._loudnorm(str(final_tmp), str(final))

        # Cleanup
        if seg_dir.exists():
            shutil.rmtree(seg_dir)
        if final_tmp.exists():
            final_tmp.unlink()

        original_dur = context.get("duration", 0)
        final_dur = sum(r["end"] - r["start"] for r in ranges)
        reduction = ((original_dur - final_dur) / original_dur * 100) if original_dur > 0 else 0
        print(f"      Original: {original_dur:.1f}s → Final: {final_dur:.1f}s ({reduction:.0f}% shorter)")
        return {"final_path": str(final), "edl": edl, "final_dur": final_dur}

    def _crossfade_concat(self, seg_files: list, output: str, xfade_dur: float = 0.3):
        """Concatenate segments with smooth xfade — reset PTS for reliable filter chain."""
        import json

        n = len(seg_files)
        durations = []
        for sf in seg_files:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "json", str(sf)],
                capture_output=True, text=True, timeout=15)
            try:
                durations.append(float(json.loads(r.stdout)["format"]["duration"]))
            except:
                durations.append(3.0)

        # Build filter: reset PTS on all inputs first, then chain xfade + acrossfade
        filters = []
        for i in range(n):
            filters.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}];")
            filters.append(f"[{i}:a]asetpts=PTS-STARTPTS[a{i}];")

        # Chain video xfades
        prev_v = "v0"
        cum_offset = 0.0
        for i in range(1, n):
            offset = round(cum_offset + durations[i - 1] - xfade_dur, 3)
            if offset < 0.01: offset = 0.01
            cum_offset += durations[i - 1] - xfade_dur
            next_v = "xv" if i == n - 1 else f"xv{i}"
            filters.append(f"[{prev_v}][v{i}]xfade=transition=fade:duration={xfade_dur}:offset={offset}[{next_v}];")
            prev_v = next_v

        # Chain audio acrossfades
        prev_a = "a0"
        for i in range(1, n):
            next_a = "xa" if i == n - 1 else f"xa{i}"
            filters.append(f"[{prev_a}][a{i}]acrossfade=d={xfade_dur}[{next_a}]")
            if i < n - 1: filters.append(";")
            else: filters.append(";")
            prev_a = next_a

        filter_complex = "".join(filters)

        cmd = ["ffmpeg", "-y"]
        for sf in seg_files:
            cmd.extend(["-i", str(sf)])
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[xv]", "-map", "[xa]",
        ] + ffmpeg_encode_args() +
            [output]
        )
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            # Fallback: simple concat
            err_detail = result.stderr[-200:] if result.stderr else "unknown"
            print(f"      Crossfade failed: {err_detail}")
            print("      Falling back to simple concat")
            concat_file = Path(output).parent / "_concat.txt"
            with open(concat_file, "w") as f:
                for sf in seg_files:
                    f.write(f"file '{Path(sf).resolve().as_posix()}'\n")
            cmd2 = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file)] + ffmpeg_encode_args() + [output]
            subprocess.run(cmd2, capture_output=True, text=True, timeout=300)
            if concat_file.exists():
                concat_file.unlink()
        else:
            print("      Crossfade applied")

    def _loudnorm(self, input_path: str, output_path: str):
        """Apply EBU R128 loudness normalization."""
        # First pass: measure
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-af",
             "loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=60)
        try:
            import json
            # Find JSON in stderr
            stderr = r.stderr
            start = stderr.find("{")
            end = stderr.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(stderr[start:end])
                measured_i = float(data.get("input_i", -23))
                measured_tp = float(data.get("input_tp", -1))
                measured_lra = float(data.get("input_lra", 11))
                measured_thresh = float(data.get("input_thresh", -33))
                # Second pass: apply
                subprocess.run(
                    ["ffmpeg", "-y", "-i", input_path,
                     "-af", f"loudnorm=I=-16:LRA=11:TP=-1.5:measured_I={measured_i}:measured_TP={measured_tp}:measured_LRA={measured_lra}:measured_thresh={measured_thresh}:linear=true:print_format=summary",
                     "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", output_path],
                    capture_output=True, text=True, timeout=120)
                print(f"      Loudnorm: I={measured_i:.1f} LUFS → -16 LUFS")
                return
        except:
            pass
        # Fallback
        shutil.copy2(input_path, output_path)
        print("      Loudnorm skipped (fallback)")

    def _postprocess(self, ranges):
        if not ranges:
            return ranges
        # 🔴 keep_ranges 已是 LLM 语义删减的精准结果，只排序，不合并/不强制（否则破坏字词级删除）
        ranges = sorted(ranges, key=lambda r: r["start"])
        # 确保叙事弧完整
        beats = [r.get("beat", "").upper() for r in ranges]
        if not any("HOOK" in b for b in beats) and len(ranges) >= 1:
            ranges[0]["beat"] = "HOOK"
        if not any(b in ("CONFLICT", "STRUGGLE", "PROBLEM", "TURN") for b in beats) and len(ranges) >= 2:
            ranges[len(ranges) // 2]["beat"] = "CONFLICT"
        if not any("RESOLUTION" in b for b in beats) and len(ranges) >= 1:
            ranges[-1]["beat"] = "RESOLUTION"
        return ranges

"""Upscale skill — 2x to 4K via FFmpeg lanczos (NVENC-accelerated).

Fallback: Video2X realesrgan-plus (opt-in via context['upscale_method']='video2x').
"""
from __future__ import annotations
import subprocess
from pathlib import Path
from core.base import SkillBase

VIDEO2X_EXE = Path(r"E:\Hermes-Agent\workspace\xiaoshan\video-factory\tools\video2x\video2x.exe")


class Upscale(SkillBase):
    name = "upscale"

    def execute(self, context: dict) -> dict:
        if context.get("no_2x"):
            print("      --no-2x: 跳过 2x 放大（省空间）")
            return context
        input_video = Path(context.get("final_polished") or context.get("final_path", "") or ".")
        if not input_video.is_file():
            print("      No video to upscale, skipping")
            return context

        output_path = input_video.parent / "final_polished_2x.mp4"
        print(f"\n      Upscaling 2x to 4K (lanczos) ...")
        print(f"      Input : {input_video}")
        print(f"      Output: {output_path}")

        success = self._ffmpeg_lanczos(input_video, output_path)

        if success:
            mb = output_path.stat().st_size / (1024 * 1024)
            print(f"      Upscaled: {output_path} ({mb:.1f} MB)")
            context["final_polished_2x"] = str(output_path)
        else:
            print("      Upscale failed")

        return context

    def _ffmpeg_lanczos(self, src: Path, dst: Path) -> bool:
        """2x lanczos upscale → 4K, NVENC h264, copy audio."""
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-vf", "scale=3840:2160:flags=lanczos",
            "-c:v", "h264_nvenc",
            "-preset", "p4",
            "-cq", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(dst),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0 and dst.exists():
                return True
            print(f"      FFmpeg exit {result.returncode}")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-3:]:
                    print(f"      {line}")
        except subprocess.TimeoutExpired:
            print("      FFmpeg upscale timeout (10min)")
        except Exception as e:
            print(f"      FFmpeg error: {e}")
        return False

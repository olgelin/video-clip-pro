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

    def _detect_2x_scale(self, src: Path) -> str:
        """探测输入视频分辨率，返回 2x 的 scale 目标（保持竖屏/横屏）。"""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0", str(src)],
                capture_output=True, text=True, timeout=30,
            )
            nums = [int(x) for x in result.stdout.replace(",", " ").split()]
            w, h = nums[0], nums[1]
            # 保持宽高比 2x（20:9 等非标准竖屏不再强制 2160:3840 拉伸变形）
            tw, th = w * 2, h * 2
            # NVENC h264 硬编码上限 4096：超长竖屏（1080x2400 → 2160x4800）等比缩到长边 4096
            max_dim = max(tw, th)
            if max_dim > 4096:
                scale = 4096 / max_dim
                tw, th = int(tw * scale), int(th * scale)
                tw -= tw % 2; th -= th % 2
            return f"{tw}:{th}"
        except Exception:
            return "3840:2160"  # 探测失败，默认横屏

    def _ffmpeg_lanczos(self, src: Path, dst: Path) -> bool:
        """2x lanczos upscale → 4K（保持宽高比），NVENC h264, copy audio."""
        target = self._detect_2x_scale(src)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-vf", f"scale={target}:flags=lanczos",
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

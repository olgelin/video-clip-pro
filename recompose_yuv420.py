# -*- coding: utf-8 -*-
"""批量重新合成受影响成品：_compose_pip(PIP叠加) + upscale(2x放大)，强制 yuv420p。"""
import sys, subprocess
from pathlib import Path

ROOT = Path(r"E:\Hermes-Agent\workspace\xiaoshan\video-clip-pro")
sys.path.insert(0, str(ROOT / "core"))
from hf_card_builder import _compose_pip

DIRS = [
    "output/pip/align_test_v19",
    "output/pip/align_test_v19_portrait",
    "output/pip/batch_贸易",
    "output/pip/batch_GPT5",
    "output/pip/batch_SpaceX",
    "output/pip/batch_竖屏1",
    "output/pip/batch_竖屏2",
]

def upscale(src: Path, dst: Path) -> bool:
    cmd = ["ffmpeg", "-y", "-i", str(src),
           "-vf", "scale=3840:2160:flags=lanczos",
           "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23",
           "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
           str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return r.returncode == 0 and dst.exists()

for d in DIRS:
    d = ROOT / d
    hf_dir = d / "hyperframes"
    polished = d / "final_polished.mp4"
    print(f"\n=== {d.name} ===", flush=True)
    if not (hf_dir / "index.html").exists() or not (d / "final.mp4").exists():
        print("  中间产物缺失，跳过", flush=True)
        continue
    # 1. PIP 叠加（现在输出 yuv420p）
    _compose_pip(hf_dir, polished)
    # 2. 2x 放大（现在输出 yuv420p）
    if polished.exists():
        up = d / "final_polished_2x.mp4"
        if upscale(polished, up):
            print(f"  2x 放大完成: {up.stat().st_size/1024/1024:.1f}MB", flush=True)
        else:
            print("  2x 放大失败", flush=True)
    print(f"  完成", flush=True)

print("\n全部重新合成完成", flush=True)

#!/usr/bin/env python3
"""抽帧验证粒子动（独立版，不依赖 hf_build_avatar 目录）"""
import subprocess, os, sys
import numpy as np
from PIL import Image

FFMPEG = r"C:/ProgramData/chocolatey/bin/ffmpeg"
base = r"E:\Hermes-Agent\workspace\xiaoshan\video-clip-pro\output\avatar-short\固态电池为什么迟迟不能量产？"
video = os.path.join(base, "final_polished.mp4")
tmp = os.path.join(base, "cache", "verify_final")
os.makedirs(tmp, exist_ok=True)

scenes = [
    ("scene0 quote_hero", 0.0, 10.4),
    ("scene1 data_impact", 10.4, 30.2),
    ("scene2 compare", 30.2, 53.0),
    ("scene3 list_alert", 53.0, 73.0),
    ("scene4 timeline_event", 73.0, 94.7),
    ("scene5 quote_hero", 94.7, 112.0),
    ("scene6 flow", 112.0, 129.5),
]

def extract(t, out):
    subprocess.run([FFMPEG, "-y", "-ss", str(t), "-i", video, "-frames:v", "1", out],
                   capture_output=True)

GRID = 4
print("=== 粒子动画验证（4x4 网格，间隔3s，背景区=排除最动2网格）===")
for name, s, e in scenes:
    t1 = s + 0.5
    t2 = min(s + 3.5, e - 0.5)
    f1, f2 = os.path.join(tmp, "a.jpg"), os.path.join(tmp, "b.jpg")
    extract(t1, f1); extract(t2, f2)
    a = np.asarray(Image.open(f1).convert("L"), dtype=np.float64)
    b = np.asarray(Image.open(f2).convert("L"), dtype=np.float64)
    h, w = a.shape
    gh, gw = h // GRID, w // GRID
    cells = []
    for i in range(GRID):
        for j in range(GRID):
            ca = a[i*gh:(i+1)*gh, j*gw:(j+1)*gw]
            cb = b[i*gh:(i+1)*gh, j*gw:(j+1)*gw]
            cells.append(float(np.abs(ca - cb).mean()))
    srt = sorted(cells)
    bg_avg = float(np.mean(srt[:-2]))
    moving = bg_avg > 3.0
    print(f"  {name} [{t1:.1f}s vs {t2:.1f}s]: 背景区均值={bg_avg:5.2f} "
          f"(最静{srt[0]:.2f}/最动{srt[-1]:.2f}) {'✅粒子动' if moving else '❌粒子静'}")

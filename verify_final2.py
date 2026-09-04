# -*- coding: utf-8 -*-
"""聚焦核验 43-46s 窗口：1s 间隔连抽 5 帧看四角是否连续细微变化（动）还是完全冻结（静）。"""
import subprocess, os
import numpy as np
from PIL import Image

VIDEO = r"output/avatar-short/为什么现在的年轻人越来越不愿意结婚？/final_polished.mp4"
TMP = r"output/avatar-short/_verify_frames2"
os.makedirs(TMP, exist_ok=True)

CORNERS = {
    "TL": (30, 30, 150, 150),
    "TR": (1770, 30, 1890, 150),
    "BL": (30, 860, 150, 980),
    "BR": (1770, 860, 1890, 980),
}

def extract(t):
    p = os.path.join(TMP, f"f{int(t*10):04d}.png")
    subprocess.run([
        "C:/ProgramData/chocolatey/bin/ffmpeg", "-y", "-ss", str(t),
        "-i", VIDEO, "-frames:v", "1", "-q:v", "2", p
    ], capture_output=True)
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)

frames = [extract(t) for t in (42.0, 43.0, 44.0, 45.0, 46.0)]
print("1s间隔四角像素差（43-46s 窗口）:")
print(f"{'对':>8} | {'TL':>6} {'TR':>6} {'BL':>6} {'BR':>6} | 连续变化?")
for i in range(len(frames) - 1):
    a, b = frames[i], frames[i+1]
    row = []
    for (x1, y1, x2, y2) in CORNERS.values():
        row.append(float(np.abs(a[y1:y2, x1:x2] - b[y1:y2, x1:x2]).mean()))
    total = sum(row)
    print(f"{42+i:>4}-{43+i:>4} | {row[0]:6.2f} {row[1]:6.2f} {row[2]:6.2f} {row[3]:6.2f} | 四角和={total:6.2f} {'✅有变化' if total > 1.0 else '❌冻结'}")

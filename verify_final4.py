# -*- coding: utf-8 -*-
"""聚焦核验话题1两个弱窗口(63-66s场景4flow, 75-78s场景5timeline_e)：
1s间隔看四角是连续冻结(0.00)还是细微运动，判断是技法特性还是bug回归。"""
import subprocess, os
import numpy as np
from PIL import Image

VIDEO = r"output/avatar-short/固态电池为什么迟迟不能量产？/final_polished.mp4"
TMP = r"output/avatar-short/_verify_frames_t1b"
os.makedirs(TMP, exist_ok=True)

CORNERS = {"TL": (30, 30, 150, 150), "TR": (1770, 30, 1890, 150),
           "BL": (30, 860, 150, 980), "BR": (1770, 860, 1890, 980)}

def extract(t):
    p = os.path.join(TMP, f"f{int(t*10):04d}.png")
    subprocess.run(["C:/ProgramData/chocolatey/bin/ffmpeg", "-y", "-ss", str(t),
                    "-i", VIDEO, "-frames:v", "1", "-q:v", "2", p], capture_output=True)
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)

def check_window(label, t0):
    print(f"\n=== {label} ({t0}-{t0+4}s) 1s间隔四角像素差 ===")
    frames = [extract(t) for t in (t0, t0+1, t0+2, t0+3, t0+4)]
    print(f"{'对':>8} | {'TL':>6} {'TR':>6} {'BL':>6} {'BR':>6} | 四角和 判定")
    for i in range(4):
        a, b = frames[i], frames[i+1]
        row = [float(np.abs(a[y1:y2,x1:x2]-b[y1:y2,x1:x2]).mean()) for (x1,y1,x2,y2) in CORNERS.values()]
        s = sum(row)
        print(f"{t0+i:>4}-{t0+i+1:>4} | {row[0]:6.2f} {row[1]:6.2f} {row[2]:6.2f} {row[3]:6.2f} | {s:6.2f} {'✅细微动' if s>1.0 else '❌冻结'}")

check_window("场景4 flow 自定义3D", 63)
check_window("场景5 timeline_e 网格脉冲", 75)

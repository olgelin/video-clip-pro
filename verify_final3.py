# -*- coding: utf-8 -*-
"""验证话题1「固态电池」成片粒子是否全动（根因⑦修复的 2+ 话题交叉验证第2环）。"""
import subprocess, os
import numpy as np
from PIL import Image

VIDEO = r"output/avatar-short/固态电池为什么迟迟不能量产？/final_polished.mp4"
TMP = r"output/avatar-short/_verify_frames_t1"
os.makedirs(TMP, exist_ok=True)

# 先拿真实时长
r = subprocess.run([
    "C:/ProgramData/chocolatey/bin/ffprobe", "-v", "error",
    "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1", VIDEO
], capture_output=True, text=True)
DUR = float(r.stdout.strip().split("=")[-1])
print(f"时长: {DUR:.1f}s")

CORNERS = {
    "TL": (30, 30, 150, 150),
    "TR": (1770, 30, 1890, 150),
    "BL": (30, 860, 150, 980),
    "BR": (1770, 860, 1890, 980),
}

def extract(t):
    p = os.path.join(TMP, f"f{int(t):03d}.png")
    subprocess.run([
        "C:/ProgramData/chocolatey/bin/ffmpeg", "-y", "-ss", str(t),
        "-i", VIDEO, "-frames:v", "1", "-q:v", "2", p
    ], capture_output=True)
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)

print(f"{'窗口(s)':>12} | {'TL':>6} {'TR':>6} {'BL':>6} {'BR':>6} | 判定")
print("-" * 60)

moving = static = 0
times = list(range(3, int(DUR) - 4, 4))
for t in times:
    t2 = t + 3.0
    a, b = extract(t), extract(t2)
    d = {}
    for name, (x1, y1, x2, y2) in CORNERS.items():
        d[name] = float(np.abs(a[y1:y2, x1:x2] - b[y1:y2, x1:x2]).mean())
    verdict = "动" if max(d.values()) > 3.0 else "静"
    moving += verdict == "动"
    static += verdict == "静"
    print(f"{t:5.0f}-{t2:5.0f} | {d['TL']:6.2f} {d['TR']:6.2f} {d['BL']:6.2f} {d['BR']:6.2f} | {verdict}")

print("-" * 60)
print(f"动 {moving} / 静 {static} / 共 {moving+static} 窗口")
print("结论:", "✅ 粒子全动" if static == 0 else f"⚠️ 仍有 {static} 个静态窗口")

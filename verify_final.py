# -*- coding: utf-8 -*-
"""验证根因⑦修复：话题2 最终成片粒子是否全动。
方法：每 4s 抽一帧，相邻帧（4s 间隔）对四角纯背景区域做像素差。
四角是粒子场所在（远离中心卡片/数字人、底部字幕）。
判据：四角任一 > 3.0 = 该窗口粒子在动；四角全 ~0 = 静态。
"""
import subprocess, os, sys
import numpy as np
from PIL import Image

VIDEO = r"output/avatar-short/为什么现在的年轻人越来越不愿意结婚？/final_polished.mp4"
TMP = r"output/avatar-short/_verify_frames"
os.makedirs(TMP, exist_ok=True)

DUR = 124.1
STEP = 4.0

# 四角区域（横屏 1920x1080），避开中心卡片/数字人和底部字幕
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
    return p

def corner_diff(a, b):
    ia, ib = np.asarray(Image.open(a).convert("RGB"), dtype=np.float32), \
             np.asarray(Image.open(b).convert("RGB"), dtype=np.float32)
    out = {}
    for name, (x1, y1, x2, y2) in CORNERS.items():
        ra = ia[y1:y2, x1:x2]
        rb = ib[y1:y2, x1:x2]
        out[name] = float(np.abs(ra - rb).mean())
    return out

times = np.arange(3.0, DUR - 4, STEP)
print(f"{'窗口(s)':>12} | {'TL':>6} {'TR':>6} {'BL':>6} {'BR':>6} | 判定")
print("-" * 60)

moving = 0
static = 0
for t in times:
    t2 = t + 3.0  # 3s 间隔，确保同场景内
    a = extract(t)
    b = extract(t2)
    d = corner_diff(a, b)
    verdict = "动" if max(d.values()) > 3.0 else "静"
    if verdict == "动":
        moving += 1
    else:
        static += 1
    print(f"{t:5.0f}-{t2:5.0f} | {d['TL']:6.2f} {d['TR']:6.2f} {d['BL']:6.2f} {d['BR']:6.2f} | {verdict}")

print("-" * 60)
print(f"动 {moving} / 静 {static} / 共 {moving+static} 窗口")
print("结论:", "✅ 粒子全动" if static == 0 else f"⚠️ 仍有 {static} 个静态窗口")

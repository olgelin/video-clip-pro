# -*- coding: utf-8 -*-
"""验证奶茶横屏版粒子运动（帧差法，横屏 1920×1080），确认根治后 GSAP 驱动仍可靠。"""
import os, subprocess
from PIL import Image

def grab(video, t, name, tmp):
    p = os.path.join(tmp, name)
    subprocess.run(["C:/ProgramData/chocolatey/bin/ffmpeg", "-y", "-ss", str(t), "-i", video,
                    "-frames:v", "1", "-q:v", "2", p], capture_output=True)
    return p

def motion_ratio(p1, p2, x1, y1, x2, y2, thr=12):
    a = Image.open(p1).convert("RGB")
    b = Image.open(p2).convert("RGB")
    moving = total = 0
    for y in range(y1, y2, 3):
        for x in range(x1, x2, 3):
            pa = a.getpixel((x, y)); pb = b.getpixel((x, y))
            d = abs(pa[0]-pb[0]) + abs(pa[1]-pb[1]) + abs(pa[2]-pb[2])
            total += 1
            if d > thr:
                moving += 1
    return moving / total * 100 if total else 0

# 横屏 1920×1080 背景区域（避开中央卡片 + 右侧数字人竖条 + 底部角标）
BG = [("顶部", 0, 0, 1200, 250), ("左上", 0, 250, 500, 600), ("中左", 0, 600, 500, 900)]

base = r"E:\Hermes-Agent\workspace\xiaoshan\video-clip-pro\output\avatar-short"
video = os.path.join(base, "为什么奶茶越卖越贵了", "final_polished.mp4")
tmp = os.path.join(base, "为什么奶茶越卖越贵了", "_verify_tmp")
os.makedirs(tmp, exist_ok=True)

# 采样粒子场景：bg3d(0-9s)、grid(26-42s)、银河漩涡(89-104s)
sample = [(4, 6), (30, 32), (95, 97)]

print("【奶茶横屏版(根治后)】粒子运动强度")
for t1, t2 in sample:
    p1 = grab(video, t1, f"ml_{t1}.png", tmp)
    p2 = grab(video, t2, f"ml_{t2}.png", tmp)
    ratios = []
    for rname, x1, y1, x2, y2 in BG:
        r = motion_ratio(p1, p2, x1, y1, x2, y2)
        ratios.append(f"{rname}={r:.1f}%")
    print(f"  {t1}s vs {t2}s: {'  '.join(ratios)}")

print("\n对比基准：不愿意结婚(旧) 13-47%，bg3d 场景应 ≥10%")

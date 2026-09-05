# -*- coding: utf-8 -*-
"""验证奶茶话题粒子运动强度（帧差法，竖屏 1080×1920），确认架构清理后 GSAP 驱动仍可靠。"""
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

# 竖屏 1080×1920 背景区域（避开中央卡片 + 底部数字人）
BG = [("顶部", 0, 0, 1080, 300), ("左上", 0, 300, 400, 700), ("右侧", 700, 300, 1080, 800)]

base = r"E:\Hermes-Agent\workspace\xiaoshan\video-clip-pro\output\avatar-short"
video = os.path.join(base, "为什么奶茶越卖越贵了", "final_polished.mp4")
tmp = os.path.join(base, "为什么奶茶越卖越贵了", "_verify_tmp")
os.makedirs(tmp, exist_ok=True)

# 采样粒子场景：bg3d(0-15s 奶茶通胀)、rain(50-67s 卷生卷死)、bg3d(83-102s 情绪溢价)
sample = [(8, 10), (55, 57), (90, 92)]

print("【奶茶话题(架构清理后 GSAP timeline+__timelines)】粒子运动强度")
for t1, t2 in sample:
    p1 = grab(video, t1, f"mt_{t1}.png", tmp)
    p2 = grab(video, t2, f"mt_{t2}.png", tmp)
    ratios = []
    for rname, x1, y1, x2, y2 in BG:
        r = motion_ratio(p1, p2, x1, y1, x2, y2)
        ratios.append(f"{rname}={r:.1f}%")
    print(f"  {t1}s vs {t2}s: {'  '.join(ratios)}")

print("\n对比基准：不愿意结婚(旧) 13-47%，固态电池(__hfThreeRender不可靠) 0-32%")

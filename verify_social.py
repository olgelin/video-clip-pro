# -*- coding: utf-8 -*-
"""验证社会话题粒子运动强度（帧差法），对比"不愿意结婚"旧代码水平(13-47%)。"""
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

BG = [("顶部", 0, 0, 1920, 250), ("左上", 0, 250, 500, 600), ("右侧", 1400, 250, 1920, 700)]

base = r"E:\Hermes-Agent\workspace\xiaoshan\video-clip-pro\output\avatar-short"
video = os.path.join(base, "为什么现在的年轻人越来越不想生孩子了？", "final_polished.mp4")
tmp = os.path.join(base, "为什么现在的年轻人越来越不想生孩子了？", "_verify_tmp")
os.makedirs(tmp, exist_ok=True)

# 场景内采样（避开边界），对应 pt3d/bg3d 粒子场景
sample = [(5, 7), (22, 24), (62, 64), (85, 87), (108, 110)]

print("【社会话题(新驱动 GSAP timeline+__timelines)】粒子运动强度")
all_strong = True
for t1, t2 in sample:
    p1 = grab(video, t1, f"sh_{t1}.png", tmp)
    p2 = grab(video, t2, f"sh_{t2}.png", tmp)
    ratios = []
    for rname, x1, y1, x2, y2 in BG:
        r = motion_ratio(p1, p2, x1, y1, x2, y2)
        ratios.append(f"{rname}={r:.1f}%")
    print(f"  {t1}s vs {t2}s: {'  '.join(ratios)}")

print("\n对比基准：不愿意结婚(旧) 13-47%，固态电池(__hfThreeRender) 0-32%")

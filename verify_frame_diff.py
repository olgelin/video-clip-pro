# -*- coding: utf-8 -*-
"""精确帧差验证：抽场景两帧，统计纯背景粒子区域的运动像素。
排除数字人(person_zone 左下)和卡片/文字，只看背景粒子是否真的在动。"""
import os, subprocess, sys
from PIL import Image

base = r"E:\Hermes-Agent\workspace\xiaoshan\video-clip-pro\output\avatar-short\固态电池为什么迟迟不能量产？"
video = os.path.join(base, "final_polished.mp4")
tmp = os.path.join(base, "_verify_tmp")
os.makedirs(tmp, exist_ok=True)

def grab(t, name):
    p = os.path.join(tmp, name)
    subprocess.run(["C:/ProgramData/chocolatey/bin/ffmpeg", "-y", "-ss", str(t), "-i", video,
                    "-frames:v", "1", "-q:v", "2", p], capture_output=True)
    return p

# 关键场景：scene0 (0-12.2s) 和 scene2 (27.9-46.6s) —— 之前用户指出"静"的两个
checks = [
    ("scene0", 2.4, 6.1),
    ("scene2", 30.0, 34.0),
    ("scene4", 65.0, 69.0),
]

# 纯背景粒子区域（排除左下数字人 0-500x700-1080，排除中心卡片区）
# 只看顶部 0-250 和 右侧 1500-1920 的背景
BG_REGIONS = [
    ("顶部", 0, 0, 1920, 250),
    ("右上", 1500, 0, 1920, 250),
    ("左侧中上", 0, 250, 400, 600),
]

def region_motion(p1, p2, x1, y1, x2, y2, thr=12):
    a = Image.open(p1).convert("RGB")
    b = Image.open(p2).convert("RGB")
    moving = 0
    total = 0
    for y in range(y1, y2, 3):
        for x in range(x1, x2, 3):
            pa = a.getpixel((x, y)); pb = b.getpixel((x, y))
            d = abs(pa[0]-pb[0]) + abs(pa[1]-pb[1]) + abs(pa[2]-pb[2])
            total += 1
            if d > thr:
                moving += 1
    return moving, total

all_ok = True
for name, t1, t2 in checks:
    p1 = grab(t1, f"m_{name}_a.png")
    p2 = grab(t2, f"m_{name}_b.png")
    print(f"【{name}】 {t1}s vs {t2}s")
    scene_ok = False
    for rname, x1, y1, x2, y2 in BG_REGIONS:
        moving, total = region_motion(p1, p2, x1, y1, x2, y2)
        ratio = moving / total * 100
        flag = "✅动" if ratio > 0.5 else "❌静"
        if ratio > 0.5:
            scene_ok = True
        print(f"   {flag} {rname}区({x1},{y1})-({x2},{y2}): 运动像素 {moving}/{total} = {ratio:.1f}%")
    if not scene_ok:
        all_ok = False
    print()

print("✅ 背景粒子区域确认运动" if all_ok else "❌ 存在背景粒子静止")
sys.exit(0 if all_ok else 1)

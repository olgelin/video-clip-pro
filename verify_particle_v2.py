# -*- coding: utf-8 -*-
"""严格验证粒子动/静：每场景抽 2 帧（隔 2s），计算四角+中心像素 diff。
判据：四角+中心全 0.00 = 真冻结（bug）；任一 > 0 = 粒子动（正常）。"""
import json, os, subprocess, sys

base = r"E:\Hermes-Agent\workspace\xiaoshan\video-clip-pro\output\avatar-short\固态电池为什么迟迟不能量产？"
video = os.path.join(base, "final_polished.mp4")
durs = json.load(open(os.path.join(base, "voice_scene_durations.json"), encoding="utf-8"))

# 累计场景时间段
starts = []
t = 0.0
for d in durs:
    starts.append(t)
    t += d["duration"]

# 成片分辨率 1920x1080；四角 + 中心采样点（3x3 区域）
pts = {"TL": (80, 80), "TR": (1840, 80), "BL": (80, 1000), "BR": (1840, 1000), "C": (960, 540)}

import glob
tmp = os.path.join(base, "_verify_tmp")
os.makedirs(tmp, exist_ok=True)

def grab(t, name):
    p = os.path.join(tmp, name)
    subprocess.run(["C:/ProgramData/chocolatey/bin/ffmpeg", "-y", "-ss", str(t), "-i", video,
                    "-frames:v", "1", "-q:v", "2", p], capture_output=True)
    return p

def px(png, x, y):
    """3x3 邻域平均 RGB"""
    from PIL import Image
    im = Image.open(png).convert("RGB")
    r = g = b = n = 0
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            px_ = im.getpixel((x + dx, y + dy))
            r += px_[0]; g += px_[1]; b += px_[2]; n += 1
    return (r / n, g / n, b / n)

print(f"成片: {video}")
print(f"场景数: {len(durs)}，累计时段: {[f'{s:.1f}' for s in starts]}")
print()

all_moving = True
for i, d in enumerate(durs):
    s = starts[i]
    dur = d["duration"]
    # 抽场景内两帧（避免场景边界，取 20% 和 50% 处）
    t1 = s + dur * 0.2
    t2 = s + dur * 0.5
    p1 = grab(t1, f"f_{i}_a.png")
    p2 = grab(t2, f"f_{i}_b.png")
    diffs = {}
    for name, (x, y) in pts.items():
        c1 = px(p1, x, y)
        c2 = px(p2, x, y)
        d = abs(c1[0] - c2[0]) + abs(c1[1] - c2[1]) + abs(c1[2] - c2[2])
        diffs[name] = round(d, 2)
    # 四角 + 中心全 < 1.0（几乎零 diff）判冻结
    corner_sum = diffs["TL"] + diffs["TR"] + diffs["BL"] + diffs["BR"]
    center = diffs["C"]
    frozen = corner_sum < 1.0 and center < 1.0
    if frozen:
        all_moving = False
    flag = "❌冻结" if frozen else "✅动"
    print(f"{flag} scene{i} ({s:.1f}-{s+dur:.1f}s): TL={diffs['TL']} TR={diffs['TR']} BL={diffs['BL']} BR={diffs['BR']} C={diffs['C']}")

print()
print("✅ 所有场景粒子动（无冻结）" if all_moving else "❌ 存在冻结场景")
sys.exit(0 if all_moving else 1)

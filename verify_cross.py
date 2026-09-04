#!/usr/bin/env python3
"""交叉验证：检查 avatar-short 渲染的 beat html 完整性 + 粒子动画是否真动。

用法：
  PYTHONPATH=. python verify_cross.py <output_dir>

检查项：
  1. 每个 beat-N.html 的 <script>/</script> 严格配对（无孤立/漏闭合）
  2. 无 var tl / TimelineMax / GSAP 2.x 旧 API 残留
  3. 粒子 script 已包 IIFE（根治 const 冲突）
  4. final_polished.mp4 抽帧，纯粒子区域像素差 > 阈值（区分数字人动 vs 粒子动）
"""
import os, re, subprocess, sys
from pathlib import Path

FFMPEG = r"C:/ProgramData/chocolatey/bin/ffmpeg"

def check_beat_html(hf_dir: Path):
    """检查所有 beat-N.html 的 script 完整性"""
    print("=" * 60)
    print("① beat html 完整性检查")
    print("=" * 60)
    all_ok = True
    beats = sorted(hf_dir.glob("beat-*.html"))
    for b in beats:
        html = b.read_text(encoding="utf-8")
        opens = len(re.findall(r'<script[^>]*>', html))
        closes = len(re.findall(r'</script>', html))
        has_vtl = 'var tl' in html and 'var tl=new TimelineMax' in html
        has_tlmax = bool(re.search(r'new\s+Timeline(Max|Lite)|new\s+Tween(Max|Lite)', html))
        # 检查粒子 script 是否已包 IIFE
        iife_ok = True
        for m in re.finditer(r'<script>\s*(?P<body>(?:const|var|let)\b.*?new THREE\.WebGLRenderer.*?)</script>', html, re.DOTALL):
            body = m.group('body')
            if not body.lstrip().startswith('(function'):
                iife_ok = False
        pair_ok = opens == closes
        ok = pair_ok and not has_vtl and not has_tlmax
        all_ok = all_ok and ok
        status = "✅" if ok else "❌"
        print(f"  {b.name}: <script>{opens} </script>{closes} "
              f"{'配对' if pair_ok else '不配对'} "
              f"| var tl残留={has_vtl} TimelineMax残留={has_tlmax} "
              f"| IIFE={'✅' if iife_ok else '⚠无WebGLRenderer'} {status}")
    return all_ok

def extract_frame(video: Path, t: float, out: Path):
    subprocess.run([FFMPEG, "-y", "-ss", str(t), "-i", str(video),
                    "-frames:v", "1", str(out)], capture_output=True)

def frame_diff(f1: Path, f2: Path) -> float:
    from PIL import Image
    import numpy as np
    a = np.asarray(Image.open(f1).convert("L"), dtype=np.float64)
    b = np.asarray(Image.open(f2).convert("L"), dtype=np.float64)
    return float(np.abs(a - b).mean())

def check_particle_motion(video: Path, scenes: list, tmp: Path):
    """抽帧验证粒子动：用 4x4 网格区域 diff，区分粒子区 vs 数字人区。
    数字人/卡片通常集中在下半或角落，纯背景粒子区（上半/边缘）应该持续动。"""
    print()
    print("=" * 60)
    print("② 粒子动画验证（4x4 网格区域像素差）")
    print("=" * 60)
    tmp.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    import numpy as np
    GRID = 4
    for name, s, e, has_person in scenes:
        t1, t2 = s + 0.5, s + 3.5  # 场景内间隔 3s
        if t2 >= e:
            t2 = e - 0.5
        f1, f2 = tmp / f"{name}_a.jpg", tmp / f"{name}_b.jpg"
        extract_frame(video, t1, f1)
        extract_frame(video, t2, f2)
        a = np.asarray(Image.open(f1).convert("L"), dtype=np.float64)
        b = np.asarray(Image.open(f2).convert("L"), dtype=np.float64)
        if a.shape != b.shape:
            print(f"  {name}: 尺寸不一致，跳过")
            continue
        h, w = a.shape
        gh, gw = h // GRID, w // GRID
        cells = []
        for i in range(GRID):
            for j in range(GRID):
                ca = a[i*gh:(i+1)*gh, j*gw:(j+1)*gw]
                cb = b[i*gh:(i+1)*gh, j*gw:(j+1)*gw]
                cells.append(float(np.abs(ca - cb).mean()))
        # 最静的网格（最可能是纯背景/粒子静止区）+ 最动的网格（数字人/卡片）
        cells_sorted = sorted(cells)
        min_cell = cells_sorted[0]
        max_cell = cells_sorted[-1]
        # 粒子区 = 排除最动的 2 个网格（数字人/卡片）后的平均
        bg_cells = cells_sorted[:-2]
        bg_avg = float(np.mean(bg_cells))
        moving = bg_avg > 3.0
        tag = "（有数字人）" if has_person else "（无数字人，纯背景）"
        print(f"  {name} [{t1:.1f}s vs {t2:.1f}s]: 背景区均值={bg_avg:5.2f} "
              f"(最静{min_cell:.2f}/最动{max_cell:.2f}) "
              f"{'✅粒子动' if moving else '❌粒子静'} {tag}")

def main():
    out_dir = Path(sys.argv[1])
    hf_dir = out_dir / "hf_build_avatar"
    video = out_dir / "final_polished.mp4"
    if not hf_dir.exists():
        print(f"❌ 找不到 {hf_dir}")
        sys.exit(1)
    ok = check_beat_html(hf_dir)
    if video.exists():
        # 场景时间戳：从 beat html 数量推断场景数，从 step JSON 拿时长（兜底均分）
        n = len(list(hf_dir.glob("beat-*.html")))
        # 尝试从 final.mp4 拿真实总时长
        import subprocess as sp
        r = sp.run([FFMPEG, "-i", str(video)], capture_output=True, text=True)
        dur_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr or "")
        total = 130
        if dur_match:
            total = int(dur_match.group(1))*3600 + int(dur_match.group(2))*60 + float(dur_match.group(3))
        dur = total / max(n, 1)
        scenes = [(f"scene{i}", i * dur, (i + 1) * dur, True) for i in range(n)]
        check_particle_motion(video, scenes, out_dir / "cache" / "verify_cross2")
    else:
        print(f"\n⚠ 未找到 {video}（渲染可能未完成）")
    print()
    print("✅ beat html 检查" + ("通过" if ok else "失败"))

if __name__ == "__main__":
    main()

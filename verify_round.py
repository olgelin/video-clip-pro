# -*- coding: utf-8 -*-
"""验证本轮修复：三产物齐全 + 粒子变圆 + outro话题完整 + BGM时长固定。"""
import subprocess, os, json
from pathlib import Path

OUT = Path(r"E:\Hermes-Agent\workspace\xiaoshan\video-clip-pro\output\avatar-short\为什么现在的年轻人越来越不愿意结婚？")

print("========== 三产物检查 ==========")
for name in ["final_polished.mp4", "final_polished_2x.mp4", "bgm.wav", "lyrics.txt"]:
    p = OUT / name
    if p.exists():
        size = p.stat().st_size / (1024 * 1024)
        print(f"  ✅ {name}: {size:.1f} MB")
    else:
        print(f"  ❌ {name}: 缺失")

print("\n========== 各产物时长/分辨率 ==========")
def probe(path):
    r = subprocess.run([
        "C:/ProgramData/chocolatey/bin/ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,width,height",
        "-of", "json", str(path)
    ], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        dur = float(d.get("format", {}).get("duration", 0))
        streams = d.get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), None)
        a = next((s for s in streams if s.get("codec_type") == "audio"), None)
        res = f"{v.get('width')}x{v.get('height')}" if v else "无视频"
        audio = "有" if a else "无"
        return dur, res, audio
    except Exception:
        return 0, "?", "?"

for name in ["final_polished.mp4", "final_polished_2x.mp4", "bgm.wav"]:
    p = OUT / name
    if p.exists():
        dur, res, audio = probe(p)
        print(f"  {name}: 时长={dur:.1f}s 分辨率={res} 音频={audio}")

# 抽帧：粒子场景(10s) + outro(120s) 供 vision 验证
print("\n========== 抽帧验证 ==========")
for t, label in [(10, "particle"), (120, "outro")]:
    out = OUT / f"_verify_{label}.png"
    r = subprocess.run([
        "C:/ProgramData/chocolatey/bin/ffmpeg", "-y", "-ss", str(t),
        "-i", str(OUT / "final_polished.mp4"), "-frames:v", "1", "-q:v", "2", str(out)
    ], capture_output=True, text=True)
    print(f"  {label}@{t}s: {'✅' if out.exists() else '❌'} {out.name}")

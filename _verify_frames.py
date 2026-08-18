import subprocess
from PIL import Image
from pathlib import Path

video = Path('output/weixin_150755/final_polished.mp4')
frame_dir = Path('output/weixin_150755/frames')
frame_dir.mkdir(exist_ok=True)

for t in [3, 15, 30, 45, 60, 75]:
    out = frame_dir / f'frame_{t}s.jpg'
    subprocess.run(['ffmpeg', '-y', '-ss', str(t), '-i', str(video),
                    '-frames:v', '1', '-q:v', '2', str(out)], capture_output=True)
    img = Image.open(out).convert('RGB')
    w, h = img.size
    px = list(img.getdata())
    total = len(px)
    colorful = sum(1 for r, g, b in px if max(r, g, b) - min(r, g, b) > 40 and max(r, g, b) > 60)
    bright = sum(1 for r, g, b in px if max(r, g, b) > 150)
    lum = sum((r * 299 + g * 587 + b * 114) // 1000 for r, g, b in px) / total
    print(f't={t:2d}s  尺寸={w}x{h}  彩色={colorful/total:6.1%}  亮像素={bright/total:6.1%}  平均亮度={lum:5.1f}')

"""person_zone.py — 人物区坐标单一来源（v39 同层排版）

定义数字人在最终画面里的位置+尺寸。stage_template（占位框）和
_compose_pip（ffmpeg 叠加）都从这里取坐标，保证两层对齐不偏差。

返回 dict: {x, y, w, h, ratio}
  - x/y/w/h: 画布像素坐标（横屏 1920x1080 / 竖屏 1080x1920）
  - ratio:   宽/高（crop 比例对齐用，让 crop 比例 = 窗口比例，scale 不变形）

布局：
  corner      角标（现状，右下角小窗）
  left-rail   左分栏（数字人左侧竖条，卡片右侧）——抖音最常用
  right-rail  右分栏（对称）
"""


def person_zone(layout: str, orientation: str = "portrait") -> dict:
    fw, fh = (1920, 1080) if orientation == "landscape" else (1080, 1920)
    is_portrait = fh > fw

    if layout == "corner":
        # 🔴 严格对齐 _compose_pip 现状：横屏 12%宽×4:3高，竖屏 22%宽×1:1
        w = int(fw * (0.22 if is_portrait else 0.12))
        h = w if is_portrait else int(w * 4 / 3)
        # 右下角，留 40px 边距（对齐现状 to_xy 的初始位置附近）
        x = fw - w - 40
        y = fh - h - 40

    elif layout == "left-rail":
        if is_portrait:
            # 竖屏左分栏太窄会变形，回退 corner
            return person_zone("corner", orientation)
        w = int(fw * 0.35)   # 横屏左侧竖条 35% 宽
        h = fh
        x = 0
        y = 0

    elif layout == "right-rail":
        if is_portrait:
            return person_zone("corner", orientation)
        w = int(fw * 0.35)
        h = fh
        x = fw - w
        y = 0

    else:
        return person_zone("corner", orientation)

    return {"x": x, "y": y, "w": w, "h": h, "ratio": w / h}

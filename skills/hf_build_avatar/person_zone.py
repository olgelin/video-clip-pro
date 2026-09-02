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

# 🔴 v42 横屏真分区常量：人物区 + 缝隙 + 内容区 三者物理分离（不是叠放）
LANDSCAPE_PERSON_W = 640   # 横屏人物区宽（B: 520→640=1/3，治瘦高，内容区 1920-640-30=1250）
LANDSCAPE_GAP = 30         # 人物区与内容区之间的缝隙


def person_zone(layout: str, orientation: str = "portrait") -> dict:
    fw, fh = (1920, 1080) if orientation == "landscape" else (1080, 1920)
    is_portrait = fh > fw

    if layout in ("corner", "corner-br"):
        # 🔴 严格对齐 _compose_pip 现状：横屏 12%宽×4:3高，竖屏 22%宽×1:1
        w = int(fw * (0.22 if is_portrait else 0.12))
        h = w if is_portrait else int(w * 4 / 3)
        # 右下角，留 40px 边距（对齐现状 to_xy 的初始位置附近）
        x = fw - w - 40
        y = fh - h - 40

    elif layout == "corner-bl":
        # 🔴 v41 语义换位：左下角。竖屏 22%宽×1:1，横屏 12%宽×4:3，留 40px 边距
        w = int(fw * (0.22 if is_portrait else 0.12))
        h = w if is_portrait else int(w * 4 / 3)
        x = 40
        y = fh - h - 40

    elif layout == "left-rail":
        if is_portrait:
            # 竖屏左分栏太窄会变形，回退 corner
            return person_zone("corner", orientation)
        w = LANDSCAPE_PERSON_W   # 横屏人物区 520 宽（真分区，非 35%）
        h = fh
        x = 0
        y = 0

    elif layout == "right-rail":
        if is_portrait:
            return person_zone("corner", orientation)
        w = LANDSCAPE_PERSON_W
        h = fh
        x = fw - w
        y = 0

    elif layout == "hidden":
        # 🔴 A: 数字人移出画面（纯内容场景，人物与内容轮流当主角）。
        #    尺寸用小角标，位置移出右边缘外（被 overflow hidden 裁剪，不可见）。内容全屏。
        w = int(fw * (0.22 if is_portrait else 0.12))
        h = w if is_portrait else int(w * 4 / 3)
        x = fw + 60
        y = fh - h - 40

    else:
        return person_zone("corner", orientation)

    return {"x": x, "y": y, "w": w, "h": h, "ratio": w / h}


# 🔴 v41 语义换位：视觉类型 → 人物位置。让数字人在整条视频里按内容语义换位置，
#    而不是死贴一个角。金句/对比/时间线 → 左下（或横屏右分栏），内容有足够空间；
#    数据/流程/列表/仪表盘 → 右下角标（内容在上/左）。
_VT_LAYOUT_PORTRAIT = {
    "quote_hero": "corner-bl",
    "compare": "corner-bl",
    "timeline_event": "corner-bl",
    # 默认（data_impact / flow / list_alert / hud / 其他）→ 右下角标
}
_VT_LAYOUT_LANDSCAPE = {
    "quote_hero": "right-rail",
    "compare": "right-rail",
    "timeline_event": "right-rail",
    # 数据/流程/列表/仪表盘 → 人物左（内容右），与金句/对比形成左右切换
    "data_impact": "left-rail",
    "flow": "left-rail",
    "list_alert": "left-rail",
    "hud": "left-rail",
    # 默认 → right-rail（横屏统一分栏，不做角标叠放）
}


def person_layout_for_visual_type(visual_type: str, orientation: str = "portrait") -> str:
    """按视觉类型决定人物位置布局（v42）。横屏统一分栏（人物侧边+内容对侧真分区）；
    竖屏仍按金句→左下、其余→右下角标。"""
    vt = (visual_type or "").strip().lower()
    if orientation == "landscape":
        return _VT_LAYOUT_LANDSCAPE.get(vt, "right-rail")
    return _VT_LAYOUT_PORTRAIT.get(vt, "corner-br")


def content_zone(layout: str, orientation: str = "portrait") -> dict:
    """🔴 v42 横屏真分区：返回内容区（sub-composition 画布）坐标。
    横屏分栏时，内容画布 = 全屏 - 人物区 - 缝隙，LLM 在内容区内排版，人物独占对侧，物理分离。
    竖屏/角标 → 内容全屏。"""
    fw, fh = (1920, 1080) if orientation == "landscape" else (1080, 1920)
    if orientation != "landscape":
        return {"x": 0, "y": 0, "w": fw, "h": fh}
    if layout == "left-rail":
        # 人物左（520），内容右：内容 x = 520+30 = 550，宽 = 1920-550 = 1370
        cx = LANDSCAPE_PERSON_W + LANDSCAPE_GAP
        return {"x": cx, "y": 0, "w": fw - cx, "h": fh}
    if layout == "right-rail":
        # 人物右（520），内容左：内容 x = 0，宽 = 1920-520-30 = 1370
        return {"x": 0, "y": 0, "w": fw - LANDSCAPE_PERSON_W - LANDSCAPE_GAP, "h": fh}
    # 角标 → 内容全屏
    return {"x": 0, "y": 0, "w": fw, "h": fh}

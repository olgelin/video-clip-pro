"""motion_director.py v2 — 场景时长驱动动效序列，精确秒数，不注入通用模板"""

ANIMATIONS = {
    "stagger_blur": {"target": "#main-title"},
    "spring_pop": {"target": "#main-title"},
    "fade_up": {"target": "#subtitle"},
    "tag_reveal": {"target": ".tag-card"},
    "scale_bounce": {"target": ".tag-card"},
    "glitch_in": {"target": "#data-metric"},
    "sweep": {"target": "#light-scan"},
    "flip_in": {"target": "#main-title"},
    "breathe": {"target": "#main-title"},
    "particle_drift": {"target": ".p-rain"},
}


def direct(scene_duration: float, motion_style: str, scene_index: int) -> dict:
    """输出精确动效时间线，每条带绝对秒数 start"""

    # motion_style → 动画效果名映射
    STYLE_MAP = {
        "逐字渐入": "stagger_blur",
        "弹簧弹入": "spring_pop",
        "blur dissolve": "fade_up",
        "扫光横穿": "sweep",
        "呼吸脉冲": "breathe",
        "粒子爆发": "particle_drift",
        "翻转切入": "flip_in",
    }

    # 分解复合技法
    styles_raw = [s.strip() for s in motion_style.replace("+", ",").split(",") if s.strip()]
    styles = [STYLE_MAP.get(s, "fade_up") for s in styles_raw]

    timeline = []
    pos = 0.0

    # 入场段 (0 → 30% 时长)
    entry_end = scene_duration * 0.3
    for style in styles:
        if style in ANIMATIONS and pos < entry_end:
            anim = ANIMATIONS[style]
            timeline.append({
                "effect": style,
                "start": round(pos, 1),
                "target": anim["target"],
            })
            pos += 0.3 if pos > 0 else 0.4

    # 中段呼吸 (30% → 70%), only for 5s+ scenes
    if scene_duration > 5:
        timeline.append({
            "effect": "breathe",
            "start": round(scene_duration * 0.35, 1),
            "target": "#main-title",
        })

    # 扫光 (40% → end-20%), only for 4s+ scenes
    if scene_duration > 4:
        timeline.append({
            "effect": "sweep",
            "start": round(scene_duration * 0.4, 1),
            "target": "#light-scan",
        })

    # 粒子 (50% → end)
    if scene_duration > 3:
        timeline.append({
            "effect": "particle_drift",
            "start": round(scene_duration * 0.5, 1),
            "target": ".p-rain",
        })

    # tag 渐入
    timeline.append({
        "effect": "tag_reveal",
        "start": round(scene_duration * 0.15, 1),
        "target": ".tag-card",
    })

    # 第二段呼吸（12s+）
    if scene_duration > 12:
        timeline.append({
            "effect": "breathe_2",
            "start": round(scene_duration * 0.7, 1),
            "target": "#main-title",
        })

    return {
        "scene_duration": scene_duration,
        "motion_style": motion_style,
        "timeline": timeline,
    }

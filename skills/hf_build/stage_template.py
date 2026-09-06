"""stage_template.py — 透明浮空科技面板壳（对齐 hf_build_pip/stage_template.py）

框架（代码层）写死：透明浮空面板 container 的「背景/边框/圆角/发光」——
半透明渐变 + 圆角 18px + 渐变发光边框 + 双层光晕 + 顶部渐变光带 + 角部光晕装饰。
内容层（标题/数据/装饰）交给 LLM 填充。GSAP 动画由 hf_card_builder 的
_build_gsap_animation 统一处理（入场/元素揭示/微动），本模块不生成 GSAP，
避免与框架 timeline 重复注册 window.__timelines。

对齐原因：card 原本让 LLM 生成整个卡片 HTML（含 container 背景/边框），
LLM 遵守度不稳定（透明面板时好时坏）。把壳移到代码层后 100% 稳定。
"""

# emotion → 边框/发光主色（蓝色科技风，禁红/绿；金只用于关键数字，禁整条金边框）
_EMOTION_COLOR = {
    "neutral": "#00D4FF",      # 青
    "urgent": "#6C8CFF",       # 蓝
    "tense": "#A855F7",        # 紫
    "hopeful": "#00D4FF",      # 青
    "triumphant": "#00D4FF",   # 青
}


def _hex_to_rgb(hx: str) -> tuple:
    hx = hx.lstrip("#")
    return tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))


def build_card(idx: int, dur: float, emotion: str, cw: int, ch: int,
               content_html: str) -> str:
    """透明浮空科技面板壳：背景/边框/圆角/发光由代码写死，LLM 只填内容。

    container 用 inset:0 + width/height 100% 填满 host 的 beat-N div（位置/尺寸由
    hf_card_builder 的 card_style + data-width/height 决定，不在壳里重复定位）。
    """
    accent = _EMOTION_COLOR.get(emotion, "#00D4FF")
    a_r, a_g, a_b = _hex_to_rgb(accent)

    panel = (
        f'<div id="panel" data-composition-id="card" data-width="{cw}" data-height="{ch}" '
        f'style="position:absolute;inset:0;width:100%;height:100%;overflow:hidden;'
        f'background:linear-gradient(135deg,rgba(6,14,24,0.32),rgba(8,18,32,0.5));'
        f'backdrop-filter:blur(16px) saturate(140%);'
        f'border:1px solid rgba({a_r},{a_g},{a_b},0.45);'
        f'border-radius:18px;'
        f'box-shadow:0 30px 60px rgba(0,0,0,0.5),0 0 30px rgba({a_r},{a_g},{a_b},0.3),'
        f'inset 0 0 0 1px rgba({a_r},{a_g},{a_b},0.08);">\n'
        f'  <div style="position:absolute;top:0;left:0;width:100%;height:1px;'
        f'background:linear-gradient(90deg,transparent,rgba({a_r},{a_g},{a_b},0.7),transparent);"></div>\n'
        f'  <div class="glow" style="position:absolute;top:-40px;right:-40px;width:200px;height:200px;'
        f'border-radius:50%;background:radial-gradient(circle,rgba({a_r},{a_g},{a_b},0.25),transparent 70%);'
        f'mix-blend-mode:screen;"></div>\n'
        f'  <!-- LLM_CONTENT_INSERT -->\n'
        f'</div>'
    )

    return panel.replace("<!-- LLM_CONTENT_INSERT -->", content_html)

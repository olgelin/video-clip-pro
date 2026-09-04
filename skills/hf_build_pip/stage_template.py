"""stage_template.py v5 — 背景外壳（对齐 video-factory 背景规范）
框架提供：背景渐变 + CSS 3D 透视网格 + 径向光晕×3 + 地平线辉光带 + ghost 水印 +
CSS 粒子雨(18条三层景深坠线,仅上半区) + 扫光 + Three.js 内联 + GSAP 动效模板。
内容层(标题/卡片/数据)交给 LLM。
"""
import random


_RAIN = '<div class="{cls}" style="position:absolute;z-index:1;pointer-events:none;top:{top}%;left:{x}%;width:{w}px;height:{h}px;background:linear-gradient(180deg,transparent,rgba({r},{g},{b},{a1}),rgba({r},{g},{b},{a2}),transparent);border-radius:1px;"></div>'

_GSAP_FIXED = """{gsap_local}
<script>window.__timelines=window.__timelines||{{}};(function(){{
var tl=gsap.timeline({{paused:true}});
{motion_code}
window.__timelines["beat-{scene_idx}"]=tl;
}})();
</script>"""


def _load_gsap_local() -> str:
    """内联本地 GSAP（headless 渲染无法访问 CDN）"""
    import pathlib
    p = pathlib.Path(__file__).parent / "assets" / "gsap.min.js"
    if p.exists():
        js = p.read_text(encoding="utf-8")
        return f"<script>{js}</script>"
    return '<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js"></script>'


def _load_three_local() -> str:
    """内联本地 Three.js UMD（r147 全局 THREE，headless 无法访问 CDN importmap）"""
    import pathlib
    p = pathlib.Path(__file__).parent / "assets" / "three.min.js"
    if p.exists():
        js = p.read_text(encoding="utf-8")
        return f"<script>{js}</script>"
    return '<script src="https://cdn.jsdelivr.net/npm/three@0.147.0/build/three.min.js"></script>'


def hex_to_rgb(hx: str) -> tuple:
    hx = hx.lstrip("#")
    return tuple(int(hx[i:i+2], 16) for i in (0, 2, 4))


def _dedup_motion(motion_code: str) -> str:
    """🔴 去重相同 selector 的 from 入场动画（相隔 <1s）。
    根因：框架层 motion_director 和 LLM 各自生成标题/卡片入场动画，两条重复叠加 → 闪烁。"""
    import re
    lines = motion_code.split('\n')
    from_seen = {}
    deduped = []
    for line in lines:
        if line.strip().startswith('tl.from'):
            m_sel = re.search(r'tl\.from\("?([#.\w\- >]+?)"?\s*,\s*\{', line)
            m_ts = re.search(r',\s*([\d.]+)\s*\)\s*;?\s*$', line)
            if m_sel and m_ts:
                sel = m_sel.group(1).strip()
                t = float(m_ts.group(1))
                if sel in from_seen and (t - from_seen[sel]) < 1.0:
                    continue
                from_seen[sel] = t
        deduped.append(line)
    return '\n'.join(deduped)


def build_stage(scene_idx: int, dur: float, palette: dict, motion: dict,
                ghost: str, quote: str, llm_motion: str = "",
                orientation: str = "portrait") -> str:
    fw, fh = (1920, 1080) if orientation == "landscape" else (1080, 1920)
    gs = palette["gradient_start"]
    gm = palette["gradient_mid"]
    ge = palette["gradient_end"]
    accent = palette.get("accent", "#6C8CFF")
    secondary = palette.get("secondary", "#00D4FF")
    primary = palette.get("primary", "#6C8CFF")

    a_r, a_g, a_b = hex_to_rgb(accent)
    s_r, s_g, s_b = hex_to_rgb(secondary)

    # ── 背景层（照 video-factory 背景规范：网格 + 光晕 + 辉光带 + ghost 水印 + 粒子雨 + 扫光）──

    # 1. CSS 3D 透视网格（rotateX 58deg，消失点 42%）
    grid_3d = (f'<div style="position:absolute;inset:0;z-index:0;pointer-events:none;perspective:1000px;overflow:hidden;">'
               f'<div style="position:absolute;left:-20%;right:-20%;top:42%;bottom:-30%;transform:rotateX(58deg);'
               f'background-image:linear-gradient(rgba({a_r},{a_g},{a_b},0.08) 1px,transparent 1px),'
               f'linear-gradient(90deg,rgba({a_r},{a_g},{a_b},0.08) 1px,transparent 1px);background-size:60px 60px;"></div></div>')

    # 2. 径向光晕 ×3（蓝+紫+青，mix-blend-mode:screen）
    glow = (f'<div style="position:absolute;inset:0;z-index:0;pointer-events:none;mix-blend-mode:screen;">'
            f'<div style="position:absolute;top:5%;left:8%;width:680px;height:520px;background:radial-gradient(ellipse at center,rgba({a_r},{a_g},{a_b},0.14),transparent 70%);"></div>'
            f'<div style="position:absolute;top:20%;right:5%;width:720px;height:560px;background:radial-gradient(ellipse at center,rgba({s_r},{s_g},{s_b},0.12),transparent 70%);"></div>'
            f'<div style="position:absolute;bottom:10%;left:35%;width:800px;height:400px;background:radial-gradient(ellipse at center,rgba({s_r},{s_g},{s_b},0.07),transparent 70%);"></div></div>')

    # 3. 地平线辉光带（蓝紫渐变，blur 60px）
    horizon = (f'<div style="position:absolute;top:40%;left:0;right:0;height:180px;z-index:0;pointer-events:none;'
               f'background:linear-gradient(90deg,transparent,rgba({a_r},{a_g},{a_b},0.18),rgba({s_r},{s_g},{s_b},0.22),transparent);filter:blur(60px);"></div>')

    # 4. ghost text 中文水印（180px，opacity 0.04，用有意义 title 关键词）
    ghost_word = ghost if len(ghost) >= 2 else (quote[:2] if len(quote) >= 2 else "?")
    ghost_text = (f'<div style="position:absolute;inset:0;z-index:0;display:flex;align-items:center;justify-content:center;pointer-events:none;overflow:hidden;">'
                  f'<span style="font-size:180px;font-weight:900;color:{primary};opacity:0.04;letter-spacing:12px;transform:rotate(-8deg);white-space:nowrap;">{ghost_word}</span></div>')

    # 5. CSS 粒子雨：18 条三层景深坠线（p-near 6 + p-mid 6 + p-far 6），严格分层（对齐 vf：near 0-8% / mid 10-18% / far 20-28%）
    rain_html = ""
    depths = [("p-near", 0.75, 0.35, 11, 16, 0, 8),
              ("p-mid", 0.50, 0.22, 7, 10, 10, 18),
              ("p-far", 0.32, 0.12, 5, 6, 20, 28)]
    rng = random.Random(scene_idx * 7 + int(dur))
    for cls_name, a1, a2, h_min, h_max, top_min, top_max in depths:
        for _ in range(6):
            x = rng.randint(2, 92)
            top = rng.randint(top_min, top_max)  # 三层景深严格分层
            h = h_min + rng.randint(0, h_max - h_min)
            w = max(1, h // 6)
            rain_html += _RAIN.format(cls=cls_name, top=top, x=x, w=w, h=h,
                                      r=a_r, g=a_g, b=a_b, a1=a1, a2=a2)

    # 6. 扫光（对角线方向）
    scan = (f'<div id="light-scan" style="position:absolute;top:-20%;left:-30%;width:50%;height:180%;z-index:3;pointer-events:none;'
            f'background:linear-gradient(105deg,transparent 30%,rgba({a_r},{a_g},{a_b},0.08) 50%,transparent 70%);transform:rotate(8deg);"></div>')

    # 动效
    tl_lines = motion.get("timeline", [])
    motion_code = ""
    seen = set()  # 🔴 去重：motion_director 可能产出重复 effect（sweep/particle_drift 出现两次）
    for m in tl_lines:
        eff = m.get("effect", "")
        t = m.get("start", 0)
        if "stagger_blur" in eff:
            motion_code += f'tl.from("#main-title span",{{opacity:0,y:50,stagger:{{each:.04,from:"center"}},duration:.5,ease:"power3.out"}},{t});\n'
        elif "breathe" in eff:
            motion_code += f'tl.to("#main-title",{{duration:2,scale:1.03,ease:"sine.inOut"}},{t});\n'
        elif "sweep" in eff:
            if "sweep" in seen: continue
            seen.add("sweep")
            motion_code += f'if(document.getElementById("light-scan")){{tl.fromTo("#light-scan",{{opacity:0.01,left:"-30%",top:"-20%"}},{{opacity:0.9,left:"120%",top:"90%",duration:2.8,ease:"power2.inOut"}},{t});}}\n'
        elif "particle_drift" in eff:
            if "particle_drift" in seen: continue
            seen.add("particle_drift")
            # 🔴 对齐 vf：粒子雨向下坠落（tl.to y 分层 + repeat），不是 tl.from 回位
            motion_code += f'tl.to(".p-near",{{y:1150,opacity:0.3,duration:4,repeat:2,ease:"none"}},0);\n'
            motion_code += f'tl.to(".p-mid",{{y:1000,opacity:0.25,duration:7,repeat:1,ease:"none"}},0);\n'
            motion_code += f'tl.to(".p-far",{{y:820,opacity:0.15,duration:10,repeat:1,ease:"none"}},0);\n'
        elif "tag_reveal" in eff:
            motion_code += f'tl.from(".tag-card",{{scale:.6,opacity:0,stagger:.08,duration:.4,ease:"back.out(1.4)"}},{t});\n'

    # 🔴 P0：LLM 的动画语句合并进统一 timeline（HyperFrames 只 seek "beat-N" 一个 key）
    if llm_motion:
        motion_code += llm_motion + "\n"

    # 🔴 去重：框架层 motion + LLM 动画合并后，统一去重重复的 from 入场动画（<1s）
    motion_code = _dedup_motion(motion_code)

    gsap_block = _GSAP_FIXED.format(gsap_local=_load_gsap_local(), motion_code=motion_code, scene_idx=scene_idx)
    three_block = _load_three_local()

    return f"""<div data-composition-id="beat-{scene_idx}" data-width="{fw}" data-height="{fh}" style="position:absolute;inset:0;z-index:10;overflow:hidden;background:linear-gradient(180deg,{gs},{gm},{ge});font-family:'PingFang SC','Microsoft YaHei',sans-serif;">
{three_block}
{grid_3d}
{glow}
{horizon}
{ghost_text}
<!-- LLM_CONTENT_INSERT -->
{rain_html}
{scan}
<div style="position:absolute;inset:0;z-index:45;pointer-events:none;background:radial-gradient(ellipse 75% 65% at 50% 45%,transparent 55%,rgba(0,0,0,0.38) 100%);"></div>
</div>
{gsap_block}"""

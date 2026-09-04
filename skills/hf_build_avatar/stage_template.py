"""stage_template.py v5 — 背景外壳（对齐 video-factory 背景规范）
框架提供：背景渐变 + CSS 3D 透视网格 + 径向光晕×3 + 地平线辉光带 + ghost 水印 +
CSS 粒子雨(18条三层景深坠线,仅上半区) + 扫光 + Three.js 内联 + GSAP 动效模板。
内容层(标题/卡片/数据)交给 LLM。
"""



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


def _dedup_motion(motion_code: str) -> str:
    """🔴 去重相同 selector 的 from 入场动画（相隔 <1s）。
    根因：框架层 motion_director（stagger_blur 等 effect）和 LLM 各自生成标题/卡片入场动画，
    两条重复叠加 → 元素"入场→消失→再入场"闪烁。合并后统一去重，保留时间戳最早一条。"""
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
                    continue  # 重复入场（<1s），丢弃
                from_seen[sel] = t
        deduped.append(line)
    return '\n'.join(deduped)


def build_stage(scene_idx: int, dur: float, palette: dict, motion: dict,
                ghost: str, quote: str, llm_motion: str = "",
                orientation: str = "portrait", person_layout: str = "corner") -> str:
    fw, fh = (1920, 1080) if orientation == "landscape" else (1080, 1920)
    # 🔴 v42 横屏真分区：分栏时内容画布 = 内容区宽度（人物区 520 + 缝隙 30 之外），
    #    LLM 在内容区内排版，数字人独占对侧竖条，物理分离不叠放。
    is_split = orientation == "landscape" and person_layout in ("left-rail", "right-rail")
    if is_split:
        from skills.hf_build_avatar.person_zone import content_zone as _cz
        fw = _cz(person_layout, orientation)["w"]
    gs = palette["gradient_start"]
    gm = palette["gradient_mid"]
    ge = palette["gradient_end"]

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

    # ── 人物区占位框（v39 同层排版）：data-person-zone 标记，LLM 视觉避让提示 ──
    # 🔴 v42 横屏真分区：分栏时数字人在内容区之外（host 层），不需要占位框；竖屏/角标才需要。
    person_zone_html = ""
    if not is_split:
        try:
            from skills.hf_build_avatar.person_zone import person_zone as _pz
            _zone = _pz(person_layout, orientation)
            person_zone_html = (
                f'<div data-person-zone="{person_layout}" '
                f'data-person-x="{_zone["x"]}" data-person-y="{_zone["y"]}" '
                f'data-person-w="{_zone["w"]}" data-person-h="{_zone["h"]}" '
                f'style="position:absolute;left:{_zone["x"]}px;top:{_zone["y"]}px;'
                f'width:{_zone["w"]}px;height:{_zone["h"]}px;z-index:40;pointer-events:none;'
                f'border:2px dashed rgba(255,255,255,0.12);background:rgba(255,255,255,0.02);'
                f'box-sizing:border-box;border-radius:16px;"></div>')
        except Exception:
            person_zone_html = ""

    # 🔴 方向2：背景交给 LLM 生成（照 vf 背景规范）。框架只提供最小骨架：
    #    container(兜底深色底) + Three.js 内联 + LLM 内容插入点 + 人物占位框 + GSAP 统一 timeline。
    #    网格/光晕/辉光/ghost水印/粒子雨/扫光 全部由 LLM 在 scene_system.md 背景规范下生成。
    return f"""<div data-composition-id="beat-{scene_idx}" data-width="{fw}" data-height="{fh}" style="position:absolute;inset:0;z-index:10;overflow:hidden;background:linear-gradient(180deg,{gs},{gm},{ge});font-family:'PingFang SC','Microsoft YaHei',sans-serif;">
{three_block}
<!-- LLM_CONTENT_INSERT -->
{person_zone_html}
</div>
{gsap_block}"""

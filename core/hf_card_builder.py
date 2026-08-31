import json, os, time, subprocess, shutil, re
from pathlib import Path
from core.card_constants import *
from core.card_decor import *
from core.card_layouts import *

def _build_gsap_animation(beat_id, beat, exit_offset, is_highlight=False):
    """Minimal card animation: entrance + micro + exit. Sequenced element reveals handled inline."""
    preset = ANIMATION_PRESETS.get(beat, DEFAULT_ANIM)
    ent = preset["entrance"]; ext = preset["exit"]; mic = preset["micro"]
    lines = ['<script>window.__timelines=window.__timelines||{};(function(){']
    lines.append('var tl=gsap.timeline({paused:true});')
    lines.append(f'var card=document.querySelector("[data-composition-id={beat_id}]");')
    lines.append('if(!card){window.__timelines["'+beat_id+'"]=gsap.timeline({paused:true});return;}')
    etype, edur, eease = ent["type"], ent["duration"], ent["ease"]
    if is_highlight: edur *= 1.3
    if etype == "scaleBounce": lines.append(f'gsap.set(card,{{opacity:0,scale:0.3}});'); lines.append(f'tl.to(card,{{opacity:1,scale:1,duration:{edur},ease:"{eease}"}},0);')
    elif etype == "fadeSlideUp": lines.append(f'gsap.set(card,{{opacity:0,y:40,scale:0.95}});'); lines.append(f'tl.to(card,{{opacity:1,y:0,scale:1,duration:{edur},ease:"{eease}"}},0);')
    elif etype == "fadeSlideDown": lines.append(f'gsap.set(card,{{opacity:0,y:-30,scale:0.95}});'); lines.append(f'tl.to(card,{{opacity:1,y:0,scale:1,duration:{edur},ease:"{eease}"}},0);')
    elif etype == "fadeSlideRight": lines.append(f'gsap.set(card,{{opacity:0,x:60,scale:0.94}});'); lines.append(f'tl.to(card,{{opacity:1,x:0,scale:1,duration:{edur},ease:"{eease}"}},0);')
    elif etype == "fadeSlideLeft": lines.append(f'gsap.set(card,{{opacity:0,x:-60,scale:0.94}});'); lines.append(f'tl.to(card,{{opacity:1,x:0,scale:1,duration:{edur},ease:"{eease}"}},0);')
    elif etype == "scaleFade": lines.append(f'gsap.set(card,{{opacity:0,scale:0.7}});'); lines.append(f'tl.to(card,{{opacity:1,scale:1,duration:{edur},ease:"{eease}"}},0);')
    elif etype == "dropBounce": lines.append(f'gsap.set(card,{{opacity:0,y:-80,scale:0.9}});'); lines.append(f'tl.to(card,{{opacity:1,y:0,scale:1,duration:{edur},ease:"{eease}"}},0);')
    else: lines.append(f'gsap.set(card,{{opacity:0,y:25}});'); lines.append(f'tl.to(card,{{opacity:1,y:0,duration:{edur},ease:"{eease}"}},0);')
    # Element reveals handled by CSS animation-delay (see CARD_DECOR_CSS .card-header, .card-headline, etc.)
    # Highlight pulse
    if is_highlight: lines.append(f'tl.to(card,{{scale:1.03,duration:0.3,ease:"power1.inOut"}},"+=0.4");'); lines.append(f'tl.to(card,{{scale:1,duration:0.3,ease:"power1.inOut"}});'); exit_offset = max(exit_offset - 0.5, 0.3)
    # V12: element sequential reveals (standard IDs, auto-skip if missing)
    ELEM_DELAYS = [
        ("#value", "0.12", "{scale:0,opacity:0}", "{scale:1,opacity:1,duration:0.35,ease:'back.out(2)'}"),
        (".badge-item", "0.15", "{scale:0,opacity:0}", "{scale:1,opacity:1,duration:0.25,stagger:0.1,ease:'back.out(1.5)'}"),
        ("#bar-fill", "0.2", "{width:'0%'}", "{width:'85%',duration:0.6,ease:'power2.inOut'}"),
        (".fact-tag", "0.1", "{opacity:0}", "{opacity:1,duration:0.3,ease:'power1.out'}"),
        ("#quote-mark", "0.12", "{scale:0.5,opacity:0}", "{scale:1,opacity:1,duration:0.25,ease:'back.out(1.2)'}"),
        (".pulse-dot", "0.08", "{scale:0,opacity:0}", "{scale:1,opacity:1,duration:0.3,ease:'elastic.out(1,0.5)'}"),
        (".check-item", "0.15", "{scale:0,opacity:0}", "{scale:1,opacity:1,duration:0.25,stagger:0.1,ease:'back.out(1.5)'}"),
        (".step-dot", "0.15", "{scale:0,opacity:0}", "{scale:1,opacity:1,duration:0.25,stagger:0.12,ease:'back.out(1.5)'}"),
    ]
    for sel, delay, from_v, to_v in ELEM_DELAYS:
        lines.append(f'(function(){{var e=card.querySelector("{sel}");if(e)tl.fromTo(e,{from_v},{to_v},"+={delay}");}})();')
    # Exit
    etype2, edur2, eease2 = ext["type"], ext["duration"], ext["ease"]; exit_label = f'+={exit_offset}'
    if etype2 == "fadeSlideUp": lines.append(f'tl.to(card,{{y:-30,opacity:0,duration:{edur2},ease:"{eease2}"}},"{exit_label}");')
    elif etype2 == "fadeSlideDown": lines.append(f'tl.to(card,{{y:30,opacity:0,duration:{edur2},ease:"{eease2}"}},"{exit_label}");')
    elif etype2 == "scaleOut": lines.append(f'tl.to(card,{{scale:0.8,opacity:0,duration:{edur2},ease:"{eease2}"}},"{exit_label}");')
    elif etype2 == "shakeOut": lines.append(f'tl.to(card,{{x:8,duration:0.06,ease:"none"}},"{exit_label}");'); lines.append(f'tl.to(card,{{x:-8,duration:0.06,ease:"none"}});'); lines.append(f'tl.to(card,{{x:0,opacity:0,duration:{edur2},ease:"{eease2}"}});')
    elif etype2 == "fadeOut": lines.append(f'tl.to(card,{{opacity:0,duration:{edur2},ease:"{eease2}"}},"{exit_label}");')
    else: lines.append(f'tl.to(card,{{opacity:0,y:-20,duration:{edur2},ease:"{eease2}"}},"{exit_label}");')
    # Micro
    mic_type = mic["type"]
    if mic_type == "float": lines.append(f'card.style.animation="floatAnim {mic.get("period",3)}s ease-in-out infinite";')
    elif mic_type == "pulse": lines.append(f'card.style.animation="pulseAnim {mic.get("period",2.5)}s ease-in-out infinite";')
    elif mic_type == "glowPulse": lines.append(f'card.style.animation="glowPulseAnim {mic.get("period",2)}s ease-in-out infinite";')
    elif mic_type == "breathe": lines.append(f'card.style.animation="breatheAnim {mic.get("period",3)}s ease-in-out infinite";')
    # Sweep
    if is_highlight or beat in ("HOOK","CONFLICT","RESOLUTION","TURN"): lines.append('var sweep=document.createElement("div");sweep.style.cssText="position:absolute;top:0;left:0;width:30%;height:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.06),transparent);transform:skewX(-20deg);z-index:4;pointer-events:none;animation:lightSweep 3s ease-in-out infinite;";'); lines.append('card.querySelector("div").appendChild(sweep);')
    lines.append(f'window.__timelines["{beat_id}"]=tl;}})();</script>')
    return ''.join(lines)

def _sanitize(s):
    if not s: return ""
    return s.replace("&","&amp;").replace('"',"&quot;").replace("<","&lt;").replace(">","&gt;")

def _detect_orientation(video_path):
    try:
        r = subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","csv=p=0",str(video_path)], capture_output=True, text=True, timeout=30)
        parts = r.stdout.strip().split(",")
        if len(parts) >= 2: return "portrait" if int(parts[1]) > int(parts[0]) else "landscape"
    except: pass
    return "portrait"

def _find_npx():
    for c in ["npx.cmd","npx","npx.bat"]:
        p = shutil.which(c)
        if p: return p
    ap = os.environ.get("APPDATA","")
    if ap:
        p = Path(ap) / "npm" / "npx.cmd"
        if p.exists(): return str(p)
    return None

def _extract_beat_parts(beat_html):
    """🔴 0.7.109 sub-composition timeline seek 失效 → 内联单一 timeline。
    提取 beat HTML 的 (html_fragment, motion_js)：
    html_fragment = div 内容（去掉 three.min.js/gsap.min.js 库 + GSAP script）
    motion_js = tl.from/to 语句（去掉 window.__timelines 注册）
    """
    import re
    m = re.search(r'<body>(.*)</body>', beat_html, re.DOTALL)
    body = m.group(1) if m else beat_html
    # 去掉 three.min.js 库（含 "Three.js Authors" 标记）
    body = re.sub(r'<script>\s*/\*\*.*?Three\.js Authors.*?</script>', '', body, flags=re.DOTALL)
    # 去掉 gsap.min.js 库（含 "GSAP" 注释标记）
    body = re.sub(r'<script>\s*/\*!.*?GSAP.*?_inheritsLoose.*?</script>', '', body, flags=re.DOTALL)
    # 提取 GSAP 动画 script（结尾 })(); 和 </script> 之间允许换行）
    m = re.search(r'<script>window\.__timelines=window\.__timelines\|\|\{\};\(function\(\)\{(.*?)\}\)\(\);\s*</script>', body, re.DOTALL)
    motion_js = m.group(1) if m else ""
    if m:
        body = body.replace(m.group(0), '')
    # 去掉 motion_js 里的 var tl 定义和 __timelines 注册
    motion_js = re.sub(r'var\s+tl\s*=\s*gsap\.timeline\(\{paused:true\}\);?', '', motion_js)
    motion_js = re.sub(r'window\.__timelines\[[^\]]+\]=tl;?', '', motion_js)
    return body, motion_js.strip()

def _dedup_canvas_ids(frag, idx):
    """内联后多个 beat 的 canvas id 会冲突（bg3d/glx/...），加 beat 后缀去重"""
    import re
    canvas_ids = set(re.findall(r'<canvas id="([^"]+)"', frag))
    for cid in canvas_ids:
        new_cid = cid + "-" + str(idx)
        frag = frag.replace('id="' + cid + '"', 'id="' + new_cid + '"')
        frag = frag.replace('getElementById("' + cid + '")', 'getElementById("' + new_cid + '")')
        frag = frag.replace("getElementById('" + cid + "')", "getElementById('" + new_cid + "')")
    return frag

def _offset_motion(motion, pos):
    """把 motion 里每个 tl.from/to/fromTo 的绝对时间参数偏移 pos（平铺到主 timeline）。
    用括号栈正确匹配（处理 ease 值 back.out(1.4) 的嵌套括号）。"""
    import re
    result = []
    i = 0
    while True:
        m = re.search(r'tl\.(from|to|fromTo)\(', motion[i:])
        if not m:
            result.append(motion[i:]); break
        start = i + m.start()
        depth = 0
        j = i + m.end() - 1  # 指向 (
        while j < len(motion):
            ch = motion[j]
            if ch == '(': depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0: break
            j += 1
        stmt = motion[start:j + 1]
        last_comma = -1; depth = 0
        for k in range(len(stmt) - 2, -1, -1):
            ch = stmt[k]
            if ch == ')': depth += 1
            elif ch == '(': depth -= 1
            elif ch == ',' and depth == 0:
                last_comma = k; break
        if last_comma > 0:
            tstr = stmt[last_comma + 1:-1].strip()
            try:
                t = float(tstr)
                new_stmt = stmt[:last_comma + 1] + str(round(pos + t, 2)) + ')'
                result.append(motion[i:start]); result.append(new_stmt); i = j + 1; continue
            except ValueError:
                pass
        result.append(motion[i:start]); result.append(stmt); i = j + 1
    return ''.join(result)

def _wrap_scripts_scope(frag):
    """把片段里的 <script> 用 IIFE 包裹，避免内联后变量名冲突（const c/r/s/cam 等）。"""
    import re
    return re.sub(r'<script>(.*?)</script>', lambda m: '<script>(function(){' + m.group(1) + '})();</script>', frag, flags=re.DOTALL)

# Visual components

def build_hyperframes_composition(edl, words, output_dir, video_path, layout_mode="fullscreen", orientation=None):
    hf_dir = output_dir / "hyperframes"; comp_dir = hf_dir / "compositions"
    hf_dir.mkdir(parents=True, exist_ok=True); comp_dir.mkdir(exist_ok=True)
    src_v = str(output_dir / "final.mp4")
    # 🔴 avatar 新流程：无剪切无 final.mp4，用数字人视频（video_path=avatar_video.mp4）
    if not os.path.exists(src_v) and video_path and os.path.exists(str(video_path)):
        src_v = str(video_path)
    dst_v = str(hf_dir / "final.mp4")
    if os.path.exists(src_v): shutil.copy2(src_v, dst_v); print("      Video copied")
    # 🔴 场景方向优先用传入 orientation（数字人合成用竖屏素材时，场景仍可横屏）
    orientation = orientation or _detect_orientation(video_path)
    print("      Orientation:", orientation)
    ranges = edl.get("ranges", [])
    if not ranges: return None
    seg_offsets = []; acc = 0.0
    for seg in ranges: seg_offsets.append(acc); acc += seg["end"] - seg["start"]
    total_dur = acc
    # 🔴 场景尺寸由 orientation 决定（横屏 1920×1080 / 竖屏 1080×1920），
    #    不读数字人视频分辨率（竖屏素材放横屏场景时，场景尺寸必须独立于素材）
    fw, fh = (1920, 1080) if orientation == "landscape" else (1080, 1920)
    captions = _build_captions(ranges, words, seg_offsets, orientation, fw)
    beat_files = []
    for idx, seg in enumerate(ranges):
        offset = seg_offsets[idx]; beat_id = "beat-" + str(idx)
        dur = round(seg["end"] - seg["start"], 2); beat = seg.get("beat", "INFO").upper()
        quote = seg.get("quote", "")
        card_headline = seg.get("card_headline", "") or seg.get("title", "")
        card_subtext = seg.get("card_subtext", ""); card_metric = seg.get("card_metric")
        card_emotion = seg.get("card_emotion", "neutral"); card_scene = seg.get("card_scene", "context")
        card_vk = seg.get("card_vk", ""); card_data = seg.get("card_data", [])
        card_icon = seg.get("card_icon", "")
        card_layout = seg.get("card_layout", "title-only")
        card_bullets = seg.get("card_bullets", [])
        card_takeaway = seg.get("card_takeaway", "")
        card_vstyle = seg.get("card_vstyle", "tech"); card_threejs_flag = seg.get("card_threejs", True)
        safe_headline = _sanitize(card_headline); safe_subtext = _sanitize(card_subtext); sanitized_quote = _sanitize(quote)
        tc = TAG_COLORS.get(beat, COLORS["cyan"]); beat_name = BEAT_LABELS.get(beat, beat)
        icon = BEAT_ICONS.get(beat, "\u25c6")
        # Smart fill: upgrade before sizing (layout may change → need right dimensions)
        safe_headline, card_metric, card_data, card_layout, card_bullets = _smart_fill(
            safe_headline, safe_subtext, card_metric, card_data, card_layout, card_bullets,
            beat_name=beat_name, quote=sanitized_quote)
        # Size based on upgraded layout
        if card_layout in ("big-number", "comparison"):
            cw, ch = (680, 280) if orientation != "portrait" else (600, 300)
        elif card_layout == "bullets":
            cw, ch = (620, 280) if orientation != "portrait" else (560, 300)
        elif card_layout == "quote-card":
            cw, ch = (600, 220) if orientation != "portrait" else (540, 240)
        else: cw, ch = (560, 260) if orientation != "portrait" else (500, 250)
        exit_offset = max(0.5, dur - 1.0); is_highlight = (idx == len(ranges) - 1)
        # V6: LLM直出HTML优先
        llm_html = seg.get("_llm_html", "")
        scene_html = seg.get("_scene_html", "")  # 🔴 P0: hf_build_pip 全屏完整场景（含背景+内容+GSAP）
        card_threejs_flag = False
        # ── PIP模式：全屏场景，不用卡片模板 ──
        if layout_mode in ("pip", "avatar"):
            cw, ch = fw, fh  # 全视口
            if scene_html and len(scene_html) > 100:
                card_html = scene_html
            elif llm_html and len(llm_html) > 100:
                card_html = llm_html
            else:
                # PIP回退：生成默认全屏深色场景而非500px卡片
                card_html = f'<div data-composition-id="{beat_id}" data-width="{fw}" data-height="{fh}" style="position:absolute;inset:0;z-index:10;overflow:hidden;background:linear-gradient(180deg,#0A0A1A,#1A0A2E,#0C1030);"><div class="scene-atmo" style="position:absolute;inset:0;z-index:1;background:radial-gradient(ellipse at 50% 40%,rgba(108,140,255,0.06),transparent 50%),radial-gradient(ellipse at 70% 70%,rgba(168,85,247,0.04),transparent 40%);"></div><div style="position:relative;z-index:2;display:flex;align-items:center;justify-content:center;height:100%;padding:60px 40px;"><div id="headline" style="font-size:72px;font-weight:900;color:#fff;text-align:center;max-width:80%;line-height:1.3;">{safe_headline}</div></div></div><script>(function(){{var tl=gsap.timeline({{paused:true}});tl.from(\'#headline\',{{scale:0,opacity:0,duration:0.5,ease:\\"back.out(2)\\"}});tl.play();}})();</script>'
        elif llm_html and len(llm_html) > 100 and re.search(r'<div[^>]*data-composition-id\s*=', llm_html):
            card_html = llm_html
        else:
            card_html = _build_card(beat_id, beat, tc, beat_name, icon, safe_headline, safe_subtext, card_metric, card_emotion, card_scene, card_vk, card_data, card_icon, cw, ch, _sanitize(quote), orientation, card_layout, card_bullets, card_takeaway, card_vstyle)
        gsap_script = _build_gsap_animation(beat_id, beat, exit_offset, is_highlight)
        threejs_bg = _threejs_card_bg(tc) if card_threejs_flag else ""
        if scene_html and len(scene_html) > 100:
            # 完整场景（已含背景+内容+GSAP+__timelines），包 DOCTYPE 写 beat-N.html
            full_html = '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>' + FONT_CSS + '*{margin:0;padding:0;box-sizing:border-box}body{overflow:hidden;background:transparent}</style></head><body>' + scene_html + '</body></html>'
        elif llm_html and len(llm_html) > 100:
            gsap_exit = _build_gsap_animation(beat_id, beat, exit_offset, is_highlight)
            full_html = '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>'+FONT_CSS+MICRO_CSS+CARD_DECOR_CSS+'*{margin:0;padding:0;box-sizing:border-box}body{overflow:hidden;background:transparent;font-family:CJK,Inter,"Segoe UI",sans-serif}</style></head><body>'+card_html+gsap_exit+'</body></html>'
        else:
            full_html = '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>'+FONT_CSS+MICRO_CSS+CARD_DECOR_CSS+'*{margin:0;padding:0;box-sizing:border-box}body{overflow:hidden;background:transparent;font-family:CJK,Inter,"Segoe UI",sans-serif}</style></head><body>'+threejs_bg+card_html+gsap_script+'</body></html>'
        (comp_dir / (beat_id + ".html")).write_text(full_html, encoding="utf-8")
        if layout_mode in ("pip", "avatar"):
            card_style = f"position:absolute;inset:0;width:{fw}px;height:{fh}px;z-index:10;"
        else:
            # 位置轮换：左→中→右循环（按 idx），避免卡片锁死底部
            if orientation == "portrait":
                _pos_styles = [
                    "left:30px;bottom:40px",
                    "left:50%;bottom:30px;transform:translateX(-50%)",
                    "right:30px;top:50%;transform:translateY(-50%)",
                ]
            else:
                _pos_styles = [
                    "left:30px;top:50%;transform:translateY(-50%)",
                    "left:50%;top:50%;transform:translate(-50%,-50%)",
                    "right:30px;top:50%;transform:translateY(-50%)",
                ]
            card_style = f"position:absolute;{_pos_styles[idx % 3]};width:{cw}px;height:{ch}px;z-index:10;"
        beat_files.append((beat_id, offset, dur, card_style, cw, ch))
    host_lines = []
    for bid, pos, dur_clean, style, cw, ch in beat_files:
        host_lines.append(f'<div id="{bid}" data-composition-id="{bid}" data-composition-src="compositions/{bid}.html" data-start="{round(pos,2)}" data-duration="{round(dur_clean,2)}" data-width="{cw}" data-height="{ch}" class="clip audio-pulse" style="{style}"></div>')
    for cp in captions:
        cid = "cap-" + str(cp["idx"])
        host_lines.append(f'<div id="{cid}" class="clip caption-word" data-start="{cp["start"]}" data-duration="{cp["dur"]}" style="bottom:{cp.get("bottom",130)}px;left:{cp.get("left_pct",50)}%;transform:translateX(-50%);font-size:{cp.get("font_size",38)}px;text-align:center;">{cp["text"]}</div>')
    host_block = "\n".join(host_lines); td_str = str(round(total_dur, 2))
    main_style = f"body{{margin:0;background:{COLORS['bg_deep']}}}#root{{position:relative;width:{fw}px;height:{fh}px;overflow:hidden;background:{COLORS['bg_deep']}}}.bg-glow{{position:absolute;inset:0;z-index:2;pointer-events:none;background:radial-gradient(ellipse at 50% 40%,rgba(0,229,255,0.04),transparent 60%),radial-gradient(ellipse at 70% 70%,rgba(239,68,68,0.03),transparent 50%),radial-gradient(ellipse at 30% 60%,rgba(34,211,160,0.03),transparent 50%);}}#src-v{{animation:kenburns {td_str}s ease-in-out infinite alternate;}}@keyframes kenburns{{0%{{transform:scale(1)}}100%{{transform:scale(1.03)}}}}.unified-timeline{{position:absolute;bottom:4px;left:2%;right:2%;height:2px;background:rgba(255,255,255,0.06);border-radius:1px;overflow:hidden;z-index:30;}}.unified-timeline-fill{{height:100%;background:linear-gradient(90deg,{COLORS['cyan']},{COLORS['purple']},#22d3a0);border-radius:1px;width:0%;}}.caption-word{{position:absolute;color:#fff;font-weight:600;text-shadow:0 2px 12px rgba(0,0,0,0.9);white-space:nowrap;z-index:20;transition:text-shadow 0.15s}}.caption-word.active{{text-shadow:0 0 20px rgba(0,229,255,0.8),0 2px 12px rgba(0,0,0,0.9);color:#fff}}.audio-pulse{{filter:brightness(calc(1 + var(--audio-level,0) * 0.3))}}.env-vignette{{position:absolute;inset:0;z-index:5;pointer-events:none;background:radial-gradient(ellipse at 50% 45%,transparent 52%,rgba(5,8,20,0.55) 100%);}}.env-scan{{position:absolute;top:-18%;bottom:-18%;width:38%;z-index:6;pointer-events:none;background:linear-gradient(105deg,transparent,rgba(140,165,255,0.07),transparent);mix-blend-mode:screen;transform:skewX(-12deg);}}.fg-particles{{position:absolute;inset:0;z-index:17;pointer-events:none;overflow:hidden;}}.fg-p{{position:absolute;border-radius:50%;background:rgba(185,155,255,0.85);box-shadow:0 0 12px rgba(165,140,255,0.95),0 0 4px rgba(200,180,255,0.9);}}"

    # ── PIP/avatar layout (person-in-window / multi-form avatar) ──
    pip_motion = ""  # 🔴 窗口定时换位的 GSAP 动画语句
    if layout_mode in ("pip", "avatar"):
        import random
        is_avatar = (layout_mode == "avatar")
        # 🔴 窗口大小：竖屏 22%，横屏 12%（12% 在 1920 宽 = 230px，换位靠 rotation 动画已恢复，窗口小更精致）
        pip_size = 22 if orientation == "portrait" else 12  # % of viewport width
        # 🔴 竖屏 → 圆框（1:1 圆形），横屏 → 竖向长方形框（3:4，高>宽，带边框）
        radius = "50%" if orientation == "portrait" else "16px"
        shift_interval = 5

        if is_avatar:
            # ── avatar v40：数字人 video 作为 host root 直接子元素，同层渲染（方案 A，整体渲染）──
            # 数字人位置：横屏左侧竖条(left-rail)，竖屏角标(corner)。满幅→缩位动画第2步再加。
            from skills.hf_build_avatar.person_zone import person_zone as _pz
            _pl = "left-rail" if orientation == "landscape" else "corner"
            _zone = _pz(_pl, orientation)
            hero_dur = 5.0  # 保留（第2步满幅→缩位用）
            pos_name, pos_css = "avatar-rail", ""
            frame_name, frame_css = "minimal-line", PIP_FRAMES["minimal-line"]
            # 前景粒子层（z17，人物窗口之上）+ 环境呼吸 + 数字人呼吸（repeat 有限，符合 determinism 规则）
            import random as _rnd3
            # 🔴 粒子集中在数字人窗口附近（覆盖窗口 + 周围 30% 余量），明显从数字人前面飘过（"包装"关键）
            _pad_x = int(_zone["w"] * 0.3)
            _pad_y = int(_zone["h"] * 0.3)
            _fg = []
            for _i in range(30):
                _fs = _rnd3.choice([4, 5, 6, 7, 8])
                _px = max(0, _zone["x"] - _pad_x + _rnd3.randint(0, _zone["w"] + 2 * _pad_x))
                _py = max(0, _zone["y"] - _pad_y + _rnd3.randint(0, _zone["h"] + 2 * _pad_y))
                _fg.append(f'<span class="fg-p" style="left:{_px}px;top:{_py}px;width:{_fs}px;height:{_fs}px;"></span>')
            fg_particles_html = f'<div class="fg-particles" id="fg-particles">{"".join(_fg)}</div>'
            pip_motion = ''
            pip_motion += 'tl.fromTo("#env-vignette",{opacity:0.55},{opacity:1,duration:8,repeat:3,yoyo:true,ease:"sine.inOut"},0);'
            pip_motion += 'tl.fromTo("#env-scan",{left:"-45%"},{left:"110%",duration:12,repeat:3,ease:"none"},0);'
            pip_motion += 'tl.to(".fg-p",{y:"random(-200,-320)",duration:9,repeat:3,ease:"none",stagger:0.4},0);'
            # 🔴 满幅→缩位 transform 动画（在 LLM 复杂 sub-composition 下 HyperFrames 不生效，暂时回退固定位置）
            #    hf_debug 实验：简单场景满幅缩位生效，LLM 复杂场景不生效（根因待查，见 skill avatar-v40）
            pip_motion += 'tl.to("#avatar-video",{scale:1.005,duration:2.2,repeat:3,yoyo:true,ease:"sine.inOut"},0);'
            avatar_shadow_css = "#avatar-video{box-shadow:0 26px 52px rgba(0,0,0,0.6),0 10px 20px rgba(0,0,0,0.45);}"
            _aspect = "1" if orientation == "portrait" else "3/4"
            _init_size = 100  # 占位，avatar 用 person_zone 绝对像素定位
            _zr = _zone["w"] // 2 if orientation == "portrait" else 16
            # 🔴 数字人 video 是 host root 直接子元素（不包 div），框架才能 seek/解码
            pip_video_block = (
                f'<video id="avatar-video" class="clip" src="final.mp4" data-start="0" data-duration="{td_str}" data-track-index="0" muted playsinline '
                f'style="position:absolute;left:{_zone["x"]}px;top:{_zone["y"]}px;width:{_zone["w"]}px;height:{_zone["h"]}px;object-fit:cover;z-index:15;border-radius:{_zr}px;"></video>')
        else:
            # ── pip 原有：定时换位（垂直中部）──
            n_shifts = max(1, int(total_dur // shift_interval))
            # 🔴 循环使用位置（横屏 76s 有 9 次换位，不能只换 6 个位置就停——后半段窗口会一直不动）
            shuffled = random.sample(PIP_POSITIONS, len(PIP_POSITIONS))
            chosen = [shuffled[i % len(shuffled)] for i in range(n_shifts)]
            pos_name, pos_css = chosen[0]
            frame_name = random.choice(list(PIP_FRAMES.keys()))
            frame_css = PIP_FRAMES[frame_name]
            pip_motion_lines = []
            for i in range(1, len(chosen)):
                _name, _css = chosen[i]
                # _css = "left:75%;bottom:14%" → 解析成 left="75%" bottom="14%"
                _kv = {}
                for _pair in _css.split(";"):
                    if ":" in _pair:
                        _k, _v = _pair.split(":", 1)
                        _kv[_k.strip()] = _v.strip()
                _left = _kv.get("left", "3%")
                _bottom = _kv.get("bottom", "14%")
                _t = i * shift_interval
                if i % 3 == 0:
                    # 🔴 偶尔消失式换位：双属性滑出视口（消失 1s）→ 滑入新位置（出现）
                    pip_motion_lines.append(f'tl.to("#pip-win",{{left:"-32%",bottom:"-12%",duration:0.5,ease:"power1.in"}},{_t});')
                    pip_motion_lines.append(f'tl.to("#pip-win",{{left:"{_left}",bottom:"{_bottom}",duration:0.6,ease:"power2.out"}},{_t + 1.4});')
                else:
                    # 普通换位
                    pip_motion_lines.append(f'tl.to("#pip-win",{{left:"{_left}",bottom:"{_bottom}",duration:0.8,ease:"power2.inOut"}},{_t});')
            pip_motion = "".join(pip_motion_lines)
            _aspect = "1" if orientation == "portrait" else "3/4"
            _init_size = pip_size
            fg_particles_html = ""
            avatar_shadow_css = ""

        pip_css_block = PIP_CSS.replace("%%TD%%", td_str)
        main_style = f"body{{margin:0;background:{COLORS['bg_deep']}}}#root{{position:relative;width:{fw}px;height:{fh}px;overflow:hidden;background:{COLORS['bg_deep']}}}.bg-glow{{position:absolute;inset:0;z-index:4;pointer-events:none;background:radial-gradient(ellipse at 50% 40%,rgba(0,229,255,0.04),transparent 60%),radial-gradient(ellipse at 70% 70%,rgba(239,68,68,0.03),transparent 50%),radial-gradient(ellipse at 30% 60%,rgba(34,211,160,0.03),transparent 50%);}}.unified-timeline{{position:absolute;bottom:4px;left:2%;right:2%;height:2px;background:rgba(255,255,255,0.06);border-radius:1px;overflow:hidden;z-index:30;}}.unified-timeline-fill{{height:100%;background:linear-gradient(90deg,{COLORS['cyan']},{COLORS['purple']},#22d3a0);border-radius:1px;width:0%;}}.caption-word{{position:absolute;color:#fff;font-weight:600;text-shadow:0 2px 12px rgba(0,0,0,0.9);white-space:nowrap;z-index:20;transition:text-shadow 0.15s}}.caption-word.active{{text-shadow:0 0 20px rgba(0,229,255,0.8),0 2px 12px rgba(0,0,0,0.9);color:#fff}}.audio-pulse{{filter:brightness(calc(1 + var(--audio-level,0) * 0.3))}}.env-vignette{{position:absolute;inset:0;z-index:5;pointer-events:none;background:radial-gradient(ellipse at 50% 45%,transparent 52%,rgba(5,8,20,0.55) 100%);}}.env-scan{{position:absolute;top:-18%;bottom:-18%;width:38%;z-index:6;pointer-events:none;background:linear-gradient(105deg,transparent,rgba(140,165,255,0.07),transparent);mix-blend-mode:screen;transform:skewX(-12deg);}}.fg-particles{{position:absolute;inset:0;z-index:17;pointer-events:none;overflow:hidden;}}.fg-p{{position:absolute;border-radius:50%;background:rgba(185,155,255,0.85);box-shadow:0 0 12px rgba(165,140,255,0.95),0 0 4px rgba(200,180,255,0.9);}}"
        # 🔴 窗口比例：竖屏 1:1（圆框），横屏 3:4（竖向长方形框，高>宽）
        _aspect = "1" if orientation == "portrait" else "3/4"
        # 🔴 avatar 已在分支内生成 pip_video_block（video direct child），这里只给 pip 生成
        if not is_avatar:
            pip_video_block = f'<div id="pip-bg"></div><video id="pip-bg-v" src="final.mp4" data-start="0" data-duration="{td_str}" data-track-index="0" muted playsinline></video><div id="pip-win" style="{pos_css};width:{_init_size}%;aspect-ratio:{_aspect};--pip-radius:{radius};">'
            pip_video_block += f'<video id="pip-win-v" src="final.mp4" data-start="0" data-duration="{td_str}" data-track-index="1" muted playsinline></video>'
            pip_video_block += f'<div id="pip-frame" style="{frame_css}"></div></div>'
        print(f"      PIP mode: pos={pos_name} frame={frame_name}")
    else:
        pip_css_block = ""
        pip_video_block = f'<video id="src-v" src="final.mp4" data-start="0" data-duration="{td_str}" data-track-index="0" muted playsinline style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:1;"></video>'

    main_style += '"'
    # Load GSAP + Three.js locally (CDN inaccessible in headless browser)
    import pathlib
    _assets = pathlib.Path(__file__).resolve().parent.parent / "skills" / "hf_build_pip" / "assets"
    gsap_asset = _assets / "gsap.min.js"
    if gsap_asset.exists():
        gsap_js = gsap_asset.read_text(encoding="utf-8")
        gsap_tag = f'<script>{gsap_js}</script>'
        print("      GSAP embedded locally")
    else:
        gsap_tag = '<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>'
        print("      GSAP from CDN (may fail in headless)")
    index_html = '\n'.join(['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"/>',f'<meta name="viewport" content="width={fw},height={fh}"/>','<title>Edited Video</title>',gsap_tag,f'<style>{FONT_CSS}{pip_css_block}{main_style}{avatar_shadow_css}</style></head><body>',f'<div id="root" data-composition-id="main" data-start="0" data-layout="{layout_mode}" data-width="{fw}" data-height="{fh}" data-duration="{td_str}">',pip_video_block,f'<audio id="src-a" src="final.mp4" data-start="0" data-duration="{td_str}" data-track-index="10"></audio>','<div class="bg-glow"></div>',('<div class="env-vignette" id="env-vignette"></div><div class="env-scan" id="env-scan"></div>' if is_avatar else ''),fg_particles_html,host_block,'</div>','<div class="unified-timeline"><div class="unified-timeline-fill" id="main-timeline"></div></div>',f'<script>window.__timelines=window.__timelines||{{}};const tl=gsap.timeline({{paused:true}});tl.to("#main-timeline",{{width:"100%",duration:{td_str},ease:"linear"}},0);{pip_motion}window.__timelines["main"]=tl;</script>',THREEP_SCRIPT,AUDIO_SYNC_SCRIPT,'</body></html>'])
    (hf_dir / "index.html").write_text(index_html, encoding="utf-8")
    print("      HyperFrames project:", str(hf_dir / "index.html"))
    print("      Beats:", len(beat_files), "sub-compositions,", len(captions), "caption words")
    layouts_used = {}
    for idx, seg in enumerate(ranges):
        b = seg.get("beat", "INFO").upper()
        lname = "hook" if b in ("HOOK",) else "conflict" if b in ("CONFLICT","STRUGGLE","PROBLEM","TURN") else "resolution" if b in ("RESOLUTION","CLOSE") else "default"
        layouts_used[lname] = layouts_used.get(lname, 0) + 1
    print("      Layouts:", ", ".join(f"{k}x{v}" for k, v in sorted(layouts_used.items())))
    return hf_dir

def _build_captions(ranges, words, seg_offsets, orientation="portrait", video_width=None):
    captions = []
    if video_width is None: video_width = 1080 if orientation == "portrait" else 1920
    safe_width = video_width * 0.85
    for seg_idx, seg in enumerate(ranges):
        s, e = seg["start"], seg["end"]; offset = seg_offsets[seg_idx]
        seg_words = [w for w in words if w["start"] >= s - 0.1 and w["end"] <= e + 0.1]
        if not seg_words: continue
        phrase_text = ""; ps = pe = None
        for w in seg_words:
            ft = w["start"] - s + offset; fe = w["end"] - s + offset
            if ps is None: ps, pe, phrase_text = ft, fe, w["text"]
            elif ft - pe < 0.3: pe = fe; phrase_text += w["text"]
            else:
                dur = round(pe - ps + 0.1, 2)
                if dur >= 0.2: _make_caption(captions, ps, dur, phrase_text.strip(), safe_width, orientation)
                ps, pe, phrase_text = ft, fe, w["text"]
        if phrase_text:
            dur = round(pe - ps + 0.1, 2)
            if dur >= 0.2: _make_caption(captions, ps, dur, phrase_text.strip(), safe_width, orientation)
    return captions[:200]

def _make_caption(captions, start, dur, text, safe_width, orientation):
    max_font = 48 if orientation == "portrait" else 42
    bottom = 130 if orientation == "portrait" else 100

    # V23: 长句拆多条字幕，每条 ≤14 字单行
    if not text or not text.strip():
        return
    if len(text) <= 14:
        captions.append({"idx": len(captions), "start": round(start - 0.05, 2),
            "dur": max(0.4, dur), "text": text, "font_size": max_font, "bottom": bottom, "left_pct": 50})
        return

    # 在标点处拆，否则按字拆
    parts = []
    remaining = text
    while remaining:
        if len(remaining) <= 14:
            parts.append(remaining)
            break
        # 在第 7-14 字之间找标点
        cut = 14
        for i in range(min(14, len(remaining))-1, 6, -1):
            if remaining[i] in '，。、？！… ':
                cut = i + 1
                break
        else:
            # 没标点，在第 10-14 字间找空格
            cut = min(14, len(remaining))
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip('，。、？！… ')

    sub_dur = max(0.4, dur / len(parts))
    for pi, part in enumerate(parts):
        if not part: continue
        captions.append({"idx": len(captions), "start": round(start + sub_dur * pi - 0.05, 2),
            "dur": round(sub_dur, 2), "text": part, "font_size": max_font, "bottom": bottom, "left_pct": 50})

def render_hyperframes(hf_dir):
    from core.gpu import detect_gpu
    import re as _re
    npx_path = _find_npx()
    if not npx_path: return None
    hf_dir = Path(hf_dir).resolve()  # 🔴 绝对路径，否则 --output 相对 cwd 会错位（渲染到 standalone_NN 子目录）
    gpu = detect_gpu(); gpu_flag = "--gpu" if gpu["available"] else ""
    print("\n[8/8] Rendering HyperFrames composition (standalone per-beat) ..." + (" (GPU)" if gpu["available"] else ""))
    t0 = time.time()

    # 🔴 fullscreen（卡片 sub-composition）与 pip（全屏场景 standalone）渲染方式不同
    # fullscreen 的 beat-N.html 是 500x260 小卡片（叠加在背景视频上），standalone 会把卡片当全屏渲染→卡住
    # 必须整体渲染 index.html（背景视频+卡片 sub-composition）
    try:
        _idx_html = (hf_dir / "index.html").read_text(encoding="utf-8")
    except Exception:
        _idx_html = ""
    if "pip-win" not in _idx_html or 'data-layout="avatar"' in _idx_html:
        # 🔴 fullscreen（卡片 sub-comp 叠加背景视频）→ 整体渲染 index.html
        # 🔴 avatar v40（数字人 video direct child + 卡片 sub-comp + 前景粒子）→ 整体渲染 index.html
        #    （数字人作为 composition 里的 video 轨道，和卡片同层渲染，不再 ffmpeg 后期叠加）
        return _render_fullscreen(hf_dir, gpu_flag)

    # 🔴 照抄 video-factory：每个 beat 单独 standalone 渲染成 segment，再 concat 拼接
    comp_dir = hf_dir / "compositions"
    beat_htmls = sorted(comp_dir.glob("beat-*.html"), key=lambda p: int(p.stem.split("-")[1]))
    if not beat_htmls:
        print("      无 beat HTML")
        return None

    # 解析每个 beat 的 duration
    try:
        index_html = (hf_dir / "index.html").read_text(encoding="utf-8")
        dur_map = {}
        for m in _re.finditer(r'data-composition-id="(beat-\d+)"[^>]*?data-duration="([\d.]+)"', index_html):
            dur_map[m.group(1)] = float(m.group(2))
    except Exception:
        dur_map = {}

    temp_dir = hf_dir / "_render_segments"
    temp_dir.mkdir(exist_ok=True)
    segment_files = []

    for i, beat_html in enumerate(beat_htmls):
        bid = beat_html.stem
        duration = dur_map.get(bid, 5.0)
        standalone_dir = temp_dir / f"standalone_{i:02d}"
        standalone_dir.mkdir(exist_ok=True)
        shutil.copy2(str(beat_html), str(standalone_dir / "index.html"))
        # 🔴 beat-N.html 缺 data-duration → 注入正确时长（否则 HyperFrames 用默认 12.6s，渲染慢且时长错）
        try:
            _h = (standalone_dir / "index.html").read_text(encoding="utf-8")
            _h = _h.replace(f'data-composition-id="{bid}"', f'data-composition-id="{bid}" data-duration="{duration}"', 1)
            (standalone_dir / "index.html").write_text(_h, encoding="utf-8")
        except Exception:
            pass
        clip_path = (temp_dir / f"segment_{i:02d}.mp4").resolve()
        # 🔴 照抄 vf：shell=True + 直接 hyperframes 命令（.cmd 文件 shell=False 会静默失败）
        cmd = f'hyperframes render . --output "{clip_path}" --quality high --workers 1 {gpu_flag}'
        try:
            result = subprocess.run(cmd, shell=True, cwd=str(standalone_dir), capture_output=True, encoding="utf-8", errors="replace", timeout=900)
            if result.returncode == 0 and clip_path.exists():
                segment_files.append(clip_path)
                print(f"      [{i+1}/{len(beat_htmls)}] {bid} 渲染完成 ({duration:.1f}s)")
            else:
                print(f"      [{i+1}/{len(beat_htmls)}] {bid} 渲染失败 (rc={result.returncode})")
        except subprocess.TimeoutExpired:
            print(f"      [{i+1}/{len(beat_htmls)}] {bid} 渲染超时")
        except Exception as e:
            print(f"      [{i+1}/{len(beat_htmls)}] {bid} 渲染错误: {e}")

    if not segment_files:
        print("      无成功 segment")
        return None

    # concat 拼接
    concat_list = temp_dir / "concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for seg in segment_files:
            f.write(f"file '{seg}'\n")
    pol = hf_dir.parent / "final_polished.mp4"
    concat_cmd = f'ffmpeg -y -f concat -safe 0 -i "{concat_list}" -c copy "{pol}"'
    try:
        subprocess.run(concat_cmd, shell=True, capture_output=True, timeout=120)
        if pol.exists():
            elapsed = time.time() - t0
            mb = pol.stat().st_size / (1024 * 1024)
            print(f"      Rendered: {pol} ({mb:.0f} MB, {elapsed:.0f}s)")
            # 🔴 standalone 渲染只产出背景动画，PIP 小窗 + 字幕 + 音频需 ffmpeg 补上
            try:
                composed = _compose_pip(hf_dir, pol)
                if composed and Path(composed).exists():
                    return composed
            except Exception as e:
                print(f"      PIP 叠加错误: {e}")
            return pol
    except Exception as e:
        print(f"      concat 错误: {e}")
    print("      Using base final.mp4")
    return None


def _compose_pip(hf_dir, polished_path):
    """standalone 渲染只产出背景动画 concat，PIP 小窗 + 字幕 + 音频需 ffmpeg 补上。
    从 index.html 解析 PIP 换位序列 + 字幕，动态检测人物 crop，ffmpeg 叠加。
    返回最终成品路径（叠加后）。非 PIP 模式只补音频。"""
    import re as _re
    import numpy as _np
    import io as _io
    from PIL import Image as _Img
    hf_dir = Path(hf_dir).resolve()
    out_dir = hf_dir.parent
    final_mp4 = out_dir / "final.mp4"
    if not final_mp4.exists():
        print("      无 final.mp4，跳过叠加")
        return polished_path
    try:
        index_html = (hf_dir / "index.html").read_text(encoding="utf-8")
    except Exception:
        index_html = ""

    is_pip = 'pip-win' in index_html
    if not is_pip:
        # 非 PIP 模式：只补音频（背景动画 concat 无音轨）
        try:
            tmp = out_dir / "_with_audio.mp4"
            cmd = f'ffmpeg -y -i "{polished_path}" -i "{final_mp4}" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest "{tmp}"'
            r = subprocess.run(cmd, shell=True, capture_output=True, timeout=300)
            if r.returncode == 0 and tmp.exists():
                tmp.replace(polished_path)
                print("      音频已补")
        except Exception as e:
            print(f"      音频补齐失败: {e}")
        return polished_path

    # ── PIP/avatar 模式 ──
    is_avatar = 'data-layout="avatar"' in index_html
    # 1. 解析换位序列（GSAP tl.to）—— 宽松 regex，兼容 avatar 缩位动画里的 width 参数
    motions = []
    for m in _re.finditer(r'tl\.to\("#pip-win",\{left:"(-?[\d.]+)%",bottom:"(-?[\d.]+)%"[^}]*\},([\d.]+)\)', index_html):
        motions.append((float(m.group(3)), float(m.group(1)), float(m.group(2))))

    # 2. 解析字幕
    captions = []
    for m in _re.finditer(r'<div id="cap-\d+" class="clip caption-word" data-start="(-?[\d.]+)" data-duration="([\d.]+)" style="bottom:(\d+)px;left:([\d.]+)%;[^"]*font-size:(\d+)px[^"]*">(.*?)</div>', index_html):
        start = float(m.group(1)); dur = float(m.group(2))
        if start >= 0 and dur > 0:
            captions.append((start, dur, int(m.group(3)), float(m.group(4)), int(m.group(5)), m.group(6).strip()))

    # 3. 窗口尺寸（横屏 12%×1920=230，3:4→307；竖屏 22%×1080=238，1:1→238）
    try:
        vid_w, vid_h = int(_re.search(r'data-width="(\d+)" data-height="(\d+)"', index_html).group(1)), int(_re.search(r'data-width="(\d+)" data-height="(\d+)"', index_html).group(2))
    except Exception:
        vid_w, vid_h = 1920, 1080
    is_portrait = vid_h > vid_w
    win_w = int(vid_w * (0.22 if is_portrait else 0.12))
    win_h = win_w if is_portrait else int(win_w * 4 / 3)

    # avatar 满幅尺寸 + 时长（与 build 函数一致）
    hero_dur = 5.0
    hero_w = int(vid_w * (0.62 if is_portrait else 0.38))
    hero_h = hero_w if is_portrait else int(hero_w * 4 // 3)

    def to_xy(left_pct, bottom_pct):
        x = int(left_pct / 100 * vid_w)
        y = int(vid_h - (bottom_pct / 100 * vid_h) - win_h)
        return x, y

    # 4. 动态检测人物 crop（人脸检测优先 + 肤色检测兜底；fallback 按视频实际尺寸，clamp 不越界）
    def detect_person_crop(video, t=5, require_person=False, target_ratio=None):
        import cv2 as _cv2
        face_cascade = _cv2.CascadeClassifier(_cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        best = None
        best_face = None
        _W_ref, _H_ref = 1080, 1920
        for tt in [t, 3, 8, 10, 15, 20]:
            cmd = ['ffmpeg', '-ss', str(tt), '-i', str(video), '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-']
            try:
                data = subprocess.run(cmd, capture_output=True, timeout=30).stdout
                arr = _np.frombuffer(data, _np.uint8)
                frame_bgr = _cv2.imdecode(arr, _cv2.IMREAD_COLOR)
                img = _np.array(_Img.open(_io.BytesIO(data)).convert('RGB'), dtype=_np.float32)
            except Exception:
                continue
            H, W = frame_bgr.shape[:2]
            _W_ref, _H_ref = W, H
            # 🔴 视频自身方向（竖屏素材放横屏场景时，crop 必须按视频方向切，不能用场景方向）
            is_pv = H > W
            # ── 人脸检测（优先）：脸宽 > 画面宽 15% 才算真人/数字人，过滤头像/界面元素误检 ──
            gray = _cv2.cvtColor(frame_bgr, _cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
            valid_faces = [(x, y, w, h) for (x, y, w, h) in faces if w > W * 0.15]
            if valid_faces:
                x, y, w, h = max(valid_faces, key=lambda f: f[2] * f[3])
                if target_ratio is not None:
                    # 🔴 v39 按窗口比例 crop：ph 由脸高决定露半身，pw = ph * target_ratio，scale 不变形
                    ph = int(h * 3.2)
                    pw = int(ph * target_ratio)
                    # clamp 到视频尺寸（宽不超 W，高不超 H）
                    if pw > W: pw = W; ph = int(pw / target_ratio)
                    if ph > H: ph = H; pw = int(ph * target_ratio)
                else:
                    # 🔴 正常半身比例：crop 宽=画面宽90%(竖屏)/48%(横屏)，脸靠上(crop 33%)露更多身体
                    pw = int(W * (0.90 if is_pv else 0.48))
                    pw = max(200, min(pw, W))
                    ph = pw if is_pv else int(pw * 4 / 3)
                    # 🔴 横屏 clamp：3:4 竖向 crop 不能超画面高（否则 ffmpeg crop 越界报 Invalid argument）
                    if not is_pv and ph > H:
                        ph = H; pw = int(ph * 3 / 4)
                cx = x + w // 2; cy = y + h // 2
                crop_x = cx - pw // 2
                crop_y = cy - int(ph * 0.33)  # 脸中心在 crop 上 33% 处（脸靠上，露更多身体）
                crop_x = max(0, min(crop_x, W - pw)); crop_y = max(0, min(crop_y, H - ph))
                return pw, ph, crop_x, crop_y
            if faces:
                _bf = max(faces, key=lambda f: f[2] * f[3])
                if best_face is None or _bf[2] > best_face[2]:
                    best_face = _bf
            # ── 肤色检测兜底 ──
            R, G, B = img[:, :, 0], img[:, :, 1], img[:, :, 2]
            skin = (R > 100) & (R > G) & (G > B) & (R - B > 20) & (R - G > 12)
            col = skin.sum(axis=0); row = skin.sum(axis=1)
            dense_cols = _np.where(col > 40)[0]; dense_rows = _np.where(row > 25)[0]
            if len(dense_cols) >= 30 and len(dense_rows) >= 30:
                cx0, cx1 = dense_cols.min(), dense_cols.max()
                cy0, cy1 = dense_rows.min(), dense_rows.max()
                pw_ratio = (cx1 - cx0) / max(W, 1)
                ph_ratio = (cy1 - cy0) / max(H, 1)
                if require_person and (pw_ratio < 0.15 or ph_ratio < 0.08):
                    if best is None or len(dense_cols) > best[0]:
                        best = (len(dense_cols), W, H)
                    continue
                pw = min(max(cx1 - cx0 + 60, 200), 500)
                ph = pw if is_pv else int(pw * 4 / 3)
                cx = (cx0 + cx1) // 2
                y = max(0, cy0 - 40)
                x = cx - pw // 2
                pw = min(pw, W); ph = min(ph, H)
                x = max(0, min(x, W - pw)); y = max(0, min(y, H - ph))
                return pw, ph, x, y
            if best is None or len(dense_cols) > best[0]:
                best = (len(dense_cols), W, H)
        # 全部采样完成：人脸检测放宽阈值（脸宽 > 10%）再试一次
        if require_person:
            _is_pv = _H_ref > _W_ref  # 🔴 视频自身方向
            if best_face is not None and best_face[2] > _W_ref * 0.10:
                x, y, w, h = best_face
                pw = int(_W_ref * (0.90 if _is_pv else 0.48))
                pw = max(200, min(pw, _W_ref))
                ph = pw if _is_pv else int(pw * 4 / 3)
                # 🔴 横屏 clamp：3:4 竖向 crop 不能超画面高
                if not _is_pv and ph > _H_ref:
                    ph = _H_ref; pw = int(ph * 3 / 4)
                cx = x + w // 2; cy = y + h // 2
                crop_x = max(0, min(cx - pw // 2, _W_ref - pw))
                crop_y = max(0, min(cy - int(ph * 0.33), _H_ref - ph))
                return pw, ph, crop_x, crop_y
            return None
        # fallback：按视频实际尺寸中心 crop
        if best is not None:
            _, W, H = best
        else:
            W, H = 1080, 1920
        if H > W:  # 🔴 视频自身方向
            pw = ph = min(W, H)
        else:
            pw = min(W, H * 3 // 4); ph = min(H, pw * 4 // 3)
        x = (W - pw) // 2; y = (H - ph) // 2
        return pw, ph, x, y

    def detect_face_bbox(video, t=5):
        """检测人脸 bbox（素材像素系），返回 (x, y, w, h) 或 None。脸宽>10% 才算真人/数字人。"""
        import cv2 as _cv2
        face_cascade = _cv2.CascadeClassifier(_cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        for tt in [t, 3, 8, 10, 15]:
            cmd = ['ffmpeg', '-ss', str(tt), '-i', str(video), '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-']
            try:
                data = subprocess.run(cmd, capture_output=True, timeout=30).stdout
                frame_bgr = _cv2.imdecode(_np.frombuffer(data, _np.uint8), _cv2.IMREAD_COLOR)
            except Exception:
                continue
            H, W = frame_bgr.shape[:2]
            gray = _cv2.cvtColor(frame_bgr, _cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
            valid = [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces if w > W * 0.10]
            if valid:
                return max(valid, key=lambda f: f[2] * f[3])
        return None

    # 🔴 v39 同层排版：解析人物区（数字人叠加位置），从 compositions/beat-0.html 读 data-person-zone 属性
    # （index.html 只有 beat 占位 div，实际内容+占位框在 compositions/beat-N.html）
    person_layout = "corner"
    person_zw, person_zh = win_w, win_h
    person_zx = person_zy = None
    try:
        _beat0 = hf_dir / "compositions" / "beat-0.html"
        if _beat0.exists():
            _pz_html = _beat0.read_text(encoding="utf-8")
            _pzm = _re.search(r'data-person-zone="([\w-]+)"[^>]*data-person-x="(\d+)" data-person-y="(\d+)" data-person-w="(\d+)" data-person-h="(\d+)"', _pz_html)
            if _pzm:
                person_layout = _pzm.group(1)
                person_zx = int(_pzm.group(2)); person_zy = int(_pzm.group(3))
                person_zw = int(_pzm.group(4)); person_zh = int(_pzm.group(5))
    except Exception:
        pass
    person_ratio = person_zw / max(person_zh, 1)
    # hero 满幅 crop（4:3）+ pip crop（按人物区比例），让 crop 比例 = 窗口比例，scale 不变形
    hero_ratio = hero_w / max(hero_h, 1)
    hero_crop = detect_person_crop(final_mp4, require_person=is_avatar, target_ratio=hero_ratio)
    if person_layout in ("left-rail", "right-rail") and abs(person_ratio - hero_ratio) > 0.05:
        pip_crop = detect_person_crop(final_mp4, require_person=is_avatar, target_ratio=person_ratio)
    else:
        pip_crop = hero_crop
    _crop = hero_crop
    if _crop is None:
        # 无人物 → 降级纯 fullscreen：只补字幕+音频，不叠加人物窗口
        print("      无人物检测 → 降级纯 fullscreen（只补字幕+音频）")
        try:
            tmp = out_dir / "_no_person.mp4"
            cmd = f'ffmpeg -y -i "{polished_path}" -i "{final_mp4}" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest "{tmp}"'
            r = subprocess.run(cmd, shell=True, capture_output=True, timeout=300)
            if r.returncode == 0 and tmp.exists():
                tmp.replace(polished_path)
                print("      音频已补（无人物降级）")
        except Exception as e:
            print(f"      无人物降级失败: {e}")
        return polished_path
    pw, ph, px, py = hero_crop
    ppw, pph, ppx, ppy = pip_crop if pip_crop else hero_crop

    # 5. 换位表达式（从 index.html 解析的实际换位序列，mod 循环）
    init_left, init_bottom = 75.0, 58.0
    try:
        _ws = _re.search(r'id="pip-win" style="([^"]+)"', index_html)
        if _ws:
            _l = _re.search(r'left:(-?[\d.]+)%', _ws.group(1))
            _b = _re.search(r'bottom:(-?[\d.]+)%', _ws.group(1))
            if _l: init_left = float(_l.group(1))
            if _b: init_bottom = float(_b.group(1))
    except Exception:
        pass
    timeline = [(0.0, init_left, init_bottom)] + sorted(motions, key=lambda m: m[0])
    # 找周期：回到初始位置的时间点
    period = None
    for t, l, b in timeline[1:]:
        if t > 1 and abs(l - init_left) < 0.5 and abs(b - init_bottom) < 0.5:
            period = t
            break
    if period is None:
        period = max(timeline[-1][0] + 5.0, 30.0)

    def _build_axis_expr(axis):
        segs = []
        for i, (t, l, b) in enumerate(timeline):
            if t >= period:
                break
            x, y = to_xy(l, b)
            val = x if axis == 'x' else y
            t_end = timeline[i + 1][0] if i + 1 < len(timeline) else period
            segs.append((t_end, val))
        expr = str(segs[-1][1]) if segs else '0'
        for t_end, val in reversed(segs[:-1]):
            expr = f"if(lt(mod(t,{period}),{t_end}),{val},{expr})"
        return expr
    x_expr = _build_axis_expr('x')
    y_expr = _build_axis_expr('y')

    # 5.5 精确人脸安全区（avatar）：检测人脸 bbox，上扩60%+30px，映射画布，字幕避开
    if is_avatar:
        _face = detect_face_bbox(final_mp4)
        if _face is not None:
            fx, fy, fw, fh = _face
            # 满幅位置（bottom 22%，水平居中）
            _hx = (vid_w - hero_w) // 2
            _hy = max(0, int(vid_h - 0.22 * vid_h - hero_h))
            # 人脸在 crop 内相对位置 → 映射到画布
            rel_x = (fx - px) / max(pw, 1)
            rel_y = (fy - py) / max(ph, 1)
            face_cy = _hy + rel_y * hero_h
            face_ch = fh / max(ph, 1) * hero_h
            safe_bottom_y = face_cy + face_ch + 30  # 脸下沿 + 30px 余量
            _cap_bottom = 130
            _cap_font = 48
            cap_top_y = vid_h - _cap_bottom - _cap_font  # 字幕顶部 y
            if safe_bottom_y > cap_top_y:
                _shift = int(safe_bottom_y - cap_top_y) + 6
                captions = [(s, d, max(b, _cap_bottom + _shift), l, f, t) for (s, d, b, l, f, t) in captions]
                print(f"      🔴 人脸安全区：字幕下移 {_shift}px 避开人脸（脸底={safe_bottom_y:.0f} 字幕顶={cap_top_y:.0f}）")
            else:
                print(f"      ✅ 人脸安全区通过（脸底={safe_bottom_y:.0f} 字幕顶={cap_top_y:.0f} 不压脸）")

    # 6. ASS 字幕
    def _ass_time(sec):
        h = int(sec // 3600); m = int((sec % 3600) // 60); s = sec % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    ass_lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {vid_w}", f"PlayResY: {vid_h}",
                 "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
                 "[V4+ Styles]",
                 "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                 "Style: Default,Microsoft YaHei,42,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,2,0,0,100,1",
                 "", "[Events]",
                 "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for (start, dur, bottom, left_pct, font, text) in captions:
        end = start + dur
        x_pos = int(left_pct / 100 * vid_w)
        y_pos = vid_h - bottom - font
        text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        ass_lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{{\\pos({x_pos},{y_pos})\\an2\\bord2\\shad2}}{text}")
    ass_path = out_dir / "_captions.ass"
    ass_path.write_text("\n".join(ass_lines), encoding="utf-8")

    # 7. ffmpeg 叠加（圆角 + 边框，对齐 V12 人物窗口边缘）
    hero_crop_expr = f"crop={pw}:{ph}:{px}:{py}"
    pip_crop_expr = f"crop={ppw}:{pph}:{ppx}:{ppy}"

    # 圆角 alpha 表达式（geq，四角透明）：横屏 16px 圆角，竖屏圆形（50%）
    def _round_alpha(w, h, r):
        w1 = w - 1 - r
        h1 = h - 1 - r
        inner = '255'
        inner = f'if(gt(X,{w1})*gt(Y,{h1}),if(gt(hypot(X-{w1},Y-{h1}),{r}),0,255),{inner})'
        inner = f'if(lt(X,{r})*gt(Y,{h1}),if(gt(hypot({r}-X,Y-{h1}),{r}),0,255),{inner})'
        inner = f'if(gt(X,{w1})*lt(Y,{r}),if(gt(hypot(X-{w1},{r}-Y),{r}),0,255),{inner})'
        inner = f'if(lt(X,{r})*lt(Y,{r}),if(gt(hypot({r}-X,{r}-Y),{r}),0,255),{inner})'
        return inner

    if is_avatar:
        # ── avatar: 片头满幅(0-5s 居中) + pip(5s+ 换位/分栏) ──
        # 🔴 v39 同层排版：pip 窗口尺寸按 layout——corner 用 win_w/win_h，left/right rail 用人物区 person_zw/person_zh
        is_rail = person_layout in ("left-rail", "right-rail")
        pip_w = person_zw if is_rail else win_w
        pip_h = person_zh if is_rail else win_h
        r_hero = hero_w // 2 if is_portrait else 16
        r_pip = pip_w // 2 if is_portrait else 16
        hero_alpha = _round_alpha(hero_w, hero_h, r_hero)
        pip_alpha = _round_alpha(pip_w, pip_h, r_pip)
        # 满幅居中位置（bottom 22%）
        hero_x = (vid_w - hero_w) // 2
        hero_y = max(0, int(vid_h - 0.22 * vid_h - hero_h))
        # 角标换位 timeline（motions 已含缩位目标 + 后续换位）
        av_timeline = motions if motions else [(hero_dur, 3.0, 10.0)]
        av_period = max(av_timeline[-1][0] + 5.0, 30.0)

        def _av_axis(axis):
            segs = []
            for i, (t, l, b) in enumerate(av_timeline):
                x, y = to_xy(l, b)
                val = x if axis == 'x' else y
                t_end = av_timeline[i + 1][0] if i + 1 < len(av_timeline) else av_period
                segs.append((t_end, val))
            expr = str(segs[-1][1]) if segs else '0'
            for t_end, val in reversed(segs[:-1]):
                expr = f"if(lt(t,{t_end}),{val},{expr})"
            return expr
        av_x = _av_axis('x')
        av_y = _av_axis('y')

        # 稍加装饰：白色淡边框（跟随形状：竖屏圆 / 横屏圆角矩形），不套彩色发光环
        try:
            from PIL import Image as _ImgR, ImageDraw as _DrawR
            def _make_frame_png(w, h, r):
                _fp = _ImgR.new('RGBA', (w, h), (0, 0, 0, 0))
                _d = _DrawR.Draw(_fp)
                if r >= min(w, h) // 2:
                    # 竖屏圆形窗口 → 椭圆细边框
                    _d.ellipse([0, 0, w - 1, h - 1], outline=(255, 255, 255, 30), width=2)
                else:
                    # 横屏圆角矩形窗口 → 圆角矩形细边框
                    _d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, outline=(255, 255, 255, 30), width=2)
                return _fp
            frame_hero_path = out_dir / "_avatar_frame_hero.png"
            frame_pip_path = out_dir / "_avatar_frame_pip.png"
            _make_frame_png(hero_w, hero_h, hero_w // 2 if is_portrait else 16).save(str(frame_hero_path))
            _make_frame_png(pip_w, pip_h, pip_w // 2 if is_portrait else 16).save(str(frame_pip_path))
        except Exception:
            frame_hero_path = frame_pip_path = None

        # 🔴 video-talkcraft 让位过渡：hero 让位前 0.6s 变暗+模糊（前兆），pip 让位后 0.6s 从暗模糊恢复
        _hdr = hero_dur
        # 🔴 硬切：去掉让位变暗+模糊（用户反馈"开屏突然变灰"），直接切换不变暗
        hero_chain = f"[1:v]{hero_crop_expr},scale={hero_w}:{hero_h},setpts=PTS-STARTPTS,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{hero_alpha}'[heror]"
        pip_chain = f"[1:v]{pip_crop_expr},scale={pip_w}:{pip_h},setpts=PTS-STARTPTS,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{pip_alpha}'[pipr]"
        # 🔴 v39 pip 位置：left/right rail 固定坐标，corner 换位表达式
        if is_rail:
            pip_x_expr = str(person_zx)
            pip_y_expr = str(person_zy)
        else:
            pip_x_expr = f"'{av_x}'"
            pip_y_expr = f"'{av_y}'"
        if frame_hero_path and frame_pip_path:
            overlay_expr = (f"{hero_chain};{pip_chain};"
                            f"[0:v][heror]overlay=x={hero_x}:y={hero_y}:enable='lt(t,{hero_dur})'[v1];"
                            f"[v1][2:v]overlay=x={hero_x}:y={hero_y}:enable='lt(t,{hero_dur})'[v2];"
                            f"[v2][pipr]overlay=x={pip_x_expr}:y={pip_y_expr}:enable='gte(t,{hero_dur})'[v3];"
                            f"[v3][3:v]overlay=x={pip_x_expr}:y={pip_y_expr}:enable='gte(t,{hero_dur})':format=auto[vout]")
            inputs = ["ffmpeg", "-y", "-i", "final_polished.mp4", "-i", "final.mp4",
                      "-i", "_avatar_frame_hero.png", "-i", "_avatar_frame_pip.png"]
        else:
            overlay_expr = (f"{hero_chain};{pip_chain};"
                            f"[0:v][heror]overlay=x={hero_x}:y={hero_y}:enable='lt(t,{hero_dur})'[v1];"
                            f"[v1][pipr]overlay=x={pip_x_expr}:y={pip_y_expr}:enable='gte(t,{hero_dur})':format=auto[vout]")
            inputs = ["ffmpeg", "-y", "-i", "final_polished.mp4", "-i", "final.mp4"]
    else:
        # ── pip 原有：单 overlay（固定角标尺寸，换位）──
        r_round = win_w // 2 if is_portrait else 16
        round_alpha = _round_alpha(win_w, win_h, r_round)
        # 圆角边框 PNG（白色淡边框，对齐 V12：border 1.5px rgba(255,255,255,0.1)）
        frame_path = out_dir / "_pip_frame.png"
        try:
            from PIL import Image as _Img2, ImageDraw as _Draw2
            _fp = _Img2.new('RGBA', (win_w, win_h), (0, 0, 0, 0))
            _d = _Draw2.Draw(_fp)
            _d.rounded_rectangle([0, 0, win_w - 1, win_h - 1], radius=r_round, outline=(255, 255, 255, 26), width=2)
            _fp.save(str(frame_path))
        except Exception:
            frame_path = None

        pip_chain = f"[1:v]{hero_crop_expr},scale={win_w}:{win_h},setpts=PTS-STARTPTS,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{round_alpha}'[pipr]"
        if frame_path:
            overlay_expr = (f"{pip_chain};[0:v][pipr]overlay=x='{x_expr}':y='{y_expr}':format=auto[v1];"
                            f"[v1][2:v]overlay=x='{x_expr}':y='{y_expr}':format=auto[vout]")
            inputs = ["ffmpeg", "-y", "-i", "final_polished.mp4", "-i", "final.mp4", "-i", "_pip_frame.png"]
        else:
            overlay_expr = f"{pip_chain};[0:v][pipr]overlay=x='{x_expr}':y='{y_expr}':format=auto[vout]"
            inputs = ["ffmpeg", "-y", "-i", "final_polished.mp4", "-i", "final.mp4"]

    tmp_out = out_dir / "_composed.mp4"
    cmd = inputs + [
        "-filter_complex",
        overlay_expr + ";" + "[vout]ass=_captions.ass[vfinal]",
        "-map", "[vfinal]",
        "-map", "1:a",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "_composed.mp4",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, cwd=str(out_dir))
        if r.returncode == 0 and tmp_out.exists():
            tmp_out.replace(polished_path)
            print(f"      PIP 叠加完成: {polished_path}")
        else:
            print(f"      PIP 叠加失败 (rc={r.returncode})")
            if r.stderr:
                print(f"        {r.stderr[-300:]}")
    except Exception as e:
        print(f"      PIP 叠加错误: {e}")
    return polished_path


def _render_fullscreen(hf_dir, gpu_flag):
    """fullscreen 模式：整体渲染 index.html（背景视频 + 卡片 sub-composition）。"""
    t0 = time.time()
    try:
        # 动态超时：卡片越多渲染越久（22 卡 ≈ 4-5 分钟，241 卡 ≈ 45-60 分钟）
        _comp_dir = hf_dir / "compositions"
        _n_beats = len(list(_comp_dir.glob("beat-*.html"))) if _comp_dir.exists() else 1
        _timeout = max(900, _n_beats * 15)
        print(f"      渲染超时预算: {_timeout}s ({_n_beats} 张卡片)")
        cmd = f'hyperframes render --quality high {gpu_flag}'
        proc = subprocess.Popen(cmd, shell=True, cwd=str(hf_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate(timeout=_timeout)
        rd = hf_dir / "renders"
        if rd.exists():
            mp4s = sorted(rd.glob("*.mp4"), key=lambda q: q.stat().st_mtime, reverse=True)
            if mp4s:
                pol = hf_dir.parent / "final_polished.mp4"
                shutil.copy2(str(mp4s[0]), str(pol))
                mb = mp4s[0].stat().st_size / (1024 * 1024)
                print(f"      Rendered: {pol} ({mb:.0f} MB, {time.time()-t0:.0f}s)")
                return pol
        err_text = stderr.decode("utf-8", errors="replace") if stderr else ""
        if proc.returncode != 0:
            print(f"      整体渲染失败 (rc={proc.returncode})")
            if err_text:
                for line in err_text.strip().split("\n")[-6:]:
                    print(f"        {line}")
    except subprocess.TimeoutExpired:
        print("      整体渲染超时（卡片过多，渲染时间超预算）")
    except Exception as e:
        print(f"      整体渲染错误: {e}")
    return None

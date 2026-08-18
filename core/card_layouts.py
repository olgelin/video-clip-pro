import json, os, time, subprocess, shutil
from pathlib import Path
from core.card_constants import *
from core.card_decor import *

def _layout_hook(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, quote="", orientation="portrait"):
    is_v = orientation == "portrait"
    w_pct = 0.75 if is_v else 0.70
    cw = min(cw + 120, int(1920 * w_pct) if not is_v else 1050)
    h_sz = 62 if is_v else 52 if len(headline) <= 6 else 46 if len(headline) <= 10 else 38
    bg = BEAT_BG.get("HOOK", BEAT_BG["HOOK"])
    anim = EMOTION_ANIM.get(emotion, EMOTION_ANIM["neutral"])
    vk_ic = card_icon or _vk_icon(vk)
    vk_pat = _vk_bg(vk, tc)
    has_tech = any(k in vk.lower() for k in ["signal","network","connect","device","code","data","chip"])
    metric_val = metric if metric else ""
    pos_h = POSITION_MAP.get(scene_type, ("center","bottom",0.70))[0]
    ps = "left:50%;bottom:20px;transform:translateX(-50%)" if pos_h == "center" else "left:20px;bottom:20px"
    parts = []
    parts.append(f'<div data-composition-id="{beat_id}" data-width="{cw}" data-height="{ch}" style="width:{cw}px;height:auto;min-height:{ch}px;z-index:50;overflow:visible;background:{bg};backdrop-filter:blur(60px);-webkit-backdrop-filter:blur(60px);border-left:4px solid {tc};border-radius:0 20px 20px 0;--glow-color:{tc}44;animation:cardFloat 6s ease-in-out infinite,cardBreathe 4s ease-in-out infinite;box-shadow:0 20px 80px rgba(0,0,0,0.85),0 0 120px {tc}20;">')
    parts.append(_pulse_rings(tc, 100))
    parts.append(_corner_sparks(tc))
    parts.append(_orbit_dots(tc))
    if vk_pat:
        parts.append(f'<div style="position:absolute;inset:0;opacity:0.06;pointer-events:none;background:{vk_pat};background-size:40px 40px;border-radius:0 20px 20px 0;"></div>')
    parts.append(f'<div style="position:absolute;left:-4px;top:10%;bottom:10%;width:4px;background:{tc};border-radius:0 2px 2px 0;z-index:5;animation:borderGlow 2.5s ease-in-out infinite;--glow-color:{tc};"></div>')
    pad = 36 if is_v else 28
    parts.append(f'<div style="padding:{pad}px 40px 32px;">')
    parts.append(f'<div class="card-header" style="display:flex;align-items:center;gap:8px;margin-bottom:10px;"><span style="font-size:20px;animation:iconFloat 3s ease-in-out infinite,countUpPulse 2s ease-in-out infinite;">{vk_ic}</span><span style="color:{tc};font-size:13px;font-weight:600;letter-spacing:1px;animation:labelPulse 3s ease-in-out infinite;">{scene_type}</span></div>')
    parts.append(f'<div class="card-headline" style="font-size:{h_sz}px;font-weight:900;color:#ffffff;line-height:1.15;letter-spacing:-1px;text-shadow:0 0 80px {tc}44,0 8px 32px rgba(0,0,0,0.5);">{_wrap_chars(headline)}</div>')
    if subtext:
        parts.append(f'<div class="card-subtext" style="font-size:22px;font-weight:400;color:{COLORS["text_dim"]};line-height:1.4;margin-top:12px;max-width:90%;animation:subtitleSway 5s ease-in-out infinite 1s;">{_wrap_chars(subtext, "em")}</div>')
    parts.append(_signal_bars(tc, 50) if has_tech else _progress_bar(tc, 78))
    if metric_val:
        parts.append(f'<div style="margin-top:10px;display:flex;align-items:center;gap:12px;">{_count_up_badge(tc, metric_val, "core")}</div>')
    parts.append(_data_badges(data_points, tc, cw - 80))
    parts.append('</div></div>')
    html = "".join(parts)
    # subtext stagger handled by CSS animation-delay
    # dp-badge animation handled by CSS .dp-badge rule
    return html

def _layout_conflict(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, quote="", orientation="portrait"):
    is_v = orientation == "portrait"
    cw = min(cw + 50, 580)
    h_sz = 42 if is_v else 36 if len(headline) <= 6 else 34 if len(headline) <= 10 else 28
    bg = BEAT_BG.get("CONFLICT", BEAT_BG["CONFLICT"])
    anim = EMOTION_ANIM.get(emotion, EMOTION_ANIM["tense"])
    vk_ic = card_icon or _vk_icon(vk)
    vk_pat = _vk_bg(vk, tc)
    alert_a = "alertFlash 1.5s ease-in-out infinite" if emotion in ("urgent","tense") else "cardBreathe 3.5s ease-in-out infinite"
    has_barrier = any(k in vk.lower() for k in ["block","barrier","broken","error"])
    parts = []
    card_pos_con = "right:10px;top:50%;transform:translateY(-50%)" if not is_v else "right:10px;bottom:30px;transform:none"
    parts.append(f'<div data-composition-id="{beat_id}" data-width="{cw}" data-height="{ch}" style="width:{cw}px;height:auto;min-height:{ch}px;z-index:50;overflow:visible;background:{bg};backdrop-filter:blur(50px);-webkit-backdrop-filter:blur(50px);border-right:4px solid {tc};border-radius:20px 0 0 20px;--glow-color:{tc}33;animation:cardFloat 4s ease-in-out infinite,{alert_a};box-shadow:0 16px 60px rgba(0,0,0,0.8),0 0 80px {tc}15;">')
    parts.append(_pulse_rings(tc, 60))
    parts.append(_corner_sparks(tc, "20px 0 0 20px"))
    parts.append(_orbit_dots(tc, 100))
    if vk_pat:
        parts.append(f'<div style="position:absolute;inset:0;opacity:0.06;pointer-events:none;background:{vk_pat};background-size:30px 30px;border-radius:20px 0 0 20px;"></div>')
    parts.append(f'<div style="position:absolute;right:-4px;top:10%;bottom:10%;width:4px;background:{tc};border-radius:2px 0 0 2px;z-index:5;animation:borderGlow 2s ease-in-out infinite;--glow-color:{tc};"></div>')
    parts.append(f'<div style="padding:28px 32px 24px;">')
    parts.append(f'<div class="card-header" style="display:flex;align-items:center;gap:6px;margin-bottom:10px;color:{tc};font-size:13px;font-weight:700;letter-spacing:2px;animation:labelPulse 3s ease-in-out infinite;">{vk_ic} {beat_name}</div>')
    parts.append(f'<div class="card-headline" style="font-size:{h_sz}px;font-weight:800;color:#ffffff;line-height:1.2;text-shadow:0 0 60px {tc}33,0 4px 16px rgba(0,0,0,0.4);">{_wrap_chars(headline)}</div>')
    parts.append(f'<div style="margin-top:10px;height:4px;background:{tc}22;border-radius:2px;overflow:hidden;"><div style="height:100%;width:72%;background:linear-gradient(90deg,{tc},#ef4444);border-radius:2px;box-shadow:0 0 12px {tc}55;animation:accentBar 2s ease-in-out infinite;"></div></div>')
    if has_barrier: parts.append(_barrier_indicator(tc))
    if subtext: parts.append(f'<div class="card-subtext" style="font-size:18px;color:{COLORS["text_dim"]};line-height:1.4;margin-top:10px;animation:subtitleSway 5s ease-in-out infinite 1s;">{_wrap_chars(subtext, "em")}</div>')
    parts.append(_data_badges(data_points, tc, cw - 60))
    parts.append('</div></div>')
    html = "".join(parts)
    # dp-badge animation handled by CSS .dp-badge rule
    return html

def _layout_resolution(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, quote="", orientation="portrait"):
    is_v = orientation == "portrait"
    w_pct = 0.70 if is_v else 0.65
    cw = min(cw + 100, int(1920 * w_pct) if not is_v else 1050)
    h_sz = 46 if is_v else 40 if len(headline) <= 6 else 36 if len(headline) <= 10 else 30
    bg = BEAT_BG.get("RESOLUTION", BEAT_BG["RESOLUTION"])
    anim = EMOTION_ANIM.get(emotion, EMOTION_ANIM["hopeful"])
    vk_ic = card_icon or _vk_icon(vk)
    vk_pat = _vk_bg(vk, "#22d3a0")
    parts = []
    # Position: landscape = center-center, portrait = center-bottom
    card_pos = "left:50%;top:50%;transform:translate(-50%,-50%)" if not is_v else "left:50%;bottom:20px;transform:translateX(-50%)"
    parts.append(f'<div data-composition-id="{beat_id}" data-width="{cw}" data-height="{ch}" style="width:{cw}px;height:auto;min-height:{ch}px;z-index:50;overflow:visible;background:{bg};backdrop-filter:blur(60px);-webkit-backdrop-filter:blur(60px);border-left:4px solid #22d3a0;border-radius:0 24px 24px 0;--glow-color:rgba(34,211,160,0.3);animation:cardFloat 7s ease-in-out infinite,cardBreathe 5s ease-in-out infinite;box-shadow:0 20px 80px rgba(0,0,0,0.85),0 0 100px rgba(34,211,160,0.2);">')
    parts.append(_corner_sparks("#22d3a0", "0 24px 24px 0"))
    parts.append(_orbit_dots("#22d3a0", 160))
    if vk_pat: parts.append(f'<div style="position:absolute;inset:0;opacity:0.06;pointer-events:none;background:{vk_pat};background-size:40px 40px;border-radius:0 24px 24px 0;"></div>')
    parts.append(f'<div style="position:absolute;left:-4px;top:10%;bottom:10%;width:4px;background:#22d3a0;border-radius:0 2px 2px 0;z-index:5;animation:borderGlow 3s ease-in-out infinite;--glow-color:#22d3a0;"></div>')
    pad = 36 if is_v else 28
    parts.append(f'<div style="padding:{pad}px 40px 32px;">')
    parts.append(f'<div class="card-header" style="display:flex;align-items:center;gap:8px;margin-bottom:10px;"><span style="font-size:20px;animation:iconFloat 3s ease-in-out infinite,countUpPulse 2s ease-in-out infinite;">{vk_ic}</span><span style="color:#22d3a0;font-weight:700;font-size:14px;letter-spacing:1px;animation:labelPulse 3s ease-in-out infinite;">{beat_name}</span></div>')
    parts.append(f'<div class="card-headline" style="font-size:{h_sz}px;font-weight:900;color:#ffffff;line-height:1.15;letter-spacing:-1px;text-shadow:0 0 60px rgba(34,211,160,0.3),0 4px 20px rgba(0,0,0,0.5);">{_wrap_chars(headline)}</div>')
    if subtext: parts.append(f'<div class="card-subtext" style="font-size:20px;font-weight:400;color:{COLORS["text_dim"]};line-height:1.4;margin-top:10px;max-width:90%;animation:subtitleSway 5s ease-in-out infinite 1s;">{_wrap_chars(subtext, "em")}</div>')
    parts.append(_check_grid("#22d3a0", 3))
    parts.append(_progress_bar("#22d3a0", 85))
    parts.append(_data_badges(data_points, "#22d3a0", cw - 80))
    parts.append('</div></div>')
    html = "".join(parts)
    return html

def _layout_default(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, quote="", orientation="portrait"):
    """PPT-style default card: header bar + headline + tag pills + divider + subtext + bottom bar"""
    is_v = orientation == "portrait"
    cw = min(cw + 40, 580)
    h_sz = 38 if is_v else 34 if len(headline) <= 6 else 30 if len(headline) <= 10 else 26
    sub_sz = 18 if is_v else 16
    anim = EMOTION_ANIM.get(emotion, EMOTION_ANIM["neutral"])
    vk_ic = card_icon or _vk_icon(vk)
    vk_pat = _vk_bg(vk, tc)
    tag_pills = data_points[:3] if data_points else []
    parts = []
    # ── Card shell with PPT accent bar at top ──
    # Position: landscape = left-center, portrait = left-bottom
    card_pos = "left:20px;top:50%;transform:translateY(-50%)" if not is_v else "left:20px;bottom:30px"
    parts.append(f'<div data-composition-id="{beat_id}" data-width="{cw}" data-height="{ch}" style="width:{cw}px;height:auto;min-height:{ch}px;z-index:50;overflow:visible;background:{DEFAULT_BG};backdrop-filter:blur(50px);-webkit-backdrop-filter:blur(50px);border-radius:0 16px 16px 0;--glow-color:{tc}22;animation:cardFloat 8s ease-in-out infinite,cardBreathe 6s ease-in-out infinite;box-shadow:0 12px 50px rgba(0,0,0,0.7);">')
    # PPT accent strip at top-left
    parts.append(f'<div style="position:absolute;top:0;left:0;right:0;height:5px;background:linear-gradient(90deg,{tc},transparent 80%);border-radius:0 0 16px 0;animation:accentBar 3s ease-in-out infinite;z-index:2;"></div>')
    # Corner sparks
    parts.append(_corner_sparks(tc, "0 16px 16px 0"))
    # Background pattern
    if vk_pat: parts.append(f'<div style="position:absolute;inset:0;opacity:0.06;pointer-events:none;background:{vk_pat};background-size:30px 30px;border-radius:0 16px 16px 0;z-index:0;"></div>')
    # Left border accent glow
    parts.append(f'<div style="position:absolute;left:-3px;top:15%;bottom:15%;width:3px;background:{tc};border-radius:0 2px 2px 0;z-index:5;animation:borderGlow 4s ease-in-out infinite;--glow-color:{tc};"></div>')
    # ── Content ──
    parts.append(f'<div style="padding:28px 28px 24px;position:relative;z-index:1;">')
    # Row 1: scene label + icon
    parts.append(f'<div class="card-header" style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">')
    parts.append(f'<span style="display:inline-block;width:24px;height:24px;background:{tc}22;border-radius:6px;text-align:center;line-height:24px;font-size:14px;animation:iconFloat 3s ease-in-out infinite;">{vk_ic}</span>')
    parts.append(f'<span style="color:{tc};font-size:12px;font-weight:700;letter-spacing:2px;animation:labelPulse 4s ease-in-out infinite;">{beat_name}</span>')
    parts.append(f'</div>')
    # Row 2: headline (large, bold)
    parts.append(f'<div class="card-headline" style="font-size:{h_sz}px;font-weight:900;color:#ffffff;line-height:1.2;letter-spacing:-0.5px;text-shadow:0 0 40px {tc}22,0 3px 12px rgba(0,0,0,0.5);">{_wrap_chars(headline)}</div>')
    # Row 3: tag pills from data_points (if any)
    if tag_pills:
        parts.append(f'<div class="card-badges" style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;">')
        for i, dp in enumerate(tag_pills):
            label = dp.get("label","") or dp.get("value","")
            val = dp.get("value","") if dp.get("label") else ""
            text = f"{label}: {val}" if val else label
            delay = 0.1 + i * 0.12
            parts.append(f'<span style="display:inline-block;padding:2px 10px;background:{tc}15;border:1px solid {tc}33;border-radius:20px;color:{tc};font-size:12px;font-weight:600;animation:badgePop 0.4s ease-out both;animation-delay:{delay}s;">{text}</span>')
        parts.append(f'</div>')
    # Row 4: subtle divider (if both headline and subtext exist)
    if subtext:
        parts.append(f'<div style="margin-top:12px;height:1px;background:linear-gradient(90deg,{tc}44,transparent 70%);border-radius:1px;animation:accentBar 2.5s ease-in-out infinite;"></div>')
        parts.append(f'<div class="card-subtext" style="font-size:{sub_sz}px;color:{COLORS["text_dim"]};line-height:1.5;margin-top:8px;animation:subtitleSway 5s ease-in-out infinite 1s;">{_wrap_chars(subtext, "em")}</div>')
    # Row 5: metric badge (if metric exists)
    if metric:
        parts.append(f'<div class="card-metric" style="margin-top:10px;display:flex;align-items:center;gap:8px;">')
        parts.append(f'<span style="font-size:20px;font-weight:900;color:{tc};animation:countUpPulse 2s ease-in-out infinite;">{metric}</span>')
        parts.append(f'<span style="font-size:12px;color:{COLORS["text_dim"]};">↑ 关键指标</span>')
        parts.append(f'</div>')
    # Bottom mini progress bar
    parts.append(f'<div style="margin-top:14px;height:2px;background:{tc}15;border-radius:1px;overflow:hidden;"><div class="card-bar" style="height:100%;width:60%;background:{tc}55;border-radius:1px;box-shadow:0 0 6px {tc}33;animation:barFill 2s ease-out both;"></div></div>')
    parts.append('</div></div>')
    html = "".join(parts)
    return html

# ── v7 PPT-style layouts ──

def _layout_quote_card(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, bullets=None, takeaway="", vstyle="editorial", quote="", orientation="portrait"):
    """PPT quote card: large quotation marks + speaker attribution + decorative line"""
    is_v = orientation == "portrait"
    cw = min(cw + 60, 600)
    q_sz = 36 if is_v else 32 if len(headline) <= 8 else 28
    anim = EMOTION_ANIM.get(emotion, EMOTION_ANIM["neutral"])
    vk_ic = card_icon or _vk_icon(vk)
    vk_pat = _vk_bg(vk, tc)
    parts = []
    # Position: landscape = left-center, portrait = left-bottom
    card_pos = "left:20px;top:50%;transform:translateY(-50%)" if not is_v else "left:20px;bottom:30px"
    parts.append(f'<div data-composition-id="{beat_id}" data-width="{cw}" data-height="{ch}" style="width:{cw}px;height:auto;min-height:{ch}px;z-index:50;overflow:visible;background:{DEFAULT_BG};backdrop-filter:blur(50px);-webkit-backdrop-filter:blur(50px);border-left:3px solid {tc};border-radius:0 16px 16px 0;--glow-color:{tc}22;animation:cardFloat 8s ease-in-out infinite,cardBreathe 6s ease-in-out infinite;box-shadow:0 12px 50px rgba(0,0,0,0.7);">')
    # Large quotation mark background
    parts.append(f'<div style="position:absolute;top:10px;left:14px;font-size:72px;color:{tc}18;font-family:Georgia,serif;line-height:1;pointer-events:none;z-index:0;">"</div>')
    parts.append(_corner_sparks(tc, "0 16px 16px 0"))
    if vk_pat: parts.append(f'<div style="position:absolute;inset:0;opacity:0.06;pointer-events:none;background:{vk_pat};background-size:30px 30px;border-radius:0 16px 16px 0;z-index:0;"></div>')
    parts.append(f'<div style="position:absolute;left:-3px;top:15%;bottom:15%;width:3px;background:{tc};border-radius:0 2px 2px 0;z-index:5;animation:borderGlow 4s ease-in-out infinite;--glow-color:{tc};"></div>')
    parts.append(f'<div style="padding:32px 32px 28px;position:relative;z-index:1;">')
    # Quote text
    parts.append(f'<div class="card-headline" style="font-size:{q_sz}px;font-weight:700;color:#ffffff;line-height:1.3;font-style:italic;font-family:CJK,Georgia,serif;text-shadow:0 0 40px {tc}22,0 3px 12px rgba(0,0,0,0.5);">{_wrap_chars(headline)}</div>')
    # Decorative line
    parts.append(f'<div style="margin-top:14px;height:2px;background:linear-gradient(90deg,{tc},transparent 60%);border-radius:1px;"></div>')
    # Attribution
    if subtext: parts.append(f'<div style="font-size:15px;color:{COLORS["text_dim"]};margin-top:8px;letter-spacing:1px;animation:subtitleSway 5s ease-in-out infinite 1s;">—— {subtext}</div>')
    if takeaway: parts.append(f'<div style="font-size:13px;color:{tc};margin-top:6px;font-weight:600;">{takeaway}</div>')
    parts.append('</div></div>')
    html = "".join(parts)
    return html

def _layout_bullets(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, bullets=None, takeaway="", vstyle="tech", quote="", orientation="portrait"):
    """PPT bullet-points card: headline + icon-bullet list + bottom takeaway"""
    is_v = orientation == "portrait"
    cw = min(cw + 60, 620)
    h_sz = 34 if is_v else 30 if len(headline) <= 8 else 26
    anim = EMOTION_ANIM.get(emotion, EMOTION_ANIM["neutral"])
    vk_ic = card_icon or _vk_icon(vk)
    vk_pat = _vk_bg(vk, tc)
    bullets = bullets or []
    # PPT accent colors
    accent_bg = BEAT_BG.get(beat_name.upper(), DEFAULT_BG) if beat_name.upper() in BEAT_BG else DEFAULT_BG
    parts = []
    card_pos_bul = "left:20px;top:50%;transform:translateY(-50%)" if not is_v else "left:10px;bottom:30px;transform:none"
    parts.append(f'<div data-composition-id="{beat_id}" data-width="{cw}" data-height="{ch}" style="width:{cw}px;height:auto;min-height:{ch}px;z-index:50;overflow:visible;background:{accent_bg};backdrop-filter:blur(40px);-webkit-backdrop-filter:blur(40px);border-left:4px solid {tc};border-radius:0 18px 18px 0;--glow-color:{tc}33;animation:cardFloat 6s ease-in-out infinite;box-shadow:0 16px 60px rgba(0,0,0,0.8),0 0 80px {tc}15;">')
    parts.append(_corner_sparks(tc, "0 18px 18px 0"))
    if vk_pat: parts.append(f'<div style="position:absolute;inset:0;opacity:0.06;pointer-events:none;background:{vk_pat};background-size:30px 30px;border-radius:0 18px 18px 0;"></div>')
    parts.append(f'<div style="position:absolute;left:-4px;top:10%;bottom:10%;width:4px;background:{tc};border-radius:0 2px 2px 0;z-index:5;animation:borderGlow 2.5s ease-in-out infinite;--glow-color:{tc};"></div>')
    parts.append(f'<div style="padding:24px 32px 24px;">')
    # Header with icon + scene type
    parts.append(f'<div class="card-header" style="display:flex;align-items:center;gap:8px;margin-bottom:12px;"><span style="font-size:18px;animation:iconFloat 3s ease-in-out infinite;">{vk_ic}</span><span style="color:{tc};font-size:12px;font-weight:700;letter-spacing:2px;animation:labelPulse 3s ease-in-out infinite;">{beat_name}</span></div>')
    # Headline
    parts.append(f'<div class="card-headline" style="font-size:{h_sz}px;font-weight:900;color:#ffffff;line-height:1.2;margin-bottom:14px;text-shadow:0 0 40px {tc}33;">{_wrap_chars(headline)}</div>')
    # Bullet points
    if bullets:
        parts.append(f'<div class="bullets-{beat_id}" style="display:flex;flex-direction:column;gap:10px;margin-bottom:12px;">')
        for j, bp in enumerate(bullets[:4]):
            delay = 0.3 + j * 0.15
            parts.append(f'<div class="bp-item" style="display:flex;align-items:flex-start;gap:10px;animation:stackRise 0.4s power3.out {delay}s both;"><span style="flex-shrink:0;width:6px;height:6px;border-radius:50%;background:{tc};margin-top:6px;box-shadow:0 0 8px {tc}66;"></span><span style="font-size:15px;color:rgba(226,232,240,0.85);line-height:1.4;font-weight:500;">{bp[:25]}</span></div>')
        parts.append('</div>')
    # Subtext if no bullets
    elif subtext:
        parts.append(f'<div class="card-subtext" style="font-size:16px;color:{COLORS["text_dim"]};line-height:1.4;margin-bottom:12px;animation:subtitleSway 5s ease-in-out infinite 1s;">{_wrap_chars(subtext, "em")}</div>')
    # Data badges
    if data_points: parts.append(_data_badges(data_points, tc, cw - 64))
    # Bottom takeaway
    if takeaway:
        parts.append(f'<div style="margin-top:12px;padding:10px 16px;background:rgba(8,16,28,0.8);border-left:3px solid {tc};border-radius:0 6px 6px 0;font-size:13px;color:{tc};font-weight:600;line-height:1.4;animation:badgePop 0.5s ease-out 0.8s both;">💡 {takeaway}</div>')
    parts.append('</div></div>')
    html = "".join(parts)
    return html

def _layout_big_number(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, bullets=None, takeaway="", vstyle="tech", quote="", orientation="portrait"):
    """Big number impact card: massive metric + small label"""
    is_v = orientation == "portrait"
    cw = min(cw + 40, 480)
    anim = EMOTION_ANIM.get(emotion, EMOTION_ANIM["triumphant"])
    vk_ic = card_icon or _vk_icon(vk)
    vk_pat = _vk_bg(vk, tc)
    metric_val = metric or "—"
    metric_sz = 72 if len(str(metric_val)) <= 4 else 56 if len(str(metric_val)) <= 6 else 42
    parts = []
    card_pos_bn = "right:10px;top:50%;transform:translateY(-50%)" if not is_v else "right:10px;bottom:30px;transform:none"
    parts.append(f'<div data-composition-id="{beat_id}" data-width="{cw}" data-height="{ch}" style="width:{cw}px;height:auto;min-height:{ch}px;z-index:50;overflow:visible;background:linear-gradient(135deg,{tc}22,rgba(3,5,14,0.96));backdrop-filter:blur(40px);-webkit-backdrop-filter:blur(40px);border:1px solid {tc}33;border-radius:20px;--glow-color:{tc}44;animation:cardFloat 5s ease-in-out infinite;box-shadow:0 20px 80px rgba(0,0,0,0.85),0 0 100px {tc}18;">')
    parts.append(_pulse_rings(tc, 90))
    if vk_pat: parts.append(f'<div style="position:absolute;inset:0;opacity:0.06;pointer-events:none;background:{vk_pat};background-size:30px 30px;border-radius:20px;"></div>')
    parts.append(f'<div style="position:absolute;top:10px;right:14px;width:5px;height:5px;background:{tc};border-radius:50%;animation:cornerSpark 2.5s ease-in-out infinite 0s;box-shadow:0 0 10px {tc}88;"></div>')
    parts.append(f'<div style="position:absolute;bottom:10px;left:14px;width:5px;height:5px;background:{tc};border-radius:50%;animation:cornerSpark 2.5s ease-in-out infinite 0.7s;box-shadow:0 0 10px {tc}88;"></div>')
    parts.append(f'<div style="padding:32px 36px;text-align:center;">')
    # Small label top
    parts.append(f'<div class="card-header" style="font-size:13px;color:{tc};font-weight:700;letter-spacing:2px;margin-bottom:8px;animation:labelPulse 3s ease-in-out infinite;">{vk_ic} {headline[:12]}</div>')
    # BIG NUMBER
    parts.append(f'<div class="card-metric" style="font-size:{metric_sz}px;font-weight:900;color:{tc};line-height:1;font-family:JetBrains Mono,Inter,sans-serif;text-shadow:0 0 60px {tc}55,0 4px 30px rgba(0,0,0,0.5);animation:countUpPulse 2s ease-in-out infinite;">{metric_val}</div>')
    # Label below
    if subtext:
        parts.append(f'<div style="font-size:16px;color:{COLORS["text_dim"]};margin-top:10px;font-weight:500;animation:subtitleSway 5s ease-in-out infinite 1s;">{subtext[:30]}</div>')
    # Small data badges
    if data_points: parts.append(_data_badges(data_points, tc, cw - 72))
    if takeaway:
        parts.append(f'<div style="margin-top:14px;font-size:12px;color:{tc}99;font-weight:600;">{takeaway}</div>')
    parts.append('</div></div>')
    html = "".join(parts)
    return html

def _layout_comparison(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, bullets=None, takeaway="", vstyle="tech", quote="", orientation="portrait"):
    """Comparison card: left vs right, before vs after"""
    is_v = orientation == "portrait"
    cw = min(cw + 80, 680)
    h_sz = 30 if is_v else 26
    anim = EMOTION_ANIM.get(emotion, EMOTION_ANIM["neutral"])
    vk_ic = card_icon or _vk_icon(vk)
    vk_pat = _vk_bg(vk, tc)
    bullets = bullets or []
    parts = []
    # Position: landscape = center-center, portrait = center-bottom
    card_pos = "left:50%;top:50%;transform:translate(-50%,-50%)" if not is_v else "left:50%;bottom:20px;transform:translateX(-50%)"
    parts.append(f'<div data-composition-id="{beat_id}" data-width="{cw}" data-height="{ch}" style="width:{cw}px;height:auto;min-height:{ch}px;z-index:50;overflow:visible;background:{DEFAULT_BG};backdrop-filter:blur(50px);-webkit-backdrop-filter:blur(50px);border-left:4px solid {tc};border-radius:0 20px 20px 0;--glow-color:{tc}33;animation:cardFloat 6s ease-in-out infinite;box-shadow:0 16px 60px rgba(0,0,0,0.85),0 0 80px {tc}15;">')
    if vk_pat: parts.append(f'<div style="position:absolute;inset:0;opacity:0.06;pointer-events:none;background:{vk_pat};background-size:30px 30px;border-radius:0 20px 20px 0;"></div>')
    parts.append(f'<div style="padding:24px 36px 24px;">')
    parts.append(f'<div class="card-header" style="display:flex;align-items:center;gap:8px;margin-bottom:10px;"><span style="font-size:18px;animation:iconFloat 3s ease-in-out infinite;">{vk_ic}</span><span style="color:{tc};font-size:13px;font-weight:700;letter-spacing:2px;animation:labelPulse 3s ease-in-out infinite;">{headline[:16]}</span></div>')
    # Comparison rows: two items side by side
    if len(bullets) >= 2:
        a, b = bullets[0], bullets[1]
        parts.append(f'<div style="display:flex;gap:12px;margin-bottom:10px;">')
        parts.append(f'<div style="flex:1;background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.25);border-radius:10px;padding:14px 16px;text-align:center;"><div style="font-size:11px;color:#ef4444;font-weight:700;margin-bottom:4px;">❌ 过去</div><div style="font-size:16px;color:#fca5a5;font-weight:600;line-height:1.3;">{a[:20]}</div></div>')
# Close comparison row
        tc2 = "#22d3a0"
        parts.append(f'<div style="flex:1;background:rgba(34,211,160,0.12);border:1px solid rgba(34,211,160,0.25);border-radius:10px;padding:14px 16px;text-align:center;"><div style="font-size:11px;color:{tc2};font-weight:700;margin-bottom:4px;">✅ 现在</div><div style="font-size:16px;color:#86efac;font-weight:600;line-height:1.3;">{b[:20]}</div></div>')
        parts.append('</div>')
    elif subtext:
        parts.append(f'<div class="card-subtext" style="font-size:18px;color:{COLORS["text_dim"]};line-height:1.4;margin-bottom:10px;animation:subtitleSway 5s ease-in-out infinite 1s;">{_wrap_chars(subtext, "em")}</div>')
    if metric:
        parts.append(f'<div class="card-metric" style="text-align:center;margin:8px 0;"><span style="font-size:32px;font-weight:900;color:{tc};font-family:JetBrains Mono,monospace;animation:countUpPulse 2s ease-in-out infinite;">{metric}</span><span style="font-size:14px;color:{COLORS["text_dim"]};margin-left:6px;">{takeaway[:20]}</span></div>')
    if data_points: parts.append(_data_badges(data_points, tc, cw - 72))
    parts.append('</div></div>')
    html = "".join(parts)
    return html

SCENE_LAYOUTS = {"spotlight":"HOOK","alert":"CONFLICT","struggle":"CONFLICT","breakthrough":"RESOLUTION","process":"RESOLUTION","context":"DEFAULT"}
LAYOUTS = {"HOOK":_layout_hook,"CONFLICT":_layout_conflict,"STRUGGLE":_layout_conflict,"PROBLEM":_layout_conflict,"TURN":_layout_conflict,"RESOLUTION":_layout_resolution,"CLOSE":_layout_resolution}

def _smart_fill(headline, subtext, metric, data_points, layout_hint, bullets, beat_name="", quote=""):
    """Post-process enrichment: fill gaps even when LLM output is thin."""
    import re
    dp = list(data_points) if data_points else []
    bl = list(bullets) if bullets else []
    m = metric
    lh = layout_hint
    hl = headline

    # 0. Headline repair — critical for card quality
    SCENE_LABELS = {'HOOK','CONTEXT','PROBLEM','STRUGGLE','RESOLUTION','CLOSE','TURN','INFO','开场','结尾','解决','挣扎',''}
    is_scene_label = beat_name.strip() in SCENE_LABELS
    is_empty = not hl or len(hl.strip()) < 2
    is_subtitle_like = len(hl) > 15 and not ('：' in hl or '？' in hl or '！' in hl)  # raw speech with only commas

    if is_empty:
        if not is_scene_label and beat_name and len(beat_name) > 2:
            hl = beat_name
            lh = 'title-only'
        elif quote:
            hl = quote.strip()[:18]
        elif subtext:
            hl = subtext.strip()[:18]
    elif is_subtitle_like:
        hl = hl[:18].rstrip('，,的在了是和') or hl[:18]

    # 1. Extract numbers from headline for metric
    if not m:
        nums = re.findall(r'(\d+[\d%倍万千亿xX\+\.]*)\s*(个|人|倍|%|万|亿|千)?', hl)
        if nums:
            m = nums[0][0] + (nums[0][1] if nums[0][1] else '')

    # 2. Extract numbers as data_points
    if not dp:
        nums = re.findall(r'(\d+[\d%倍万千亿xX\+\.]*)', hl)
        for n in nums[:3]:
            dp.append({"label": "关键数据", "value": n})

    # 3. Detect comparison patterns → upgrade to comparison
    compare_words = ['vs','VS','以前','现在','过去','如今','之前','之后','但是','但','却','反而','不是','而是']
    has_compare = any(w in hl for w in compare_words)
    if has_compare and lh == 'title-only':
        lh = 'comparison'
        if not bl:
            bl = ['过去：传统方式', '现在：全新模式']

    # 4. If headline has bullet-able structure, suggest bullets
    if lh == 'title-only' and ('：' in hl or '；' in hl):
        parts = re.split(r'[：；]', hl)
        if len(parts) >= 2 and len(parts[1].strip()) >= 3:
            lh = 'bullets'
            bl = [p.strip()[:15] for p in parts[1:3] if p.strip()]

    # 5. Force at least one data_point if still empty
    if not dp:
        dp = [{"label": "核心", "value": hl[:12]}]

    return hl, m, dp, lh, bl
# ── Three.js 卡片背景（可选，默认关闭）──

def _threejs_card_bg(tc="#00e5ff"):
    """极简 Three.js 3D 背景：旋转发光环，颜色跟随卡片主题色。
    通过 seg["card_threejs"] = True 启用，每条卡片独立控制。"""
    hex_color = int(tc.lstrip("#"), 16)
    hex_emissive = hex_color // 2
    return """<canvas id="card3d" style="position:absolute;inset:0;z-index:0;pointer-events:none;opacity:0.7;"></canvas>
<script type="importmap">
{ "imports": { "three": "https://cdn.jsdelivr.net/npm/three@0.181.2/build/three.module.js" } }
</script>
<script type="module">
import * as THREE from "three";
const c=document.getElementById("card3d"), r=new THREE.WebGLRenderer({canvas:c,alpha:true});
r.setSize(1920,1080,false); r.setPixelRatio(1);
const s=new THREE.Scene(), cam=new THREE.PerspectiveCamera(40,1920/1080,0.1,20);
cam.position.set(0,0,8);
const ring=new THREE.Mesh(new THREE.TorusGeometry(3.5,0.06,16,100),new THREE.MeshStandardMaterial({color:0x""" + f"{hex_color:06x}" + """,roughness:0.1,metalness:0.6,emissive:0x""" + f"{hex_emissive:06x}" + """,emissiveIntensity:0.8,transparent:true,opacity:0.6}));
s.add(ring);
function renderAt(t){ring.rotation.y=t*0.25;ring.rotation.x=Math.sin(t*0.35)*0.12;r.render(s,cam);}
window.addEventListener("hf-seek",e=>renderAt(e.detail.time));
renderAt(window.__hfThreeTime||0);
</script>"""

def _build_card(beat_id, beat, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, quote="", orientation="portrait", layout_hint="title-only", bullets=None, takeaway="", vstyle="tech"):
    # Headline safeguard: never show raw subtitle or empty text as main headline
    SCENE_LABELS_SAFE = {'HOOK','CONTEXT','PROBLEM','STRUGGLE','RESOLUTION','CLOSE','TURN','INFO','开场','结尾','解决','挣扎',''}
    if not headline or len(headline.strip()) < 2 or (len(headline.strip()) <= 3 and headline.strip().replace('%','').isdigit()):
        if beat_name and beat_name.strip() not in SCENE_LABELS_SAFE:
            headline = beat_name
        elif subtext and len(subtext.strip()) >= 2:
            headline = subtext[:18]
    elif len(headline) > 15 and '：' not in headline and '？' not in headline:
        if beat_name and beat_name.strip() not in SCENE_LABELS_SAFE and len(beat_name) < len(headline):
            headline = beat_name
        else:
            headline = headline[:18]
    # Route by layout_hint first, fall back to scene_type
    if layout_hint == "bullets" and bullets:
        return _layout_bullets(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, bullets, takeaway, vstyle, quote, orientation)
    if layout_hint == "big-number" and metric:
        return _layout_big_number(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, bullets, takeaway, vstyle, quote, orientation)
    if layout_hint == "comparison":
        return _layout_comparison(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, bullets, takeaway, vstyle, quote, orientation)
    if layout_hint == "quote-card":
        return _layout_quote_card(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, bullets, takeaway, vstyle, quote, orientation)
    # Fallback: route by scene_type
    layout_beat = SCENE_LAYOUTS.get(scene_type, beat.upper())
    builder = LAYOUTS.get(layout_beat, _layout_default)
    return builder(beat_id, tc, beat_name, icon, headline, subtext, metric, emotion, scene_type, vk, data_points, card_icon, cw, ch, quote, orientation)

__all__ = ['LAYOUTS', 'SCENE_LAYOUTS', '_build_card', '_layout_big_number', '_layout_bullets', '_layout_comparison', '_layout_conflict', '_layout_default', '_layout_hook', '_layout_quote_card', '_layout_resolution', '_smart_fill', '_threejs_card_bg']

import json, os, time, subprocess, shutil
from pathlib import Path
from core.card_constants import *

def _wrap_chars(text, tag="span"):
    if not text: return ""
    return "".join(f'<{tag} class="char">{c}</{tag}>' for c in text)

# _stagger_script removed — element reveals now handled by CSS animation-delay in CARD_DECOR_CSS

def _pulse_rings(tc, size=80):
    rings = []
    for i in range(3):
        rings.append(f'<div class="pulse-ring" style="position:absolute;top:50%;left:50%;width:{size}px;height:{size}px;margin-left:-{size//2}px;margin-top:-{size//2}px;border:2px solid {tc}44;border-radius:50%;pointer-events:none;animation:pulseRing {2+i*0.8}s ease-out infinite {i*0.6}s;"></div>')
    return "".join(rings)

def _signal_bars(tc, height=60):
    return f'<div style="display:flex;align-items:flex-end;gap:6px;height:{height}px;margin-top:8px;"><div style="width:8px;background:{tc};border-radius:2px;animation:signalBar1 1.5s ease-in-out infinite;"></div><div style="width:8px;background:{tc}99;border-radius:2px;animation:signalBar2 1.5s ease-in-out infinite 0.15s;"></div><div style="width:8px;background:{tc}77;border-radius:2px;animation:signalBar3 1.5s ease-in-out infinite 0.3s;"></div><div style="width:8px;background:{tc}55;border-radius:2px;animation:signalBar1 1.5s ease-in-out infinite 0.45s;"></div></div>'

def _check_grid(tc, steps=3):
    items = []; labels = ["识别","分析","解决","验证"][:steps]
    for i in range(steps):
        items.append(f'<div class="check-item" style="display:flex;align-items:center;gap:8px;"><span style="width:20px;height:20px;border-radius:50%;background:{tc};display:inline-flex;align-items:center;justify-content:center;font-size:11px;color:#000;font-weight:bold;animation:checkPop 0.5s ease-out {0.3+i*0.2}s both;">&#10003;</span><span style="font-size:14px;color:#ddd;font-weight:600;">{labels[i]}</span></div>')
    return f'<div style="display:flex;gap:16px;margin-top:10px;">' + "".join(items) + '</div>'

def _data_badges(data_points, tc, width):
    if not data_points: return ""
    badges = []
    for i, dp in enumerate(data_points[:3]):
        label = dp.get("label","")[:6]; value = dp.get("value","-")[:10]
        badges.append(f'<div class="dp-badge" style="flex:1;background:rgba(8,16,28,0.92);border:1px solid rgba(255,255,255,0.07);border-radius:6px;padding:8px 12px;text-align:center;box-shadow:0 3px 16px rgba(0,0,0,0.4);animation:borderShimmer 3.5s ease-in-out infinite {i*0.4}s,badgeGlow 2s ease-in-out infinite {i*0.6}s;--glow-color:{tc}22;"><div style="font-size:10px;color:#888;font-weight:600;margin-bottom:3px;">{label}</div><div style="font-size:16px;font-weight:800;color:{tc};font-family:JetBrains Mono,monospace;animation:countUpPulse 2s ease-in-out infinite {i*0.3}s;">{value}</div></div>')
    return f'<div style="display:flex;gap:8px;margin-top:10px;width:{width}px;">' + "".join(badges) + '</div>'

def _progress_bar(tc, pct=72):
    return f'<div style="margin-top:8px;height:4px;background:rgba(255,255,255,0.06);border-radius:2px;overflow:hidden;position:relative;"><div style="height:100%;--bar-pct:{pct}%;background:linear-gradient(90deg,{tc},transparent);border-radius:2px;box-shadow:0 0 8px {tc}44;animation:barFill 1.5s ease-out forwards;"></div><div style="position:absolute;top:0;height:100%;width:30%;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.18),transparent);border-radius:2px;animation:barShimmer 2.5s linear infinite 1.8s;pointer-events:none;\"></div></div>'

def _barrier_indicator(tc):
    return f'<div style="display:flex;align-items:center;gap:8px;margin-top:6px;animation:barrierCrack 2s ease-in-out infinite;"><div style="flex:1;height:3px;background:{tc}33;border-radius:1px;"></div><span style="font-size:12px;color:{tc};font-weight:700;">&#8856;</span><div style="flex:1;height:3px;background:{tc}33;border-radius:1px;"></div></div>'

def _corner_sparks(tc, radius="0 20px 20px 0"):
    return f'<div class="corner-spark" style="position:absolute;top:10px;right:14px;width:5px;height:5px;background:{tc};border-radius:50%;pointer-events:none;z-index:3;animation:cornerSpark 2.5s ease-in-out infinite 0s;box-shadow:0 0 10px {tc}88;"></div><div class="corner-spark" style="position:absolute;bottom:10px;left:14px;width:5px;height:5px;background:{tc};border-radius:50%;pointer-events:none;z-index:3;animation:cornerSpark 2.5s ease-in-out infinite 0.7s;box-shadow:0 0 10px {tc}88;"></div>'

def _orbit_dots(tc, radius=140):
    return f'<div style="position:absolute;top:50%;left:50%;width:0;height:0;pointer-events:none;z-index:2;"><div style="position:absolute;width:4px;height:4px;background:{tc}66;border-radius:50%;animation:dotOrbit 8s linear infinite;box-shadow:0 0 8px {tc}44;"></div><div style="position:absolute;width:3px;height:3px;background:{tc}44;border-radius:50%;animation:dotOrbit2 10s linear infinite;box-shadow:0 0 6px {tc}33;"></div></div>'

def _count_up_badge(tc, value, label=""):
    inner = f'<div style="font-size:22px;font-weight:800;color:{tc};font-family:JetBrains Mono,monospace;animation:countUpPulse 2s ease-in-out infinite;">{value}</div>'
    if label: inner += f'<div style="font-size:10px;color:#888;font-weight:600;margin-top:2px;">{label}</div>'
    return f'<div style="display:inline-block;background:rgba(8,16,28,0.92);border:1px solid {tc}33;border-radius:6px;padding:8px 16px;text-align:center;animation:countUpRoll 0.6s ease-out forwards,badgePop 0.5s ease-out 0.6s both;">{inner}</div>'

# vk patterns
VK_PATTERNS = {"signal":"\u2b21","network":"\u2b21","connect":"\u2b21","device":"\u25a3","broken":"\u2715","error":"\u2715","block":"\u2298","barrier":"\u2298","fire":"\u25c6","crack":"\u25c6","fix":"\u2713","repair":"\u2713","unlock":"\u25ce","key":"\u25ce","light":"\u25ce","path":"\u2192","bridge":"\u2192","fear":"!","cost":"$","heavy":"\u2b07","rise":"\u2b06","break":"\u26a1","free":"\u26a1","steps":"\u2460","arrow":"\u2192","check":"\u2713","target":"\u25ce","build":"\u25a3","evolve":"\u2197","spotlight":"\u2605","compare":"\u21c4","numbers":"#","time":"\u25f7"}

def _vk_icon(vk_str):
    if not vk_str: return "\u25c6"
    for kw in vk_str.lower().replace(" ","").split(","):
        for pat, ic in VK_PATTERNS.items():
            if pat in kw: return ic
    return "\u25c6"

VK_BG_PATTERNS = {"signal":"repeating-radial-gradient(circle at 50% 50%,{tc}08 0,{tc}08 2px,transparent 2px,transparent 20px)","network":"repeating-radial-gradient(circle at 50% 50%,{tc}08 0,{tc}08 2px,transparent 2px,transparent 20px)","connect":"linear-gradient(90deg,{tc}06 1px,transparent 1px),linear-gradient(0deg,{tc}06 1px,transparent 1px)","broken":"repeating-linear-gradient(45deg,transparent,transparent 8px,{tc}08 8px,{tc}08 10px)","error":"repeating-linear-gradient(45deg,transparent,transparent 8px,{tc}08 8px,{tc}08 10px)","block":"linear-gradient(0deg,{tc}15 2px,transparent 2px),linear-gradient(90deg,{tc}15 2px,transparent 2px)","barrier":"linear-gradient(0deg,{tc}15 2px,transparent 2px),linear-gradient(90deg,{tc}15 2px,transparent 2px)","fix":"repeating-linear-gradient(0deg,transparent,transparent 6px,{tc}05 6px,{tc}05 8px)","repair":"repeating-linear-gradient(0deg,transparent,transparent 6px,{tc}05 6px,{tc}05 8px)","unlock":"radial-gradient(circle at 70% 30%,{tc}10 0,transparent 50%)","cost":"repeating-linear-gradient(0deg,transparent,transparent 4px,{tc}06 4px,{tc}06 6px)","rise":"linear-gradient(180deg,{tc}08 0,transparent 60%)","steps":"repeating-linear-gradient(90deg,transparent,transparent 12px,{tc}05 12px,{tc}05 14px)","numbers":"repeating-linear-gradient(0deg,transparent,transparent 8px,{tc}04 8px,{tc}04 10px)","spotlight":"radial-gradient(ellipse at 50% 0%,{tc}12 0,transparent 60%)"}

def _vk_bg(vk_str, tc):
    if not vk_str: return ""
    for kw in vk_str.lower().replace(" ","").split(","):
        for pat, bg in VK_BG_PATTERNS.items():
            if pat in kw: return bg.replace("{tc}", tc)
    return ""

EMOTION_ANIM = {"urgent":{"entrance":"slamRight","entrance_dur":0.35,"stagger":0.06,"ease":"power4.out"},"tense":{"entrance":"slamRight","entrance_dur":0.45,"stagger":0.08,"ease":"power3.out"},"neutral":{"entrance":"stackRise","entrance_dur":0.5,"stagger":0.12,"ease":"power3.out"},"hopeful":{"entrance":"unfoldDown","entrance_dur":0.55,"stagger":0.15,"ease":"power3.out"},"triumphant":{"entrance":"celebrateBounce","entrance_dur":0.6,"stagger":0.18,"ease":"elastic.out(1,0.6)"}}

POSITION_MAP = {"spotlight":("center","bottom",0.70),"alert":("right","center",0.30),"struggle":("right","center",0.28),"breakthrough":("center","bottom",0.65),"process":("left","bottom",0.35),"context":("left","bottom",0.28)}


BEAT_BG = {"HOOK":"linear-gradient(135deg,rgba(0,229,255,0.25),rgba(2,8,24,0.96))","CONFLICT":"linear-gradient(135deg,rgba(239,68,68,0.28),rgba(8,2,4,0.96))","STRUGGLE":"linear-gradient(135deg,rgba(168,85,247,0.28),rgba(6,3,16,0.96))","PROBLEM":"linear-gradient(135deg,rgba(239,68,68,0.25),rgba(8,2,4,0.96))","TURN":"linear-gradient(135deg,rgba(245,158,11,0.26),rgba(8,6,2,0.96))","RESOLUTION":"linear-gradient(135deg,rgba(34,211,160,0.28),rgba(2,10,6,0.96))","CLOSE":"linear-gradient(135deg,rgba(34,211,160,0.24),rgba(2,8,6,0.96))"}
DEFAULT_BG = "linear-gradient(135deg,rgba(5,8,18,0.96),rgba(3,5,14,0.94))"

def _mk_style(props):
    """Build inline style string from dict."""
    return ";".join(f"{k}:{v}" for k,v in props.items())

__all__ = ['BEAT_BG', 'DEFAULT_BG', 'EMOTION_ANIM', 'POSITION_MAP', 'VK_BG_PATTERNS', 'VK_PATTERNS', '_barrier_indicator', '_check_grid', '_corner_sparks', '_count_up_badge', '_data_badges', '_mk_style', '_orbit_dots', '_progress_bar', '_pulse_rings', '_signal_bars', '_vk_bg', '_vk_icon', '_wrap_chars']

import json, os, time, subprocess, shutil
from pathlib import Path

# hf_card_builder.py v5 — content-aware card system
# HTML uses single-quoted attributes to avoid Python string escaping issues


COLORS = {
    "bg_deep": "#060911", "bg_card": "rgba(8,16,32,0.94)", "cyan": "#00e5ff",
    "magenta": "#ff2d7b", "purple": "#a78bfa", "text": "#f1f5f9",
    "text_dim": "rgba(226,232,240,0.6)", "border": "rgba(0,229,255,0.18)",
}
TAG_COLORS = {
    "HOOK": "#00e5ff", "SETUP": "#38bdf8", "CONFLICT": "#ff2d7b",
    "STRUGGLE": "#a78bfa", "TURN": "#f59e0b", "PROBLEM": "#ef4444",
    "RESOLUTION": "#22d3a0", "CLOSE": "#38bdf8", "INFO": "#60a5fa",
}
BEAT_LABELS = {
    "HOOK": "开场", "SETUP": "铺垫", "CONFLICT": "冲突", "STRUGGLE": "挣扎",
    "TURN": "转折", "PROBLEM": "问题", "RESOLUTION": "解决", "CLOSE": "收尾", "INFO": "信息",
}
BEAT_ICONS = {
    "HOOK": "\u26a1", "SETUP": "\U0001f4cb", "CONFLICT": "\u2694", "STRUGGLE": "\U0001f4aa",
    "TURN": "\U0001f504", "PROBLEM": "\u26a0", "RESOLUTION": "\u2705", "CLOSE": "\U0001f3af", "INFO": "\U0001f4a1",
}
FONT_CSS = "@font-face{font-family:CJK;src:local('Microsoft YaHei'),local('PingFang SC'),local('Noto Sans SC')}"

# Animation presets per beat type
ANIMATION_PRESETS = {
    "HOOK": {"entrance": {"type": "scaleBounce", "duration": 0.7, "ease": "elastic.out(1,0.6)"}, "micro": {"type": "float", "amplitude": 6, "period": 3}, "exit": {"type": "fadeSlideUp", "duration": 0.5, "ease": "power3.in"}},
    "CONFLICT": {"entrance": {"type": "fadeSlideRight", "duration": 0.55, "ease": "power4.out"}, "micro": {"type": "glowPulse", "period": 2}, "exit": {"type": "shakeOut", "duration": 0.45, "ease": "power2.in"}},
    "STRUGGLE": {"entrance": {"type": "dropBounce", "duration": 0.6, "ease": "bounce.out"}, "micro": {"type": "float", "amplitude": 4, "period": 4}, "exit": {"type": "fadeSlideDown", "duration": 0.4, "ease": "power3.in"}},
    "PROBLEM": {"entrance": {"type": "fadeSlideRight", "duration": 0.5, "ease": "power3.out"}, "micro": {"type": "pulse", "scale": 1.02, "period": 2.5}, "exit": {"type": "shakeOut", "duration": 0.45, "ease": "power2.in"}},
    "TURN": {"entrance": {"type": "scaleFade", "duration": 0.5, "ease": "back.out(1.4)"}, "micro": {"type": "glowPulse", "period": 2.5}, "exit": {"type": "fadeSlideUp", "duration": 0.4, "ease": "power2.in"}},
    "RESOLUTION": {"entrance": {"type": "scaleBounce", "duration": 0.65, "ease": "elastic.out(1,0.5)"}, "micro": {"type": "breathe", "period": 3}, "exit": {"type": "scaleOut", "duration": 0.5, "ease": "power3.in"}},
    "CLOSE": {"entrance": {"type": "scaleFade", "duration": 0.55, "ease": "power3.out"}, "micro": {"type": "float", "amplitude": 5, "period": 3.5}, "exit": {"type": "fadeOut", "duration": 0.6, "ease": "power2.in"}},
}
DEFAULT_ANIM = {"entrance": {"type": "fadeSlideUp", "duration": 0.5, "ease": "power3.out"}, "micro": {"type": "float", "amplitude": 3, "period": 4}, "exit": {"type": "fadeSlideUp", "duration": 0.4, "ease": "power2.in"}}

MICRO_CSS = """
@keyframes floatAnim{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
@keyframes pulseAnim{0%,100%{transform:scale(1)}50%{transform:scale(1.15)}}
@keyframes glowPulseAnim{0%,100%{box-shadow:0 0 20px var(--glow-color, rgba(0,229,255,0.1))}50%{box-shadow:0 0 40px var(--glow-color, rgba(0,229,255,0.25))}}
@keyframes breatheAnim{0%,100%{opacity:0.6}50%{opacity:1}}
@keyframes lightSweep{0%{transform:translateX(-100%)}100%{transform:translateX(400%)}}
@keyframes borderShimmer{0%,100%{border-color:rgba(255,255,255,0.08)}50%{border-color:rgba(255,255,255,0.18)}}
"""

CARD_DECOR_CSS = """
@keyframes cornerPulse{0%,100%{opacity:0.3;transform:scale(1)}50%{opacity:0.8;transform:scale(1.15)}}
@keyframes dotOrbit{0%{transform:rotate(0deg) translateX(140px) rotate(0deg)}100%{transform:rotate(360deg) translateX(140px) rotate(-360deg)}}
@keyframes dotOrbit2{0%{transform:rotate(120deg) translateX(120px) rotate(-120deg)}100%{transform:rotate(480deg) translateX(120px) rotate(-480deg)}}
@keyframes dotOrbit3{0%{transform:rotate(240deg) translateX(160px) rotate(-240deg)}100%{transform:rotate(600deg) translateX(160px) rotate(-600deg)}}
@keyframes gradientShift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
@keyframes ringPulse{0%,100%{box-shadow:0 0 20px var(--ring-color, rgba(0,229,255,0.1)),0 0 60px var(--ring-color, rgba(0,229,255,0.05))}50%{box-shadow:0 0 35px var(--ring-color, rgba(0,229,255,0.2)),0 0 80px var(--ring-color, rgba(0,229,255,0.1))}}
@keyframes accentBar{0%,100%{height:30%}50%{height:70%}}
@keyframes shimmerText{0%,100%{background-position:-200% center}100%{background-position:200% center}}
@keyframes borderGlow{0%,100%{box-shadow:0 0 8px var(--glow-color)}50%{box-shadow:0 0 25px var(--glow-color),0 0 40px var(--glow-color)}}
@keyframes cardBreathe{0%,100%{box-shadow:0 20px 80px rgba(0,0,0,0.8),0 0 100px var(--glow-color)}50%{box-shadow:0 20px 80px rgba(0,0,0,0.8),0 0 150px var(--glow-color),0 0 200px var(--glow-color)}}
@keyframes pulseRing{0%{transform:scale(0.6);opacity:0.8}100%{transform:scale(1.8);opacity:0}}
@keyframes signalBar1{0%,100%{height:20%}50%{height:100%}}
@keyframes signalBar2{0%,100%{height:45%}50%{height:80%}}
@keyframes signalBar3{0%,100%{height:70%}50%{height:55%}}
@keyframes checkPop{0%{transform:scale(0)}60%{transform:scale(1.2);opacity:1}100%{transform:scale(1);opacity:1}}
@keyframes progressFill{0%{width:0%}100%{width:var(--progress-pct, 85%)}}
@keyframes countUpPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.15)}}
@keyframes alertFlash{0%,100%{background:rgba(239,68,68,0.15)}50%{background:rgba(239,68,68,0.35)}}
@keyframes greenWave{0%{width:0%;opacity:1}50%{width:100%}100%{width:100%}}
@keyframes arrowSlide{0%{transform:translateX(-100%)}100%{transform:translateX(0);opacity:1}}
@keyframes countUpRoll{0%{opacity:0;transform:translateY(20px)}100%{opacity:1;transform:translateY(0)}}
@keyframes barFill{0%{width:0%}100%{width:var(--bar-pct,75%)}}
@keyframes barrierCrack{0%,100%{opacity:0.3;transform:scaleX(1)}50%{opacity:0.8;transform:scaleX(1.05)}}
@keyframes badgePop{0%{transform:scale(0) rotate(-10deg)}60%{transform:scale(1.2) rotate(3deg)}100%{transform:scale(1) rotate(0)}}
@keyframes stackRise{0%{opacity:0;transform:translateY(30px)}100%{opacity:1;transform:translateY(0)}}
@keyframes slamRight{0%{opacity:0;transform:translateX(-80px) scale(1.1)}100%{opacity:1;transform:translateX(0) scale(1)}}
@keyframes unfoldDown{0%{opacity:0;transform:scaleY(0);transform-origin:top}100%{opacity:1;transform:scaleY(1)}}
@keyframes celebrateBounce{0%{opacity:0;transform:scale(0.3)}50%{transform:scale(1.15)}70%{transform:scale(0.9)}100%{opacity:1;transform:scale(1)}}
@keyframes cardFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-14px)}}
@keyframes iconFloat{0%,100%{transform:rotate(-4deg) scale(1)}50%{transform:rotate(4deg) scale(1.1)}}
@keyframes labelPulse{0%,100%{opacity:0.6;letter-spacing:1px}50%{opacity:1;letter-spacing:3px}}
@keyframes barShimmer{0%{left:-100%}100%{left:200%}}
@keyframes badgeGlow{0%,100%{box-shadow:0 0 4px var(--glow-color, rgba(0,229,255,0.06))}50%{box-shadow:0 0 16px var(--glow-color, rgba(0,229,255,0.22))}}
@keyframes cornerSpark{0%,100%{opacity:0.12;transform:scale(0.6)}50%{opacity:0.5;transform:scale(1.4)}}
@keyframes subtitleSway{0%{transform:translate(0,0)}25%{transform:translate(1px,-1px)}50%{transform:translate(0,0)}75%{transform:translate(-1px,1px)}100%{transform:translate(0,0)}}
/* ── CSS-only sequenced element reveals (no JS, hardware-accelerated) ── */
@keyframes elemRise{0%{opacity:0;transform:translateY(16px)}100%{opacity:1;transform:translateY(0)}}
@keyframes elemPop{0%{opacity:0;transform:scale(0.6)}100%{opacity:1;transform:scale(1)}}
.card-header{animation:elemRise 0.28s ease-out 0.06s both}
.card-headline{animation:elemRise 0.35s ease-out 0.14s both}
.card-subtext{animation:elemRise 0.3s ease-out 0.24s both}
.card-badges>*{animation:elemPop 0.28s ease-out both}
.card-badges>*:nth-child(1){animation-delay:0.33s}
.card-badges>*:nth-child(2){animation-delay:0.40s}
.card-badges>*:nth-child(3){animation-delay:0.47s}
.card-metric{animation:elemRise 0.3s ease-out 0.48s both}
.card-bar{animation:elemRise 0.35s ease-out 0.54s both}
.dp-badge{animation:elemPop 0.28s ease-out 0.35s both}
"""

# V23: 纯JS粒子悬浮层（不依赖Three.js CDN，headless兼容）
THREEP_SCRIPT = """<script>
(function(){
  var c=document.createElement('canvas');
  c.style.cssText='position:absolute;inset:0;z-index:5;pointer-events:none;';
  document.getElementById('root').appendChild(c);
  var ctx=c.getContext('2d'),W,H;
  var N=150,ps=[];
  function resize(){W=c.width=c.offsetWidth;H=c.height=c.offsetHeight;}
  resize();window.addEventListener('resize',resize);
  // Initialize: blue-cyan-purple particles drifting upward
  for(var i=0;i<N;i++){
    var hue=Math.random()<0.5?195:280;
    ps.push({
      x:Math.random()*W, y:Math.random()*H,
      r:Math.random()*3+1.5,
      vx:(Math.random()-0.5)*0.5, vy:-(0.2+Math.random()*0.6),
      hue:hue, alpha:0.3+Math.random()*0.5,
      pulse:Math.random()*Math.PI*2
    });
  }
  function draw(){
    ctx.clearRect(0,0,W,H);
    var t=Date.now()*0.001;
    for(var i=0;i<N;i++){
      var p=ps[i];
      p.x+=p.vx; p.y+=p.vy;
      if(p.y<-10)p.y=H+10;
      if(p.x<-10)p.x=W+10;if(p.x>W+10)p.x=-10;
      // Pulsing opacity
      var a=p.alpha*(0.6+0.4*Math.sin(p.pulse+t*2));
      // Glow
      var g=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,p.r*3);
      g.addColorStop(0,'hsla('+p.hue+',90%,75%,'+a+')');
      g.addColorStop(0.4,'hsla('+p.hue+',80%,60%,'+(a*0.4)+')');
      g.addColorStop(1,'hsla('+p.hue+',80%,60%,0)');
      ctx.fillStyle=g;
      ctx.beginPath();ctx.arc(p.x,p.y,p.r*3,0,Math.PI*2);ctx.fill();
      // Connection lines
      for(var j=i+1;j<N;j++){
        var q=ps[j],dx=p.x-q.x,dy=p.y-q.y,d=Math.sqrt(dx*dx+dy*dy);
        if(d<70){
          ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);
          ctx.strokeStyle='hsla('+p.hue+',80%,70%,'+(0.08*(1-d/70)*a)+')';
          ctx.lineWidth=0.5;ctx.stroke();
        }
      }
    }
    requestAnimationFrame(draw);
  }
  draw();
})();
</script>"""


AUDIO_SYNC_SCRIPT = """<script>(function(){try{var video=document.getElementById('src-v');var ctx=new(window.AudioContext||window.webkitAudioContext)();var src=ctx.createMediaElementSource(video);var analyser=ctx.createAnalyser();analyser.fftSize=64;src.connect(analyser);analyser.connect(ctx.destination);var data=new Uint8Array(analyser.frequencyBinCount);function tick(){analyser.getByteFrequencyData(data);var sum=0;for(var i=0;i<data.length;i++)sum+=data[i];var level=Math.min(1,sum/data.length/128);document.getElementById('root').style.setProperty('--audio-level',level);requestAnimationFrame(tick);}tick();}catch(e){}})();</script>"""

# ── PIP mode constants ──
PIP_CSS = """#pip-bg{position:absolute;inset:0;z-index:1;background:linear-gradient(135deg,#0a0f1e 0%,#121828 50%,#0d1420 100%);}
#pip-bg-v{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:1;opacity:0.18;filter:blur(12px) brightness(0.6);animation:kenburns %%TD%%s ease-in-out infinite alternate;}
#pip-win{position:absolute;z-index:15;pointer-events:none;}
#pip-win-v{width:100%;height:100%;object-fit:cover;border-radius:var(--pip-radius,50%);}
#pip-frame{position:absolute;inset:-4px;z-index:16;border-radius:var(--pip-radius,50%);pointer-events:none;}
@keyframes kenburns{0%{transform:scale(1)}100%{transform:scale(1.03)}}
@keyframes pipPulse{0%,100%{box-shadow:0 0 0 0 rgba(0,229,255,0.35)}50%{box-shadow:0 0 0 6px rgba(0,229,255,0)}}"""

# 🔴 统一用 left% + bottom%（不用 right，方便 GSAP 定时换位动画插值）
# 位置在垂直中部（bottom 30-50%），避免顶部和底部（用户定版要求）
PIP_POSITIONS = [
    ("left-low",   "left:3%;bottom:18%"),
    ("right-mid",  "left:75%;bottom:38%"),
    ("left-high",  "left:3%;bottom:58%"),
    ("right-low",  "left:75%;bottom:18%"),
    ("left-mid",   "left:3%;bottom:38%"),
    ("right-high", "left:75%;bottom:58%"),
]

PIP_FRAMES = {
    "glow-ring":     "box-shadow:0 0 30px rgba(0,229,255,0.25),0 0 60px rgba(0,229,255,0.08);border:2px solid rgba(0,229,255,0.2);",
    "glass-plate":   "background:rgba(255,255,255,0.04);backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.08);",
    "dark-bloom":    "box-shadow:0 0 80px 18px rgba(0,0,0,0.7);",
    "pulse-border":  "border:2px solid rgba(0,229,255,0.25);animation:pipPulse 2.5s ease-in-out infinite;",
    "minimal-line":  "border:1.5px solid rgba(255,255,255,0.1);",
    "hue-echo":      "box-shadow:0 0 40px var(--pip-hue, rgba(0,229,255,0.18));border:1.5px solid var(--pip-hue-border, rgba(0,229,255,0.15));",
}

print("Module constants loaded OK")

__all__ = ['ANIMATION_PRESETS', 'AUDIO_SYNC_SCRIPT', 'BEAT_ICONS', 'BEAT_LABELS', 'CARD_DECOR_CSS', 'COLORS', 'DEFAULT_ANIM', 'FONT_CSS', 'MICRO_CSS', 'PIP_CSS', 'PIP_FRAMES', 'PIP_POSITIONS', 'TAG_COLORS', 'THREEP_SCRIPT']

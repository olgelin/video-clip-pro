# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, ".")
from skills.hf_build_avatar.stage_template import _dedup_motion

ok = True
def check(name, cond):
    global ok
    print(("✅" if cond else "❌") + f" {name}")
    if not cond:
        ok = False

# 框架层 stagger_blur（0.0s）+ LLM（0.2s）→ 应去重剩 1 条
mc1 = 'tl.from("#main-title span",{opacity:0,y:50,stagger:{each:.04,from:"center"},duration:.5,ease:"power3.out"},0.0);\ntl.from("#main-title span",{opacity:0,y:40,rotationX:-90,stagger:0.04,duration:0.5,ease:"back.out(1.7)"},0.2);'
out1 = _dedup_motion(mc1)
check(f"1. 框架层+LLM #main-title span 去重（剩1，实际{out1.count('main-title span')}）", out1.count("main-title span") == 1)

# 框架层 breathe（scale 动画，tl.to 不去重）
mc2 = 'tl.to("#main-title",{duration:2,scale:1.03,ease:"sine.inOut"},7.6);\ntl.from("#main-title",{scale:1.2,duration:0.6,ease:"power3.out"},0.2);'
out2 = _dedup_motion(mc2)
check(f"2. tl.to + tl.from 不同 selector 类型不去重", out2.count("#main-title") == 2)

# 相隔 >1s 不去重
mc3 = 'tl.from(".kpi-card",{opacity:0,y:40},0.8);\ntl.from(".kpi-card",{opacity:0,y:40},2.0);'
out3 = _dedup_motion(mc3)
check(f"3. .kpi-card 相隔1.2s 不去重（剩2，实际{out3.count('kpi-card')}）", out3.count("kpi-card") == 2)

print()
print("✅ 全部通过" if ok else "❌ 有失败")
sys.exit(0 if ok else 1)

# -*- coding: utf-8 -*-
"""验证 from 动画去重逻辑（修复"闪现消失"）"""
import sys, os, re
sys.path.insert(0, ".")
from skills.hf_build_avatar.impl import Hf_build_avatar

base = Hf_build_avatar.__new__(Hf_build_avatar)

def count_from(motion, sel):
    """统计 motion 里某 selector 的 from 动画数量"""
    return len(re.findall(r'tl\.from\("?' + re.escape(sel) + r'"?\s*,\s*\{', motion))

ok = True
def check(name, cond):
    global ok
    print(("✅" if cond else "❌") + f" {name}")
    if not cond:
        ok = False

# 用例1：.metric-card 0.8s 和 1.0s 两条重复 → 去重后只剩 1 条
content1 = '''
<script>var tl=gsap.timeline();tl.from(".metric-card",{opacity:0,y:40,duration:0.6},0.8);tl.from(".metric-card",{opacity:0,y:40,duration:0.6},1.0);</script>
<div class="metric-card">卡片</div>
'''
html1, motion1 = base._extract_llm_motion(content1, dur=20)
check(f"1. .metric-card 重复 from 去重（剩 1 条，实际 {count_from(motion1,'.metric-card')}）", count_from(motion1, ".metric-card") == 1)

# 用例2：.tag-pill 0.8s 和 3.2s（相隔 2.4s）→ 不去重（保留 2 条）
content2 = '''
<script>var tl=gsap.timeline();tl.from(".tag-pill",{opacity:0,y:-20},0.8);tl.from(".tag-pill",{opacity:0,y:20},3.2);</script>
<div class="tag-pill">标签</div>
'''
html2, motion2 = base._extract_llm_motion(content2, dur=20)
check(f"2. .tag-pill 相隔2.4s 不去重（剩 2 条，实际 {count_from(motion2,'.tag-pill')}）", count_from(motion2, ".tag-pill") == 2)

# 用例3：不同 selector 不去重
content3 = '''
<script>var tl=gsap.timeline();tl.from(".a",{opacity:0},0.5);tl.from(".b",{opacity:0},0.5);</script>
<div class="a"></div><div class="b"></div>
'''
html3, motion3 = base._extract_llm_motion(content3, dur=20)
check(f"3. 不同 selector 不去重（.a=1, .b=1）", count_from(motion3, ".a") == 1 and count_from(motion3, ".b") == 1)

# 用例4：用真实 beat-3 HTML 验证 .metric-card 去重
real = r"E:\Hermes-Agent\workspace\xiaoshan\video-clip-pro\output\avatar-short\为什么现在的年轻人越来越不想生孩子了？\hf_build_avatar\beat-3.html"
content4 = open(real, encoding="utf-8").read()
html4, motion4 = base._extract_llm_motion(content4, dur=22)
mc = count_from(motion4, ".metric-card")
check(f"4. 真实 beat-3 .metric-card 去重（应=1，实际 {mc}）", mc == 1)

print()
print("✅ 全部通过" if ok else "❌ 有失败")
sys.exit(0 if ok else 1)

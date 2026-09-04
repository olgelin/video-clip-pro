# -*- coding: utf-8 -*-
"""验证粒子驱动定版：GSAP timeline + __timelines（cli.js 无条件 seek，实测可靠）"""
import sys, re
sys.path.insert(0, ".")
from skills.hf_build_avatar.impl import Hf_build_avatar

base = Hf_build_avatar.__new__(Hf_build_avatar)

ok = True
def check(name, cond, detail=""):
    global ok
    print(("✅" if cond else "❌") + f" {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        ok = False

# 用例1：LLM 照抄菜单（hf-seek 驱动）→ 追加 GSAP timeline + __timelines（hf-seek 保留）
inner1 = 'const c=document.getElementById("pt3d"),r=new THREE.WebGLRenderer({canvas:c});function rd(t){r.render(s,cam)}globalThis.addEventListener("hf-seek",e=>rd(e.detail.time));rd(globalThis.__hfThreeTime||0);'
out1 = base._fix_particle_drive(inner1)
check("1. 追加 GSAP timeline", "gsap.timeline" in out1)
check("1. 注册 __timelines", "__timelines" in out1 and "_particle_pt3d" in out1)
check("1. hf-seek 保留（额外保险）", "hf-seek" in out1)
check("1. 不注入 __hfThreeRender", "__hfThreeRender" not in out1)
check("1. onUpdate 驱动 rd", "onUpdate" in out1 and "rd(_tl.time())" in out1)

# 用例2：已有 GSAP timeline 驱动 → 跳过（不重复注册）
inner2 = 'const c=document.getElementById("bg3d");function rd(t){r.render(s,cam)};(function(){var _tl=gsap.timeline({paused:true});_tl.to({},{duration:3600,onUpdate:function(){rd(_tl.time())}});globalThis.__timelines=globalThis.__timelines||{};globalThis.__timelines["_particle_bg3d"]=_tl;})();'
out2 = base._fix_particle_drive(inner2)
check("2. 已有驱动不重复注入", out2.count("gsap.timeline") == 1)

# 用例3：_default_threejs 兜底走 wrap → 有 GSAP timeline + __timelines
default_html = base._default_threejs("portrait")
wrapped = base._wrap_particle_iife(default_html)
check("3. 兜底粒子经 wrap 后有 GSAP timeline", "gsap.timeline" in wrapped)
check("3. 兜底粒子经 wrap 后注册 __timelines", "__timelines" in wrapped and "_particle_pt3d" in wrapped)

# 用例4：菜单输出保持 hf-seek 原样（无 __hfThreeRender）
menu = base._threejs_menu("portrait", "corner")
check("4. 菜单保持 hf-seek", "hf-seek" in menu)
check("4. 菜单无 __hfThreeRender", "__hfThreeRender" not in menu)
check("4. 菜单 6 个技法都有 hf-seek", menu.count("hf-seek") >= 6)

print()
print("✅ 全部通过" if ok else "❌ 有失败")
sys.exit(0 if ok else 1)

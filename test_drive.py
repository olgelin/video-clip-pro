# -*- coding: utf-8 -*-
"""验证粒子驱动源头修复：hf-seek → __hfThreeRender"""
import sys, re
sys.path.insert(0, ".")
from skills._common.scene_base import SceneBuilderBase
from skills.hf_build_avatar.impl import Hf_build_avatar

# 绕过 __init__（这些方法都是纯函数，不依赖实例状态；用具体类 Hf_build_avatar 继承全部方法）
base = Hf_build_avatar.__new__(Hf_build_avatar)
avatar = base

HD = 'globalThis.addEventListener("hf-seek",e=>rd(e.detail.time));rd(globalThis.__hfThreeTime||0);'
DRV = '(function(){var _p=globalThis.__hfThreeRender;globalThis.__hfThreeRender=function(){if(_p)_p();rd(globalThis.__hfThreeTime||0)}})();'

ok = True
def check(name, cond, detail=""):
    global ok
    print(("✅" if cond else "❌") + f" {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        ok = False

# 用例1：LLM 照抄旧菜单（hf-seek 驱动）→ 移除 hf-seek + 注入 __hfThreeRender
inner1 = 'const c=document.getElementById("pt3d"),r=new THREE.WebGLRenderer({canvas:c});function rd(t){r.render(s,cam)}' + HD
out1 = base._fix_particle_drive(inner1)
check("1. hf-seek 被移除", "hf-seek" not in out1)
check("1. __hfThreeRender 已注入", "__hfThreeRender" in out1)
check("1. 无残留孤立 )", out1.rstrip().endswith(")();") or out1.rstrip().endswith("})();"))

# 用例2：LLM 照抄新菜单（已含 __hfThreeRender）→ 跳过不重复注入
inner2 = 'const c=document.getElementById("pt3d");function rd(t){r.render(s,cam)}' + DRV
out2 = base._fix_particle_drive(inner2)
check("2. 已含 __hfThreeRender 不重复注入", out2.count("__hfThreeRender") == 2)  # DRV 里出现 2 次

# 用例3：只有 rd(0) 初始渲染（无 hf-seek 无 __hfThreeRender）→ 注入
inner3 = 'const c=document.getElementById("pt3d");function rd(t){r.render(s,cam)}rd(globalThis.__hfThreeTime||0);'
out3 = base._fix_particle_drive(inner3)
check("3. 只有 rd(0) 也注入 __hfThreeRender", "__hfThreeRender" in out3)

# 用例4：window.addEventListener 变体 → 也能移除
inner4 = 'window.addEventListener("hf-seek",e=>rd(e.detail.time));'
out4 = base._fix_particle_drive(inner4)
check("4. window 前缀 hf-seek 被移除", "hf-seek" not in out4)

# 用例5：菜单输出（_threejs_menu）→ 无 hf-seek，有 __hfThreeRender
menu = avatar._threejs_menu("portrait", "corner")
check("5. 菜单无 hf-seek", "hf-seek" not in menu)
check("5. 菜单有 __hfThreeRender", "__hfThreeRender" in menu)
check("5. 菜单 6 个技法都有 __hfThreeRender", menu.count("__hfThreeRender") >= 6)

# 用例6：_default_threejs 兜底走 _wrap_particle_iife → 无 hf-seek，有 __hfThreeRender
default_html = base._default_threejs("portrait")
wrapped = base._wrap_particle_iife(default_html)
check("6. 兜底粒子经 wrap 后无 hf-seek", "hf-seek" not in wrapped)
check("6. 兜底粒子经 wrap 后有 __hfThreeRender", "__hfThreeRender" in wrapped)

print()
print("✅ 全部通过" if ok else "❌ 有失败")
sys.exit(0 if ok else 1)

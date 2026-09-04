# -*- coding: utf-8 -*-
"""架构清理验证：四条管线共享技法菜单/兜底粒子/布局菜单，输出一致且用新版粒子"""
import sys
sys.path.insert(0, ".")
from skills.hf_build_avatar.impl import Hf_build_avatar
from skills.hf_build_pip.impl import Hf_build_pip

avatar = Hf_build_avatar.__new__(Hf_build_avatar)
pip = Hf_build_pip.__new__(Hf_build_pip)

ok = True
def check(name, cond, detail=""):
    global ok
    print(("✅" if cond else "❌") + f" {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        ok = False

# 1. avatar 和 pip 技法菜单输出一致（共享同一份）
m_avatar = avatar._threejs_menu("portrait")
m_pip = pip._threejs_menu("portrait")
check("1. avatar/pip 技法菜单完全一致", m_avatar == m_pip)

# 2. 技法菜单用新版：globalThis（非 window）+ 确定性下坠（非累积 -=）
check("2. 用 globalThis 非 window", "globalThis.addEventListener" in m_avatar and "window.addEventListener" not in m_avatar)
check("2. 确定性下坠 y0-spd*t 非累积 -=", "y0[i]-spd[i]*t" in m_avatar and "-=spd[i]" not in m_avatar)
check("2. 快粒子 spd=0.3+", "0.3+Math.random()*0.7" in m_avatar)

# 3. 尺寸替换正确
check("3. 竖屏 setSize(1080,1920)", "setSize(1080,1920,false)" in m_avatar)
m_land = avatar._threejs_menu("landscape")
check("3. 横屏 setSize(1920,1080)", "setSize(1920,1080,false)" in m_land)

# 4. _default_threejs 从共享模板加载，尺寸正确
d_portrait = avatar._default_threejs("portrait")
d_land = avatar._default_threejs("landscape")
check("4. 兜底粒子竖屏 setSize(1080,1920)", "setSize(1080,1920,false)" in d_portrait)
check("4. 兜底粒子横屏 setSize(1920,1080)", "setSize(1920,1080,false)" in d_land)
check("4. 兜底粒子用 globalThis", "globalThis.addEventListener" in d_portrait)

# 5. _layout_menu 从共享文件加载 6 个选项
lm = avatar._layout_menu(0)
check("5. 布局菜单 6 个选项", lm.count("|") == 5 and "建议方向" in lm)

# 6. pip 也拿到新版粒子（不再有 window 代理 bug + 累积 desync bug）
check("6. pip 技法菜单无 window bug", "window.addEventListener" not in m_pip)
check("6. pip 技法菜单无累积下坠 bug", "-=spd[i]" not in m_pip)

print()
print("✅ 架构清理全部通过" if ok else "❌ 有失败")
sys.exit(0 if ok else 1)

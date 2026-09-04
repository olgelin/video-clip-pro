# -*- coding: utf-8 -*-
"""验证 avatar build_stage 删死代码后仍正常输出"""
import sys
sys.path.insert(0, ".")
from skills.hf_build_avatar.stage_template import build_stage

palette = {"gradient_start": "#0a0a1a", "gradient_mid": "#101030", "gradient_end": "#1a1040",
           "accent": "#6C8CFF", "secondary": "#00D4FF", "primary": "#6C8CFF"}
motion = {"timeline": [{"effect": "stagger_blur", "start": 0}, {"effect": "particle_drift", "start": 0}]}

out = build_stage(0, 5.0, palette, motion, ghost="测试", quote="测试口播", orientation="portrait", person_layout="corner")

checks = {
    "含 beat-0": "beat-0" in out,
    "含 gsap.timeline": "gsap.timeline" in out,
    "含 LLM_CONTENT_INSERT": "LLM_CONTENT_INSERT" in out,
    "含 Three.js 内联": "THREE" in out or "WebGLRenderer" in out,
    "含 person_zone 占位框": "data-person-zone" in out,
    "含 __timelines 注册": "__timelines" in out,
    "无死代码 grid_3d": "grid_3d" not in out and "perspective:1000px" not in out,
    "无死代码 _RAIN 模板": "border-radius:1px" not in out and "linear-gradient(180deg,transparent" not in out,
    "含 particle_drift 粒子动画": "p-near" in out,
}
ok = True
for name, cond in checks.items():
    print(("✅" if cond else "❌") + f" {name}")
    if not cond:
        ok = False

print(f"\n输出长度: {len(out)} 字符")
print("✅ build_stage 正常" if ok else "❌ 有问题")
sys.exit(0 if ok else 1)

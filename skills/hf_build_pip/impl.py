"""hf_build_pip v82 — 从 storyboard 接收场景，生成HTML
架构: storyboard(分镜+视觉方向) → Python框架(grid+粒子+辉光) → Scene LLM(Three.js+标题+标签)
"""
import json, re, time
from pathlib import Path
from skills._common.scene_base import SceneBuilderBase

class Hf_build_pip(SceneBuilderBase):
    name = "hf_build_pip"

    def execute(self, context: dict) -> dict:
        provider = context.get("provider")
        scenes = context.get("scenes", [])
        if not scenes:
            print("  ⛔ 无 storyboard 场景")
            return {"html_files": [], "review": {}}

        n = len(scenes)
        print(f"\n[6/6] PIP — {n}场景")

        # 🔴 P1：检测输入视频方向（竖屏/横屏），动态场景尺寸
        from core.hf_card_builder import _detect_orientation
        orientation = _detect_orientation(context.get("video_path", ""))
        print(f"      方向: {'横屏 1920×1080' if orientation == 'landscape' else '竖屏 1080×1920'}")

        from skills.hf_build_pip.color_grader import grade
        from skills.hf_build_pip.motion_director import direct as motion_gen
        from skills.hf_build_pip.stage_template import build_stage

        scene_prompt_tpl = self.load_prompt("scene_system")
        output_dir = Path(context.get("output_dir", ".")) / "hf_build_pip"
        output_dir.mkdir(parents=True, exist_ok=True)
        html_files = []
        prev_scene = None

        for idx, scene in enumerate(scenes):
            quote = scene.get("narration", "")
            mood = scene.get("mood", "冷静理性")
            dur = scene.get("duration", 5)

            ke = scene.get("key_elements", [])
            d_tags = [e["text"] for e in ke if e.get("type") == "tag"]
            d_titles = [e["text"] for e in ke if e.get("type") == "title"]
            # 🔴 ghost 水印优先用 LLM 产出的 title（有意义关键词），tag 关闭时不再从口播截废话
            ghost = d_titles[0] if d_titles else (d_tags[0] if d_tags else (quote[:2] if len(quote) >= 2 else "?"))

            palette = grade(mood)
            motion = motion_gen(dur, scene.get("animation_style", "逐字渐入"), idx)

            brief = self._dict_to_brief(scene, idx, n, prev_scene)
            prompt = scene_prompt_tpl
            reps = {
                "visual_brief": brief,
                "color_palette": json.dumps(palette, ensure_ascii=False, indent=2),
                "layout_options": self._layout_menu(idx),
                "threejs_menu": self._threejs_menu(orientation),
                "motion_instructions": self._motion_nl(motion),
                "opening_hint": self._opening_hint(idx),
            }
            for k, v in reps.items():
                prompt = prompt.replace("{" + k + "}", v)

            content = self._call_scene(provider, prompt)
            if content:
                # 🔴 P0：提取 LLM 动画语句，合并进 stage 的统一 timeline（单一 __timelines["beat-N"]）
                content_html, llm_motion = self._extract_llm_motion(content, dur=dur)
                content_html = self._ensure_threejs(content_html, orientation)  # 🔴 兜底：Three.js 缺失注入默认粒子
                stage = build_stage(idx, dur, palette, motion, ghost=ghost, quote=quote, llm_motion=llm_motion, orientation=orientation)
                html = stage.replace("<!-- LLM_CONTENT_INSERT -->", content_html)
                (output_dir / f"beat-{idx}.html").write_text(html, encoding="utf-8")
                html_files.append(str(output_dir / f"beat-{idx}.html"))
                # 记录本场实际使用的 Three.js 技法，供下一场对比
                scene["_threejs_tech"] = self._detect_threejs_tech(content)
                print(f"  [{idx+1}/{n}] {len(html)//1024}KB [{scene.get('visual_type','?')[:10]}] {scene['_threejs_tech']} {quote[:20]}")
                prev_scene = scene
            else:
                print(f"  [{idx+1}/{n}] ❌ [{scene.get('visual_type','?')[:10]}]")

        ok = len(html_files)
        print(f"\n  质量: {ok}/{n} {'✅全通过' if ok == n else '⚠'}")
        # 🔴 P0：把 HTML 全屏场景渲染进最终视频（HyperFrames）
        render_result = self._render_scenes(context, scenes, output_dir)
        return {"html_files": html_files, **render_result}

    def _render_scenes(self, context: dict, scenes: list, output_dir: Path) -> dict:
        """P0：把 hf_build_pip 的全屏 HTML 场景渲染进最终视频"""
        if not scenes:
            return {}
        from core.hf_card_builder import build_hyperframes_composition, render_hyperframes
        words = context.get("words", [])
        video_path = Path(context.get("video_path", ""))
        project_root = Path(context.get("output_dir", "."))  # 项目根（final.mp4/hyperframes 所在）
        render_ranges = []
        for i, scene in enumerate(scenes):
            # output_dir 已是 hf_build_pip 子目录，直接拼 beat-N.html
            html_path = output_dir / f"beat-{i}.html"
            if not html_path.exists():
                continue
            html_content = html_path.read_text(encoding="utf-8")
            render_ranges.append({
                "start": scene.get("final_start", scene.get("start", 0)),
                "end": scene.get("final_end", scene.get("start", 0) + scene.get("duration", 5)),
                "beat": "INFO",
                "quote": scene.get("narration", ""),
                "_scene_html": html_content,
            })
        if not render_ranges:
            print("      ⚠ 渲染跳过：无 HTML 场景文件")
            return {}
        render_edl = {"ranges": render_ranges}
        try:
            print(f"\n[渲染] HyperFrames 合成 {len(render_ranges)} 个全屏场景 (PIP)...")
            hf_dir = build_hyperframes_composition(render_edl, words, project_root, video_path, layout_mode="pip")
            if hf_dir:
                polished = render_hyperframes(hf_dir)
                if polished:
                    return {"final_polished": str(polished)}
        except Exception as e:
            print(f"      PIP 渲染错误: {e}")
        return {}

    def _dict_to_brief(self, d: dict, idx: int, total: int, prev: dict = None) -> str:
        parts = [
            f"第{idx+1}/{total}场",
            f"🔴 本场时长：{d.get('duration', 5):.1f}秒（所有 GSAP 动画时间戳必须 < 此值，禁止动画超时）",
            f"视觉类型：{d.get('visual_type', 'quote_hero')}",
            f"画面隐喻（创作方向，不直接显示）：{d.get('concept', '')}",
            f"情绪：{d.get('mood', '')}",
            f"口播参考（理解语义用，禁止>15字原文贴入）：{d.get('narration', '')}",
        ]
        # 🔴 Cross-scene contrast
        if prev:
            prev_tech = prev.get("_threejs_tech", "")
            tech_hint = f"，上一场用了 {prev_tech} Three.js 技法你禁止再用" if prev_tech else ""
            parts.insert(2, f"🔴 上一场用了 {prev.get('visual_type','?')} 类型{tech_hint}，你这场的视觉/布局/Three.js技法/配色比重 必须完全不同")
        ke = d.get("key_elements", [])
        if ke:
            titles = [e["text"] for e in ke if e.get("type") == "title"]
            # 🔴 h1#main-title 必须用这个文字——禁止用 concept/画面隐喻里的文字
            if titles:
                parts.insert(1, f"🔴 h1#main-title 文字（禁止用画面隐喻里的文字做标题）：{titles[0]}")
            tags = [e["text"] for e in ke if e.get("type") == "tag"]
            nums = [e["text"] for e in ke if e.get("type") == "number"]
            if tags:
                parts.append(f"标签：{', '.join(tags)}")
            if nums:
                parts.append(f"数据：{', '.join(nums)}")
        if d.get("animation_style"):
            parts.append(f"入场动效：{d['animation_style']}")
        if d.get("chart_type"):
            parts.append(f"图表类型：{d['chart_type']}")
        # ── 抄自 video-factory：depth_layers / density_target / camera_motion / choreography ──
        dl = d.get("depth_layers", {})
        if dl:
            dl_text = " | ".join(f"{k}:{v}" for k, v in dl.items() if v)
            parts.append(f"🔴 层次结构（前景/中景/背景，必须按此分层）：{dl_text}")
        if d.get("density_target"):
            parts.append(f"🔴 元素密度：至少 {d['density_target']} 个可见元素（标题+卡片+进度条+标签+装饰层）")
        cm = d.get("camera_motion")
        if cm:
            cm_type = cm.get("type") if isinstance(cm, dict) else str(cm)
            parts.append(f"🔴 镜头运动（MUST 必须实现，禁止整场静止）：{cm_type}")
        ch = d.get("choreography", {})
        if ch:
            parts.append(f"动画动词：标题 {ch.get('title','')}，内容 {ch.get('content','')}")
        return "\n".join(parts)

    def _opening_hint(self, idx: int) -> str:
        if idx == 0:
            return "🔴 开场——大字110-130px，选最炫Three.js，1-2个标签慢飘入，不用KPI。"
        return ""
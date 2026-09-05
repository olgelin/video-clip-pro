"""hf_build_avatar — 从 storyboard 接收场景，生成HTML
架构: storyboard(分镜+视觉方向) → Python框架(grid+粒子+辉光) → Scene LLM(Three.js+标题+标签)
"""
import json, re, time
from pathlib import Path
from skills._common.scene_base import SceneBuilderBase

class Hf_build_avatar(SceneBuilderBase):
    name = "hf_build_avatar"

    def execute(self, context: dict) -> dict:
        provider = context.get("provider")
        scenes = context.get("scenes", [])
        if not scenes:
            print("  ⛔ 无 storyboard 场景")
            return {"html_files": [], "review": {}}

        # 🔴 avatar 数据适配：数字人视频 + 口播稿字幕（无剪切，不走转录）
        if context.get("avatar_video_path"):
            context["video_path"] = context["avatar_video_path"]
            # 数字人视频复制成 final.mp4（叠加逻辑 _compose_pip 期待 final.mp4）
            import shutil as _shutil
            _av = Path(context["avatar_video_path"])
            _final = Path(context.get("output_dir", ".")) / "final.mp4"
            if _av.exists() and not _final.exists():
                _shutil.copy2(_av, _final)
            if not context.get("words") and context.get("script_data"):
                context["words"] = self._script_to_words(
                    context["script_data"], context.get("voice_scene_durations", []))

        n = len(scenes)
        print(f"\n[6/6] Avatar — {n}场景")

        # 🔴 场景方向优先用 --orientation（数字人合成用竖屏素材时，场景仍可横屏）
        from core.hf_card_builder import _detect_orientation
        orientation = context.get("orientation") or _detect_orientation(context.get("video_path", ""))
        print(f"      方向: {'横屏 1920×1080' if orientation == 'landscape' else '竖屏 1080×1920'}")

        from skills.hf_build_avatar.color_grader import grade
        from skills.hf_build_avatar.motion_director import direct as motion_gen
        from skills.hf_build_avatar.stage_template import build_stage

        scene_prompt_tpl = self.load_prompt("scene_system")
        output_dir = Path(context.get("output_dir", ".")) / "hf_build_avatar"
        output_dir.mkdir(parents=True, exist_ok=True)
        # 🔴 清空旧的 beat-N.html 残留（--debug 下目录不清理，场景数变化时旧文件会污染渲染）
        for _old in output_dir.glob("beat-*.html"):
            _old.unlink(missing_ok=True)
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
            # 🔴 数字人编排优先用 LLM 判断结果（storyboard 里 _direct_person_layouts 产出），失败回退硬编码
            _pl = scene.get("person_layout") or self._person_layout(orientation, scene.get('visual_type'))
            reps = {
                "visual_brief": brief,
                "color_palette": json.dumps(palette, ensure_ascii=False, indent=2),
                "layout_options": self._layout_menu(idx),
                "threejs_menu": self._threejs_menu(orientation, _pl),
                "motion_instructions": self._motion_nl(motion),
                "opening_hint": self._opening_hint(idx, orientation),
                "canvas_hint": self._canvas_hint(orientation, _pl),
            }
            for k, v in reps.items():
                prompt = prompt.replace("{" + k + "}", v)

            content = self._call_scene(provider, prompt)
            if content:
                # 🔴 渲染前质量 review：错别字/文案/重叠/数据/配色，不合格带反馈重新生成（最多重试2次）
                content = self._review_scene(provider, prompt, content)
                # 🔴 P0：提取 LLM 动画语句，合并进 stage 的统一 timeline（单一 __timelines["beat-N"]）
                content_html, llm_motion = self._extract_llm_motion(content, dur=dur)
                content_html = self._ensure_threejs(content_html, orientation)  # 🔴 兜底：Three.js 缺失注入默认粒子
                stage = build_stage(idx, dur, palette, motion, ghost=ghost, quote=quote, llm_motion=llm_motion,
                                    orientation=orientation, person_layout=_pl)
                scene["person_layout"] = _pl
                html = stage.replace("<!-- LLM_CONTENT_INSERT -->", content_html)
                # 🔴 移除 data-person-zone 占位框：它只是给 LLM 的避让提示（canvas_hint 里已文字说明），
                # 不是最终内容——虚线框 z-index:40 高于数字人视频 z-index:15，会透出来像残留虚线。
                html = re.sub(r'<div data-person-zone=[^>]*></div>', '', html)
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
                "visual_type": scene.get("visual_type", ""),  # 🔴 v41 语义换位：传给 build 决定人物位置
                "person_layout": scene.get("person_layout", ""),  # 🔴 LLM 编排的数字人摆位（大/小/左/右）
                "_scene_html": html_content,
            })
        if not render_ranges:
            print("      ⚠ 渲染跳过：无 HTML 场景文件")
            return {}
        render_edl = {"ranges": render_ranges, "topic": context.get("topic", "")}
        try:
            print(f"\n[渲染] HyperFrames 合成 {len(render_ranges)} 个全屏场景 (Avatar)...")
            hf_dir = build_hyperframes_composition(render_edl, words, project_root, video_path,
                                                   layout_mode="avatar", orientation=context.get("orientation"))
            if hf_dir:
                polished = render_hyperframes(hf_dir)
                if polished:
                    return {"final_polished": str(polished)}
        except Exception as e:
            print(f"      PIP 渲染错误: {e}")
        return {}

    def _script_to_words(self, script_data: dict, scene_durations: list) -> list:
        """口播稿段落 + 配音时长 → words（逐段字幕，时间戳从配音时长累积，音画同步）"""
        sections = script_data.get("voiceover_sections", [])
        words = []
        acc = 0.0
        for i, sec in enumerate(sections):
            dur = scene_durations[i]["duration"] if i < len(scene_durations) else max(len(sec.get("content", "")) / 4.0, 2.0)
            words.append({"start": round(acc, 2), "end": round(acc + dur, 2), "text": sec.get("content", "")})
            acc += dur
        return words

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
        ss = d.get("shot_scale", "")
        if ss:
            parts.append(f"🔴 画面景别（MUST 遵守，见 scene_system 的「画面景别」段）：{ss}")
        return "\n".join(parts)

    def _person_layout(self, orientation: str, visual_type: str = "") -> str:
        """🔴 数字人位置布局（v41 语义换位）：按视觉类型决定，金句/对比/时间线 → 左下（横屏右分栏），
        其余 → 右下角标。占位框（stage_template）和数字人 video 位置（hf_card_builder）都走同一映射，
        保证两层对齐。v40 已改 HyperFrames 同层渲染，位置切换用 GSAP 动画在 main timeline 上做，
        不再受 v39「ffmpeg 叠加统一位置」的约束。"""
        from skills.hf_build_avatar.person_zone import person_layout_for_visual_type
        return person_layout_for_visual_type(visual_type, orientation)

    def _canvas_hint(self, orientation: str, person_layout: str) -> str:
        """🔴 v42 画布尺寸提示：横屏分栏时告诉 LLM 画布=内容区(1370×1080)，不是全屏 1920×1080。
        这样 LLM 在内容区内排版，数字人独占对侧竖条，真分区不叠放。"""
        from skills.hf_build_avatar.person_zone import person_zone as _pz, content_zone as _cz, LANDSCAPE_PERSON_W as _LPW
        if orientation == "landscape" and person_layout in ("left-rail", "right-rail"):
            z = _cz(person_layout, orientation)
            w = z["w"]
            person_side = "右侧" if person_layout == "right-rail" else "左侧"
            content_side = "左侧" if person_layout == "right-rail" else "右侧"
            return (f"- 🔴 画布 = 横屏内容区 {w}×1080（你在{content_side}；{person_side} {_LPW}px 是数字人竖条，不在你的画布内，你根本不用管它）。"
                    f"安全区：左右 {max(20, int(w * 0.05))}px、顶部 54px、**底部 150px（字幕区，绝对禁入）**。水平填满不留大片空白。所有 left/right/width 定位都基于 {w}px 宽。")
        if orientation == "landscape":
            hint = ("- 🔴 画布 = 横屏 1920×1080。安全区：左右 96px、顶部 54px、**底部 150px（字幕区，绝对禁入，含注脚/标签/图例）**。水平填满不留大片空白")
        else:
            hint = ("- 🔴 画布 = 竖屏 1080×1920。安全区：左右 54px、顶部 96px、**底部 180px（字幕区，绝对禁入，含注脚/标签/图例）**。垂直填满不留大片空白")
        # 🔴 角标场景：数字人小窗在角落，明确告诉 LLM 避让的具体像素范围（之前只说"画布=全屏"，LLM 把 2×2 卡片排满四角→遮挡）
        if person_layout in ("corner-bl", "corner-br"):
            z = _pz(person_layout, orientation)
            corner = "左下角" if person_layout == "corner-bl" else "右下角"
            hint += (f"\n- 🔴 {corner}（约 x:{z['x']}-{z['x']+z['w']}、y:{z['y']}-{z['y']+z['h']}）是数字人角标小窗，"
                     f"你的卡片/数据/文字**必须避开{corner}这一块**——别把任何内容排到{corner}，那里留给数字人。")
        return hint

    def _opening_hint(self, idx: int, orientation: str = "portrait") -> str:
        if idx != 0:
            return ""
        if orientation == "landscape":
            return "🔴 开场——满幅数字人在右侧竖条，你的内容全部排在左侧内容区（标题大字 + 1-2 个标签慢飘入，不用 KPI）。禁止把内容排到右侧——右侧是满幅数字人的位置，会被盖住。"
        return "🔴 开场——满幅数字人在底部（占下 1/3），你的内容全部排在上 2/3（标题大字110-130px + 1-2个标签慢飘入，不用KPI）。禁止把内容排到底部——底部是满幅数字人的位置，会被盖住。"
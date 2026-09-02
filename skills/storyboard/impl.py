"""Storyboard skill — Python 确定性分镜（不用 LLM）
EDL片段 → 智能合并 → 推断 visual_type + 提取 key_elements
"""
from __future__ import annotations
import re
from core.base import SkillBase
from core.provider import Provider

# ── 抄自 video-factory：depth_layers 8 种变体（前景/中景/背景轮换）──
DEPTH_VARIANTS = [
    {"bg": "dark fill + radial glow", "mg": "content cards", "fg": "accent lines + grain"},
    {"bg": "gradient mesh + particles", "mg": "floating panels", "fg": "scan lines + noise"},
    {"bg": "circuit pattern + pulse", "mg": "data cards stack", "fg": "glow edges + dust"},
    {"bg": "grid wireframe + nebula", "mg": "metric panels", "fg": "laser lines + sparks"},
    {"bg": "matrix rain + void", "mg": "glass cards", "fg": "hologram flicker"},
    {"bg": "hex grid + aurora", "mg": "info blocks", "fg": "particle stream"},
    {"bg": "dot matrix + glow orbs", "mg": "stacked modules", "fg": "energy ribbons"},
    {"bg": "noise texture + gradient", "mg": "quote panel", "fg": "accent strokes"},
]

# ── 抄自 video-factory：动画动词（标题高能 / 内容低能）──
TITLE_VERBS = ["SLAMS", "CRASHES", "BURSTS", "PUNCHES", "STAMPS", "SHATTERS"]
CONTENT_VERBS = ["FLOATS", "MORPHS", "COUNTS UP", "FADES IN", "DRIFTS", "TYPES ON"]

# ── 抄自 video-factory：镜头运动轮换 ──
CAMERA_MOTIONS = [
    {"type": "dolly_in", "intensity": "subtle"},
    {"type": "pan_left", "intensity": "subtle"},
    {"type": "zoom_in", "intensity": "moderate"},
    {"type": "dolly_out", "intensity": "subtle"},
    {"type": "pan_right", "intensity": "subtle"},
]

# ── 语义映射（对齐 vf 的 LLM 语义产出，不是机械轮换）──
# vf 的 depth_layers/camera_motion/choreography 是 LLM 按场景语义产出的，
# vcp 用确定性 Python 分镜，所以用 visual_type 做语义映射补上这个差异。
DEPTH_LAYERS_BY_TYPE = {
    "data_impact": {"bg": "gradient mesh + glow orbs", "mg": "data cards stack + KPI panels", "fg": "accent lines + spark particles"},
    "quote_hero": {"bg": "dark fill + radial glow", "mg": "quote panel + floating glyphs", "fg": "grain + light streaks"},
    "compare": {"bg": "split gradient + nebula", "mg": "left/right metric panels", "fg": "divider line + contrast sparks"},
    "flow": {"bg": "grid wireframe + aurora", "mg": "node chain + progress cards", "fg": "particle stream + connectors"},
    "list_alert": {"bg": "circuit pattern + pulse", "mg": "stacked alert cards", "fg": "glow edges + warning marks"},
    "timeline_event": {"bg": "dot matrix + glow orbs", "mg": "timeline rail + event nodes", "fg": "energy ribbons"},
    "hud": {"bg": "hex grid + scan", "mg": "dashboard panels + gauges", "fg": "hologram flicker + target marks"},
}

CAMERA_BY_TYPE = {
    "data_impact": {"type": "zoom_in", "intensity": "moderate"},
    "quote_hero": {"type": "dolly_in", "intensity": "subtle"},
    "compare": {"type": "pan_left", "intensity": "subtle"},
    "flow": {"type": "pan_right", "intensity": "subtle"},
    "list_alert": {"type": "dolly_out", "intensity": "subtle"},
    "timeline_event": {"type": "pan_right", "intensity": "subtle"},
    "hud": {"type": "dolly_in", "intensity": "subtle"},
}

CHOREO_BY_TYPE = {
    "data_impact": {"title": "SLAMS in from left", "content": "COUNTS UP rapidly"},
    "quote_hero": {"title": "BURSTS from center", "content": "FLOATS gently"},
    "compare": {"title": "PUNCHES from both sides", "content": "FADES IN staggered"},
    "flow": {"title": "STAMPS in sequence", "content": "MORPHS along path"},
    "list_alert": {"title": "CRASHES in", "content": "DRIFTS in staggered"},
    "timeline_event": {"title": "BURSTS in", "content": "TYPES ON sequentially"},
    "hud": {"title": "SLAMS in", "content": "COUNTS UP"},
}


class Storyboard(SkillBase):
    name = "storyboard"

    def execute(self, context: dict) -> dict:
        # 🔴 avatar 分支：口播稿 + 配音时长直接分镜（无剪切，不依赖转录）
        if context.get("script_data") and context.get("voice_scene_durations"):
            ranges = self._script_to_ranges(context["script_data"], context["voice_scene_durations"])
        elif context.get("re_transcribed") and context.get("words"):
            ranges = self._words_to_ranges(context["words"])
        else:
            edl = context.get("edl") or context.get("draft_edl", {})
            ranges = edl.get("ranges", [])

        if not ranges:
            print("  Storyboard: no ranges")
            return {"scenes": []}

        provider = context.get("provider")
        orientation = context.get("orientation", "portrait")
        scenes = self._build(ranges, provider=provider, orientation=orientation)
        print(f"  Storyboard: {len(ranges)} segments → {len(scenes)} visual scenes")
        for s in scenes:
            ke = s.get("key_elements", [])
            ke_str = ", ".join(f"{e['type']}={e['text']}" for e in ke[:4])
            print(f"    {s['start']:.1f}-{s['end']:.1f}s [{s['visual_type']}] {ke_str}")
        return {"scenes": scenes}

    def _words_to_ranges(self, words: list) -> list:
        """re_transcribe 后：新 words（新视频时间戳）→ ranges（beat 按位置标注）"""
        n = len(words)
        beats = ["HOOK", "CONTEXT", "PROBLEM", "STRUGGLE", "RESOLUTION"]
        ranges = []
        for i, w in enumerate(words):
            beat_idx = min(int(i / max(n, 1) * len(beats)), len(beats) - 1)
            ranges.append({
                "start": w["start"], "end": w["end"],
                "beat": beats[beat_idx],
                "title": "",
                "quote": w["text"],
                "trimmed": w["text"],
            })
        return ranges

    def _script_to_ranges(self, script_data: dict, scene_durations: list) -> list:
        """avatar：口播稿段落 + 配音时长 → ranges（每段一个场景，时间戳从配音时长累积，音画同步）"""
        sections = script_data.get("voiceover_sections", [])
        beats = ["HOOK", "CONTEXT", "PROBLEM", "STRUGGLE", "RESOLUTION"]
        ranges = []
        acc = 0.0
        n = max(len(sections), 1)
        for i, sec in enumerate(sections):
            dur = scene_durations[i]["duration"] if i < len(scene_durations) else max(len(sec.get("content", "")) / 4.0, 2.0)
            beat = beats[min(int(i / n * len(beats)), len(beats) - 1)]
            content = sec.get("content", "")
            ranges.append({
                "start": round(acc, 2),
                "end": round(acc + dur, 2),
                "beat": beat,
                "title": "",
                "quote": content,
                "trimmed": content,
            })
            acc += dur
        return ranges

    def _build(self, ranges: list, provider=None, orientation: str = "portrait") -> list:
        """核心：语义分镜 + 推断 + 提取"""
        if not ranges:
            return []

        # Step 1: 语义分镜（LLM 读全文切话题/信息点/转折点，不机械合并）
        merged = self._semantic_split_merge(ranges, provider)

        # Step 2: per-group enrichment
        scenes = []
        prev_vt = ""
        prev_prev_vt = ""
        acc = 0.0  # 连续时间轴累加（对应 final.mp4，不含原始视频间隙）
        for i, g in enumerate(merged):
            real_dur = g.get("real_dur", g["end"] - g["start"])
            dur = real_dur
            narration = g["narration"]
            beat = g.get("beat", "")
            is_first = (i == 0)
            is_last = (i == len(merged) - 1)

            # Visual type from content + beat
            vt = self._detect_type(narration, beat, is_first, is_last)
            # 🔴 避免和最近 2 个场景重复（竖屏场景少，隔一个重复也会显得单调）
            recent = {prev_vt, prev_prev_vt}
            if vt in recent:
                alternatives = {
                    "quote_hero": "timeline_event",
                    "data_impact": "flow",
                    "compare": "list_alert",
                    "flow": "data_impact",
                    "list_alert": "compare",
                    "hud": "quote_hero",
                    "timeline_event": "hud",
                }
                alt = alternatives.get(vt, "quote_hero")
                _guard = 0
                while alt in recent and _guard < 6:
                    alt = alternatives.get(alt, "quote_hero")
                    _guard += 1
                vt = alt
            prev_prev_vt = prev_vt
            prev_vt = vt

            # Chart type — for data_impact/comparison scenes
            chart_type = self._detect_chart(narration, vt)

            # Concept + Title — LLM 一次调用同时产出（标题|隐喻），零额外开销
            concept, title_hint = self._make_concept_llm(narration, provider) if provider else (narration[:20], "")

            # Key elements (title 用 LLM 产出的，number 从 narration 提取)
            ke = self._extract_elements(narration, vt, concept, title_hint)

            # Mood from beat
            mood_map = {
                "HOOK": "冲击 悬念", "CONTEXT": "冷静 理性",
                "PROBLEM": "紧张 对立", "STRUGGLE": "冲突 焦虑",
                "RESOLUTION": "开阔 希望",
            }
            mood = mood_map.get(beat, "冷静 理性")

            # Animation from beat
            anim_map = {
                "HOOK": "弹入冲击", "CONTEXT": "逐字渐入",
                "PROBLEM": "blur浮现", "STRUGGLE": "粒子汇聚",
                "RESOLUTION": "扫光揭开",
            }
            anim = anim_map.get(beat, "逐字渐入")

            scenes.append({
                "start": g["start"], "end": g["end"], "duration": max(dur, 1.0),
                "final_start": round(acc, 2), "final_end": round(acc + real_dur, 2),
                "narration": narration, "visual_type": vt, "concept": concept,
                "mood": mood, "key_elements": ke, "animation_style": anim,
                "chart_type": chart_type,
                "shot_scale": self._shot_scale(i, len(merged), beat),
                # ── 抄自 video-factory：语义映射（对齐 vf 的 LLM 语义产出，不是机械轮换）──
                "depth_layers": DEPTH_LAYERS_BY_TYPE.get(vt, DEPTH_VARIANTS[i % len(DEPTH_VARIANTS)]),
                "density_target": 8,
                "camera_motion": CAMERA_BY_TYPE.get(vt, CAMERA_MOTIONS[i % len(CAMERA_MOTIONS)]),
                "choreography": CHOREO_BY_TYPE.get(vt, {
                    "title": f"{TITLE_VERBS[i % len(TITLE_VERBS)]} in from left",
                    "content": f"{CONTENT_VERBS[i % len(CONTENT_VERBS)]} gently",
                }),
            })
            acc += real_dur

        # 🔴 数字人编排 LLM 判断（不代码锁死）：读场景语义，LLM 决定每个场景数字人摆位（大/小/左/右）
        scenes = self._direct_person_layouts(scenes, orientation, provider)

        return scenes

    def _direct_person_layouts(self, scenes: list, orientation: str, provider) -> list:
        """🔴 数字人编排：景别决定大小（full→corner角标/inset→rail分栏，确定性、稳定），
        LLM 判断左右换位（灵活、创意）。这样既不死锁（左右由 LLM 判断），又稳定（大↔小由景别保证，不依赖 LLM 随机性）。
        LLM 失败 → fallback 到 person_layout_for_visual_type 硬编码映射。"""
        from skills.hf_build_avatar.person_zone import person_layout_for_visual_type as _plvt

        n = len(scenes)
        # 先填 fallback（LLM 失败时兜底）
        for s in scenes:
            s["person_layout"] = _plvt(s.get("visual_type", ""), orientation)

        if not provider or n < 2:
            return scenes

        lines = []
        for i, s in enumerate(scenes):
            vt = s.get("visual_type", "")
            sc = s.get("shot_scale", "")
            nar = (s.get("narration", "") or "").strip()[:24]
            lines.append(f"[{i}] 视觉类型:{vt} 景别:{sc} 内容:{nar}")
        scene_list = "\n".join(lines)

        prompt = (
            f"你是数字人出镜导演。下面是一个{'横屏' if orientation == 'landscape' else '竖屏'}口播视频的 {n} 个场景"
            f"（视觉类型+景别+内容要点）。数字人「大小」已由景别定好（full满版→缩角落小图标，inset缩小→大竖条分栏），"
            f"你只需判断每个场景数字人靠「左(L)/右(R)/隐藏(H)」，让换位自然有节奏。\n\n"
            f"{scene_list}\n\n"
            f"要求：\n"
            f"1. 相邻场景数字人左右尽量不同（换位），避免连续多个场景挤在同一侧\n"
            f"2. 高潮数据冲击/金句升华/需要内容全屏震撼的场景，用隐藏(H)——数字人完全不出镜，纯内容画面\n"
            f"3. 隐藏(H)不要超过一半场景，数字人大部分时间还是在画面里讲解\n\n"
            f"只输出 JSON：{{\"sides\": [\"L\", \"R\", \"H\", ...]}}，长度={n}，按场景顺序，每个值是 L/R/H，不要解释。"
        )

        try:
            raw = provider.call("storyboard_split", prompt,
                                system="你是数字人出镜导演。只输出 JSON 数组，不要解释。",
                                max_tokens=200)
            if not raw:
                return scenes
            import json as _json, re as _re
            m = _re.search(r'\[[^\]]*\]', raw, _re.DOTALL)
            if not m:
                return scenes
            sides = _json.loads(m.group(0))
            if isinstance(sides, list) and len(sides) == n:
                for i, s in enumerate(scenes):
                    sv = str(sides[i]).upper()
                    sc = s.get("shot_scale", "")
                    if sv in ("H", "HIDDEN", "隐藏", "X", "无", "无数字人"):
                        s["person_layout"] = "hidden"
                    else:
                        side = "L" if sv in ("L", "LEFT", "左") else "R"
                        if orientation == "landscape":
                            if sc == "inset":
                                s["person_layout"] = "left-rail" if side == "L" else "right-rail"
                            else:
                                s["person_layout"] = "corner-bl" if side == "L" else "corner-br"
                        else:
                            s["person_layout"] = "corner-bl" if side == "L" else "corner-br"
        except Exception:
            pass
        return scenes

    def _shot_scale(self, i: int, total: int, beat: str) -> str:
        """🔴 画面景别（满/小严格交替）：full=全屏满版(冲击)，inset=缩小的小画面(缩放+移动动画)。
        开场满(i=0)，之后 full/inset 交替，保证整条视频有全屏与小画面的节奏变化，绝不连续两个满版。"""
        return "full" if i % 2 == 0 else "inset"

    def _semantic_split_merge(self, ranges: list, provider=None) -> list:
        """语义分镜：LLM 读全文切话题/信息点/转折点，按分组合并 ranges。
        时间戳/real_dur 从 ranges 精确累加（不含间隙），保证音画同步。"""
        n = len(ranges)
        if n <= 2 or not provider:
            return self._merge(ranges)  # 太短或无 provider，回退简单合并

        groups = self._semantic_split(ranges, provider)
        if not groups:
            return self._merge(ranges)  # LLM 分镜失败，回退

        merged = []
        for group in groups:
            # 统一解析：group 是 [a,b] 区间（与 _parse_split 一致）
            if isinstance(group, list) and len(group) >= 2:
                a, b = int(group[0]), int(group[-1])
                indices = list(range(a, b + 1))
            elif isinstance(group, int):
                indices = [group]
            else:
                continue
            rs = [ranges[i] for i in indices]
            # beat：取组内最后一个有意义的 beat（跳过 CONTEXT）
            beat = rs[-1].get("beat", "")
            for r in rs:
                if r.get("beat") and r.get("beat") != "CONTEXT":
                    beat = r["beat"]
            merged.append({
                "start": rs[0]["start"], "end": rs[-1]["end"],
                "beat": beat,
                "narration": "".join(r.get("trimmed", r.get("quote", "")) for r in rs),
                "real_dur": sum(r["end"] - r["start"] for r in rs),
            })
        return merged

    def _semantic_split(self, ranges: list, provider):
        """LLM 读全文语义，输出分镜分组（ranges 索引）。返回 groups 或 None"""
        n = len(ranges)
        lines = [f"[{i}] {r['start']:.1f}-{r['end']:.1f}s {r.get('trimmed', r.get('quote', ''))}"
                 for i, r in enumerate(ranges)]
        full_text = "\n".join(lines)
        prompt = (
            f"以下是口播视频的 {n} 个连续片段（带索引和起止秒）：\n{full_text}\n\n"
            "请按语义切分镜：读全文，识别话题切换、信息点、转折点，把连续片段分组为视觉场景。\n"
            "规则：\n"
            "1. 每个场景是语义连贯的一段（一个话题/一个信息点/一个转折点）\n"
            "2. 场景数由内容自然决定，不设上限\n"
            "3. 所有片段必须被覆盖，不重不漏，按顺序\n"
            f"4. 只输出 JSON：{{\"scenes\": [[起始索引, 结束索引], ...]}}，索引范围 0-{n-1}\n"
        )
        try:
            raw = provider.call("storyboard_split", prompt,
                system="你是视频分镜导演。只输出 JSON，覆盖所有片段不重不漏按顺序。",
                max_tokens=300)
            return self._parse_split(raw, n)
        except Exception:
            return None

    def _parse_split(self, raw: str, n: int):
        """解析 LLM 分镜分组，校验覆盖所有片段不重不漏（音画同步的关键）"""
        import json as _json
        if not raw:
            return None
        m = re.search(r'\{[^{}]*"scenes"[^{}]*\}', raw, re.DOTALL)
        if not m:
            m = re.search(r'\[\[[^\]]*\](?:,[^\]]*\])*\]', raw)
        if not m:
            return None
        try:
            data = _json.loads(m.group(0))
        except Exception:
            return None

        groups = data.get("scenes") if isinstance(data, dict) else data
        if not isinstance(groups, list) or not groups:
            return None

        covered = []
        for g in groups:
            if isinstance(g, list) and len(g) >= 2:
                a, b = int(g[0]), int(g[1])
                if not (0 <= a <= b < n):
                    return None  # 越界
                covered.extend(range(a, b + 1))
            elif isinstance(g, int):
                if not (0 <= g < n):
                    return None
                covered.append(g)
            else:
                return None

        # 不重不漏：覆盖所有 0..n-1
        if sorted(covered) != list(range(n)):
            return None
        return groups

    def _merge(self, ranges: list) -> list:
        """回退：只合并碎片（<8字），正常段独立成场景（自由场景数，不锁死）"""
        n = len(ranges)
        if n <= 3:
            return [{
                "start": r["start"], "end": r["end"], "beat": r.get("beat", ""),
                "narration": r.get("trimmed", r.get("quote", "")),
            } for r in ranges]

        # 一遍合并：只合并碎片（<8字），正常段独立成场景（自由场景数，不锁死）
        merged = [{
            "start": ranges[0]["start"], "end": ranges[0]["end"],
            "beat": ranges[0].get("beat", ""),
            "narration": ranges[0].get("trimmed", ranges[0].get("quote", "")),
            "real_dur": ranges[0]["end"] - ranges[0]["start"],
        }]
        for i in range(1, n):
            r = ranges[i]
            txt = r.get("trimmed", r.get("quote", ""))
            # 只合并碎片（<8字），不吞掉正常段
            if len(merged[-1]["narration"]) < 8 or len(txt) < 8:
                merged[-1]["end"] = r["end"]
                merged[-1]["narration"] += txt
                merged[-1]["real_dur"] += r["end"] - r["start"]
                # keep the more meaningful beat
                if r.get("beat") and r["beat"] not in ("CONTEXT",):
                    merged[-1]["beat"] = r["beat"]
            else:
                merged.append({
                    "start": r["start"], "end": r["end"],
                    "beat": r.get("beat", ""), "narration": txt,
                    "real_dur": r["end"] - r["start"],
                })

        # 🔴 自由场景数：不再强制合并到 ≤5，按内容语义自然决定
        # （相邻短段 <15 字已在上面合并，这里保留自然段落数）
        return merged

    def _detect_type(self, text: str, beat: str, is_first: bool, is_last: bool) -> str:
        """从文本内容推断 visual_type"""
        # Numbers → data_impact
        if any(kw in text for kw in ["%", "倍", "万", "亿", "飙升", "翻倍", "准确率",
                                       "处理速度", "效率", "提升", "增长", "下降", "数据"]):
            return "data_impact"
        # Compare/conflict (not first scene)
        if any(kw in text for kw in ["vs", "对比", "但是", "却", "而", "不过", "相反",
                                       "挑战", "风险", "偏见", "冲击"]) and not is_first:
            return "compare"
        # Flow/process
        if any(kw in text for kw in ["首先", "然后", "最后", "步骤", "流程", "背后",
                                       "架构", "系统", "混合", "强化"]):
            return "flow"
        # List
        if any(kw in text for kw in ["第一", "第二", "包括", "比如", "颠覆"]):
            return "list_alert"
        # Tech
        if any(kw in text for kw in ["AI", "GPT", "模型", "算法", "代码", "开源"]):
            if any(kw in text for kw in ["系统", "架构", "混合专家"]):
                return "hud"
        # Time
        if any(kw in text for kw in ["时间", "发展", "未来", "普及", "改变"]) and not is_first:
            return "timeline_event"
        return "quote_hero"

    def _detect_chart(self, text: str, vt: str) -> str | None:
        """根据场景类型和内容推荐图表类型"""
        if vt == "data_impact":
            nums = re.findall(r'(\d+[%％]?)', text)
            if len(nums) >= 3:
                return "bar_chart"
            if any(kw in text for kw in ["趋势", "增长", "下降", "变化"]):
                return "line_chart"
            if any(kw in text for kw in ["占比", "份额", "比例", "构成"]):
                return "pie_chart"
            return "kpi_grid"
        if vt == "compare":
            return "bar_chart"
        if vt == "flow":
            return "kpi_grid"
        return None

    def _extract_elements(self, text: str, vt: str, concept: str = "", title_hint: str = "") -> list:
        """从口播文本和概念提取 key_elements"""
        elements = []
        import re as _re

        # Title: 优先用 LLM 产出的 title_hint，否则从 concept/narration 兜底
        title = title_hint.strip() if title_hint else ""
        if len(title) < 2:
            title = concept[:6]
        if len(title) < 2:
            title = text[:6]
        title = title.replace("，", "").replace("。", "").replace(" ", "").strip()
        # Never let VT descriptors leak as title
        vt_keywords = {"金句冲击","数据实证","对立碰撞","层层推进","要点拆解","科技界面","时间推演"}
        if title in vt_keywords or len(title) < 2:
            title = text[:6].replace("，","").replace("。","").strip()
        elements.append({"type": "title", "text": title[:8]})

        # Numbers only — no tags (Chinese NLP without jieba is unreliable)
        # 🔴 提取完整数字（带单位），"300万"→"300万"、"下降80%"→"80%"、"1/10"→"1/10"、"10倍"→"10倍"
        nums = _re.findall(r'(\d+(?:\.\d+)?(?:万|亿|千万|百万|倍|[%％]|/\d+)?)', text)
        for n in nums[:3]:
            elements.append({"type": "number", "text": n})

        return elements[:6]

    def _make_concept_llm(self, narration: str, provider):
        """LLM 生成标题+视觉隐喻。返回 (concept, title)。deepseek-chat（非推理）输出干净"""
        prompt = (
            "给这段口播提炼一个2-6字标题和一个15字以内的视觉隐喻。\n"
            "严格按格式输出两行：\n"
            "标题：xxx\n"
            "隐喻：xxx\n\n"
            f"口播：{narration[:80]}"
        )
        try:
            raw = provider.call("concept", prompt,
                system="你是视觉创意导演。输出两行：标题(2-6字)和隐喻(≤15字)，不要引号不要解释。",
                max_tokens=60)
            if raw and len(raw.strip()) > 2:
                title = ""
                concept = raw.strip()
                for line in raw.strip().split('\n'):
                    line = line.strip().strip('"\'“”')
                    if line.startswith("标题"):
                        title = line.split("：", 1)[-1].split(":", 1)[-1].strip().strip('"\'“”')
                    elif line.startswith("隐喻") or line.startswith("视觉隐喻"):
                        concept = line.split("：", 1)[-1].split(":", 1)[-1].strip().strip('"\'“”').strip('。')
                if not title or len(title) < 2:
                    title = concept[:6]
                if len(concept) > 2:
                    return concept[:40], title[:8]
        except Exception:
            pass
        return narration[:20], narration[:6]

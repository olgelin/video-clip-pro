"""HF build skill — HyperFrames composition + render with card enrichment
V6: LLM直出卡片HTML + 旧模板fallback"""
from __future__ import annotations
import sys, os, subprocess, shutil, time, json, re
from pathlib import Path
from core.base import SkillBase
from core.provider import Provider
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.hf_card_builder import build_hyperframes_composition, render_hyperframes, _detect_orientation
from skills.hf_build.stage_template import build_card

_PROMPTS_DIR = Path(__file__).parent / "prompts"

def _load_prompt(name):
    p = _PROMPTS_DIR / f"{name}.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def _css_has_chinese(html: str) -> bool:
    """检测 <style> 区域是否含中文（LLM 把中文写进 CSS 会导致 HyperFrames 编译失败）。"""
    for m in re.finditer(r'<style[^>]*>(.*?)</style>', html, re.DOTALL | re.IGNORECASE):
        css = m.group(1)
        css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)          # 去注释
        css = re.sub(r'content\s*:\s*["\'][^"\']*["\']', '', css)      # 去 content 字符串
        if re.search(r'[\u4e00-\u9fff]', css):
            return True
    return False


def _is_empty_card(html: str) -> bool:
    """检测空内容/坏卡片：内容过短、省略号占位符、无动画 script、无 GSAP 动画、无文字内容。
    这类卡片渲染出来是空壳/静态，应 fallback 到模板卡片。"""
    if len(html) < 800:
        return True
    if "..." in html:
        return True
    if "<script" not in html:
        return True
    if not re.search(r'\btl\.(?:from|to|fromTo)\(', html):
        return True
    # 🔴 排除 script/style 里的代码，只检测「可见文字」（div 里的实际标题/数据）。
    # 旧逻辑 re.sub 会把 <script> 里的 JS（var tl=gsap...）也算文字 → 空 div + 有 script 的卡片漏检。
    visible = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', html, flags=re.DOTALL)
    visible_text = re.sub(r'<[^>]+>', '', visible).strip()
    if len(visible_text) < 2:
        return True
    return False


_ANIM_STMT = re.compile(r'tl\.(?:to|fromTo)\((?:[^()]|\([^()]*\))*\)')


def _is_weak_animation(html: str) -> bool:
    """检测持续微动动画质量：持续动画(repeat≥2)不足2个，或幅度太小肉眼看不出。True=弱(应fallback)。

    只匹配 tl.to/tl.fromTo（入场动画 tl.from 的 scale:0 不误判），区分"持续微动"与"一次性入场"。"""
    stmts = _ANIM_STMT.findall(html)
    sustained = [s for s in stmts if re.search(r'repeat\s*:\s*([2-9])', s)]
    if len(sustained) < 2:
        return True
    strong = 0
    for s in sustained:
        scales = [float(x) for x in re.findall(r'scale\s*:\s*([\d.]+)', s)]
        if any(v >= 1.12 or v <= 0.88 for v in scales):
            strong += 1
            continue
        ops = [float(x) for x in re.findall(r'opacity\s*:\s*([\d.]+)', s)]
        if any(v <= 0.4 for v in ops):
            strong += 1
            continue
        ys = [float(x) for x in re.findall(r'\by\s*:\s*(-?[\d.]+)', s)]
        if any(abs(v) >= 100 for v in ys):
            strong += 1
            continue
        lefts = [float(x) for x in re.findall(r'left\s*:\s*[\'"]?(-?[\d.]+)%', s)]
        if any(abs(v) >= 50 for v in lefts):
            strong += 1
            continue
    return strong < 2


def _card_quality_check(html: str):
    """卡片质量门禁：空内容 / 中文CSS / 动画弱 → (False, 原因)；合格 → (True, '')。

    LLM 输出偶发坏卡，此门禁在进入渲染前拦截，fallback 到保证质量的模板卡。"""
    if _is_empty_card(html):
        return False, "空内容"
    if _css_has_chinese(html):
        return False, "中文CSS"
    if _is_weak_animation(html):
        return False, "动画弱(幅度不足/不持续)"
    return True, ""


ENRICH_PROMPT = """你是知识科普类短视频的**PPT视觉设计师**。你的任务是把口播文字转化成视觉卡片——像Keynote幻灯片一样有数据、有图表、有对比，不只是一行字。

🔴 核心使命：每张卡片必须有至少一个"视觉锚点"——数字、对比、图标阵列、进度条、徽章链——让观众"看到信息"而不只是"听到文字"。

## 字段说明
- headline: 核心观点（6-18字），PPT标题风格
- subtext: 支撑说明（8-30字），可为""
- metric: 数字指标（"3倍""85%""1000万"），必须从原文提取，没有则填null
- emotion: "urgent"/"tense"/"neutral"/"hopeful"/"triumphant"
- scene_type: "spotlight"/"alert"/"struggle"/"breakthrough"/"process"/"context"
- visual_keyword: 1-3个英文词（见下方词库），用于图标和背景
- data_points: 数据点列表 [{"label":"指标名","value":"数值"}], 🔴必须至少1个！
- icon_hint: 1个emoji
- layout_hint: ⭐选最能展示内容的排版——
  "big-number" 有数字→大字冲击 | "comparison" 有对比→左右对照 |
  "bullets" 有要点→列表拆解 | "quote-card" 金句→引号卡片 |
  "title-only" 仅当确实没有任何可视觉化的内容时
- bullets: layout_hint="bullets"时必填2-4条（8-15字/条）
- key_takeaway: 底部金句（10-20字）
- visual_style: "minimal"/"bold"/"editorial"/"tech"

## 视觉关键词库（visual_keyword）
科技: signal,network,code,data,chip,robot,ai,brain
问题: broken,error,block,barrier,fire,crack,dark,warning
解决: fix,repair,unlock,key,light,path,bridge,rocket,growth
数据: numbers,chart,scale,trend,percent,compare,rank
流程: steps,arrow,check,target,build,evolve,cycle,layer

## 🔴 Few-Shot 示例（严格模仿！）

示例1 — 有数字：
口播："接入率已经超过50%了，全球开发者都在用"
→ {"headline":"AI工具接入率超50%","subtext":"全球开发者加速采用","metric":"50%+","emotion":"triumphant","scene_type":"breakthrough","visual_keyword":"chart,trend,rocket","data_points":[{"label":"接入率","value":"50%+"},{"label":"覆盖","value":"全球"}],"icon_hint":"📊","layout_hint":"big-number","bullets":[],"key_takeaway":"AI编程已成主流","visual_style":"tech"}

示例2 — 有对比：
口播："以前一个人只能干一个程序员的活，现在一个人顶十个"
→ {"headline":"1人 = 10人效率","subtext":"AI让个体生产力飙升","metric":"10x","emotion":"triumphant","scene_type":"breakthrough","visual_keyword":"compare,rocket,growth","data_points":[{"label":"过去","value":"1人=1人"},{"label":"现在","value":"1人=10人"}],"icon_hint":"⚡","layout_hint":"comparison","bullets":["过去：单兵作战效率低","现在：AI加持以一当十"],"key_takeaway":"AI是生产力倍增器","visual_style":"bold"}

示例3 — 叙事拆解：
口播："AI的体系就像一座金字塔，底层是基础模型，中间是工具链，顶层是应用"
→ {"headline":"AI体系三层金字塔","subtext":"从基础模型到应用层","metric":null,"emotion":"neutral","scene_type":"context","visual_keyword":"build,layer,pyramid","data_points":[{"label":"底层","value":"基础模型"},{"label":"中层","value":"工具链"},{"label":"顶层","value":"应用"}],"icon_hint":"🔺","layout_hint":"bullets","bullets":["底层：基础模型提供算力","中层：工具链连接生态","顶层：应用触达用户"],"key_takeaway":"三层架构支撑AI生态","visual_style":"editorial"}

示例4 — 金句：
口播："不会用AI的人，就像10年前不会用智能手机的人"
→ {"headline":"不会AI=10年前不会用手机","subtext":"时代淘汰不拥抱工具的人","metric":null,"emotion":"urgent","scene_type":"alert","visual_keyword":"time,compare,warning","data_points":[{"label":"类比","value":"AI vs 智能手机"}],"icon_hint":"⚠️","layout_hint":"quote-card","bullets":[],"key_takeaway":"拥抱AI，否则被淘汰","visual_style":"bold"}

## 输入
{segments_json}

## 只输出JSON数组（不要markdown包裹）：
[{{"headline":"...","subtext":"...","metric":null,"emotion":"neutral","scene_type":"context","visual_keyword":"...","data_points":[{{"label":"...","value":"..."}}],"icon_hint":"...","layout_hint":"bullets","bullets":["要点1","要点2"],"key_takeaway":"...","visual_style":"tech"}}, ...]"""

CARD_HTML_PROMPT_TEMPLATE = """你是口播视频知识卡片设计师。根据下面的卡片信息，生成一个完整的卡片HTML。

## 卡片信息
- 标题: {headline}
- 副文: {subtext}
- 节奏: {beat_type}
- 情绪: {emotion}
- 布局: {layout_hint}
- 金句: {key_takeaway}
{data_section}

## 尺寸参考
{size_hint}

{scene_prompt}

## 输出
只输出完整HTML（div + script），不要解释文字。
"""

DATA_SECTION_HAS = """🔴 有真实数据可用：
- 核心数字: {metric}（放大展示，GSAP弹入）
- 数据: {data_points_str}（做成badge条/进度条/对比条/信号条）
- 从菜单选数据元素"""

DATA_SECTION_NONE = """🔴 没有真实数据——不要编造数字！
- 用图标浮标(emoji/图标+浮动动画) + 脉冲灯表达情绪
- 或用引用引号(大引号+斜体)放大金句
- 绝不要塞假数字或无意义的进度条"""

# V19: 口播原文 + 结构化数据 → 画面一步到位
CARD_DIRECT_PROMPT = """你是口播视频卡片设计师。下面是一段口播原文、它的结构化分析、和节奏类型。

## 口播原文（这是讲话人实际说的话）
{quote}

## 结构化数据（从原文提取的关键信息）
- 标题: {headline}
- 副文: {subtext}
- 核心数字: {metric}
- 数据点: {data_points_str}
- 金句: {key_takeaway}

## 节奏类型
{beat_type} / 情绪: {emotion} / 布局: {layout_hint}

严格按照下方 scene_system 的完整规范生成卡片 HTML——配色按情绪选色板、背景选 2-3 种元素、放 1-3 个数据元素、参照 few-shot 示例的风格。

{scene_prompt}

## 输出
只输出完整HTML（div + script），不要解释文字。
"""


class Hf_build(SkillBase):
    name = "hf_build"

    def execute(self, context: dict) -> dict:
        # 🔴 分镜导演模式（2026-09-11）：storyboard 已产出 scenes（语义分镜），
        # 每个语义单元 = 一张信息卡（按 visual_type 选类型 + 出场动画），替代旧「每句一卡堆叠」。
        scenes = context.get("scenes", [])
        if scenes:
            return self._scene_cards(context, scenes)

        edl = context.get("edl", {})
        words = context.get("words", [])
        output_dir = Path(context.get("output_dir", "test_output"))
        video_path = Path(context.get("video_path", ""))
        provider = context.get("provider")

        # Step 1: LLM 提取卡片结构化数据（保留给 fallback 用）
        edl = self._enrich_cards(edl, provider)

        # 🔴 对齐 PIP：检测输入视频方向，用于卡片尺寸（竖屏 500-600px 宽 / 横屏 560-680px 宽）
        orientation = context.get("orientation") or _detect_orientation(str(video_path))

        # Step 1.5: 语义分段（62 片段 → N 画面组，减少 LLM 调用 + 卡片依次弹入）
        edl = self._segment_groups(edl, provider)

        # Step 2: V15 口播→HTML一步到位（主流程）
        print("\n[6/6] Generating card HTML — direct quote→visual (V15)...")
        try:
            edl = self._llm_card_html_direct(edl, provider, orientation)
            if edl:
                print("      Using direct quote→visual V15 cards")
        except Exception as e:
            print(f"      V15 failed ({e}), trying V10 hybrid...")
            try:
                edl = self._llm_card_html(edl, provider)
                print("      Using V10 hybrid cards")
            except Exception as e2:
                print(f"      All LLM failed ({e2}), falling back to templates")

        # Step 3: 构建 HyperFrames composition + 渲染
        try:
            hf_dir = build_hyperframes_composition(edl, words, output_dir, video_path,
                layout_mode=context.get("layout_mode", "card"))
            if hf_dir:
                polished = render_hyperframes(hf_dir)
                if polished:
                    return {"final_polished": str(polished), "edl": edl}
        except Exception as e:
            print(f"      HyperFrames error: {e}")
        return {"final_polished": str(output_dir / "final.mp4")}

    def _scene_cards(self, context: dict, scenes: list) -> dict:
        """🔴 分镜导演模式：storyboard 的 scenes（语义分镜）→ 每个语义单元一张信息卡。

        复用 _llm_card_html_direct 的「透明浮空面板壳 build_card + scene_system 内容驱动」，
        但输入从「每句 card 字段」改为「每个语义单元的 visual_type + key_elements + mood」，
        实现「一个语义单元一张信息卡 + 出场动画」，替代旧「每句一卡堆叠」。
        """
        provider = context.get("provider")
        output_dir = Path(context.get("output_dir", "test_output"))
        video_path = Path(context.get("video_path", ""))
        words = context.get("words", [])
        orientation = context.get("orientation") or _detect_orientation(str(video_path))

        scene_prompt = _load_prompt("scene_system")
        if not scene_prompt:
            print("      scene_system.md 缺失，分镜信息卡跳过")
            return {}

        # visual_type → 卡片 layout（7 种视觉类型映射到 5 种卡片布局）
        _VT_LAYOUT = {
            "data_impact": "big-number",
            "quote_hero": "quote-card",
            "compare": "comparison",
            "flow": "bullets",
            "list_alert": "bullets",
            "timeline_event": "bullets",
            "hud": "bullets",
        }
        # 中文 mood → emotion（scene_system 按 emotion 选色板）
        _MOOD_EMOTION = {
            "冲击": "triumphant", "悬念": "urgent",
            "紧张": "tense", "对立": "tense", "冲突": "urgent", "焦虑": "tense",
            "开阔": "hopeful", "希望": "hopeful",
        }

        def _gen_scene(idx: int, scene: dict):
            narration = scene.get("narration", "")
            if not narration:
                return idx, None
            vt = scene.get("visual_type", "quote_hero")
            ke = scene.get("key_elements", []) or []
            dur = max(1.0, float(scene.get("duration", 5)))
            mood = scene.get("mood", "") or ""

            # 从 key_elements 提取标题 + 数字（兜底）
            title = next((e["text"] for e in ke if e.get("type") == "title"), "")
            nums = [e["text"] for e in ke if e.get("type") == "number"]

            # 🔴 ENRICH 提取结构化信息（headline/data/bullets/takeaway/layout），
            # 让卡片显示「提炼的信息卡」（清单/对比/数据），而非「整段口播原文」
            card = {}
            try:
                enrich_prompt = ENRICH_PROMPT.replace(
                    "{segments_json}", json.dumps([{"beat": "INFO", "quote": narration}], ensure_ascii=False))
                enrich_raw = provider.call("card_enrich", enrich_prompt)
                enrich = provider.extract_json(enrich_raw)
                if isinstance(enrich, list) and enrich:
                    card = enrich[0] or {}
            except Exception:
                card = {}

            headline = card.get("headline") or title or narration[:8]
            subtext = card.get("subtext", "")
            metric = card.get("metric") or (nums[0] if nums else "")
            data_points = card.get("data_points", []) or []
            data_str = "、".join([f'{d.get("label", "")}:{d.get("value", "")}' for d in data_points[:3]])
            takeaway = card.get("key_takeaway", "")
            layout = card.get("layout_hint") or _VT_LAYOUT.get(vt, "quote-card")
            emotion = card.get("emotion") or "neutral"
            if emotion == "neutral":
                for mk, me in _MOOD_EMOTION.items():
                    if mk in mood:
                        emotion = me
                        break

            cw, ch = self._card_size(layout, orientation)

            prompt = CARD_DIRECT_PROMPT.format(
                quote=narration, headline=headline, subtext=subtext,
                metric=metric, data_points_str=data_str,
                key_takeaway=takeaway, beat_type="INFO",
                emotion=emotion, layout_hint=layout,
                scene_prompt=scene_prompt,
            )

            content = None
            for _attempt in range(2):
                try:
                    raw = provider.call("card_direct", prompt)
                    if raw and len(raw) > 50 and not raw.startswith("[ERROR"):
                        h = raw.strip()
                        if "```html" in h:
                            h = h.split("```html")[1].split("```")[0].strip()
                        elif "```" in h:
                            h = h.split("```")[1].split("```")[0].strip()
                        if "<div" in h and "</div>" in h and _card_quality_check(h)[0]:
                            content = h
                            break
                except Exception:
                    pass

            if content:
                return idx, build_card(idx, dur, emotion, cw, ch, content)
            return idx, None

        # 并行生成（4 并发），按下标写回 scenes 保持顺序
        from concurrent.futures import ThreadPoolExecutor, as_completed
        llm_count = 0
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(_gen_scene, idx, scene): idx for idx, scene in enumerate(scenes)}
            for fut in as_completed(futures):
                idx, html = fut.result()
                if html:
                    scenes[idx]["_llm_html"] = html
                    llm_count += 1
        print(f"      分镜信息卡: {llm_count}/{len(scenes)} 卡（每语义单元一张）")

        # scenes → ranges（供 build_hyperframes_composition 生成字幕 captions + seg_offsets）
        ranges = []
        for idx, scene in enumerate(scenes):
            if not scene.get("_llm_html"):
                continue
            ranges.append({
                "start": scene.get("final_start", 0),
                "end": scene.get("final_end", scene.get("final_start", 0) + scene.get("duration", 5)),
                "beat": "INFO",
                "quote": scene.get("narration", ""),
                "card_layout": _VT_LAYOUT.get(scene.get("visual_type", "quote_hero"), "quote-card"),
                "_llm_html": scene["_llm_html"],
            })

        # 🔴 合并成一个总 HTML（配音驱动 + 切换动画）：一个 beat 覆盖整个视频，GSAP 控制每卡出场/退场
        cards_html = self._build_cards_html(scenes, orientation, _VT_LAYOUT)
        total_dur = round(sum(float(s.get("duration", 5)) for s in scenes if s.get("_llm_html")), 2)

        render_edl = {
            "ranges": ranges,
            "_segment_html": [{"start": 0, "dur": total_dur, "theme": "", "html": cards_html}],
        }
        try:
            hf_dir = build_hyperframes_composition(render_edl, words, output_dir, video_path,
                                                   layout_mode="card", orientation=orientation)
            if hf_dir:
                polished = render_hyperframes(hf_dir)
                if polished:
                    return {"final_polished": str(polished), "edl": render_edl}
        except Exception as e:
            print(f"      分镜渲染错误: {e}")
        return {}

    def _build_cards_html(self, scenes: list, orientation: str, vt_layout: dict) -> str:
        """合并 N 张信息卡成一个总 HTML（绝对定位 + GSAP 出场/退场时间线）。

        配音驱动：每张卡在 final_start（讲到对应语义单元）入场，下一张前 0.4s 淡出（切换动画）。
        全部卡在一个 HTML 里，window.__timelines["beat-0"] 由 HyperFrames seek 驱动。
        """
        # 🔴 位置铁律（用户定版）：卡片放【左右两侧】不居中（避开人物）。
        #    横屏：左侧/右侧垂直居中；竖屏：上半部分区域、靠左/靠右。
        #    左右两侧交替（idx%2），不做居中、不做底部。
        pos_styles = {
            "portrait": [
                "left:30px;top:200px",
                "right:30px;top:200px",
            ],
            "landscape": [
                "left:30px;top:50%;transform:translateY(-50%)",
                "right:30px;top:50%;transform:translateY(-50%)",
            ],
        }
        ps = pos_styles[orientation]

        card_divs = []
        stmts = []
        for idx, scene in enumerate(scenes):
            if not scene.get("_llm_html"):
                continue
            html = scene["_llm_html"]
            # 去掉 build_card 的 data-composition-id/data-width/data-height（总 HTML 内部元素不是独立 composition）
            html = html.replace(' data-composition-id="card"', '')
            html = re.sub(r' data-width="\d+"', '', html)
            html = re.sub(r' data-height="\d+"', '', html)
            # 🔴 去掉 LLM 的 <script>（tl.from opacity:0 在单一 composition 下被 HyperFrames seek 冻结→文字不显示；
            #    且 5 卡共用 #card/#headline 等 id 会串）。元素级出场 + 微动改由代码层统一 timeline 注入。
            html = re.sub(r'<script>.*?</script>', '', html, flags=re.DOTALL)
            start = round(float(scene.get("final_start", 0)), 2)
            dur = round(float(scene.get("duration", 5)), 2)
            layout = vt_layout.get(scene.get("visual_type", "quote_hero"), "quote-card")
            cw, ch = self._card_size(layout, orientation)
            pos = ps[idx % 2]
            card_divs.append(
                f'<div class="seg-card" data-seg="{idx}" style="position:absolute;{pos};width:{cw}px;height:{ch}px;opacity:0;">{html}</div>'
            )
            # 入场（配音讲到 → 卡出场）
            stmts.append(f'tl.fromTo(".seg-card[data-seg=\'{idx}\']",{{opacity:0,y:44,scale:0.92}},{{opacity:1,y:0,scale:1,duration:0.45,ease:"back.out(1.6)"}},{start});')
            # 🔴 信息点逐个弹出（跟着口播语音）：卡片内非装饰子元素 stagger 依次入场
            _decor = ":not(.glow):not(.glow-second):not(.particle):not(.pulse-dot):not(.icon-float):not(.light-scan):not(#light-scan)"
            stmts.append(f'tl.fromTo(".seg-card[data-seg=\'{idx}\'] #card > *{_decor}",{{opacity:0,y:20}},{{opacity:1,y:0,duration:0.3,stagger:0.12,ease:"power3.out"}},{round(start + 0.15, 2)});')
            # 退场（下一张卡前 0.4s 淡出 = 切换动画）
            exit_t = round(start + dur - 0.4, 2)
            if exit_t > start + 0.5:
                stmts.append(f'tl.to(".seg-card[data-seg=\'{idx}\']",{{opacity:0,y:-30,duration:0.4,ease:"power1.in"}},{exit_t});')

        return (
            '<div class="seg-panel" data-composition-id="beat-0" style="position:absolute;inset:0;width:100%;height:100%;">'
            + "".join(card_divs)
            + '<script>(function(){var tl=gsap.timeline({paused:true});'
            + "".join(stmts)
            + 'window.__timelines["beat-0"]=tl;})();</script>'
            + '</div>'
        )

    def _segment_groups(self, edl: dict, provider) -> dict:
        """语义分段：把 ranges 按语义聚成 N 个画面组，存到 edl['_segments']。

        每个 segment = {idxs, theme, start, dur}。片段太少(<6)不分段返回原 edl（走逐句逻辑）。
        分段失败/分组非法静默返回原 edl，不影响主流程（保证可回滚、不崩管道）。
        """
        ranges = edl.get("ranges", [])
        if not ranges or len(ranges) < 6 or not isinstance(provider, Provider):
            return edl

        # 构造片段列表（编号 + 节奏 + 文本）
        lines = []
        for i, r in enumerate(ranges):
            beat = r.get("beat", "INFO")
            text = r.get("text", "") or r.get("quote", "")
            if not text:
                continue
            lines.append(f"[{i}] {beat} | {text}")
        if not lines:
            return edl

        prompt_tpl = _load_prompt("segment")
        if not prompt_tpl:
            print("      segment.md 缺失，跳过语义分段")
            return edl
        prompt = prompt_tpl.replace("{segments_json}", "\n".join(lines))

        try:
            raw = provider.call("understand", prompt)
        except Exception:
            return edl
        if not raw or raw.startswith("[ERROR"):
            return edl
        data = provider.extract_json(raw)
        if not data or not isinstance(data.get("groups"), list):
            print("      分段结果解析失败，走逐句逻辑")
            return edl

        groups = data["groups"]
        # 校验分组：覆盖全部、无重叠、顺序正确（非法则走逐句逻辑兜底）
        segs = []
        prev_end = -1
        for g in groups:
            try:
                s, e = int(g.get("start", 0)), int(g.get("end", 0))
            except (ValueError, TypeError):
                return edl
            if s < 0 or e >= len(ranges) or s > e or s != prev_end + 1:
                return edl
            segs.append({"idxs": list(range(s, e + 1)), "theme": str(g.get("theme", ""))[:8]})
            prev_end = e
        if not segs or segs[0]["idxs"][0] != 0 or segs[-1]["idxs"][-1] != len(ranges) - 1:
            return edl

        # 算每个 segment 的合成轴 start / dur（和 build_hyperframes_composition 的 seg_offsets 一致）
        seg_offsets = []
        acc = 0.0
        for r in ranges:
            seg_offsets.append(acc)
            acc += r["end"] - r["start"]
        for seg in segs:
            i0, i1 = seg["idxs"][0], seg["idxs"][-1]
            seg["start"] = seg_offsets[i0]
            seg["dur"] = seg_offsets[i1] + (ranges[i1]["end"] - ranges[i1]["start"]) - seg_offsets[i0]

        edl["_segments"] = segs
        print(f"      语义分段: {len(ranges)} 片段 → {len(segs)} 画面组")
        return edl

    def _llm_segment_html(self, edl: dict, provider, orientation: str = "portrait") -> dict:
        """语义分段模式：每段生成一个 HTML（段内多卡 + 代码注入依次弹入时间线）。
        存到 edl['_segment_html'] = [{start, dur, theme, html}]。任一段失败则清空 _segments 走逐句逻辑兜底。"""
        segments = edl.get("_segments", [])
        ranges = edl.get("ranges", [])
        if not segments or not ranges or not isinstance(provider, Provider):
            return edl

        seg_tpl = _load_prompt("segment_html")
        if not seg_tpl:
            edl.pop("_segments", None)
            return edl

        # 合成轴偏移（和 _segment_groups 一致）
        seg_offsets = []
        acc = 0.0
        for r in ranges:
            seg_offsets.append(acc)
            acc += r["end"] - r["start"]

        results = []
        for si, seg in enumerate(segments):
            cards = []
            for idx in seg["idxs"]:
                r = ranges[idx]
                rel_t = round(seg_offsets[idx] - seg["start"], 2)
                cards.append({
                    "i": len(cards),
                    "headline": r.get("card_headline", "") or r.get("text", "")[:18] or r.get("quote", "")[:18],
                    "subtext": r.get("card_subtext", ""),
                    "metric": r.get("card_metric") or "",
                    "emotion": r.get("card_emotion", "neutral"),
                    "layout": r.get("card_layout", "bullets"),
                    "data": r.get("card_data", []) or [],
                    "takeaway": r.get("card_takeaway", ""),
                    "bullets": r.get("card_bullets", []) or [],
                    "rel_t": rel_t,
                })

            prompt = seg_tpl.replace("{theme}", seg.get("theme", "")).replace(
                "{cards_json}", json.dumps(cards, ensure_ascii=False))

            content = None
            for _attempt in range(2):
                try:
                    raw = provider.call("card_direct", prompt)
                    if raw and len(raw) > 100 and not raw.startswith("[ERROR"):
                        h = raw.strip()
                        if "```html" in h:
                            h = h.split("```html")[1].split("```")[0].strip()
                        elif "```" in h:
                            h = h.split("```")[1].split("```")[0].strip()
                        if "<div" in h and "seg-card" in h:
                            content = h
                            break
                except Exception:
                    pass

            if not content:
                print(f"      段 {seg.get('theme','')[:8]} 生成失败 → 走逐句逻辑兜底")
                edl.pop("_segments", None)
                return edl

            html = self._wrap_segment_html(content, cards, "beat-" + str(si), orientation)
            results.append({"start": seg["start"], "dur": seg["dur"], "theme": seg.get("theme", ""), "html": html})

        edl["_segment_html"] = results
        print(f"      段 HTML: {len(results)}/{len(segments)} 段生成成功")
        return edl

    def _wrap_segment_html(self, content: str, cards: list, beat_id: str, orientation: str = "portrait") -> str:
        """包浮空面板壳 + 代码注入「依次弹入」时间线（注册到 window.__timelines[beat_id]）。
        每张卡在 rel_t 时刻弹出，rel_t = 该句配音在段内的相对偏移。
        🔴 位置铁律（2026-09-10 用户拍板）：横屏人物居中 → 卡片靠左固定宽避开人物；
        竖屏卡片居中（竖屏人物占比小 + 半透明面板透出人物，无所谓）。"""
        if orientation == "landscape":
            # 横屏：人物居中，卡片靠左堆叠（左对齐 + 上下撑满 + 垂直居中，避开中间人物，绝不居中挡脸）
            # 🔴 用 top:0+bottom:0 撑满（top:50% 在 body 高度 auto 下会失效）
            panel_style = (
                'position:absolute;left:0;top:0;bottom:0;width:600px;'
                'display:flex;flex-direction:column;justify-content:center;align-items:flex-start;'
                'padding:20px 24px;box-sizing:border-box;overflow:hidden;'
            )
        else:
            # 竖屏：卡片靠底部堆叠，避开中上部人物面部（visual-check 曾报「卡片大面积遮挡人物面部」）
            # 🔴 用 inset:0 全屏 + flex-end 靠底（bottom 定位在 HyperFrames sub-composition 渲染下不可靠，卡片会跑到顶部）
            panel_style = (
                'position:absolute;inset:0;width:100%;height:100%;'
                'display:flex;flex-direction:column;justify-content:flex-end;align-items:center;'
                'padding:0 44px 170px;box-sizing:border-box;overflow:hidden;'
            )
        # 🔴 框架层兜底：强制外层容器透明 + seg-card 半透明 + 边框蓝色（防 LLM 生成 background:#0d0f14 纯黑 / alpha 0.92 / 红橙绿边框遮挡人物）
        _guard = ('<style>.seg-panel>div{background:transparent!important;}'
                  '.seg-card{background-color:rgba(14,17,36,0.68)!important;'
                  'border-left-color:rgba(108,140,255,0.65)!important;}</style>')
        panel = (
            f'<div class="seg-panel" data-composition-id="{beat_id}" style="{panel_style}">'
            f'{_guard}'
            f'{content}</div>'
        )
        reveal = []
        for c in cards:
            t = c["rel_t"]
            reveal.append(
                f'tl.fromTo(".seg-card[data-seg=\'{c["i"]}\']",{{opacity:0,y:44,scale:0.92}},'
                f'{{opacity:1,y:0,scale:1,duration:0.45,ease:"back.out(1.6)"}},{t});'
            )
        gsap = (
            '<script>window.__timelines=window.__timelines||{};(function(){'
            'var tl=gsap.timeline({paused:true});'
            + "".join(reveal) +
            f'window.__timelines["{beat_id}"]=tl;}})();</script>'
        )
        return panel + gsap

    def _llm_card_html(self, edl: dict, provider) -> dict:
        """V6: LLM 为每张卡片直接生成 HTML。失败时保留旧数据用于 fallback。"""
        ranges = edl.get("ranges", [])
        if not ranges or not isinstance(provider, Provider):
            return edl

        scene_prompt = _load_prompt("scene_system")
        if not scene_prompt:
            print("      scene_system.md 缺失，跳过 LLM HTML")
            return edl

        SIZE_HINTS = {
            "big-number": "580-680px 宽×280-360px 高（大字冲击）",
            "comparison": "580-680px 宽×280-360px 高（左右对比）",
            "bullets": "500-620px 宽×260-340px 高（要点列表）",
            "quote-card": "400-500px 宽×200-280px 高（金句卡片）",
            "title-only": "400-480px 宽×160-240px 高（简洁标题）",
        }
        DEFAULT_SIZE = "480-520px 宽×240-320px 高"

        llm_count = 0
        fail_count = 0

        for r in ranges:
            if not r.get("quote"):
                continue

            headline = r.get("card_headline", "") or r.get("quote", "")[:18]
            subtext = r.get("card_subtext", "")
            metric = r.get("card_metric") or ""
            emotion = r.get("card_emotion", "neutral")
            layout = r.get("card_layout", "title-only")
            data_points = r.get("card_data", [])
            takeaway = r.get("card_takeaway", "")
            icon = r.get("card_icon", "")
            data_str = ", ".join([f'{d.get("label","")}:{d.get("value","")}' for d in data_points[:3]])
            beat_type = r.get("beat", "INFO")
            size_hint = SIZE_HINTS.get(layout, DEFAULT_SIZE)
            
            # 判断是否有真实数据
            has_data = bool(metric and metric != "null" and str(metric).strip()) or \
                       bool(data_points and len(data_points) > 0 and any(
                           d.get("value","") and str(d.get("value","")).strip() 
                           for d in data_points))
            data_section = DATA_SECTION_HAS.format(metric=metric, data_points_str=data_str) \
                if has_data else DATA_SECTION_NONE

            prompt = CARD_HTML_PROMPT_TEMPLATE.format(
                headline=headline, subtext=subtext, metric=metric,
                emotion=emotion, beat_type=beat_type, layout_hint=layout,
                data_points_str=data_str, key_takeaway=takeaway, icon_hint=icon,
                size_hint=size_hint, scene_prompt=scene_prompt,
                data_section=data_section
            )

            try:
                raw = provider.call("card_html", prompt)
                if raw and len(raw) > 50 and not raw.startswith("[ERROR"):
                    # 提取纯HTML（去掉可能的markdown包裹）
                    html = raw.strip()
                    if "```html" in html:
                        html = html.split("```html")[1].split("```")[0].strip()
                    elif "```" in html:
                        html = html.split("```")[1].split("```")[0].strip()

                    if "<div" in html and "</div>" in html and _card_quality_check(html)[0]:
                        r["_llm_html"] = html
                        llm_count += 1
                        continue

                fail_count += 1
            except Exception as e:
                fail_count += 1

        print(f"      LLM HTML: {llm_count}/{llm_count+fail_count} cards (fail={fail_count})")
        return edl

    def _card_size(self, layout: str, orientation: str) -> tuple:
        """卡片尺寸（照抄 hf_card_builder 的尺寸逻辑，对齐 PIP 框架层算尺寸）。"""
        if layout in ("big-number", "comparison"):
            return (680, 280) if orientation != "portrait" else (600, 300)
        elif layout == "bullets":
            return (620, 280) if orientation != "portrait" else (560, 300)
        elif layout == "quote-card":
            return (600, 220) if orientation != "portrait" else (540, 240)
        return (560, 260) if orientation != "portrait" else (500, 250)

    def _llm_card_html_direct(self, edl: dict, provider, orientation: str = "portrait") -> dict:
        """V19: 口播原文 + 结构化数据 → 画面一步到位。
        🔴 对齐 PIP：LLM 只生成卡片内容（标题/数据/装饰 + GSAP），透明浮空面板壳由
        stage_template.build_card 代码层写死（半透明渐变+圆角+发光边框，100% 稳定）。
        🔴 2026-09-08 并行化：逐张串行生成 HTML 太慢（每张 ~2min × 60+ 张 ≈ 2h），
        改 ThreadPoolExecutor 4 并发（~4 倍加速）。"""
        # 🔴 语义分段模式：有 _segments 就走段 HTML 生成（每段一个画面，段内多卡依次弹入）
        if edl.get("_segments"):
            return self._llm_segment_html(edl, provider, orientation)

        from concurrent.futures import ThreadPoolExecutor, as_completed

        ranges = edl.get("ranges", [])
        if not ranges or not isinstance(provider, Provider):
            return edl

        scene_prompt = _load_prompt("scene_system")
        if not scene_prompt:
            print("      scene_system.md missing, skip V19")
            return edl

        def _gen_one(idx, r):
            quote = r.get("quote", "")
            if not quote:
                return idx, None

            headline = r.get("card_headline", "") or r.get("quote", "")[:18]
            subtext = r.get("card_subtext", "")
            metric = r.get("card_metric", "")
            data_points = r.get("card_data_points", [])
            data_str = ", ".join([f'{d.get("label","")}:{d.get("value","")}' for d in data_points[:3]])
            takeaway = r.get("card_takeaway", "")
            beat_type = r.get("beat", "INFO")
            emotion = r.get("card_emotion", "neutral")
            layout = r.get("card_layout_hint", "bullets")
            cw, ch = self._card_size(layout, orientation)
            dur = max(0.5, (r.get("end", 0) - r.get("start", 0)))

            prompt = CARD_DIRECT_PROMPT.format(
                quote=quote, headline=headline, subtext=subtext,
                metric=metric, data_points_str=data_str,
                key_takeaway=takeaway, beat_type=beat_type,
                emotion=emotion, layout_hint=layout,
                scene_prompt=scene_prompt
            )

            content = None
            for _attempt in range(2):
                try:
                    raw = provider.call("card_direct", prompt)
                    if raw and len(raw) > 50 and not raw.startswith("[ERROR"):
                        h = raw.strip()
                        if "```html" in h:
                            h = h.split("```html")[1].split("```")[0].strip()
                        elif "```" in h:
                            h = h.split("```")[1].split("```")[0].strip()
                        if "<div" in h and "</div>" in h and _card_quality_check(h)[0]:
                            content = h
                            break
                except Exception:
                    pass

            if content:
                # 🔴 对齐 PIP：透明浮空面板壳由代码层 build_card 写死，LLM 只填内容
                return idx, build_card(idx, dur, emotion, cw, ch, content)
            return idx, None

        llm_count = 0
        fail_count = 0
        # 并行生成（4 并发），结果按下标写回 ranges 保持顺序
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(_gen_one, idx, r): idx for idx, r in enumerate(ranges) if r.get("quote")}
            for fut in as_completed(futures):
                idx, html = fut.result()
                if html:
                    ranges[idx]["_llm_html"] = html
                    llm_count += 1
                else:
                    fail_count += 1

        print(f"      V19 direct: {llm_count}/{llm_count+fail_count} cards (fail={fail_count})")
        return edl

    def _enrich_cards(self, edl: dict, provider) -> dict:
        """Use LLM to extract headline/subtext/metric from each segment's quote. Batched for reliability."""
        ranges = edl.get("ranges", [])
        if not ranges or not isinstance(provider, Provider):
            return edl

        # Build segments for prompt
        segs_for_prompt = []
        for r in ranges:
            quote = r.get("quote", "")
            beat = r.get("beat", "INFO")
            if quote:
                segs_for_prompt.append({"beat": beat, "quote": quote})

        if not segs_for_prompt:
            return edl

        # Batch: process 8 segments at a time to avoid LLM truncation
        BATCH_SIZE = 8
        enriched_all = []
        for batch_start in range(0, len(segs_for_prompt), BATCH_SIZE):
            batch = segs_for_prompt[batch_start:batch_start + BATCH_SIZE]
            prompt = ENRICH_PROMPT.replace("{segments_json}", json.dumps(batch, ensure_ascii=False))

            try:
                raw = provider.call("card_enrich", prompt)
                if not raw or raw.startswith("[ERROR"):
                    print(f"      Card enrich batch {batch_start}: LLM failed, using raw quotes")
                    for s in batch:
                        enriched_all.append({"headline": s["quote"][:18], "subtext": s["quote"][:30],
                            "metric": None, "emotion": "neutral", "scene_type": "context",
                            "visual_keyword": "", "data_points": [], "icon_hint": "",
                            "layout_hint": "title-only", "bullets": [], "key_takeaway": "", "visual_style": "tech"})
                    continue

                enriched = None
                try:
                    enriched = json.loads(raw)
                except:
                    enriched = provider.extract_json(raw)

                if not isinstance(enriched, list):
                    if isinstance(enriched, dict):
                        enriched = [enriched]
                    else:
                        enriched = []

                # Pad if fewer returned than requested
                while len(enriched) < len(batch):
                    s = batch[len(enriched)]
                    enriched.append({"headline": s["quote"][:18], "subtext": s["quote"][:30],
                        "metric": None, "emotion": "neutral", "scene_type": "context",
                        "visual_keyword": "", "data_points": [], "icon_hint": "",
                        "layout_hint": "title-only", "bullets": [], "key_takeaway": "", "visual_style": "tech"})

                enriched_all.extend(enriched[:len(batch)])

            except Exception as e:
                print(f"      Card enrich batch {batch_start} error: {e}")
                for s in batch:
                    enriched_all.append({"headline": s["quote"][:18], "subtext": s["quote"][:30],
                        "metric": None, "emotion": "neutral", "scene_type": "context",
                        "visual_keyword": "", "data_points": [], "icon_hint": "",
                        "layout_hint": "title-only", "bullets": [], "key_takeaway": "", "visual_style": "tech"})

        # Merge enriched data into ranges
        enriched_idx = 0
        for r in ranges:
            if r.get("quote") and enriched_idx < len(enriched_all):
                card = enriched_all[enriched_idx]
                r["card_headline"] = card.get("headline", "")
                r["card_subtext"] = card.get("subtext", "")
                r["card_metric"] = card.get("metric")
                r["card_emotion"] = card.get("emotion", "neutral")
                r["card_scene"] = card.get("scene_type", "context")
                r["card_vk"] = card.get("visual_keyword", "")
                r["card_data"] = card.get("data_points", [])
                r["card_icon"] = card.get("icon_hint", "")
                r["card_layout"] = card.get("layout_hint", "title-only")
                r["card_bullets"] = card.get("bullets", [])
                r["card_takeaway"] = card.get("key_takeaway", "")
                r["card_vstyle"] = card.get("visual_style", "tech")
                enriched_idx += 1

        headlines = [r.get("card_headline","") for r in ranges if r.get("card_headline")]
        scenes = [r.get("card_scene","?") for r in ranges if r.get("card_scene")]
        if headlines:
            print(f"      Card enrich: {len(headlines)}/{len(ranges)} enriched, scenes={set(scenes)}")

        return edl

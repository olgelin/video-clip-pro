"""HF build skill — HyperFrames composition + render with card enrichment
V6: LLM直出卡片HTML + 旧模板fallback"""
from __future__ import annotations
import sys, os, subprocess, shutil, time, json, re
from pathlib import Path
from core.base import SkillBase
from core.provider import Provider
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.hf_card_builder import build_hyperframes_composition, render_hyperframes

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
    text = re.sub(r'<[^>]+>', '', html).strip()
    if len(text) < 2:
        return True
    return False

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
        edl = context.get("edl", {})
        words = context.get("words", [])
        output_dir = Path(context.get("output_dir", "test_output"))
        video_path = Path(context.get("video_path", ""))
        provider = context.get("provider")

        # Step 1: LLM 提取卡片结构化数据（保留给 fallback 用）
        edl = self._enrich_cards(edl, provider)

        # Step 2: V15 口播→HTML一步到位（主流程）
        print("\n[6/6] Generating card HTML — direct quote→visual (V15)...")
        try:
            edl = self._llm_card_html_direct(edl, provider)
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
                layout_mode=context.get("layout_mode", "fullscreen"))
            if hf_dir:
                polished = render_hyperframes(hf_dir)
                if polished:
                    return {"final_polished": str(polished), "edl": edl}
        except Exception as e:
            print(f"      HyperFrames error: {e}")
        return {"final_polished": str(output_dir / "final.mp4")}

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

                    if "<div" in html and "</div>" in html and not _css_has_chinese(html) and not _is_empty_card(html):
                        r["_llm_html"] = html
                        llm_count += 1
                        continue

                fail_count += 1
            except Exception as e:
                fail_count += 1

        print(f"      LLM HTML: {llm_count}/{llm_count+fail_count} cards (fail={fail_count})")
        return edl

    def _llm_card_html_direct(self, edl: dict, provider) -> dict:
        """V19: 口播原文 + 结构化数据 → 画面一步到位。"""
        ranges = edl.get("ranges", [])
        if not ranges or not isinstance(provider, Provider):
            return edl

        scene_prompt = _load_prompt("scene_system")
        if not scene_prompt:
            print("      scene_system.md missing, skip V19")
            return edl

        llm_count = 0
        fail_count = 0

        for r in ranges:
            quote = r.get("quote", "")
            if not quote:
                continue

            headline = r.get("card_headline", "")
            subtext = r.get("card_subtext", "")
            metric = r.get("card_metric", "")
            data_points = r.get("card_data_points", [])
            data_str = ", ".join([f'{d.get("label","")}:{d.get("value","")}' for d in data_points[:3]])
            takeaway = r.get("card_takeaway", "")
            beat_type = r.get("beat", "INFO")
            emotion = r.get("card_emotion", "neutral")
            layout = r.get("card_layout_hint", "bullets")

            prompt = CARD_DIRECT_PROMPT.format(
                quote=quote, headline=headline, subtext=subtext,
                metric=metric, data_points_str=data_str,
                key_takeaway=takeaway, beat_type=beat_type,
                emotion=emotion, layout_hint=layout,
                scene_prompt=scene_prompt
            )

            try:
                raw = provider.call("card_direct", prompt)
                if raw and len(raw) > 50 and not raw.startswith("[ERROR"):
                    html = raw.strip()
                    if "```html" in html:
                        html = html.split("```html")[1].split("```")[0].strip()
                    elif "```" in html:
                        html = html.split("```")[1].split("```")[0].strip()

                    if "<div" in html and "</div>" in html and not _css_has_chinese(html) and not _is_empty_card(html):
                        r["_llm_html"] = html
                        llm_count += 1
                        continue

                fail_count += 1
            except Exception:
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

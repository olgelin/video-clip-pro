"""publish_meta — 发布元数据生成（标题/描述/标签）。

照抄 video-factory publish_meta（short_video.yaml stage15），适配 SkillBase 结构。
输入：context["script_data"]（口播稿，含 topic/mood/voiceover_sections）
输出：context["publish_meta"] + output/publish_meta.json
"""
from __future__ import annotations
import json, re
from pathlib import Path
from core.base import SkillBase


class PublishMeta(SkillBase):
    name = "publish_meta"

    def execute(self, context: dict) -> dict:
        script = context.get("script_data", {})
        out_dir = Path(context.get("output_dir", "."))

        # 兜底：context 无 script_data 时读 step03_script.json
        if not script:
            sp = out_dir / "step03_script.json"
            if sp.exists():
                try:
                    script = json.loads(sp.read_text(encoding="utf-8"))
                except Exception:
                    script = {}

        topic = script.get("topic", "") or context.get("topic", "")
        sections = script.get("voiceover_sections", []) or script.get("scenes", [])
        full_text = "\n".join(
            s.get("content", "") or s.get("voiceover", "") for s in sections
        )

        if not topic and not full_text:
            print("  [publish-meta] ❌ 无口播稿，跳过")
            return context

        meta = self._generate(topic, script, full_text, context.get("provider"))
        if not meta:
            print("  [publish-meta] ❌ LLM 生成失败")
            return context

        meta_path = out_dir / "publish_meta.json"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        context["publish_meta_path"] = str(meta_path)
        context["publish_meta"] = meta
        print(f"  [publish-meta] ✅ 标题: {meta.get('title')}")
        print(f"  [publish-meta] ✅ 描述: {meta.get('description')}")
        print(f"  [publish-meta] ✅ 标签: {' | '.join(meta.get('tags', []))}")
        return context

    def _generate(self, topic: str, script: dict, full_text: str, provider) -> dict | None:
        if not provider:
            return None
        system_prompt = self.load_prompt("system")
        # video-factory 用 topic_selected.json 的 angle/hook，这里用 mood 代替切入角度
        mood = script.get("mood", "")

        prompt = f"""话题：{topic}
切入角度/情绪：{mood}

口播文案：
{full_text[:1500]}

请根据以上内容生成发布元数据（标题/描述/标签），输出JSON。"""

        raw = provider.call("publish_meta", prompt, system=system_prompt, max_tokens=800)
        if not raw:
            return None
        meta = self._parse_json(raw)
        if not meta:
            print("  [publish-meta] ⚠️ JSON 解析失败")
            return None

        title = self._truncate((meta.get("title") or "").strip(), 16)
        description = self._truncate((meta.get("description") or "").strip(), 40)
        tags = [str(t).strip() for t in (meta.get("tags") or []) if str(t).strip()]
        while len(tags) < 4:
            tags.append("")
        tags = tags[:4]

        return {
            "topic": topic,
            "title": title,
            "description": description,
            "tags": tags,
        }

    def _truncate(self, text: str, limit: int) -> str:
        """超长智能截断：在 limit 内去掉末尾悬空虚词/标点，避免「…不加班是」半句悬空。"""
        if len(text) <= limit:
            return text
        cut = text[:limit]
        # 末尾悬空虚词（单字助词/介词/连词/判断词）删掉
        weak = "的了在就把还被和与或及而等于是个这那呢吗吧啊"
        while cut and cut[-1] in weak:
            cut = cut[:-1]
        # 末尾标点/空格删掉
        while cut and cut[-1] in "，。！？：；、,.!?:; ":
            cut = cut[:-1]
        return cut

    def _parse_json(self, response: str) -> dict | None:
        cleaned = re.sub(r'```json\s*', '', response)
        cleaned = re.sub(r'```\s*$', '', cleaned).strip()
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            try:
                fixed = re.sub(r',\s*}', '}', m.group())
                fixed = re.sub(r',\s*]', ']', fixed)
                return json.loads(fixed)
            except Exception:
                return None

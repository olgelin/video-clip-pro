"""script_writer — 话题 → 口播稿（avatar-short 入口）

借鉴 video-factory script_writer，改造为 vcp SkillBase 结构。
输入：context["topic"]（话题文字）
输出：step03_script.json（topic + voiceover_sections）
"""
from __future__ import annotations
import json, re
from pathlib import Path
from core.base import SkillBase


class ScriptWriter(SkillBase):
    name = "script_writer"

    def execute(self, context: dict) -> dict:
        topic = (context.get("topic", "") or "").strip()
        if not topic:
            print("  [script-writer] ❌ 没有话题输入")
            return context

        print(f"  [script-writer] 话题: {topic[:40]}")

        script = self._write(topic, context.get("provider"))
        if not script:
            print("  [script-writer] ❌ LLM 生成失败")
            return context

        sections = script.get("voiceover_sections", [])
        if len(sections) < 2:
            print(f"  [script-writer] ❌ 段落太少: {len(sections)}")
            return context

        total_chars = sum(len(s.get("content", "")) for s in sections)
        print(f"  [script-writer] 生成: {len(sections)} 段, {total_chars} 字, 标题={script.get('topic', '')[:20]}")

        out_dir = Path(context.get("output_dir", "."))
        script_path = out_dir / "step03_script.json"
        script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

        context["script_path"] = str(script_path)
        context["script_data"] = script
        context["section_count"] = len(sections)
        context["total_chars"] = total_chars
        return context

    def _write(self, topic: str, provider) -> dict | None:
        system_prompt = self.load_prompt("system")
        user_prompt = (
            f"请根据以下话题，写一个有深度、有冲击力的口播脚本。\n\n"
            f"===== 话题 =====\n{topic}\n===== 话题结束 =====\n\n"
            f"请直接输出 JSON（包含 topic/mood/voiceover_sections）。"
        )
        if not provider:
            print("  [script-writer] ❌ 无 provider")
            return None
        raw = provider.call("script_writer", user_prompt, system=system_prompt, max_tokens=8000)
        if not raw:
            return None
        return self._parse_json(raw)

    def _parse_json(self, response: str) -> dict | None:
        cleaned = re.sub(r'```json\s*', '', response)
        cleaned = re.sub(r'```\s*$', '', cleaned).strip()
        try:
            data = json.loads(cleaned)
            if "voiceover_sections" in data:
                return data
        except json.JSONDecodeError:
            pass
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
                if "voiceover_sections" in data:
                    return data
            except json.JSONDecodeError:
                pass
        fixed = re.sub(r',\s*}', '}', cleaned)
        fixed = re.sub(r',\s*]', ']', fixed)
        try:
            data = json.loads(fixed)
            if "voiceover_sections" in data:
                return data
        except json.JSONDecodeError:
            pass
        return None

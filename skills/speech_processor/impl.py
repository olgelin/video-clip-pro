"""speech_processor — 口语/碎碎念 → 结构化口播稿（avatar-seed 入口）

借鉴 video-factory speech_processor，改造为 vcp SkillBase 结构：
- prompt 独立 prompts/system.md
- LLM 走 provider.call
- 输出 step03_script.json（topic + voiceover_sections）
"""
from __future__ import annotations
import json, re
from pathlib import Path
from core.base import SkillBase


class SpeechProcessor(SkillBase):
    name = "speech_processor"

    def execute(self, context: dict) -> dict:
        speech_text = context.get("speech_text", "") or context.get("topic", "")
        if not speech_text.strip():
            print("  [speech-processor] ❌ 没有口语输入")
            return context

        print(f"  [speech-processor] 输入长度: {len(speech_text)} 字")

        cleaned = self._basic_clean(speech_text)
        if len(cleaned) < 10:
            print("  [speech-processor] ❌ 清洗后内容太少")
            return context

        script = self._process_with_llm(cleaned, context.get("provider"))
        if not script:
            print("  [speech-processor] ❌ LLM 处理失败")
            return context

        sections = script.get("voiceover_sections", [])
        if len(sections) < 2:
            print(f"  [speech-processor] ❌ 段落太少: {len(sections)}")
            return context

        total_chars = sum(len(s.get("content", "")) for s in sections)
        print(f"  [speech-processor] 提炼完成: {len(sections)} 段, {total_chars} 字")
        print(f"  [speech-processor] 标题: {script.get('topic', '未生成')}")

        out_dir = Path(context.get("output_dir", "."))
        script_path = out_dir / "step03_script.json"
        script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [speech-processor] 已保存: {script_path}")

        context["script_path"] = str(script_path)
        context["script_data"] = script
        context["section_count"] = len(sections)
        context["total_chars"] = total_chars
        return context

    def _basic_clean(self, text: str) -> str:
        text = re.sub(r'\s+', ' ', text).strip()
        lines = [l for l in text.split('\n') if any('\u4e00' <= c <= '\u9fff' for c in l)]
        return '\n'.join(lines)

    def _process_with_llm(self, raw_text: str, provider) -> dict | None:
        system_prompt = self.load_prompt("system")
        user_prompt = (
            f"请深度处理以下口语原文，清洗、增强、重构为有冲击力的视频脚本。\n\n"
            f"===== 原文开始 =====\n{raw_text}\n===== 原文结束 =====\n\n"
            f"请直接输出 JSON（包含 topic/mood/audience/emotional_arc/voiceover_sections）。"
        )
        if not provider:
            print("  [speech-processor] ❌ 无 provider")
            return None
        raw = provider.call("speech_processor", user_prompt, system=system_prompt, max_tokens=8000)
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

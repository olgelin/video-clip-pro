"""lyrics_writer — 口播稿 → 歌词（映射哲学：先挖本质→找核心意象→写词）。

照抄 video-factory lyrics_writer，适配 SkillBase 结构。
输入：context["script_data"]（口播稿）
输出：context["lyrics"] + lyrics.txt（ACE-Step 格式歌词）
"""
from __future__ import annotations
import re
from pathlib import Path
from core.base import SkillBase


class LyricsWriter(SkillBase):
    name = "lyrics_writer"

    def execute(self, context: dict) -> dict:
        script = context.get("script_data", {})
        if not script or not script.get("voiceover_sections"):
            print("  [lyrics-writer] ❌ 无口播稿")
            return context

        lyrics = self._write(script, context.get("provider"))
        if not lyrics:
            print("  [lyrics-writer] ❌ LLM 生成失败")
            return context

        out_dir = Path(context.get("output_dir", "."))
        lyrics_path = out_dir / "lyrics.txt"
        lyrics_path.write_text(lyrics, encoding="utf-8")

        context["lyrics_path"] = str(lyrics_path)
        context["lyrics"] = lyrics
        lines = [l for l in lyrics.split("\n") if l.strip() and not l.strip().startswith("[")]
        print(f"  [lyrics-writer] ✅ 歌词 {len(lyrics)} 字符, {len(lines)} 行")
        return context

    def _write(self, script: dict, provider) -> str | None:
        system_prompt = self.load_prompt("lyrics_system")
        sections = script.get("voiceover_sections", [])
        topic = script.get("topic", "")
        mood = script.get("mood", "")
        full_text = "\n".join(s.get("content", "") for s in sections)
        section_summaries = [
            f"段落{i+1}: {(s.get('talking_point', '') or s.get('content', ''))[:80]}"
            for i, s in enumerate(sections[:6])
        ]

        user_prompt = (
            f"口播稿主题: {topic}\n"
            f"口播稿情绪: {mood}\n\n"
            f"口播稿内容摘要:\n{chr(10).join(section_summaries)}\n\n"
            f"口播稿全文:\n{full_text[:2000]}\n\n"
            f"请用「先挖本质，再找意象，最后写词」的创作逻辑写歌词：\n"
            f"1. 先挖出这个事件背后的人性真相：为什么会发生？暴露了人性的什么？\n"
            f"2. 提炼一句「主题」，歌词每一句都围绕它，不跑偏\n"
            f"3. 找到一个轻脆的核心意象（泡沫/露水/雪花/薄冰/糖/梦这类轻、脆、美、易碎的东西），用它贯穿全曲——举重若轻，不选数字/命/血/山/刀这类重的意象\n"
            f"4. 表层事件简短带过，深层真相重点展开\n"
            f"5. 留白：情绪藏在意象背后，不直白喊\n"
            f"6. 用遗憾美学（若是/可有/不问/别/如果/本该）翻出遗憾感\n"
            f"7. 每句通顺有意义，不通顺就删\n"
            f"8. 副歌开头唱核心意象+主题，至少重复3-4次\n"
            f"9. 长度不限\n\n"
            f"直接输出歌词，不要其他内容。"
        )
        if not provider:
            return None
        raw = provider.call("lyrics_writer", user_prompt, system=system_prompt, max_tokens=4000)
        if not raw:
            return None
        return self._clean(raw)

    def _clean(self, raw: str) -> str:
        lyrics = raw.strip()
        lyrics = re.sub(r'^```\w*\s*', '', lyrics)
        lyrics = re.sub(r'```\s*$', '', lyrics).strip()
        return lyrics

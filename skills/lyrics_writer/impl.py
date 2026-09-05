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

        user_prompt = self.load_prompt("lyrics_user").format(
            topic=topic,
            mood=mood,
            topic_info="",
            style_guide="",
            section_summaries=chr(10).join(section_summaries),
            full_text=full_text[:2000],
        )
        if not provider:
            return None
        raw = provider.call("lyrics_writer", user_prompt, system=system_prompt, max_tokens=8000)
        if not raw:
            return None
        return self._clean(raw)

    def _clean(self, raw: str) -> str:
        lyrics = raw.strip()
        lyrics = re.sub(r'^```\w*\s*', '', lyrics)
        lyrics = re.sub(r'```\s*$', '', lyrics).strip()
        return lyrics

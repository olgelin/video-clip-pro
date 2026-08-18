"""Draft skill — 将 understand 的 keep_ranges 直接映射为 EDL ranges（纯 Python，不二次调 LLM）"""
from __future__ import annotations
from core.base import SkillBase


class Draft(SkillBase):
    name = "draft"

    def execute(self, context: dict) -> dict:
        story_map = context.get("story_map", {})
        keep_ranges = story_map.get("keep_ranges", [])

        if not keep_ranges:
            # 兼容旧数据（segments 格式）
            segments = story_map.get("segments", [])
            if not segments:
                print("      Draft: no keep_ranges / segments")
                return {"edl": {"ranges": []}}
            keep_ranges = [{
                "start": s["start"], "end": s["end"],
                "beat": s.get("beat", ""),
                "title": s.get("text", "")[:30],
                "text": s.get("trimmed", "") or s.get("text", ""),
            } for s in segments if s.get("decision") != "CUT"]

        # keep_ranges → ranges（直接映射）
        ranges = [{
            "start": r["start"],
            "end": r["end"],
            "beat": r.get("beat", ""),
            "title": r.get("title", ""),
            "quote": r.get("text", ""),
        } for r in keep_ranges]

        ranges.sort(key=lambda r: r["start"])

        total_dur = sum(r["end"] - r["start"] for r in ranges)
        original_dur = context.get("duration", 1)
        pct = total_dur / original_dur * 100 if original_dur > 0 else 0
        beats = [r.get("beat", "?") for r in ranges]

        print(f"      Draft: {len(ranges)} segments, {total_dur:.1f}s ({pct:.0f}%)")
        print(f"        Arc: {' → '.join(beats)}")
        print(f"        Quotes: {' | '.join(r.get('quote','')[:30] for r in ranges)[:180]}")

        return {"edl": {"ranges": ranges}}

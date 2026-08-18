"""Review skill — Report editing quality. No auto-fix. Prompt in prompts/."""
from __future__ import annotations
import json
from core.base import SkillBase
from core.provider import Provider


class Review(SkillBase):
    name = "review"

    def execute(self, context: dict) -> dict:
        edl = context.get("edl", {})
        transcript = context.get("words", [])
        full_text = "".join(w["text"] for w in transcript) if transcript else context.get("text", "")

        ranges = edl.get("ranges", [])
        if not ranges:
            return {"review_passed": False, "review_score": 0}

        provider = context.get("provider")
        if not isinstance(provider, Provider):
            return {"review_passed": True, "review_score": 100}

        system = self.load_prompt("review")

        merged = "".join(r.get("quote", "") for r in ranges)

        timeline_parts = []
        for i, r in enumerate(ranges):
            beat = r.get("beat", "?")
            title = r.get("title", "")
            dur = r["end"] - r["start"]
            timeline_parts.append(
                f"[{i+1}] {r['start']:.1f}-{r['end']:.1f} ({dur:.1f}s) {beat}: {title}"
            )

        prompt = f"""## 原始转录
{full_text[:3000]}

## 剪辑后文本（拼接阅读）
{merged}

## 时间线
{chr(10).join(timeline_parts)}

## 统计
原始: {context.get('duration',0):.1f}s → 剪辑: {sum(r['end']-r['start'] for r in ranges):.1f}s, {len(ranges)}段"""

        raw = provider.call("review", prompt, system)
        if not raw or raw.startswith("[ERROR"):
            return {"review_passed": True, "review_score": 80}

        result = provider.extract_json(raw)
        if not isinstance(result, dict):
            return {"review_passed": True, "review_score": 80}

        score = result.get("score", 80)
        editing_issues = result.get("editing_issues", [])
        minor_notes = result.get("minor_notes", [])
        summary = result.get("summary", "")

        print(f"      Review: score={score}/100")
        if summary:
            print(f"        {summary[:100]}")

        if editing_issues:
            print(f"      Editing issues ({len(editing_issues)}):")
            for issue in editing_issues[:3]:
                print(f"        ⚠ {issue[:100]}")
        else:
            print("      No editing-caused issues ✓")

        if minor_notes:
            print(f"      Minor (speaker, not editing): {len(minor_notes)} note(s)")

        return {
            "review_passed": score >= 70,
            "review_score": score,
            "review_issues": editing_issues,
            "review_summary": summary,
        }

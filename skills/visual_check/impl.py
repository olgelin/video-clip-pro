"""visual_check/impl.py — 成片视觉质检（deepseek 视觉模型）

借鉴 video-use 的"自评回路"：对渲染出的成片抽帧，用 vision 检查画面质量，
而非只查文本/中间件。产出 visual_check.json。
"""
from __future__ import annotations
import json, os, subprocess, tempfile
from pathlib import Path
from core.base import SkillBase


class VisualCheck(SkillBase):
    name = "visual_check"
    timeout = 300

    def execute(self, context: dict) -> dict:
        # 找成片
        video_path = context.get("final_polished") or context.get("final_path") or ""
        out_dir = Path(context.get("output_dir", "."))
        if not video_path or not Path(video_path).exists():
            for name in ["final_polished.mp4", "final.mp4", "final_polished_2x.mp4"]:
                p = out_dir / name
                if p.exists():
                    video_path = str(p)
                    break
        if not video_path or not Path(video_path).exists():
            print("  [visual-check] ⚠ 找不到成片，跳过")
            return {"visual_check": {"error": "no_video_found"}}

        provider = context.get("provider")
        if not provider or not hasattr(provider, "call_vision"):
            print("  [visual-check] ⚠ 无 vision 能力，跳过")
            return {"visual_check": {"error": "no_vision"}}

        print(f"  [visual-check] 检查成片: {Path(video_path).name}")

        with tempfile.TemporaryDirectory() as tmpdir:
            frames = self._extract_frames(video_path, tmpdir, num=4)
            if not frames:
                return {"visual_check": {"error": "frame_extract_failed"}}

            prompt = self.load_prompt("check")
            results = []
            for fp in frames:
                r = self._check_frame(provider, prompt, fp)
                results.append(r)

            ok = sum(1 for r in results if r.get("ok") is True)
            issues = [r.get("issue", "") for r in results if r.get("issue")]
            verdict = "PASS" if ok >= max(len(results) * 0.5, 2) else "FAIL"

            summary = {
                "verdict": verdict,
                "video_path": video_path,
                "frames_checked": len(results),
                "ok_count": ok,
                "issues": issues,
                "per_frame": results,
            }
            (out_dir / "visual_check.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  [visual-check] {verdict} ({ok}/{len(results)} 帧正常)")
            for issue in issues:
                print(f"    ⚠ {issue}")
            return {"visual_check": summary, "visual_check_path": str(out_dir / "visual_check.json")}

    def _extract_frames(self, video_path: str, tmpdir: str, num: int = 4) -> list:
        frames = []
        dur = self._get_duration(video_path)
        if dur <= 0:
            return frames
        start_pct, end_pct = 0.10, 0.90
        usable = dur * (end_pct - start_pct)
        offset = dur * start_pct
        for i in range(num):
            t = offset + (usable * i / max(num - 1, 1))
            fp = os.path.join(tmpdir, f"frame_{i+1:02d}.jpg")
            subprocess.run(
                f'ffmpeg -y -ss {t:.2f} -i "{video_path}" -frames:v 1 -q:v 3 "{fp}"',
                shell=True, capture_output=True, timeout=30)
            if os.path.exists(fp):
                frames.append(fp)
        return frames

    def _get_duration(self, video_path: str) -> float:
        try:
            r = subprocess.run(
                f'ffprobe -v quiet -print_format json -show_format "{video_path}"',
                shell=True, capture_output=True, text=True, timeout=30)
            info = json.loads(r.stdout)
            return float(info.get("format", {}).get("duration", 0))
        except Exception:
            return 0.0

    def _check_frame(self, provider, prompt: str, frame_path: str) -> dict:
        raw = provider.call_vision(prompt, image_path=frame_path, max_tokens=500, timeout=60)
        if not raw:
            return {"frame": Path(frame_path).name, "ok": None,
                    "description": "vision_unavailable", "issue": "vision不可用"}
        result = provider.extract_json(raw)
        if isinstance(result, dict):
            return {
                "frame": Path(frame_path).name,
                "ok": bool(result.get("ok", True)),
                "description": result.get("description", ""),
                "issue": result.get("issue", ""),
            }
        return {"frame": Path(frame_path).name, "ok": True, "description": raw[:80], "issue": ""}

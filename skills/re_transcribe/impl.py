"""Re-transcribe skill — 剪辑后重新转写 final.mp4，得到新视频的精确时间戳（字幕/分镜完全同步）"""
from __future__ import annotations
from skills.transcribe.impl import Transcribe


class ReTranscribe(Transcribe):
    name = "re_transcribe"

    def execute(self, context: dict) -> dict:
        final_path = context.get("final_path")
        if not final_path:
            print("      ReTranscribe: no final_path, skip (使用原时间戳)")
            return {}

        # 🔴 关键：把 video_path 换成剪辑后的 final.mp4，重新转写
        ctx = dict(context)
        ctx["video_path"] = final_path
        print("\n[4.5/7] Re-transcribing final.mp4 ... (新时间戳，字幕同步)")
        result = super().execute(ctx)

        # 🔴 时间戳连续化：补齐 whisper 句尾 gap，对齐 final.mp4 实际时长
        words = self._make_continuous(result["words"], context.get("final_dur", 0))

        # 输出新时间戳，覆盖后续 storyboard/caption 的输入
        return {
            "words": words,
            "raw_words": result.get("raw_words", []),
            "text": result.get("text", ""),
            "duration": result.get("duration", 0),
            "re_transcribed": True,
        }

    def _make_continuous(self, words: list, final_dur: float) -> list:
        """whisper 时间戳有句尾 gap（句尾静音没算进 end），导致 Σ(end-start) < final.mp4 时长。
        补齐 gap：每个 word 的 end 延到下一个 word 的 start，最后一个 end 对齐 final_dur。"""
        if not words:
            return words
        for i in range(len(words) - 1):
            if words[i + 1]["start"] > words[i]["end"]:
                words[i]["end"] = words[i + 1]["start"]
        if final_dur and words[-1]["end"] < final_dur:
            words[-1]["end"] = final_dur
        return words

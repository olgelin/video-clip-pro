"""Transcribe skill — Whisper voice transcription with GPU auto-detection + CJK phrase merging."""
from __future__ import annotations
import time, json, re
from pathlib import Path
from core.base import SkillBase
from core.gpu import detect_gpu

# CJK Unicode ranges
_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffef]+')
# 🔴 数字/单位连续性：数字及其单位是一个不可分割的整体（"12"+"00"+"万"→"1200万"）
_NUM_RE = re.compile(r'^[\d.%,万亿千百十点分之]+$')

def _merge_cjk_words(words, max_gap=0.25, max_chars=12):
    """Merge adjacent CJK characters into natural phrases.
    faster_whisper returns each Chinese character as a separate word.
    This merges them back into readable phrases based on timing gaps.
    🔴 max_chars 限制短语长度：剪辑后视频紧凑(gap小)，不加字数限制会合并成超长短语(20s+)，导致场景太少+字幕太长。"""
    if not words:
        return words
    merged = []
    buf_text = ""
    buf_start = words[0]["start"]
    buf_end = words[0]["end"]
    buf_conf = 0.0
    buf_count = 0

    for w in words:
        text = w["text"].strip()
        is_cjk = bool(_CJK_RE.match(text))
        is_num = bool(_NUM_RE.match(text))
        gap = w["start"] - buf_end if buf_count > 0 else 0

        # 🔴 数字连续性：当前是数字/单位，且 buffer 末尾也是数字/单位 → 无条件合并（数字不可劈开）
        if is_num and buf_count > 0 and _NUM_RE.match(buf_text[-1]):
            buf_text += text
            buf_end = w["end"]
            buf_conf += w["confidence"]
            buf_count += 1
            continue

        if (is_cjk or is_num) and buf_count > 0 and gap < max_gap and len(buf_text) + len(text) <= max_chars:
            # Merge into current phrase
            buf_text += text
            buf_end = w["end"]
            buf_conf += w["confidence"]
            buf_count += 1
        else:
            # Flush previous phrase
            if buf_count > 0:
                merged.append({
                    "start": round(buf_start, 2),
                    "end": round(buf_end, 2),
                    "text": buf_text,
                    "speaker": "S0",
                    "confidence": round(buf_conf / buf_count, 3),
                })
            buf_text = text
            buf_start = w["start"]
            buf_end = w["end"]
            buf_conf = w["confidence"]
            buf_count = 1

    # Flush last phrase
    if buf_count > 0:
        merged.append({
            "start": round(buf_start, 2),
            "end": round(buf_end, 2),
            "text": buf_text,
            "speaker": "S0",
            "confidence": round(buf_conf / buf_count, 3),
        })

    return merged


class Transcribe(SkillBase):
    name = "transcribe"

    def execute(self, context: dict) -> dict:
        # 🔴 兼容转录配音：avatar 管道转录 step05_voice.wav（字幕对齐配音），其他管道转录视频
        video_path = Path(context.get("voice_path") or context["video_path"])
        model_name = context.get("whisper_model", "large-v3")  # 🔴 large-v3 时间戳精度远超 small，减少剪辑偏差/字幕不同步
        lang = context.get("lang", "zh")
        gpu = detect_gpu()

        print(f"\n[1/5] Transcribing ... (model: {model_name}, device: {gpu['whisper_device']})")
        print(f"      Source: {video_path}")
        t0 = time.time()
        from faster_whisper import WhisperModel
        model = WhisperModel(model_name, device=gpu["whisper_device"], compute_type=gpu["whisper_compute"])
        segments, info = model.transcribe(str(video_path), language=lang, beam_size=5, word_timestamps=True)

        raw_words = []
        for seg in segments:
            if seg.words:
                for w in seg.words:
                    raw_words.append({
                        "start": round(w.start, 2),
                        "end": round(w.end, 2),
                        "text": w.word.strip(),
                        "speaker": "S0",
                        "confidence": round(w.probability, 3),
                    })

        # Merge CJK characters into phrases
        words = _merge_cjk_words(raw_words)
        full_text = "".join(w["text"] for w in words)

        elapsed = time.time() - t0
        print(f"      Duration: {info.duration:.1f}s, Raw tokens: {len(raw_words)}, Merged: {len(words)} phrases, Time: {elapsed:.0f}s")
        # 🔴 raw_words 保留逐字时间戳，供 understand 做字词级删减（口误/重复/口头禅）
        result = {"text": full_text, "words": words, "raw_words": raw_words, "duration": info.duration}

        out_dir = Path(context.get("output_dir", "test_output"))
        (out_dir / "transcript.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

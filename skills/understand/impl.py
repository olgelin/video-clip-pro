"""Understand skill — LLM 读逐字时间戳，按字/按句意语义删减，输出保留区间 keep_ranges"""
from __future__ import annotations
import json
from core.base import SkillBase
from core.provider import Provider


class Understand(SkillBase):
    name = "understand"

    def execute(self, context: dict) -> dict:
        raw_words = context.get("raw_words", [])
        phrases = context.get("words", [])
        if not raw_words and phrases:
            raw_words = phrases

        if not raw_words:
            print("      Understand: no transcript")
            return {"story_map": {"keep_ranges": [], "core_message": "", "narrative_arc": []}}

        full_text = "".join(w["text"] for w in raw_words)

        # 精修检测：填充词 < 3% → 跳过 LLM，直接全保留
        filler_chars = set("呢哎嘛呵哈啊哦嗯吧哇呀嘞啰噢")
        filler_words = ["就是说", "实际上", "这个", "那个", "然后", "就是", "反正", "怎么说"]
        filler_count = sum(1 for c in full_text if c in filler_chars)
        for fw in filler_words:
            filler_count += full_text.count(fw) * len(fw)
        filler_ratio = filler_count / max(len(full_text), 1)
        if filler_ratio < 0.03 and len(phrases) <= len(raw_words):
            print(f"      Polished: {filler_ratio:.0%} filler → skip LLM, KEEP all")
            return self._direct_keep(phrases or raw_words, full_text)

        provider = context.get("provider")
        if not isinstance(provider, Provider):
            raise RuntimeError("Provider required in context")

        # 🔴 第 1 层：确定性删减（代码）——语气词 + 字面重复 + 非连续重复短语（稳定，不依赖 LLM）
        delete = self._detect_deterministic(raw_words)

        # 🔴 第 2 层：LLM 短语级删减——3 次采样取 2/3 多数，识别冗余/重复/废话短语
        phrases = context.get("words", [])
        if phrases:
            cut_pids = self._llm_cut_phrases(provider, phrases, context)
            for pid in cut_pids:
                if 0 <= pid < len(phrases):
                    p = phrases[pid]
                    for i, w in enumerate(raw_words):
                        if p["start"] <= w["start"] < p["end"]:
                            delete.add(i)

        # 🔴 合并：按 word 边界生成 keep_ranges（never cut inside a word）
        keep_ranges = self._delete_to_keep_ranges(raw_words, delete)
        if not keep_ranges:
            print("      ⚠ 删减后无保留 → fallback 保守删减")
            return self._conservative_keep(raw_words, full_text)

        core_message = "".join(str(r.get("text", "")) for r in keep_ranges)[:120]
        narrative_arc = ["HOOK", "CONTEXT", "PROBLEM", "STRUGGLE", "RESOLUTION"]

        # 🔴 塌缩/删减过度检测：用保留字数判断（区间数量会因 <0.5s 合并而变化，不可靠）
        kept_chars = sum(len(r.get("text", "")) for r in keep_ranges)
        total_chars = len(full_text)
        if total_chars > 0 and kept_chars < total_chars * 0.3:
            print(f"      ⚠ 删减过度（保留 {kept_chars}/{total_chars} 字 <30%）→ fallback 保守删减")
            return self._conservative_keep(raw_words, full_text)

        kept_dur = sum(r["end"] - r["start"] for r in keep_ranges)
        total_dur = context.get("duration", 1)
        pct = kept_dur / total_dur * 100 if total_dur > 0 else 0
        deleted = sum(1 for w in raw_words if not any(
            r["start"] <= w["start"] < r["end"] for r in keep_ranges))

        # 🔴 删减过度兜底：保留率 <30% 才 fallback（LLM 删到 40-70% 属合理精简：删过程过渡+重复+自我纠正，不该误判）
        if pct < 30:
            print(f"      ⚠ 删减过度 {pct:.0f}%（<30%）→ fallback 确定性删减")
            return self._conservative_keep(raw_words, full_text)

        # 🔴 碎片检测：>3 个 <0.5s 的碎片区间 → LLM 碎片化删减（删了完整句留了碎字），fallback
        n_frag = sum(1 for r in keep_ranges if (r["end"] - r["start"]) < 0.5)
        if n_frag > 3:
            print(f"      ⚠ 碎片化删减（{n_frag} 个 <0.5s 碎片）→ fallback 保守删减")
            return self._conservative_keep(raw_words, full_text)

        print(f"      Understand: {len(raw_words)} 字 → {len(keep_ranges)} 保留区间, 删 {deleted} 字, {kept_dur:.1f}s ({pct:.0f}%)")
        if core_message:
            print(f"        Core: {core_message[:120]}")
        for r in keep_ranges:
            print(f"        ✓ [{r['start']:.2f}-{r['end']:.2f}] {r.get('beat','')[:10]} | {r.get('text','')[:40]}")

        return {
            "story_map": {
                "keep_ranges": keep_ranges,
                "core_message": core_message,
                "narrative_arc": narrative_arc,
            }
        }

    def _segments_to_keep_ranges(self, raw_words: list, segments: list) -> list:
        """LLM 输出的 segments（start_id/end_id 字编号）→ 精确时间区间 keep_ranges"""
        keep_ranges = []
        n = len(raw_words)
        for seg in segments:
            a = seg.get("start_id", 0)
            b = seg.get("end_id", a)
            if not (0 <= a <= b < n):
                continue
            ws = raw_words[a:b + 1]
            text = "".join(w["text"] for w in ws)
            keep_ranges.append({
                "start": ws[0]["start"],
                "end": ws[-1]["end"],
                "beat": seg.get("beat", ""),
                "title": seg.get("title", ""),
                "text": text,
            })
        # 排序 + 合并相邻（间隔 < 0.5s 的碎片区间合并，避免过度碎片化）
        keep_ranges.sort(key=lambda r: r["start"])
        merged = []
        for r in keep_ranges:
            if merged and r["start"] - merged[-1]["end"] < 0.5:
                merged[-1]["end"] = r["end"]
                merged[-1]["text"] += r["text"]
                if not merged[-1]["beat"] and r.get("beat"):
                    merged[-1]["beat"] = r["beat"]
            else:
                merged.append(dict(r))
        return merged

    def _direct_keep(self, transcript, full_text):
        """兜底：LLM 失败或无冗余时，直接全保留"""
        keep_ranges = []
        beats = ["HOOK", "CONTEXT", "PROBLEM", "STRUGGLE", "RESOLUTION"]
        n = len(transcript)
        for i, w in enumerate(transcript):
            beat_idx = min(int(i / max(n, 1) * len(beats)), len(beats) - 1)
            keep_ranges.append({
                "start": w["start"], "end": w["end"],
                "beat": beats[beat_idx],
                "title": w["text"][:6] if w["text"] else "",
                "text": w["text"],
            })
        return {
            "story_map": {
                "keep_ranges": keep_ranges,
                "core_message": full_text[:120],
                "narrative_arc": beats[:min(5, len(beats))],
            }
        }

    def _conservative_keep(self, transcript, full_text):
        """🔴 保守删减兜底：复用确定性删减（语气词 + 字面重复 + 非连续重复短语），不依赖 LLM"""
        delete = self._detect_deterministic(transcript)
        keep_ranges = self._delete_to_keep_ranges(transcript, delete)
        beats = ["HOOK", "CONTEXT", "PROBLEM", "STRUGGLE", "RESOLUTION"]
        return {
            "story_map": {
                "keep_ranges": keep_ranges,
                "core_message": full_text[:120],
                "narrative_arc": beats[:min(5, len(beats))],
            }
        }

    def _code_cleanup_segments(self, raw_words, result):
        """🔴 代码兜底：对 LLM 的 segments 做字符级重复 + 语气词清理（确定性，不依赖 LLM 判断）"""
        segs = result.get("segments", [])
        if not segs:
            return result
        # 得到保留的字编号集合
        kept = set()
        for s in segs:
            for i in range(int(s.get("start_id", 0)), int(s.get("end_id", 0)) + 1):
                kept.add(i)
        # 字符级重复检测（在保留字范围内）
        texts = [w.get("text", "") for w in raw_words]
        kept_list = sorted(kept)
        char_to_word = []
        for wi in kept_list:
            for _ch in texts[wi]:
                char_to_word.append(wi)
        full_chars = list("".join(texts[wi] for wi in kept_list))
        cn = len(full_chars)
        ci = 0
        while ci < cn:
            matched = False
            for L in range(min(8, (cn - ci) // 2), 1, -1):
                seg = full_chars[ci:ci + L]
                if seg and seg == full_chars[ci + L:ci + 2 * L]:
                    for _k in range(ci + L, ci + 2 * L):
                        if _k < len(char_to_word):
                            kept.discard(char_to_word[_k])
                    ci += L
                    matched = True
                    break
            if not matched:
                ci += 1
        # 语气词（单字）
        filler = {"呢", "哎", "嘛", "啊", "嗯", "呃", "哦", "哈", "呀", "吧"}
        for wi in list(kept):
            if texts[wi] in filler:
                kept.discard(wi)
        # 🔴 非连续重复短语检测：同一短语（>=5 字）出现两次，删第二次（如"我之所以整这么个设备"×2）
        kept_list2 = sorted(kept)
        if kept_list2:
            char_to_word2 = []
            for wi in kept_list2:
                for _ch in texts[wi]:
                    char_to_word2.append(wi)
            full2 = "".join(texts[wi] for wi in kept_list2)
            cn2 = len(full2)
            for L in range(min(12, cn2 // 2), 4, -1):
                i = 0
                while i <= cn2 - 2 * L:
                    phrase = full2[i:i + L]
                    j = full2.find(phrase, i + L)
                    if j > i:
                        # 删第二次出现的短语（j 到 j+L）
                        for _k in range(j, j + L):
                            if _k < len(char_to_word2):
                                kept.discard(char_to_word2[_k])
                        i = j + L
                    else:
                        i += 1
        # 重建 segments：按连续保留字分组（遇到被删的字就断开，不能用首尾覆盖缺口）
        new_segs = []
        cur = []
        for i in range(len(raw_words)):
            if i in kept:
                if cur and i == cur[-1] + 1:
                    cur.append(i)
                else:
                    if cur:
                        new_segs.append({"start_id": cur[0], "end_id": cur[-1], "beat": "HOOK", "title": ""})
                    cur = [i]
        if cur:
            new_segs.append({"start_id": cur[0], "end_id": cur[-1], "beat": "HOOK", "title": ""})
        result["segments"] = new_segs
        return result

    def _detect_deterministic(self, raw_words):
        """🔴 确定性删减（代码）：语气词 + 字面连续重复 + 非连续重复短语。返回删除的字编号集合"""
        texts = [w.get("text", "") for w in raw_words]
        n = len(texts)
        delete = set()
        # 1. 语气词（单字）
        filler = {"呢", "哎", "嘛", "啊", "嗯", "呃", "哦", "哈", "呀", "吧"}
        for i, t in enumerate(texts):
            if t in filler:
                delete.add(i)
        # 字符 -> word 映射
        char_to_word = []
        for wi, t in enumerate(texts):
            for _ch in t:
                char_to_word.append(wi)
        full_chars = list("".join(texts))
        cn = len(full_chars)
        # 2. 字符级连续重复（"X X" 模式）
        ci = 0
        while ci < cn:
            matched = False
            for L in range(min(10, (cn - ci) // 2), 0, -1):
                seg = full_chars[ci:ci + L]
                if seg and seg == full_chars[ci + L:ci + 2 * L]:
                    for _k in range(ci + L, ci + 2 * L):
                        if _k < len(char_to_word):
                            delete.add(char_to_word[_k])
                    ci += L
                    matched = True
                    break
            if not matched:
                ci += 1
        # 3. 非连续重复短语（>=5 字出现两次，删第二次，如"我之所以整这么个设备"×2）
        full_str = "".join(full_chars)
        for L in range(min(12, cn // 2), 4, -1):
            i = 0
            while i <= cn - 2 * L:
                phrase = full_str[i:i + L]
                j = full_str.find(phrase, i + L)
                if j > i:
                    for _k in range(j, j + L):
                        if _k < len(char_to_word):
                            delete.add(char_to_word[_k])
                    i = j + L
                else:
                    i += 1
        return delete

    def _llm_cut_phrases(self, provider, phrases, context):
        """🔴 LLM 短语级删减：3 次采样取 2/3 多数，输出要删的短语编号"""
        from collections import Counter
        cut_count = Counter()
        valid = 0
        for _ in range(3):
            r = self._first_pass(provider, phrases, context)
            if not r or not isinstance(r.get("remove_phrases"), list):
                continue
            valid += 1
            for pid in r["remove_phrases"]:
                try:
                    cut_count[int(pid)] += 1
                except (ValueError, TypeError):
                    pass
        if valid == 0:
            print("      ⚠ LLM 短语删减全部失败 → 只用确定性删减")
            return set()
        return {pid for pid, c in cut_count.items() if c >= 2}

    def _delete_to_keep_ranges(self, raw_words, delete):
        """🔴 删除字集合 → keep_ranges（按 word 边界，连续保留字 <0.5s 合并）"""
        keep_ranges = []
        beats = ["HOOK", "CONTEXT", "PROBLEM", "STRUGGLE", "RESOLUTION"]
        for i, w in enumerate(raw_words):
            if i in delete:
                continue
            if keep_ranges and w["start"] - keep_ranges[-1]["end"] < 0.5:
                keep_ranges[-1]["end"] = w["end"]
                keep_ranges[-1]["text"] += w["text"]
            else:
                bi = min(int(len(keep_ranges) / max(len(raw_words), 1) * len(beats)), len(beats) - 1)
                keep_ranges.append({
                    "start": w["start"], "end": w["end"],
                    "beat": beats[bi],
                    "title": w["text"][:6] if w["text"] else "",
                    "text": w["text"],
                })
        return keep_ranges

    def _first_pass(self, provider, phrases, context):
        system = self.load_prompt("understand")
        lines = [f"[{i}] {p['start']:.2f}-{p['end']:.2f} {p['text']}" for i, p in enumerate(phrases)]
        full_text = "".join(p["text"] for p in phrases)
        prompt = f"""## 口播短语（每个一行，[编号] 起止秒 文本）

总时长: {context.get('duration', 0):.1f}s，共 {len(phrases)} 个短语（编号 0-{len(phrases) - 1}）

{chr(10).join(lines)}

## 完整文本

{full_text}"""

        raw = provider.call("understand", prompt, system)
        if not raw or raw.startswith("[ERROR"):
            return None
        return provider.extract_json(raw)

    def _verify_pass(self, provider, raw_words, first_result, context):
        """第二步复查：LLM 逐字检查初编的删减，补充漏删的口误/重复，恢复误删的有信息量内容"""
        system = self.load_prompt("understand_verify")
        # 🔴 逐字标注初编结果（保留/删除），让 LLM 清楚看到每个字的处理
        kept_ids = set()
        for seg in first_result.get("segments", []):
            for _i in range(int(seg.get("start_id", 0)), int(seg.get("end_id", 0)) + 1):
                kept_ids.add(_i)
        lines = []
        for i, w in enumerate(raw_words):
            mark = "保留" if i in kept_ids else "删除"
            lines.append(f"[{i}] {mark} {w['text']}")
        full_text = "".join(w["text"] for w in raw_words)
        prompt = f"""## 逐字标注（初编结果，每个字已标 保留/删除）

{chr(10).join(lines)}

## 完整文本（对照理解句意）

{full_text}

## 你的任务：逐字复查修正

1. 标「删除」但有信息量/情感/因果的字 → 改成「保留」（尤其开头点题句）
2. 标「保留」但是口误/重复/口头禅/废弃版本的字 → 改成「删除」（尤其重复的字词只留一次）
3. 修正后连起来读要通顺、意思完整、无废话重复"""
        raw = provider.call("understand_verify", prompt, system)
        if not raw or raw.startswith("[ERROR"):
            return None
        return provider.extract_json(raw)

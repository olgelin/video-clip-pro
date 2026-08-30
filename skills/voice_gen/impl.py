"""voice_gen — VoxCPM2 配音（复用 video-factory 的 VoxCPM2 venv，不重复部署）

借鉴 video-factory voice_gen，改造为 vcp SkillBase 结构。
输入：output_dir/step03_script.json（speech_processor 产出）
输出：output_dir/step05_voice.wav + voice_duration
"""
from __future__ import annotations
import json, os, re, hashlib
from pathlib import Path
from core.base import SkillBase

# 🔴 复用 video-factory 的 VoxCPM2 工具 venv（共享基础能力，不复制几 GB torch）
VF_ROOT = Path("E:/Hermes-Agent/workspace/xiaoshan/video-factory")


class VoiceGen(SkillBase):
    name = "voice_gen"

    def execute(self, context: dict) -> dict:
        out_dir = Path(context.get("output_dir", "."))
        script_path = Path(context.get("script_path") or (out_dir / "step03_script.json"))
        voice_path = out_dir / "step05_voice.wav"

        if not script_path.exists():
            print(f"  [voice-gen] ❌ 找不到脚本: {script_path}")
            return context

        # 哈希校验：脚本没变则跳过（避免重复配音）
        script_text = script_path.read_text(encoding="utf-8")
        script_hash = hashlib.md5(script_text.encode()).hexdigest()[:8]
        hash_file = out_dir / ".voice_script_hash"
        if voice_path.exists() and voice_path.stat().st_size > 1000 and hash_file.exists():
            if hash_file.read_text().strip() == script_hash:
                print(f"  [voice-gen] ⏭️ 配音已存在且脚本未变，跳过")
                context["voice_path"] = str(voice_path)
                return context

        # 数字转中文（避免 TTS 把 21000 读成"二一零零零"）
        self._convert_numbers_in_script(script_path)

        ref_wav = context.get("voice_ref") or str(VF_ROOT / "hf-project" / "assets" / "reference_voice.wav")
        speed = context.get("voice_speed", 1.2)
        cfg = context.get("voice_cfg", 2.0)
        steps = context.get("voice_steps", 10)

        print(f"  [voice-gen] 参数: speed={speed}x, cfg={cfg}, steps={steps}")
        print(f"  [voice-gen] 参考音频: {ref_wav}")

        if voice_path.exists():
            voice_path.unlink()

        # 复用 vf 的 tool_runner.call_voxcpm
        import sys
        sys.path.insert(0, str(VF_ROOT / "hf-project"))
        from tool_runner import call_voxcpm
        result = call_voxcpm(
            input_path=str(script_path), output_path=str(voice_path),
            speed=speed, ref_audio=ref_wav, cfg=cfg, steps=steps,
        )

        if result.get("error"):
            print(f"  [voice-gen] ❌ 失败: {result['error']}")
            if voice_path.exists():
                voice_path.unlink()
            return context

        context["voice_path"] = str(voice_path)
        context["voice_duration"] = result.get("duration", 0)
        scene_durations = result.get("scene_durations", [])
        if scene_durations:
            context["voice_scene_durations"] = [
                {"text": f"scene{i}", "duration": d} for i, d in enumerate(scene_durations)
            ]
            (out_dir / "voice_scene_durations.json").write_text(
                json.dumps(context["voice_scene_durations"], ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"  [voice-gen] ✅ 配音完成: {context.get('voice_duration', 0):.1f}s")
        hash_file.write_text(script_hash)
        return context

    def _convert_numbers_in_script(self, script_path: Path):
        DIGITS_CN = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
        UNITS = ["", "十", "百", "千"]
        BIG_UNITS = ["", "万", "亿"]

        def _num_to_cn(n: int) -> str:
            if n == 0: return "零"
            if n < 10: return DIGITS_CN[n]
            if n < 20: return "十" + (DIGITS_CN[n % 10] if n % 10 else "")
            if n < 100: return DIGITS_CN[n // 10] + "十" + (DIGITS_CN[n % 10] if n % 10 else "")
            if n < 1000:
                s = DIGITS_CN[n // 100] + "百"
                rest = n % 100
                if rest:
                    if rest < 10: s += "零"
                    s += _num_to_cn(rest)
                return s
            if n < 10000:
                s = DIGITS_CN[n // 1000] + "千"
                rest = n % 1000
                if rest:
                    if rest < 100: s += "零"
                    s += _num_to_cn(rest)
                return s
            if n < 100000000:
                wan = n // 10000
                rest = n % 10000
                s = _num_to_cn(wan) + "万"
                if rest:
                    if rest < 1000: s += "零"
                    s += _num_to_cn(rest)
                return s
            return str(n)

        def _replace_num(m):
            num_str = m.group(0)
            if re.search(r'[年]', m.string[m.end():m.end() + 1] if m.end() < len(m.string) else ""):
                return num_str
            try:
                n = int(num_str)
                if n > 100000000: return num_str
                return _num_to_cn(n)
            except ValueError:
                return num_str

        script = json.loads(script_path.read_text(encoding="utf-8"))

        def _convert(obj):
            if isinstance(obj, str):
                return re.sub(r'(?<!\d)(\d{1,8})(?!\d)', _replace_num, obj)
            elif isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_convert(v) for v in obj]
            return obj

        script = _convert(script)
        script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

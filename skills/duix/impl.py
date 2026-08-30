"""duix — Duix 数字人对口型（HTTP API 自动化）

把 synthesize 脚本的 HTTP API 逻辑参数化，接进 avatar 管线：
- 输入 voice_path（配音）+ orientation（竖/横）
- 选形象库（模块化，换形象只改 AVATAR_LIBRARY）
- 调 Duix HTTP API（127.0.0.1:8383）提交合成 + 轮询
- 输出数字人视频（对口型）

Duix 容器挂载：d:/duix_avatar_data/face2face -> /code/data
"""
from __future__ import annotations
import os, time, shutil, json
from pathlib import Path
import requests
from core.base import SkillBase

DUIX_BASE = "http://127.0.0.1:8383"
# 🔴 容器内挂载根：宿主 D:/duix_avatar_data/face2face → 容器 /code/data
DUIX_HOST_DATA = Path("D:/duix_avatar_data/face2face")
DUIX_TEMP = DUIX_HOST_DATA / "temp"
DUIX_RESULTS = DUIX_HOST_DATA / "results"

# 🔴 形象库（模块化：换形象只改这里，不动其他代码）
# code = Duix 提交用的唯一标识；video = 容器内相对路径（相对 /code/data）
AVATAR_LIBRARY = {
    "portrait":  {"code": "v_01", "video": "avatar_input/v_01.mp4"},
    "landscape": {"code": "h_02", "video": "avatar_input/h_02.mp4"},
}


class Duix(SkillBase):
    name = "duix"

    def execute(self, context: dict) -> dict:
        voice_path = context.get("voice_path", "")
        if not voice_path or not Path(voice_path).exists():
            print("  [duix] ❌ 找不到配音")
            return context

        # 🔴 等 VoxCPM2 释放 GPU 显存（voice_gen 配音后模型可能未即时释放，
        #    长视频 Duix 合成需要更多显存，叠加会导致推理死锁）
        self._wait_gpu_memory(threshold_mb=8000, timeout_s=180)

        # 🔴 数字人合成固定用竖屏素材（竖屏对口型正常，横屏素材 Duix 会死锁）。
        #    场景方向由 --orientation 决定，最终画面横屏时，竖屏数字人 crop 进横屏窗口。
        #    形象库 AVATAR_LIBRARY 保留 portrait/landscape 两个入口，未来横屏素材修好再切回。
        orientation = context.get("orientation", "portrait")
        synth_avatar = AVATAR_LIBRARY["portrait"]  # 合成永远用竖屏素材
        code = synth_avatar["code"]
        avatar_video = synth_avatar["video"]

        # 1. 配音复制到 Duix 数据目录（容器内 /code/data/<name>）
        audio_name = Path(voice_path).name
        audio_dst = DUIX_HOST_DATA / audio_name
        shutil.copy2(voice_path, audio_dst)
        audio_url = f"/code/data/{audio_name}"
        video_url = f"/code/data/{avatar_video}"
        print(f"  [duix] 合成形象: {code} (竖屏素材，场景方向={orientation}), 配音: {audio_name}")

        # 2. 提交合成
        payload = {"code": code, "audio_url": audio_url, "video_url": video_url,
                   "watermark_switch": 0, "chaofen": 1, "pn": 1}
        try:
            r = requests.post(f"{DUIX_BASE}/easy/submit", json=payload, timeout=30)
            rj = r.json()
        except Exception as e:
            print(f"  [duix] ❌ 提交异常: {e}")
            return context
        if rj.get("code") != 10000:
            print(f"  [duix] ❌ 提交失败: {rj}")
            return context
        print(f"  [duix] ✅ 已提交，合成中...")

        # 3. 轮询状态
        start = time.time()
        final_result = None
        while True:
            time.sleep(5)
            try:
                q = requests.get(f"{DUIX_BASE}/easy/query", params={"code": code}, timeout=30)
                data = q.json().get("data", {})
            except Exception as e:
                print(f"  [duix] ⚠️ 查询异常: {e}")
                continue
            status = data.get("status")
            if status == 2:
                elapsed = int(time.time() - start)
                final_result = data.get("result")
                print(f"  [duix] ✅ 完成 (耗时{elapsed}s): {final_result}")
                break
            elif status == 3:
                print(f"  [duix] ❌ 失败: {data.get('msg')}")
                break
            if time.time() - start > 1800:
                print("  [duix] ❌ 超时(30min)")
                break

        if not final_result:
            return context

        # 4. 结果复制到 output_dir
        src = DUIX_TEMP / f"{code}-r.mp4"
        if not src.exists():
            print(f"  [duix] ⚠️ 结果文件未找到: {src}")
            return context
        out_dir = Path(context.get("output_dir", "."))
        dst = out_dir / "avatar_video.mp4"
        shutil.copy2(src, dst)
        context["avatar_video_path"] = str(dst)
        print(f"  [duix] 📁 数字人视频: {dst}")
        return context

    def _wait_gpu_memory(self, threshold_mb: int = 8000, timeout_s: int = 180):
        """等 GPU 显存降到阈值以下（VoxCPM2 配音后显存释放），避免和 Duix 抢显存死锁。"""
        import subprocess as _sp
        import time as _time
        start = _time.time()
        while _time.time() - start < timeout_s:
            try:
                r = _sp.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, timeout=10)
                used = int(r.stdout.strip().split()[0])
                if used < threshold_mb:
                    print(f"  [duix] GPU 显存 {used}MB < {threshold_mb}MB，安全，开始合成")
                    return
                print(f"  [duix] ⏳ GPU 显存 {used}MB ≥ {threshold_mb}MB，等 VoxCPM2 释放...")
            except Exception:
                pass
            _time.sleep(10)
        print("  [duix] ⚠️ 显存等待超时，继续合成（若失败请重试）")

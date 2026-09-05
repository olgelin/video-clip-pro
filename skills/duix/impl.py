"""duix — Duix 数字人对口型（HTTP API 自动化）

把 synthesize 脚本的 HTTP API 逻辑参数化，接进 avatar 管线：
- 输入 voice_path（配音）+ orientation（竖/横）
- 选形象库（模块化，换形象只改 AVATAR_LIBRARY）
- 调 Duix HTTP API（127.0.0.1:8383）提交合成 + 轮询
- 输出数字人视频（对口型）

🔴 卡死自愈：Duix 推理偶发卡死（Read timed out 循环 / result info [] 持续空）。
   连续查询异常 ≥6 次判定卡死 → 自动 docker restart 容器 → 重新提交（最多重启 2 次），
   不再空转 30 分钟才放弃。

Duix 容器挂载：d:/duix_avatar_data/face2face -> /code/data
"""
from __future__ import annotations
import os, time, shutil, json, subprocess
from pathlib import Path
import requests
from core.base import SkillBase

DUIX_BASE = "http://127.0.0.1:8383"
# 🔴 容器内挂载根：宿主 D:/duix_avatar_data/face2face → 容器 /code/data
DUIX_HOST_DATA = Path("D:/duix_avatar_data/face2face")
DUIX_TEMP = DUIX_HOST_DATA / "temp"
DUIX_RESULTS = DUIX_HOST_DATA / "results"

DUIX_CONTAINER = "duix-avatar-gen-video"

# 卡死判定：连续查询异常次数（5s 一次 = 30s 无响应判定卡死）
STUCK_CONSECUTIVE_ERRORS = 6
MAX_RESTARTS = 2

# 🔴 形象库（模块化：换形象只改这里，不动其他代码）
# code = Duix 提交用的唯一标识；video = 容器内相对路径（相对 /code/data）
AVATAR_LIBRARY = {
    "portrait":  {"code": "v_01", "video": "avatar_input/v_01.mp4"},
    "landscape": {"code": "h_02", "video": "avatar_input/h_02.mp4"},
}


class _DuixStuck(Exception):
    """Duix 推理卡死（连续查询异常 / 超时）。"""


class Duix(SkillBase):
    name = "duix"

    @staticmethod
    def _media_duration(path: str) -> float:
        """ffprobe 获取媒体时长（秒），失败返回 0。"""
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, timeout=30)
            return float(r.stdout.strip()) if r.stdout.strip() else 0.0
        except Exception:
            return 0.0

    def execute(self, context: dict) -> dict:
        # 🔴 幂等：数字人视频已存在则跳过合成（断点续跑，长任务失败重跑不重新合成）
        # 🔴 但必须校验配音时长匹配：LLM 每次段数不同→配音时长不同，复用旧数字人视频会导致
        #    渲染时最后一段超出数字人视频时长 → coverage 0% → 渲染中止（复用了旧竖屏成片的真凶）
        out_dir = Path(context.get("output_dir", "."))
        _dst = out_dir / "avatar_video.mp4"
        voice_path = context.get("voice_path", "")
        if _dst.exists() and _dst.stat().st_size > 1000:
            _v_dur = self._media_duration(voice_path) if voice_path else 0.0
            _a_dur = self._media_duration(str(_dst))
            # 配音时长 vs 数字人视频时长：允许 ±1.5s 缓冲（数字人合成可能有微小对齐差）
            if _v_dur > 0 and _a_dur > 0 and abs(_v_dur - _a_dur) <= 1.5:
                print("  [duix] ⏭️ 数字人视频已存在且配音时长匹配，跳过合成")
                context["avatar_video_path"] = str(_dst)
                return context
            if _v_dur > 0 and _a_dur > 0 and abs(_v_dur - _a_dur) > 1.5:
                print(f"  [duix] ⚠️ 数字人视频时长({_a_dur:.1f}s)与配音时长({_v_dur:.1f}s)不匹配，删除重新合成")
                _dst.unlink(missing_ok=True)
            else:
                # 无法获取时长（ffprobe 失败/无配音），保守跳过（保持原行为）
                print("  [duix] ⏭️ 数字人视频已存在，跳过合成")
                context["avatar_video_path"] = str(_dst)
                return context

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

        # 2. 提交 + 轮询，卡死自动重启重试（最多重启 MAX_RESTARTS 次）
        final_result = None
        for attempt in range(MAX_RESTARTS + 1):
            try:
                final_result = self._submit_and_poll(code, audio_url, video_url)
                break
            except _DuixStuck as e:
                if attempt >= MAX_RESTARTS:
                    print(f"  [duix] ❌ 重启 {MAX_RESTARTS} 次仍卡死，放弃：{e}")
                    return context
                print(f"  [duix] 🔄 {e} → 重启容器重试 ({attempt + 1}/{MAX_RESTARTS})...")
                if not self._restart_container():
                    print("  [duix] ❌ 容器重启失败，放弃")
                    return context

        if not final_result:
            return context

        # 3. 结果复制到 output_dir
        src = DUIX_TEMP / f"{code}-r.mp4"
        if not src.exists():
            print(f"  [duix] ⚠️ 结果文件未找到: {src}")
            return context
        out_dir = Path(context.get("output_dir", "."))
        dst = out_dir / "avatar_video.mp4"
        shutil.copy2(src, dst)
        # 🔴 HyperFrames 渲染要求关键帧密集（≤1s），否则多 video 分段 seek 会提取 0 帧 + audio_processing_failed。
        #    Duix 原始视频关键帧稀疏（8s+ 间隔），必须重新编码（-g 30 = 每 1s 一个关键帧）。
        _reenc = out_dir / "_avatar_reenc.mp4"
        _ffmpeg = context.get("ffmpeg_bin", "ffmpeg")
        try:
            r = subprocess.run(
                [_ffmpeg, "-y", "-i", str(dst), "-c:v", "libx264", "-preset", "medium",
                 "-crf", "18", "-r", "30", "-g", "30", "-keyint_min", "30",
                 "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", str(_reenc)],
                capture_output=True, text=True, timeout=600)
            if _reenc.exists() and _reenc.stat().st_size > 1000:
                _reenc.replace(dst)
                print(f"  [duix] 🔧 关键帧重编码完成 (GOP=1s): {dst}")
            else:
                print(f"  [duix] ⚠️ 重编码失败，保留原始视频: {r.stderr[-200:] if r.stderr else ''}")
        except Exception as e:
            print(f"  [duix] ⚠️ 重编码异常，保留原始视频: {e}")
        context["avatar_video_path"] = str(dst)
        print(f"  [duix] 📁 数字人视频: {dst}")
        return context

    def _submit_and_poll(self, code: str, audio_url: str, video_url: str):
        """提交合成 + 轮询，卡死时抛 _DuixStuck。"""
        payload = {"code": code, "audio_url": audio_url, "video_url": video_url,
                   "watermark_switch": 0, "chaofen": 1, "pn": 1}
        try:
            r = requests.post(f"{DUIX_BASE}/easy/submit", json=payload, timeout=30)
            rj = r.json()
        except Exception as e:
            print(f"  [duix] ❌ 提交异常: {e}")
            raise _DuixStuck(f"提交异常: {e}")
        if rj.get("code") != 10000:
            print(f"  [duix] ❌ 提交失败: {rj}")
            raise _DuixStuck(f"提交失败: {rj}")
        print(f"  [duix] ✅ 已提交，合成中...")

        start = time.time()
        consecutive_errors = 0
        while True:
            time.sleep(5)
            try:
                q = requests.get(f"{DUIX_BASE}/easy/query", params={"code": code}, timeout=30)
                data = q.json().get("data", {})
                consecutive_errors = 0  # 成功响应清零
            except Exception as e:
                consecutive_errors += 1
                print(f"  [duix] ⚠️ 查询异常({consecutive_errors}/{STUCK_CONSECUTIVE_ERRORS}): {e}")
                if consecutive_errors >= STUCK_CONSECUTIVE_ERRORS:
                    raise _DuixStuck("连续查询异常，判定推理卡死")
                continue
            status = data.get("status")
            if status == 2:
                elapsed = int(time.time() - start)
                print(f"  [duix] ✅ 完成 (耗时{elapsed}s): {data.get('result')}")
                return data.get("result")
            elif status == 3:
                print(f"  [duix] ❌ 失败: {data.get('msg')}")
                return None
            if time.time() - start > 1800:
                print("  [duix] ❌ 超时(30min)")
                raise _DuixStuck("合成超时 30min")

    def _restart_container(self) -> bool:
        """重启 Duix 容器；若 Docker 引擎挂，先启动 Docker Desktop 再重启。"""
        # 1. 先尝试 docker restart（容器级卡死）
        try:
            r = subprocess.run(["docker", "restart", DUIX_CONTAINER],
                               capture_output=True, text=True, timeout=120)
            out = (r.stdout or "").strip() or (r.stderr or "").strip()
            if r.returncode == 0:
                print(f"  [duix] 重启容器: {out}")
                return self._wait_container_ready()
            print(f"  [duix] ⚠️ docker restart 返回 {r.returncode}: {out[:200]}")
        except subprocess.TimeoutExpired:
            print("  [duix] ⚠️ docker restart 超时(120s)，疑似引擎挂")
        except Exception as e:
            print(f"  [duix] ⚠️ docker restart 失败: {e}")

        # 2. 引擎挂 → 启动 Docker Desktop，等引擎恢复，再 restart 容器
        print("  [duix] 🔄 Docker 引擎疑似挂，启动 Docker Desktop...")
        try:
            subprocess.run(["powershell.exe", "-Command",
                            "Start-Process 'C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe'"],
                           capture_output=True, text=True, timeout=30)
        except Exception as e:
            print(f"  [duix] ⚠️ 启动 Docker Desktop 失败: {e}")
        # 等引擎恢复（最多 300s，Docker Desktop 冷启动 + WSL2 后端可能要 3-4 分钟）
        for _ in range(30):
            time.sleep(10)
            try:
                r = subprocess.run(["docker", "ps"], capture_output=True, text=True, timeout=15)
                if r.returncode == 0:
                    print("  [duix] ✅ Docker 引擎已恢复，重启容器")
                    subprocess.run(["docker", "restart", DUIX_CONTAINER],
                                   capture_output=True, text=True, timeout=120)
                    return self._wait_container_ready(timeout_s=300)
            except Exception:
                pass
        print("  [duix] ❌ Docker 引擎恢复超时(300s)")
        return False

    def _wait_container_ready(self, timeout_s: int = 120) -> bool:
        """等 Duix 容器恢复（curl 8383/docs 直到响应）。"""
        for _ in range(timeout_s // 2):
            try:
                requests.get(f"{DUIX_BASE}/docs", timeout=5)
                print("  [duix] ✅ 容器已恢复")
                return True
            except Exception:
                time.sleep(2)
        print("  [duix] ⚠️ 容器恢复超时")
        return False

    def _wait_gpu_memory(self, threshold_mb: int = 8000, timeout_s: int = 180):
        """等 GPU 显存降到阈值以下（VoxCPM2 配音后显存释放），避免和 Duix 抢显存死锁。"""
        start = time.time()
        while time.time() - start < timeout_s:
            try:
                r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                   capture_output=True, text=True, timeout=10)
                used = int(r.stdout.strip().split()[0])
                if used < threshold_mb:
                    print(f"  [duix] GPU 显存 {used}MB < {threshold_mb}MB，安全，开始合成")
                    return
                print(f"  [duix] ⏳ GPU 显存 {used}MB ≥ {threshold_mb}MB，等 VoxCPM2 释放...")
            except Exception:
                pass
            time.sleep(10)
        print("  [duix] ⚠️ 显存等待超时，继续合成（若失败请重试）")

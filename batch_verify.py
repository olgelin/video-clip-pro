# -*- coding: utf-8 -*-
"""批量生产验证：3 横屏 + 2 竖屏，串行跑，最后汇总。"""
import subprocess, sys, time, json
from pathlib import Path

PY = r"E:\Hermes-Agent\core\venv\Scripts\python.exe"
ROOT = Path(r"E:\Hermes-Agent\workspace\xiaoshan\video-clip-pro")

JOBS = [
    # (视频路径, 输出目录, 标签)
    (r"C:\Users\Administrator\Desktop\中国外贸政策热点.mp4", "output/pip/batch_贸易", "横屏·外贸"),
    (r"C:\Users\Administrator\Desktop\GPT5-AI热点短视频.mp4", "output/pip/batch_GPT5", "横屏·GPT5"),
    (r"C:\Users\Administrator\Desktop\SpaceX-马斯克万亿美元.mp4", "output/pip/batch_SpaceX", "横屏·SpaceX"),
    (r"C:\Users\Administrator\Desktop\AA\微信视频2026-08-17_150801_616.mp4", "output/pip/batch_竖屏1", "竖屏·129s"),
    (r"C:\Users\Administrator\Desktop\AA\微信视频2026-08-17_150755_359.mp4", "output/pip/batch_竖屏2", "竖屏·208s"),
]

results = []
for i, (video, outdir, label) in enumerate(JOBS, 1):
    print(f"\n{'='*60}")
    print(f"[{i}/{len(JOBS)}] {label}: {video}")
    print(f"{'='*60}", flush=True)
    t0 = time.time()
    cmd = [PY, "pipeline.py", video, "--mode", "pip", "--output", outdir]
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=3600)
        elapsed = int(time.time() - t0)
        ok = r.returncode == 0
        # 提取 review 分数
        import re
        m = re.search(r'Review: score=(\d+)', r.stdout + r.stderr)
        score = int(m.group(1)) if m else None
        final = Path(ROOT) / outdir / "final_polished.mp4"
        size = round(final.stat().st_size / 1024 / 1024, 1) if final.exists() else None
        results.append({"label": label, "ok": ok, "score": score, "size_mb": size, "elapsed_s": elapsed})
        print(f"  {'✅ 成功' if ok else '❌ 失败'} score={score} size={size}MB 耗时{elapsed}s", flush=True)
        if not ok:
            tail = (r.stdout + r.stderr).strip().splitlines()[-5:]
            print("  末尾日志:", *tail, sep="\n    ", flush=True)
    except subprocess.TimeoutExpired:
        results.append({"label": label, "ok": False, "score": None, "size_mb": None, "elapsed_s": 3600})
        print(f"  ⏱ 超时(3600s)", flush=True)
    except Exception as e:
        results.append({"label": label, "ok": False, "score": None, "size_mb": None, "elapsed_s": None})
        print(f"  ❌ 异常: {e}", flush=True)

print(f"\n\n{'='*60}")
print("批量验证汇总")
print(f"{'='*60}")
ok_count = sum(1 for r in results if r["ok"])
print(f"成功 {ok_count}/{len(results)}")
for r in results:
    flag = "✅" if r["ok"] else "❌"
    print(f"  {flag} {r['label']}: score={r['score']} size={r['size_mb']}MB 耗时{r['elapsed_s']}s")

import sys, json
sys.path.insert(0, "E:/Hermes-Agent/workspace/xiaoshan/video-clip-pro")

base = "E:/Hermes-Agent/workspace/xiaoshan/video-clip-pro/output/avatar-short/为什么现在的新能源汽车卖不动了？"
ctx = json.load(open(base + "/pipeline_context.json", encoding="utf-8"))
ctx["enable_bgm"] = True

# bgm_mix 需要 final_polished + scenes + script_data
ctx["final_polished"] = base + "/final_polished.mp4"

from skills.bgm_mix.impl import Bgm_mix
bgm = Bgm_mix()
result = bgm.execute(ctx)

print("\n=== 结果 ===")
print("bgm_path:", result.get("bgm_path", "(无)"))
import os
for f in ["final_bgm.mp4", "bgm.wav", "final_no_bgm.mp4"]:
    p = base + "/" + f
    if os.path.exists(p):
        print(f"  {f}: {os.path.getsize(p)//1024}KB")

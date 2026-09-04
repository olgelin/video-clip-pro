# avatar-short 数字人管线 · 硬约束（违反就出 Bug）

> 这条管线（话题→口播稿→配音→Duix数字人→分镜→HyperFrames画面）的铁律。
> 改动任何 skill 前，先读这里。来源：2026-09 的 BAC 打磨 + 踩坑复盘。

## 1. 数字人布局契约（person_layout）

布局值必须用**连字符**，不能用下划线：

| 值 | 含义 | 横屏坐标(1920×1080) |
|---|---|---|
| `right-rail` | 大竖条(右) | (1280,0,640,1080)，内容区 1250 |
| `left-rail` | 大竖条(左) | (0,0,640,1080)，内容区 1250 |
| `corner-br` | 小角标(右下) | (1650,734,230,306)，内容全屏 1920 |
| `corner-bl` | 小角标(左下) | (40,734,230,306)，内容全屏 1920 |
| `hidden` | 完全消失 | x=fw+60 移出画面，内容全屏 1920 |

- 🔴 竖条宽度 640（=1920 的 1/3），缝隙 30，内容区 1920-640-30=1250。
- 🔴 `corner_bl`（下划线）和 person_zone 的 `corner-bl` 不匹配 → 全部 fallback 右下角标。**必须连字符**。

## 2. 景别决定大小，LLM 只判左右

- **大小由 shot_scale 确定性决定**（防 LLM 随机性）：
  - `full`（满版）→ 角标(230×306) + 内容全屏
  - `inset`（缩小）→ 大竖条(640×1080) + 内容分栏
- **左右/出镜由 LLM 读语义判断**（L/R/H，灵活创意）。
- 景别严格交替：开场必 full，绝不连续两个 full。

## 3. 数据铁律（画面生命线）

- 🔴 口播稿每个段落必须带 **1-2 个绝对值数字**（"月活1000万""8亿"），禁止只写相对数（"下降80%"）。
- 🔴 卡片 C 位大数字必须填真实数字，**禁止写 0 / 占位**。
- 🔴 数字写**静态真实值** + scale 弹入，**禁止 countUp 从 0 数**（见 bug-patterns/seek-rendering-traps.md）。

## 4. 数据流断裂铁律

- 上游字段升级，必须查下游消费者。
- 实例：storyboard 加 person_layout → hf_build_avatar 没消费 → hf_card_builder 又用 visual_type 硬编码丢了 LLM 结果。
- 改任何字段，`search_files` 查所有 `get("字段名")` 的下游。

## 5. 拒绝套模板（用户红线）

- 卡片/画面永远是"技法菜单给选项"，不是"完整模板照抄"。
- 用户原话："我们最讨厌的就是套模板了，我们要的是创意"。
- 约束 = 创意导向参数，不是僵化模板。给 LLM 技法菜单选，不给空白也不给锁死的模板。

## 6. 动画铁律（seek 驱动专用）

- 所有动画 `tl.to/from/fromTo`（禁止独立 gsap）。
- `repeat` 正整数 ≤5（禁止 -1）。
- 元素慢慢出来：标题先出→标签→数据逐个弹，禁止所有元素同时弹 = PPT 感。

## 7. 数字人换位 = 每段独立 video（LLM 编排位置 + 确定性渲染）

- 🔴 **根因（铁证实验）**：HyperFrames canvas 合成（drawImage）**只读 video 的初始 CSS 位置，不读 GSAP 动画（timeline seek）后的位置**。所以 GSAP 的 left/top/width/height 换位动画在整体渲染下**从未生效**——数字人一直冻结在场景 0 的初始位置。
- 🔴 **解法**：位置仍由 LLM 语义判断（person_layout→person_zone，不锁死编排），但渲染用**每段一个 video、初始 CSS 写死=该段位置 + data-start/data-duration 控制显示**。开场场景 0 拆「满幅段 + 缩位段」两个 video，hidden 场景不放 video。
- ⚠️ **历史误判教训**：① 曾以为"换位靠 GSAP 确定性生效"（错，是视觉模型误判，把内容元素当成了数字人换位）；② 曾 revert 正确的"每场景固定 video"方案（636998b），误判成"代码锁死"——实际上 person_layout 仍是 LLM 判断，只是渲染机制从 GSAP 改成确定性初始位置。**判断"是否锁死"要看"编排是否 LLM 决定"，不是看"渲染用不用动画"**。
- 验证换位必须抽帧精确看"数字人在左/右、占屏比例"，不能只看"有没有人"——视觉模型会把内容元素误判成数字人。

## 7.5 HyperFrames clip 契约（多 video 正确写法，照 hyperframes-core skill）

- 🔴 **`data-start` = 合成时间轴的秒数**（从合成开始，即"这个 clip 在时间轴哪个位置显示"），**不是文件 seek**。曾误当文件 seek 用，导致多 video 帧提取 0 帧 + audio_processing_failed。
- 🔴 **`data-media-start` = 文件内 seek**（跳过源文件前几秒）。多 video 各自播放不同场景片段时，`data-start` 和 `data-media-start` 都要设（都 = seg_offsets[i]），否则所有 video 都从文件 0s 播、内容错位。
- 🔴 **`data-track-index` 控制时间重叠，不是视觉层级**：同 track 的两个 clip 不能时间重叠（lint 报错）；视觉前后用 CSS z-index。多 video 可共享 track 0（各自 data-start 顺序排列不重叠即可），不必递增 track。
- 🔴 **关键帧必须密集（≤1s）**：Duix 原始视频关键帧间隔 8.33s，HyperFrames 报"sparse keyframes → seek failure/frame freezing"。Duix 生成后必须 ffmpeg 重编码（`-g 30 -keyint_min 30` = 每 1s 一个关键帧）。
- ✅ 实测：2-4 个 video 同 src final.mp4 分段 seek（data-start + data-media-start 都设）渲染成功、覆盖率 100%，**无需切片**。最小测试（仅 video+audio）全通过，问题只在完整 pipeline 结构里复现。

## 7.6 sub-composition 必须 `<template>` 包装（动画静态的根因）

- 🔴 **HyperFrames 的 sub-composition（data-composition-src 加载的 beat-N.html）必须用 `<template>` 包住全部内容**，`<style>` 和 `<script>` 也必须在 template 内。runtime 只克隆 `<template>` 内容，`<head>` 里的东西（含 style）被丢弃。
- 🔴 **症状**：无 template 时，渲染器捕获"静态初始帧"——视频全长度但动画不播、Three.js 粒子不显示、元素样式丢失。`lint`/`validate`/`inspect` 都查不出来（单文件孤立检查通过），只有实际渲染才暴露。
- 🔴 **avatar 的 beat-N.html 之前无 template**（`<!DOCTYPE><head><style>...</style></head><body><div>...`），导致画面"静态"。修复：`<template><style>...</style>` + scene_html(GSAP/Three.js 都在内) + `</template>`。
- ✅ 最小测试验证：sub-composition 加 template 后，GSAP 方块动画 2s→6s 位置 x=366→1300，动画正常播放。
- 检查方法：`grep "<template>" compositions/beat-*.html` 每个都应有 `<template>`。

## 7.7 Three.js 粒子 z-index（背景遮挡根因）

- 🔴 **方向2（背景 LLM 生成）后，LLM 会把不透明背景渐变放进 `main-content`（z-index:1），而 Three.js 的 `<canvas>` 是 z-index:0，在 main-content 之下 → 被背景盖住，粒子白画、画面静态**。
- 🔴 **修复**：`_fix_canvas_zindex` 兜底把 `<canvas>` 的 z-index 0→2（高于 main-content 的 1）；scene_system 约束 canvas z-index:2、背景渐变用 `rgba` 半透明。
- 🔴 **症状识别**：抽帧像素差极小（<2）= 静态；但 beat-N.html 里有 `new THREE.WebGLRenderer` + `hf-seek`（Three.js 代码在）→ 说明不是代码缺失，是 z-index 遮挡。

## 7.8 Three.js 动画必须确定性（累积下坠 desync 根因）

- 🔴 **HyperFrames 逐帧 seek 渲染（乱序/并行），任何"累积状态"（`p[i*3+1]-=spd[i]`）都会 desync → 粒子静止**。vf 用 standalone 顺序播放所以累积能侥幸动，avatar 整体渲染必须确定性。
- 🔴 **正确做法**：位置是时间 t 的纯函数 `y = y0[i] - spd[i]*t`（生成时存 `y0[i]`，rd(t) 里用 t 计算）。旋转用 `rotation.y=t*速度`（t 的纯函数），不要 `+=`。
- 🔴 **速度单位**：确定性下坠的 spd 单位是"每秒"（`0.3+Math.random()*0.7`），不是"每帧"（累积下坠的 `0.06+...` 是每帧）。
- 🔴 **determinism-rules 原文**："reaching for setTimeout/requestAnimationFrame/addEventListener to drive a visual → rebuild as a tween on the timeline"。hf-seek 事件驱动（addEventListener）本身就是反模式，正确是 GSAP timeline 或 t 的纯函数。

## 7.9 sub-composition 里 window 是代理，hf-seek 监听必须用 globalThis

- 🔴 **sub-composition 的 script 里，`window` 是 HyperFrames 的代理对象，`window.addEventListener("hf-seek",...)` 抛 `TypeError: Illegal invocation`**（native 方法被解绑，this 不对）。导致 Three.js 的 hf-seek 监听注册失败 → 粒子不更新（静态）。
- 🔴 **修复**：用 `globalThis.addEventListener("hf-seek",...)` 和 `globalThis.__hfThreeTime`（globalThis === 真实 window，绕过代理）。实测 `globalThis` 能收到 hf-seek 事件（SEEK:0.5），而 `window` 抛错、`document` 收不到 window 上的事件。
- 🔴 **诊断方法**：sub-composition 里用 try-catch 包住 `window.addEventListener`，报 "Illegal invocation" 就是代理问题。standalone 的 window 是真实的（不抛错），只有 sub-composition 才踩这个坑——所以最小测试要用 sub-composition 结构复现。

## 7.10 Three.js 库必须内联在 host（hf-seek 不触发的最终根因）

- 🔴 **hf-seek 事件由 HyperFrames 的 "three" adapter 在 seek 时 dispatch，但 "three" adapter 的 discover 检测 `window.THREE?.DefaultLoadingManager`——只有 host（真实 window）有 THREE 才启用 adapter**。若 Three.js 库只内联在 beat sub-composition（host 无 THREE），adapter 不启用 → seek 不 dispatch hf-seek → 粒子收不到事件 → rd 不执行 → 粒子静态。
- 🔴 **症状区分**：beat-N.html standalone 渲染粒子动（像素差 ~15），整体渲染（sub-composition 加载）静（<1）→ 就是 host 缺 Three.js。这是区分"Three.js 代码对不对"和"hf-seek 驱动对不对"的关键测试。
- 🔴 **修复**：`build_hyperframes_composition` 的 host index.html 里内联 `three.min.js`（之前注释写"Load GSAP + Three.js"但实际只内联了 gsap，漏了 Three.js）。
- 🔴 **完整链路（8 个叠加根因）**：①beat-N.html 无 `<template>` 包装（内容/动画静态）→ ②canvas z-index 0 被背景遮挡（粒子不可见）→ ③window.addEventListener 抛 Illegal invocation（改用 globalThis）+ 累积下坠 desync（改确定性 y0-spd*t）→ ④host 缺 Three.js（hf-seek 不触发）→ ⑤多 beat 顶层 const 冲突 → ⑥var tl 截断漏闭合 </script> → ⑦hf-seek 被 __player.renderSeek 短路（粒子偶发静）→ ⑧PointsMaterial 无 map 渲染成方块（粒子形状突兀）。八个全修粒子才稳定动+形状圆润（交叉验证暴露 ⑤⑥⑦⑧）。

## 7.11 多 sub-composition 顶层 const 冲突（粒子静态根因 5）

- 🔴 **多个 beat 的粒子 script 顶层 `const c` / `const s` / `const N` / `const g` + `function rd` 在 HyperFrames inline 到 host 后共享全局词法环境**，第二个场景执行到 `const c` 抛 `SyntaxError: Identifier 'c' has already been declared` → 整个 script 块不执行 → 粒子静态 + `window.__timelines` 注册失败（poll 报 "not registered"）。
- 🔴 **铁证**：node vm 模拟共享全局词法环境执行两个 script 块 → `SyntaxError: Identifier 'c' has already been declared`。
- 🔴 **修复**：`_wrap_particle_iife`（scene_base.py）把含 `new THREE.WebGLRenderer` 的 `<script>` 包成 IIFE `(function(){...})()`，const 变函数作用域。已包过的（`(function` 开头）跳过防双重包装。框架的 three.min.js/gsap.min.js 开头是 `/*!` 注释不匹配，不会被误包。

## 7.12 LLM 的 var tl 截断漏闭合 </script>（粒子静态根因 6，最隐蔽）

- 🔴 **LLM 偶发生成 `var tl=new TimelineMax()`（GSAP 2.x 旧 API）+ 超长深链选择器 `tl.from("#main-content > div > div > ...几百个 div...")`，陷入重复循环后截断**，导致：①语句不完整（缺 `",{...});`）②`</script>` 漏写 ③且这段 script 是 LLM content 的**最后一个元素**（后面就是 EOF，没有 `</script>`）。
- 🔴 **为什么旧 `_rm_gsap` 漏了**：`re.sub(r'<script[^>]*>.*?</script>', ...)` 匹配这段 script 时，`.*?</script>` 找不到 `</script>`（后面是 EOF，GSAP 库是框架注入的、不在 LLM content 里）→ 匹配失败 → script 残留 → script 标签不配对（5 开 4 闭）→ HyperFrames 拼接执行报 `[Browser:PAGEERROR] Invalid or unexpected token` → 所有 timeline 注册失败。
- 🔴 **误判陷阱**：用"还原的 content（含框架 GSAP 库的 `</script>`）"测试会误判 `_rm_gsap` 能移除——因为框架库的 `</script>` 恰好让 `.*?` 匹配成功。真实 LLM content 里那段 script 后面是 EOF，`_rm_gsap` 匹配失败。**必须用"script 后面 EOF 无 </script>"的真实结构测试**。
- 🔴 **修复（双保险）**：①`_rm_gsap` 判断加 `new Timeline(Max|Lite)`/`new Tween(Max|Lite)`/`TimelineMax\b`（识别 GSAP 2.x 旧 API）；②终极兜底 `re.sub(r'<script[^>]*>(?:(?!</script>|<script[^>]*>).)*$', '', html)` 清掉残留的孤立 `<script>`（有开无闭直到 EOF）。③prompt 治本（scene_system.md）：禁止 `new TimelineMax`、禁止深链选择器（最多 1 层 `>`）、禁止内联 GSAP 库、强调 `</script>` 闭合。

## 7.13 hf-seek 被 __player.renderSeek 短路（粒子偶发静根因 7）

- 🔴 **HyperFrames 有数字人 video（host 里 `<video class="avatar-clip">`）时，runtime 初始化 `__player.renderSeek`，`seekAllAdaptersInBrowser` 里 `runtimeSeeked=true` → `if (!runtimeSeeked)` 为 false → `window.dispatchEvent(new CustomEvent("hf-seek",...))` **不执行** → 粒子 `globalThis.addEventListener("hf-seek",e=>rd(...))` 收不到事件 → rd 不被调用 → 粒子静**。
- 🔴 **关键代码（cli.js `seekAllAdaptersInBrowser`）**：`if (typeof w3.__player?.renderSeek === "function") runtimeSeeked = tryCall(...); ... if (!runtimeSeeked) window.dispatchEvent(hf-seek)`。但 **GSAP timeline 的 seek 是 `Object.values(w3.__timelines).forEach(tl=>tl.totalTime(tt3))` 在 `if(!runtimeSeeked)` 之外，无条件执行**。
- 🔴 **偶发性铁证**：话题1 重新渲染 s0/s2/s4 动、s1/s3 静；话题2 第一次全静；话题2 --debug 重渲染 s2/s4/s6 动。同一份代码 + 同一技法（bg3d）结果不同 = `__player.renderSeek` 初始化时序竞争（seek 发生在 player 初始化前则 hf-seek 正常 dispatch 粒子动，之后则被短路粒子静）。
- 🔴 **修复**：`_wrap_particle_iife` 包 IIFE 时追加 GSAP timeline 驱动——`(function(){var _tl=gsap.timeline({paused:true});_tl.to({},{duration:3600,ease:"none",onUpdate:function(){rd(_tl.time())}});globalThis.__timelines["_particle_<canvasId>"]=_tl;})()`。GSAP seek 无条件执行 → onUpdate 驱动 rd → 粒子必动。hf-seek 保留作 fallback（无 video 的 hidden 场景仍走 hf-seek）。
- 🔴 **注意**：`rd` 用全局合成时间（`_tl.time()` = tt3），和 hf-seek 的 `e.detail.time` 一致，行为不变。
- 🔴 **遗漏真凶（2026-09-04 复发）**：`_default_threejs`（LLM 没生成 Three.js 时的兜底粒子，canvas id=pt3d）只有 hf-seek 没有 GSAP timeline 驱动 → 有数字人 video 时兜底粒子静（四角全 0.00 完全冻结）。之前只给 `_wrap_particle_iife`（LLM 生成粒子）加 GSAP 驱动，漏了兜底粒子。修复：`_ensure_threejs` 兜底路径 `_default_threejs` 输出也走 `_wrap_particle_iife`。
- 🔴 **验证判据（别误判）**：四角+中心**全 0.00** = 粒子脚本问题（完全冻结，bug）；只有角落弱但中心/其他角有运动 = 透视/分布特性（正常）。上次把"场景3 全 0.00 冻结"误判成"透视特性"没抓到，就是没看中心 diff。

## 7.14 PointsMaterial 无 map 渲染成方块（粒子形状突兀根因 8）

- 🔴 **Three.js `PointsMaterial` 无 `map` 纹理时，fragment shader 不裁剪 `gl_PointCoord`，点渲染成正方形**（不是圆形光点）。vf 的粒子 size 小（0.03~0.08）方块不明显，avatar 三层粒子第三层 `size:.5` 大方块非常突兀（vision 铁证："大量规整正方形粒子，像数字噪点，与星空主题不匹配"）。
- 🔴 **修复**：`_inject_round_texture`（scene_base.py）给每个 `PointsMaterial({...})` 注入 `map:_roundTex`（canvas 径向渐变圆形纹理），粒子变柔和圆形光晕。`_wrap_particle_iife` 和 `_default_threejs` 两处都调用，幂等（已注入则跳过）。
- 🔴 **附带修复（本轮同批）**：①outro 话题卡片 `topic[:10]` 截断尴尬（长话题"为什么年轻人越来越不愿意结婚"切到"越"字）→ 改 `[:20]`+省略号；②`_cleanup_output` 漏删 `bgm.wav`/`lyrics.txt` → 加入 keep_files 保留；③BGM 时长对齐 VF：`_calc_bgm_duration` 按歌词长度线性映射+随机抖动 ±3s（区间 [视频时长, +12s]，不锁死固定值）；④BGM caption 情绪对齐 VF：storyboard 的 scenes 只存 `mood`（中文情绪"冲击 悬念/冷静 理性/…"）不存 `beat`，旧 `_build_caption` 用 `s.get("beat")` 拿到空串 → mood_map 查不到 → caption 永远兜底"cinematic, engaging"；改用 `mood` 字段映射英文 music mood。

## 8. 字幕 = 词级转录对齐配音（不是整段均匀拆分）

- 🔴 VoxCPM2 只返回**段落级** scene_durations，没有词级/句级时间戳。
- 🔴 字幕必须对 step05_voice.wav 做 faster-whisper 词级转录（`voice_gen` 后加 `transcribe_voice` stage，phase 2.5），真实对齐配音语速。
- 🔴 Whisper 把"1200万"转录成 "12"+"00"+"万" 三个 token，`_merge_cjk_words` 必须加**数字连续性合并**（`_NUM_RE`），否则字幕出现"12"+"00万"断裂。
- 🔴 数字用中文读但 Whisper 转录成阿拉伯数字（"一千二百"→"1200"），合并后归一到阿拉伯数字，属正常。

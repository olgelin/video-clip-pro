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

## 8. 字幕 = 词级转录对齐配音（不是整段均匀拆分）

- 🔴 VoxCPM2 只返回**段落级** scene_durations，没有词级/句级时间戳。
- 🔴 字幕必须对 step05_voice.wav 做 faster-whisper 词级转录（`voice_gen` 后加 `transcribe_voice` stage，phase 2.5），真实对齐配音语速。
- 🔴 Whisper 把"1200万"转录成 "12"+"00"+"万" 三个 token，`_merge_cjk_words` 必须加**数字连续性合并**（`_NUM_RE`），否则字幕出现"12"+"00万"断裂。
- 🔴 数字用中文读但 Whisper 转录成阿拉伯数字（"一千二百"→"1200"），合并后归一到阿拉伯数字，属正常。

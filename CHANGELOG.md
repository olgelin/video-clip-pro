# Changelog — Video Clip Pro

## V29.3 (2026-08-20) — 小元素动画幅度加大（肉眼明显）+ 直出重试

- 根因：V29 让动画"动"了但幅度太小（光晕 opacity 1→0.6、数字 scale 1→1.06），像素能测到动但肉眼看不出来，用户感觉"没更新"
- 修复 1（幅度）：scene_system.md 动效铁律 + few-shot 加大幅度——光晕 opacity 1→0.25 + scale 1→1.5、数字呼吸 scale 1→1.15、粒子位移 ≥200px，加"幅度必须肉眼明显"铁律（光晕变化≥60%、数字≥1.12、粒子≥200px）
- 修复 2（重试）：`_llm_card_html_direct` 空/坏输出重试一次，降低 fallback 到旧模板概率

---

## V29.2 (2026-08-20) — 空内容卡片兜底

- 根因：LLM 偶发输出"完全空"（151 字符无内容）或"有内容无动画"（有 div 无 GSAP script），旧校验只查 `<div>` 导致漏过，渲染出空壳/静态卡片
- 修复：`skills/hf_build/impl.py` 加 `_is_empty_card()` 校验（内容<800字符 / `...`占位符 / 无 script / 无 tl 动画 / 无文字 → 判空），不合格 fallback 到完整模板卡片

---

## V29.1 (2026-08-20) — DeepSeek 备用 API key（欠费自动切换）

- 主 key 402 欠费时，自动切换到备用 key（存 `.env`，gitignore 不提交，key 不泄露）
- `core/provider.py`：`call()` 支持多 key 轮换，`_load_backup_key()` 从环境变量 `DEEPSEEK_API_KEY_BACKUP` 或 `.env` 读备用 key

---

## V29 (2026-08-20) — 卡片装饰元素"静态不动"修复（动效对齐 video-factory）

### 问题
用户反馈：卡片里有很多元素组件（光晕/扫光/粒子/信号条），但渲染出来是**静态的**，只有入场弹一下。

### 根因（对比 video-factory 成功基线）
1. **呼吸/光晕动画用独立的 `gsap.to`（不在 `tl` 时间线里）**：HyperFrames 渲染是"按时间 seek 时间线"，独立 gsap 不跟随 seek，渲染出来就是静态。video-factory 铁律明确禁止独立 gsap.to。
2. **`repeat:1` 只动一下就停**：video-factory 基线是呼吸 `repeat:3`，至少 2-3 个持续微动覆盖整个场景时长。
3. **"输出格式"模板含 `...`/`<!-- 注释 -->` 占位符**：LLM 被带偏，偶发输出未填充的骨架（空 div、无 script）。

### 修复（scene_system.md 动效规范对齐 video-factory）
- 所有动画用 `tl.from`/`tl.to`，禁止独立 `gsap.to`/`gsap.from` 在 tl 时间线外
- 呼吸/光晕/脉冲/扫光/粒子 `repeat≥3`（覆盖整个卡片时长），禁止 `repeat:1`
- 至少 2-3 个持续微动动画，粒子用 tl.to 从 0 秒开始持续下坠
- 禁止 CSS animation/@keyframes（渲染层不跟随 seek），动画只用 GSAP
- 时间用绝对秒（`}, 0.8)`），不用 `+=`
- 删除"输出格式"占位符模板，禁止 `...`/空注释/未填充骨架

### 验证
- 2 张测试卡（triumphant + urgent）均输出 18/17 个 tl 动画、repeat≥3 持续微动、0 独立 gsap、0 CSS animation
- triumphant 卡：10 个 tl.from 入场 + 8 个 tl.to 持续微动（数字呼吸 + 光晕脉动×2 + 扫光循环 + 粒子×3 下坠）

---

## V28 (2026-08-20) — 支持 20:9 非标准竖屏（1080×2400）

### 背景
用户投喂的视频是 1080×2400（20:9 超长竖屏，非标准 16:9），人物贯穿全画面。管道硬编码竖屏 1080×1920，直接跑会被 object-fit:cover 裁掉上下 20%（头+脚）。

### 修复
1. **渲染分辨率跟随实际视频**：`core/hf_card_builder.py` 的 `fw,fh` 从硬编码 `(1080,1920)/(1920,1080)` 改为 ffprobe 读实际宽高，失败回退 16:9 标准。标准 16:9 行为完全不变。
2. **2x 超分保持宽高比**：`skills/upscale/impl.py` 的 `_detect_2x_scale` 从强制 `2160:3840/3840:2160` 改为 `w*2:h*2`，且超 NVENC h264 硬编码上限 4096 时等比缩到长边 4096（20:9 竖屏 2x 会到 2160×4800 超限）。

### 验证
- 1080×2400 视频卡片模式成品 = 1080×2400（20:9 保持，无裁切）
- 14/14 卡片合成 + 位置左/中/右轮换正常
- 2x 目标：1080×1920→2160:3840（不变）、1920×1080→3840:2160（不变）、1080×2400→1842:4096（缩到上限不变形）

---

## V27 (2026-08-20) — 长视频卡片模式 + 飞书投喂

### 长视频卡片模式（动态渲染超时）
- **问题**：25.5 分钟视频被切成 259 段卡片，fullscreen 整体渲染超过固定 900s 超时 → 卡片全没合成，fallback 无卡片成品
- **修复**：`_render_fullscreen` 超时改动态 `max(900, 卡片数*15)` 秒，259 卡 = 3885s（65分钟）
- **验证**：259 卡渲染 40 分钟成功，卡片合成进成品（25.5 分钟 → 17.5 分钟，剪掉 31%）

### 飞书视频投喂（feishu-video-ingest skill）
- 用户发飞书文件分享链接 → 提取 token → `GET /drive/v1/files/{token}/download` → 本地处理
- 关键：机器人不能下载聊天直接发的文件（报 234008），但**分享链接 token 可以直接下载**
- 解决"人不在电脑旁、视频在手机、数据尽量本地"场景

---

## V26 (2026-08-19) — fullscreen 卡片视觉升级（蓝色科技风）+ 三个 bug 修复

### 卡片视觉升级（对齐 video-factory 设计水准）
- **scene_system.md 重写**：加「创意加速器」（隐喻降维/一个异物/颜色撒谎/空比满）+ 配色菜单（蓝 #6c8cff / 青 #00d4ff 为主，紫/金点缀）+ 背景元素菜单（渐变/光晕/粒子/扫光/网格，选 2-3 种）+ few-shot 完整示例 + 数据元素 1-3 个硬要求
- **统一蓝色科技风**：深色蓝紫渐变底 + 霓虹青蓝点缀，情绪差异用蓝色系深浅表达，不跳红/绿
- **CARD_DIRECT_PROMPT 简化**：去掉旧「第一步判断/第二步选元素」结构（导致 LLM 卡在选元素、只输出信号条片段），改成直接参照 scene_system 规范

### 三个 bug 修复
1. **CSS 中文崩溃**：LLM 把中文写进 `<style>` 导致 HyperFrames `Unknown word` 编译失败 → `_css_has_chinese()` 检测并 fallback
2. **竖屏变横屏**：upscale 写死 `scale=3840:2160` → `_detect_2x_scale()` 探测方向（含 ffprobe csv 结尾逗号解析修复）
3. **卡片位置锁底部**：位置按 beat 分类，方言视频 20/22 段被标 hook 导致全居中底部 → 改 idx%3 轮换（左下/居中底部/右侧中）

### 模型配置
- `card_direct/card_html/card_enrich` 任务 max_tokens 4000→8000（卡片 HTML 需要更多输出）

### 验证
- 23/23 卡片直出成功（fail=0），竖屏 1080×1920/4K 2160×3840，位置左/中/右轮换，字幕不重叠

---

## V25 (2026-08-18) — 全管道验收 + HyperFrames 0.7.109 适配

### 可播放性修复（核心）
- **yuv420p 强制**：`core/hf_card_builder.py` 的 `_compose_pip` 和 `skills/upscale/impl.py` 原来 `format=rgba` + 不写 `pix_fmt`，ffmpeg 自动选了 yuv444p（4:4:4），手机/微信/浏览器全拒播。修法：两处都显式加 `-pix_fmt yuv420p`。**成品必须 4:2:0，这是生产铁律。**

### 输出极简 + 空间控制
- **`--no-2x`**：跳过 4K 超采样，单视频 60~130MB（100 个约 6~13GB）
- **`--debug`**：保留中间产物，否则生产模式自动清理，每个视频目录只留 `final_polished.mp4`（+ 可选的 `_2x`）

### fullscreen 管道两处 bug（HyperFrames 升级后暴露）
1. **卡片 HTML 偶发写成 JS 字符串**（缺 `data-composition-id`）→ 加检测，坏卡片用模板兜底
2. **standalone 渲染改造误伤 fullscreen**：pip 全屏场景的"逐卡 standalone 渲染"不适合 fullscreen 小卡片 → 恢复 fullscreen 整体渲染

### 验证
- pip + fullscreen 两管道端到端通过，成品 yuv420p 可播放、有音频、完整解码

---

## V24 (2026-08-14) — PIP 管道定版

### 剪辑流程重构（核心）
- **字词级删减**：whisper `small` → `large-v3`（逐字时间戳，句首误差 0.14s），understand 按字/按句意输出 `delete_ids + segments`，edit 按精确区间剪切
- **剪辑后重新转写**：新增 `re_transcribe` 阶段，final.mp4 重新提取时间戳，字幕/分镜基于新视频 → **字幕音画同步**
- **两步 LLM 删减**：`understand`（初编）+ `understand_verify`（复查），补充漏删的口误/重复、恢复误删的有信息量内容
- **删减稳定性**：删减过度兜底（保留率 <40% fallback 保守删减）、短语合并 `max_chars=12`（避免超长短语）、语义完整短语约束（5-15 字）

### 画面稳定性三大兜底（LLM 生成 HTML 不稳定）
- **Three.js 缺失兜底**：`_ensure_threejs` 检测 LLM 只输出注释 → 注入默认蓝紫渐变粒子（N=3000）
- **省略号 style 检测**：`_validate` 检测 `style="..."` >3 个 → 强制重新生成
- **推理文字污染**：`_clean_scene` 剥离 + fallback deepseek-chat

### 视觉打磨
- **窗口形状随机**：圆形（50%）+ 钝角方（28px/42px）三形状随机切换，不裁人物、不单调
- **窗口位置**：去掉顶部/中心，只留底部 + 边缘 6 位置
- **去 2D 干扰**：移除背景大字（ghost text）+ CSS 网格，追求 3D 纯净感（只留 Three.js 粒子 + 光晕 + 扫光）
- **横竖屏**：`_detect_orientation` + 动态 fw/fh（竖屏 1080×1920 / 横屏 1920×1080），端到端验证通过

### 工程修复
- `loader` 类名驼峰兼容（`re_transcribe → ReTranscribe`，`hf_build_pip → Hf_build_pip`）
- `understand` 用 `deepseek-chat`（结构化 JSON，避免推理前奏污染）
- `edit._postprocess` 只排序不合并（keep_ranges 已是 LLM 精准结果）

---

## V23 (2026-08-03) — 定版

### 新增
- **口播→HTML一步到位**：`_llm_card_html_direct` — LLM 读原文+结构化数据直接生成，替代 enrich→HTML 两步
- **CARD_DIRECT_PROMPT**：9 模板字段（quote/metrix/headline/subtext/data_points_str/key_takeaway/beat_type/emotion/layout_hint）
- **4 策略自动分流**：数据/情绪/科普/步骤 → 不同的视觉元素
- **纯 JS 粒子悬浮层**：150 发光点 + 径向渐变 + 连接线 + 向上漂浮，z-index:5，零外部依赖

### 修复
- 清除了无效的 `_limit_elements` 方法和 `ELEMENT_SELECTORS` 类属性
- 去除了 THREE_TAG/PARTICLE_SCRIPT 死代码
- 清理了 21 个旧测试输出目录

---

## V22 (2026-08-03)

- 粒子可见度提升：size 0.08→0.12, opacity 0.6→0.85
- +console.log 加载确认

## V21 (2026-08-03)

- `function resize` 定义顺序修复（renderer→definition→call）

## V20 (2026-08-03)

- Three.js importmap → 传统 CDN `<script src>` 全局 THREE

## V19 (2026-08-03)

- **口播+结构化数据→HTML**：合并 V13 丰富提取 + V15 一步生成
- Three.js 粒子层（importmap + ES module，headless 中 CDN 不通）

## V18 (2026-08-03)

- `_limit_elements` regex → CSS `display:none`（未生效 → V23 清除）

## V17 (2026-08-03)

- `_limit_elements` inline style 注入（regex 不匹配复杂 HTML → V18 改进）

## V16 (2026-08-03)

- **CSS 隐藏**替代 regex 删除（`<style>` 注入，被 HyperFrames 忽略）

## V15 (2026-08-03)

- **口播→画面一步到位**（仅 quote+beat_type — 上下文太少 → V19 补充）

## V14 (2026-08-03)

- Prompt 加"每卡限 2 种元素"约束（LLM 不理 → 代码硬控）

## V13 (2026-08-03) ⭐

- **ELEM_DELAYS 注射生效**：8 种标准 ID 依次入场，+= 延迟 12-14 次/卡
- `_build_gsap_animation` Python 注入 querySelector 动画

## V12 (2026-08-03)

- 文件重命名为 test_output_llm12（覆盖 V11）

## V11 (2026-08-03) ⭐

- ELEM_DELAYS 首次注入（+= 延迟 → DeepSeek 不生延迟 → 代码注射）
- 13 种元素菜单：信号条/大数字/脉冲灯/badge/对比/步骤/引用/进度条/图标/勾选/冷知识/比例尺/定义卡

## V10 (2026-08-03) ⭐

- **代码级 has_data 分流**：`CARD_HTML_PROMPT_TEMPLATE` 根据 metric/data_points 是否存在动态分叉
- 评审突破 92 分（首次无剪辑问题）

## V9 (2026-08-03)

- **语义视觉策略 A/B/C**：纯概念句用隐喻（图标浮标/引用），但 enrich 强制提取数据导致分流无效

## V8 (2026-08-03)

- 10 元素菜单 + 口播设计原则（信号条/脉冲灯/步骤圆点/勾选列表）

## V7 (2026-08-03) ⭐

- **顺序入场节奏**：GSAP 时间轴改为固定延时叠加 `+=0.12`, `+=0.15`, `+=0.2`

## V6 (2026-08-03) ⭐

- **固定元素 ID**：强制 `#value`, `#bar-fill`, `.badge-item` 等标准 ID，禁止 LLM 自创

## V5 (2026-08-03)

- **7 元素菜单**：大数字/进度条/badge/A vs B/金句/倒计时/图标组 → 动画退化（去掉了 stagger）

## V4 (2026-08-03) ⭐

- **GSAP 微动画分层**：滑入+脉冲+stagger+进度条+大数字 5-7 tween

---

## 关键突破点 (⭐ = 架构级)

| 版本 | 突破 | 影响 |
|------|------|------|
| V4 | GSAP 微动画分层 | 卡片从静态→动效 |
| V6 | 固定元素 ID | 解决动画丢失 |
| V7 | 顺序入场 += 延迟 | 不挤，有节奏 |
| V10 | has_data 代码分流 | 不再对无数据句子塞假数字 |
| V11 | ELEM_DELAYS Python 注入 | 不靠 LLM，保证依次入场 |
| V13 | 注射生效 | 12-14 次 += 延迟/卡 |
| V15+V19 | 口播→HTML 一步 | 画面强相关口播内容 |
| V23 | 纯 JS 粒子 + 代码清理 | 零外部依赖，可维护 |

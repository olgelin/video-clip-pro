# Changelog — Video Clip Pro

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

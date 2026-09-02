# seek 驱动渲染的坑（HyperFrames）

> HyperFrames 是 **seek 驱动**（跳转到时间点截图，不是播放）。
> 这决定了哪些动画能渲染、哪些会"卡在初始值"。

## countUp 数字永远停在 0（最坑）

**症状**：数据卡片上的大数字全是"0万/0%/0分"，但口播字幕里有真实数字（"每天生成2000万张"）。

**根因**：GSAP countUp 靠 `onUpdate` 回调更新 `textContent`。seek 驱动下，框架跳转到时间点截图，**不触发 onUpdate**，数字停在初始值 0。

**为什么静态数字正常**：`-87%`、`3个月前`、`2022.11` 这些是 LLM 直接写死的静态文本，seek 时本来就显示，所以正常。

**修复**：数字直接写静态真实值 + 入场用 scale 弹入（scale 2.5→1 + 发光脉动）。**禁止 countUp**。

## 安全的动画（seek 正确插值）

- 位置/尺寸/透明度/scale：left/top/width/height/opacity/scale 是 CSS 属性，GSAP seek 会正确插值。
- 进度条 width 0%→目标：安全。
- SVG stroke-dasharray 绘制：安全。
- 柱状图 scaleY 0→1：安全。

## 不安全的动画（seek 不触发）

- 任何靠 `onUpdate` 回调的动画（countUp、文字逐字 typing、手动 DOM 更新）。
- `requestAnimationFrame` 循环（除非用 `hf-seek` 事件）。

## 铁律

- 🔴 数字 = 静态真实值 + scale 弹入，禁 countUp。
- 🔴 动画靠 CSS 属性（left/top/width/height/scale/opacity），不靠 onUpdate 回调。

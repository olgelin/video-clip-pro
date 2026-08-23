---
name: visual_check
description: 成片视觉质检 — 用 deepseek 视觉模型对渲染成片抽帧，检查画面质量（空白帧/字幕遮挡/元素错乱），产出 visual_check.json。借鉴 video-use 的"自评回路"：质检渲染成片，而非只查文本/中间件。
---

# visual_check

## 做什么

渲染成片后，抽 4 帧均匀分布的画面，用 `deepseek-v4-flash-vision-exp` 视觉模型检查每帧是否正常（空白/黑屏、字幕遮挡、元素错乱、乱码文字）。

## 输入

- `context["final_polished"]` 或 `output_dir/final_polished.mp4`（成片）

## 输出

- `visual_check.json`：{verdict, frames_checked, ok_count, issues, per_frame}

## 定位

- 非 critical、非 blocking —— 质检结果仅供参考，不阻断生产
- 借鉴 video-use 的 Hard Rule："verify your own output before showing it"，对**成片**而非源片/中间件质检

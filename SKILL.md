---
name: video-clip-pro
description: 口播视频智能剪辑管线 — 6阶段语义驱动的自动剪辑。先理解再动手，不是修修补补。
version: "23"
status: production
---

## 管线流程

```
transcribe → understand → draft → edit → hf_build → review → upscale
```

## V23 卡片特性

- 口播→HTML 一步到位（enrich 提取 + 原文 → LLM 直出）
- 4 策略自动分流：数据/情绪/科普/步骤
- ELEM_DELAYS 依次入场注射
- 纯 JS 粒子悬浮层（150发光点 z-index:5）

## 回滚

```bash
cp core/hf_card_builder.py.bak_v1 core/hf_card_builder.py
cp skills/hf_build/impl.py.bak_v1 skills/hf_build/impl.py
```

## 运行

```bash
python pipeline.py <视频路径> --output <输出目录>
```

# CURRENT.md — video-clip-pro 当前状态

> 本文件是 video-clip-pro 的事实源入口。新线程先读本文件，再读 README / docs。

## 定位

口播视频智能剪辑：输入一段口播视频，自动理解语义 → 剪掉废话/重复 → 生成卡片画面 + 字幕。

## 四种模式

| 模式 | 用途 |
|------|------|
| `card` | 全屏卡片场景（storyboard 语义分镜 + 卡片浮空面板），主用 |
| `pip` | 人物画中画 + 卡片 |
| `avatar-seed` | 碎碎念 → 数字人 |
| `avatar-short` | 话题 → 数字人 |

## 当前版本

- 生产基线稳定。核心模块：`pipeline.py`（主入口）+ `segment_orchestrator.py`（≥10min 长视频分段剪辑）。
- 最近关键修复：card 布局改用 storyboard visual_type 映射（治"只有 VS/列表"单调）；compare 触发词收紧（治满屏 VS）；BGM 相对路径根因修复。

## 当前状态

- ✅ **活跃**。card / pip 两管道端到端通过，成品 yuv420p 可播放。
- 15 个投喂视频批量交付 + 30min 长视频分段剪辑均验证通过。

## 入口索引

| 文件 | 用途 |
|------|------|
| `README.md` | 项目概述 |
| `CHANGELOG.md` | 版本演进 |
| `docs/项目结构说明.md` | 结构说明 |
| `SKILL.md` | 剪辑流程（分层删减方案） |
| `pipeline.py` | 主入口（`--mode` / `--no-2x` / `--debug`） |
| `segment_orchestrator.py` | 长视频分段剪辑编排 |

## 已知遗留

- 无阻塞项。card 卡片偶发 LLM 写成 JS 字符串已加检测兜底。

## 下一步

- 视频深化：切片高光模式（给 vcp 加"挑高光"能力，AutoClip 式精彩度评分）。

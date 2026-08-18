# CURRENT.md — video-clip-pro 当前状态

> 本文件是 video-clip-pro 的事实源入口。新线程先读本文件，再读 README / docs。

## 定位

口播视频智能剪辑：输入一段口播视频，自动理解语义 → 剪掉废话/重复 → 生成卡片画面 + 字幕。两条管道：pip（人物画中画 + 卡片）/ fullscreen（全屏卡片场景）。

## 当前版本

- **V25**（2026-08-18）：yuv420p 强制 + fullscreen 两 bug 修复 + 输出极简（`--no-2x` / `--debug`）。
- **最近提交**：`e559750`（初始提交，已推 GitHub `olgelin/video-clip-pro`）

## 当前状态

- ✅ **活跃，pip + fullscreen 两管道端到端通过**，成品 yuv420p 可播放。

## 入口索引

| 文件 | 用途 |
|------|------|
| `README.md` | 项目概述 |
| `CHANGELOG.md` | 版本演进（V25 是最新） |
| `docs/项目结构说明.md` | 结构说明 |
| `SKILL.md` | 剪辑流程（分层删减方案） |
| `pipeline.py` | 主入口（含 `--no-2x` / `--debug`） |

## 已知遗留

- 无阻塞项。fullscreen 卡片偶发 LLM 写成 JS 字符串已加检测兜底。

## 下一步

- 待定（当前稳定）。

# Video Clip Pro

口播视频智能剪辑管线 — AI 驱动，从原始讲话视频到成品剪辑全自动。

## 两个管道

| 管道 | 命令 | 场景 | 用途 |
|------|------|------|------|
| **PIP**（推荐） | `--mode pip` | 全屏 HTML 场景 + 人物窗口 + 字幕 | 口播视频主力，Three.js 粒子 3D 场景 |
| **V23** | `--mode fullscreen`（默认） | 卡片式画面 + 字幕 | 旧版卡片模式，保留兼容 |

两个管道共用同一套 `transcribe → understand → edit → storyboard` 剪辑内核，区别只在最后的画面生成阶段（`hf_build_pip` vs `hf_build`）。

## 快速开始

```bash
# PIP 管道（全屏 3D 场景 + 人物窗口）
python pipeline.py "输入视频.mp4" --mode pip

# V23 管道（卡片模式）
python pipeline.py "输入视频.mp4" --mode fullscreen

# 常用参数
python pipeline.py "输入.mp4" --mode pip --whisper-model large-v3 --bgm
```

## 统一输出路径

所有输出统一在 **`output/<mode>/<视频名>/`**：

```
output/
├── pip/              # PIP 管道输出
│   ├── 029/
│   │   ├── final.mp4              # 剪辑后的原视频（去口误/重复）
│   │   ├── final_polished.mp4     # 成品（场景+字幕+人物窗口）
│   │   ├── final_polished_2x.mp4  # 2x 超分版
│   │   ├── transcript.json        # 转写结果（时间戳）
│   │   ├── pipeline_context.json  # 完整上下文（调试用）
│   │   └── hyperframes/           # HyperFrames 中间产物
│   └── ...
└── v23/              # V23 管道输出
    └── ...
```

用 `--output <自定义目录>` 可覆盖默认路径。

## 架构（模块化）

```
输入视频
  → transcribe      [whisper large-v3 逐字转写 + 时间戳]
  → understand      [LLM 按字/按句意删减（初编）+ verify 复查]
  → draft           [keep_ranges 直接映射 EDL]
  → edit            [ffmpeg 按精确区间剪切 → final.mp4]
  → re_transcribe   [剪辑后重新转写，字幕音画同步]
  → storyboard      [语义分镜，场景数由内容决定]
  → hf_build_pip    [LLM 生成 3D 场景 HTML + 渲染]
  → review          [质量检查]
  → upscale         [2x 超分]
```

### 目录结构

| 路径 | 作用 |
|------|------|
| `pipeline.py` | **唯一入口** |
| `pipeline_defs/*.yaml` | 管道定义（pip / v23） |
| `core/` | 核心模块（provider / loader / gpu / hf_card_builder / card_constants） |
| `skills/<name>/impl.py` | 各阶段实现 |
| `skills/<name>/prompts/*.md` | 各阶段 LLM prompt（独立文件，不硬编码） |
| `skills/hf_build_pip/assets/` | Three.js / GSAP 本地内联 |
| `output/<mode>/<视频名>/` | 统一输出 |
| `docs/` | 说明文档 |
| `CHANGELOG.md` | 版本记录 |

## 关键设计

- **剪辑精确到字**：两步 LLM 删减（初编 + verify 复查），删口误/重复/口头禅，保留有信息量内容
- **字幕音画同步**：剪辑后重新转写，字幕基于新视频时间戳
- **画面稳定性三大兜底**：Three.js 缺失自动注入粒子 / 省略号 style 强制重生成 / 删减过度 fallback
- **场景数不锁死**：由内容语义自然决定
- **横竖屏自适应**：竖屏 1080×1920 / 横屏 1920×1080
- **窗口形状随机**：圆形 / 钝角方，避免单调、不裁人物

## 依赖

- Python 3.12、ffmpeg、npx hyperframes（Puppeteer + Chromium）
- 本地模型：whisper large-v3（已缓存）
- LLM API：deepseek-chat（结构化 JSON）/ deepseek-v4-pro（开放式 HTML）

## 回滚

改动前备份（`.bak`）+ git 历史，`git log` 查看版本。

# avatar-short 能力模块化地图

> 让 pip/fullscreen 能复制 avatar-short 的能力。每次要"复制某个能力到别的管道"，先查这里。

## 能力清单 + 归属

| 能力 | 实现位置 | 共享范围 | 说明 |
|---|---|---|---|
| 词级字幕（对齐配音） | `skills/transcribe/impl.py` | 全管道共享 | 读 voice_path（配音）或 video_path（视频），faster-whisper 词级转录 |
| visual_type LLM 语义判断 | `skills/storyboard/impl.py` `_semantic_split` | 全管道共享 | LLM 输出 [start,end,type]，关键词匹配兜底 |
| 数字人布局坐标 | `skills/hf_build_avatar/person_zone.py` | avatar 专属 | person_zone/content_zone/person_layout_for_visual_type 单一来源 |
| 数字人换位动画 | `core/hf_card_builder.py` avatar 分支 | core 内 is_avatar 隔离 | GSAP tl.to 位置动画 |
| 画面景别（full/inset） | `skills/storyboard/impl.py` `_shot_scale` | 共享 | 开场 full，严格交替 |
| BGM | `skills/bgm_mix/impl.py` | avatar_short + v23 | ACE-Step + ducking，avatar 默认开 |
| Three.js 技法菜单 | `skills/hf_build_avatar/impl.py` `_threejs_menu` | avatar 专属 | 6 技法（粒子/星空/银河/代码雨/网格/Bloom） |
| 数字人编排（左右/出镜） | `skills/storyboard/impl.py` `_direct_person_layouts` | storyboard 内 | LLM 判 L/R/H，景别决定大小 |

## 共享 core 的隔离铁律

- `core/hf_card_builder.py` 被 v23/pip/avatar 三管道共用。
- avatar 的所有改动**必须包在 `is_avatar`（layout_mode=="avatar"）判断里**，绝不污染 pip/fullscreen。
- storyboard 的字段（shot_scale/person_layout）pip 不读，无害。

## 复制能力的标准路径

以"把词级字幕复制到 pip"为例：
1. pip.yaml 加 `transcribe` stage（pip 已有，读 video_path 转录视频）
2. 字幕由 `hf_card_builder._build_captions` 统一生成，words 进 context 即可
3. 无需改 core —— 字幕逻辑是共享的

以"把 visual_type LLM 判断复制到 fullscreen"为例：
- 已经生效（storyboard 共享，改 _semantic_split 后 fullscreen 也走 LLM 判断）。

## 新增能力的低耦合原则（用户红线）

- 新功能加层不改已有代码（独立 skill，YAML 是唯一耦合点）。
- 上游字段升级必须查下游消费者（`search_files` 搜 `get("字段名")`）。
- 改共享 core 前先审计所有管道（读 pipeline_defs/*.yaml）。

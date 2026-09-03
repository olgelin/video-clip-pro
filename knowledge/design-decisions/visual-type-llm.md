# 设计决策：visual_type 改 LLM 语义判断（对齐 video-factory）

> 来源：2026-09-03 画面质量打磨。用户反馈"AI老师视频 HTML 画面质量太垃圾，没对齐老管道优秀做法"。

## 背景

video-factory 的画面质量好，核心是 **storyboard 用 LLM 语义分镜**（读全文语义，判断每个场景该用什么视觉类型）。而 video-clip-pro 的 avatar-short 之前用 **Python 关键词匹配**（`_detect_type`），机械、不贴内容。

## 根因：flow 垄断

`_detect_type` 的关键词太宽（data_impact 含"数字/效率/数据"），AI 话题每段口播都有数字 → 全判 data_impact → 避免重复逻辑（`alternatives[data_impact]=flow`）把多余的换成 flow → flow 垄断 4/6。

燃油车/直播带货看起来正常，是因为话题关键词分布恰好均衡，不是机制好。

## 方案

把 visual_type 判定交给 LLM（在已有的 `_semantic_split` 语义切分里一起输出），关键词匹配做确定性兜底：

1. `_semantic_split` prompt 加 7 种视觉类型的语义说明，输出格式 `{"scenes": [[start, end, "type"], ...]}`
2. `_semantic_split_merge` 提取 `llm_type`（修复 `group[-1]` 误当 type 的 bug，改成 `group[1]`）
3. `_build` 用 `llm_type` 优先（`VALID_TYPES` 校验），失败 fallback `_detect_type`

## 关键约束（用户红线）

- **LLM 编排，不代码锁死**：visual_type 是 LLM 读语义判断的，关键词匹配只是兜底（防 LLM 失败）。
- **确定性兜底**：LLM 失败/输出非法类型 → 回退关键词匹配，保证 pipeline 不崩。

## 验证

- 单元测试：`_parse_split` 解析三元素、`_semantic_split_merge` 提取 llm_type、`_build` 用 LLM type 优先。
- 端到端：多话题交叉验证（AI老师 + 新话题），确认场景类型多样（不再 flow 垄断）。

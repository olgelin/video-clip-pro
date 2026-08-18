# draft

**Phase 3** — 基于故事地图做机械映射，产出精确 EDL。

输入：`story_map` + 转录时间戳  
输出：`edl` — 时间段列表，不重新做语义判断

Prompt: `prompts/draft.md`  
Fallback: `_direct_map()` — 跳过 LLM，直接映射（CUT 过滤 + KEEP-TRIM 用 trimmed）

# video-clip-pro 知识库

> 借鉴 video-factory 的"先写知识再动手"铁律。改任何 skill 前，先读这里的对应文件。

## 目录

| 目录 | 内容 |
|---|---|
| `constraints/` | 硬约束（违反就出 Bug）|
| `bug-patterns/` | 缺陷→根因→修复链 |
| `tool-configs/` | 工具配置 + 已知坑 |
| `design-decisions/` | 重要设计决策及理由 |

## 索引

- **改画面/数字人前必读** → `constraints/avatar-iron-laws.md`（布局契约、数据铁律、景别、禁模板、动画铁律）
- **画面数字变 0 / 动画卡住** → `bug-patterns/seek-rendering-traps.md`（countUp 停 0、onUpdate 不触发）
- **Duix 卡死 / DeepSeek 失败** → `tool-configs/duix-and-deepseek.md`
- **数字人摆位 / 景别为什么这样设计** → `design-decisions/person-orchestration.md`

## 铁律

1. 修 Bug 前先读 `bug-patterns/`——这个坑之前踩过没？
2. 修完立刻写知识文件——症状→根因→修复→预防。
3. 每次新 session 先读 `constraints/` 刷新约束。
4. 改动前先问：影响哪些管道？哪些下游 skill？

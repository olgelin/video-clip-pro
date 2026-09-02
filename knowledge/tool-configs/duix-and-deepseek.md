# 工具坑：Duix 卡死 + DeepSeek reasoning token

## Duix 数字人对口型（127.0.0.1:8383）

### 三种卡死形态 + 判断

| 症状 | 含义 | 恢复 |
|---|---|---|
| `Read timed out` 循环 | 服务活着，推理 worker 卡死 | restart 容器 |
| `WinError 10061 拒绝连接` | 容器挂了 | restart 容器 |
| `failed to connect to docker API at npipe://...` | Docker Desktop 引擎整体挂 | 启动 Docker Desktop |

### 恢复步骤

```bash
docker restart duix-avatar-gen-video
# 若 Docker 引擎挂：
#   PowerShell 启动 "C:\Program Files\Docker\Docker\Docker Desktop.exe" + sleep 90
curl http://127.0.0.1:8383/docs   # 返回 404 = 存活
```

### 已做的自愈（skills/duix/impl.py）

- 连续查询异常 ≥6 次（30s）→ 判定卡死 → 自动 `docker restart` → 重新提交（最多 2 次）。
- 之前空转 30 分钟才放弃，现在 30 秒就重启重试。

### 未根治

- 横屏长配音合成时，Duix 推理偶发卡死（`result info []` 持续空）。根因在 Duix 引擎内部，自愈只能兜底。
- **配音时长规律（2026-09-03 观察）**：配音越长越容易卡。已观察：90s 卡过、104.4s 卡过；短配音（<80s）较少卡。横屏场景方向 + 长配音 = 超负荷。
- **三种卡死形态 + 自愈**（2026-09-03 增强）：
  1. 容器级卡死 → `docker restart`（120s 超时）
  2. 引擎挂（docker ps 返回 500）→ 自动启动 Docker Desktop → 等引擎恢复 → 再 restart
  3. Docker Desktop 进程在跑但引擎 API 无响应 → 冷启动慢，最长等 15 分钟

### 根治方向（待做，不是现在）

1. 限制配音时长（<90s，超长话题切两段）
2. Duix 分段合成（长配音切成多段合成再拼接）
3. 合成前更严格地监控 GPU 显存（当前 8000MB 阈值可能不够，合成峰值会飙）

## DeepSeek reasoning 模型 token 坑

### 症状

`LLM 生成失败`，无任何报错，content 字段空。

### 根因

`deepseek-v4-pro` 是 reasoning 模型，思考占 2000-3100 token。`max_tokens=4000` 时思考占满，content 被挤空 → 静默 return None。

### 修复

- TASK_MODELS（core/provider.py）+ skill 显式传参**都要改 8000**。
- 只改一处会被 skill 的显式 `max_tokens=4000` 覆盖（实踩的坑）。
- 实例：`script_writer/impl.py` + `speech_processor/impl.py` 显式传 4000 覆盖了 TASK_MODELS 的 8000。

### 铁律

- 找 `max_tokens=4000` 要全局搜，TASK_MODELS 和 skill impl 都要查。

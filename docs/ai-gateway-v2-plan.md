# 永嘉集团弱电运维平台 V2 - 通用 AI 网关系统

## 当前定位

这套 AI 网关已经按“协调者 + 执行者 + 可扩展注册制”落进 `platform_v2` 后端，不再依赖固定单一模型，也不再把智能体和 LLM 写死在代码里。

当前实现位置：

- 后端核心：`backend/app/ai_gateway/`
- API 接口：`backend/app/api/ai.py`
- 运行配置：`runtime/ai_gateway/ai_gateway.yaml`
- 运行日志：`runtime/logs/ai_gateway.log`
- 会话与记忆：`runtime/ai_gateway/sessions/`、`runtime/ai_gateway/memory/`

## 已完成能力

### P0 已落地

- `BaseLLMAdapter` 通用接口
  - `chat(messages, options)`
  - `embeddings(text)`
  - `models()`
- LLM 适配器池
  - OpenAI
  - Anthropic
  - GLM
  - MiniMax
  - DeepSeek
  - Local
  - Custom REST
- 智能体注册表
  - `openclaw` 固定为唯一协调者
  - `codex` 作为默认执行者
  - 其他智能体可按 YAML 注册
- 任务调度核心
  - OpenClaw 决策
  - 路由到执行者
  - 结果汇总
  - 会话和记忆落盘
- YAML 配置化
  - 配置文件首次启动自动生成
  - 注册接口会写回 YAML
- 日志与错误处理
  - AI 网关独立日志

### P1 预先顺带落地

- `POST /api/ai/alerts/analyze`
- `POST /api/ai/reports/generate`
- `POST /api/ai/device/query`

这些接口当前已经能跑通，默认在没有外部 LLM 可用时，走本地协调/执行回退逻辑。

## API 清单

### 核心接口

- `GET /api/ai/summary`
- `POST /api/ai/gateway`
- `GET /api/ai/agents/register`
- `POST /api/ai/agents/register`
- `GET /api/ai/llm/register`
- `POST /api/ai/llm/register`
- `POST /api/ai/session`

### 业务接口

- `POST /api/ai/alerts/analyze`
- `POST /api/ai/reports/generate`
- `POST /api/ai/device/query`

## 当前配置原则

- 所有智能体、LLM、协议、技能配置都在 `runtime/ai_gateway/ai_gateway.yaml`
- 运行期注册会回写 YAML
- OpenClaw 永远参与调度，不允许其他协调者替代

## 下一步建议

### P1 下一轮

- 为 `codex`、`claude_code` 这类执行者/推理者补更细的角色策略
- 把 Feishu 通知能力接进 OpenClaw 协调者
- 为报告生成补正式模板

### P2

- 真正打通 MCP 协议
- 真正打通 A2A 协议
- 给外部智能体注册补心跳和状态探测

### P3

- RAG / NAS 型知识库接入
- 多模型路由策略
- 记忆分层和长期知识沉淀

## 注意

当前这版是“可运行的通用网关骨架”，已经可以接接口、注册智能体和注册 LLM，但还没有把外部平台级智能体通信全部打通。后续扩展时，优先沿现有 `BaseLLMAdapter` 和 `BaseAgent` 继续扩，不要再回到固定硬编码方案。

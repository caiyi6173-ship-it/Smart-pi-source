# SmartPI Agent Orchestrator

SmartPI Agent Orchestrator 是 SmartPI 的 7 个 Agent 工作流编排服务。

第一版目标是先搭建最小可运行骨架，不直接改动现有语音助手、RAG 服务或树莓派环境。

## 7 个 Agent

```text
SupervisorAgent          总调度
SafetyTriageAgent        医疗安全分诊
IntentRouterAgent        意图路由
RagAgent                 中医知识库检索
TongueDiagnosisAgent     舌诊解释
DeviceControlAgent       设备控制
CitationAnswerAgent      引用校验与最终回答
```

## 本地启动

先启动 `rag-chroma`：

```bash
cd ../rag-chroma
uvicorn app.main:app --host 127.0.0.1 --port 8094
```

再启动 Agent Orchestrator：

```bash
cd agent-orchestrator
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8096 --reload
```

也可以用本地启动脚本：

```powershell
cd D:\RAG\Smart-pi-source\agent-orchestrator
.\run_local_agent.ps1 -Reload
```

脚本默认设置 `DEVICE_DRY_RUN=true`，并检查 `RAG_BASE_URL/health`。如果只想启动 Agent、不检查 RAG：

```powershell
.\run_local_agent.ps1 -SkipRagHealthCheck
```

如果 `rag-chroma` 运行在其他端口，请在 `.env` 中设置：

```env
RAG_BASE_URL=http://127.0.0.1:8094
```

## 接口

健康检查：

```bash
curl http://127.0.0.1:8096/health
```

智能体对话：

```bash
curl -X POST http://127.0.0.1:8096/api/v1/agent/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"舌苔黄腻说明什么？\",\"options\":{\"include_trace\":true}}"
```

带舌象识别标签的调用：

```bash
curl -X POST http://127.0.0.1:8096/api/v1/agent/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"帮我解释这次舌象\",\"tongue_labels\":[\"yellowcoates\",\"chihenshe\"],\"tongue_confidences\":{\"yellowcoates\":0.86,\"chihenshe\":0.74},\"options\":{\"include_trace\":true}}"
```

`tongue_labels` 使用 YOLO/边缘识别输出的 canonical label，例如 `yellowcoates`、`chihenshe`。服务会读取 `../config/class_map.json`，转换为中文舌象名，再生成更适合 RAG 检索的舌诊问题。

设备控制 dry-run：

```bash
curl -X POST http://127.0.0.1:8096/api/v1/agent/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"打开摄像头识别\",\"options\":{\"include_trace\":true}}"
```

默认 `DEVICE_DRY_RUN=true`，只返回将要执行的 `SMARTPI_ACTION`、HTTP method/path 和确认状态，不会触发真实硬件。后续确认要执行真实动作时，再把 `.env` 中的 `DEVICE_DRY_RUN=false`，并在 `user_context.confirm_device_action=true` 时调用 edge bridge。

## 当前状态

当前是第一步骨架版本：

- 已有 FastAPI 服务
- 已有结构化 Pydantic schema
- 已有 7 个 Agent 类
- 已有安全分诊规则
- 已有意图路由规则
- RAG Agent 已接入 `rag-chroma` 的 `/api/v1/query`
- 舌诊 Agent 已支持 YOLO 舌象标签解析和 RAG 查询问题生成
- DeviceControlAgent 已支持 OpenClaw 动作映射和 edge bridge dry-run 计划

启动前请先确保本地 `rag-chroma` 服务运行在 `RAG_BASE_URL` 指向的地址，默认是 `http://127.0.0.1:8095`。

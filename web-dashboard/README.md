# smartpi Web Dashboard

电脑端 smartpi Web 控制台，第一版用于本地开发和联调现有 SmartPI 服务。

## 功能

- MJPEG 实时视频流展示
- RAG 中医知识库问答
- Agent Orchestrator 文本交互
- 语音助手文本命令入口
- 传感器数据展示
- Edge Bridge 设备控制入口
- 服务健康检查和事件日志
- Mock API 演示模式，后端服务离线时也能展示完整界面

## 技术栈

```text
Vue 3
Vue Router
Pinia
Vite
TypeScript
Fetch API
Vite dev server proxy
Mock API fallback
```

## 页面结构

当前已经拆成正式路由结构：

```text
/dashboard   总览控制台
/vision      视频流、传感器、视觉相关控制
/rag         RAG 知识库问答
/agent       Agent 编排交互
/devices     设备控制、语音助手、事件日志
/settings    连接目标和服务状态
```

共享状态由 `src/stores/system.ts` 管理，包括：

```text
服务健康
传感器数据
语音助手状态
Edge Bridge 状态
连接目标
事件日志
```

## 本地启动

```powershell
cd D:\RAG\Smart-pi-source\web-dashboard
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

## 默认连接服务

第一版默认连接电脑本地服务：

```text
RAG API              http://127.0.0.1:8095
Agent Orchestrator   http://127.0.0.1:8096
Voice Agent          http://127.0.0.1:8093
Edge Bridge          http://127.0.0.1:8092
Sensor Hub           http://127.0.0.1:8091
MJPEG Stream         http://127.0.0.1:8081
Web Backend          http://127.0.0.1:18080
```

如果要连接树莓派，复制 `.env.example` 为 `.env`，改成树莓派地址：

```env
VITE_RAG_TARGET=http://192.168.65.194:8095
VITE_AGENT_TARGET=http://192.168.65.194:8096
VITE_VOICE_TARGET=http://192.168.65.194:8093
VITE_EDGE_TARGET=http://192.168.65.194:8092
VITE_SENSOR_TARGET=http://192.168.65.194:8091
VITE_STREAM_TARGET=http://192.168.65.194:8081
VITE_BACKEND_TARGET=http://127.0.0.1:18080
```

修改 `.env` 后需要重启 `npm run dev`。

## Mock API 模式

电脑没开树莓派或本地后端服务时，Web 仍然可以演示完整界面。

`.env` 中可以配置：

```env
VITE_MOCK_API=auto
```

可选值：

```text
auto  默认。优先请求真实服务，失败后自动使用 mock 数据。
on    强制使用 mock 数据，适合演示。
off   强制使用真实服务，适合联调。
```

Mock 覆盖范围：

```text
RAG health / query
Agent health / chat
Voice health / command
Edge status / device control
Sensor telemetry
MJPEG 视频流失败占位
```

Mock 数据只用于前端演示，不会写入 RAG 知识库，也不会执行真实硬件动作。

## 接口代理

前端代码只访问同源路径：

```text
/api/rag
/api/agent
/api/voice
/api/edge
/api/sensor
/api/backend
/stream/mjpeg
/stream/snapshot
```

真实目标由 `vite.config.ts` 转发，避免第一版就修改后端 CORS。

## SQLite 写入

如果 `web-backend` 在 `18080` 运行，前端会自动写入 SQLite：

```text
RAG 问答结果       -> /api/v1/rag/messages
Agent 运行结果     -> /api/v1/agent/runs
设备控制按钮       -> /api/v1/device-actions
语音文本命令       -> /api/v1/audit-logs
服务健康快照       -> /api/v1/service-snapshots
```

写入失败不会阻断页面主交互。设置页 `/settings` 会显示最近审计记录，用来确认 SQLite 是否在接收数据。

启动 web-backend：

```powershell
cd D:\RAG\Smart-pi-source\web-backend
uvicorn app.main:app --host 127.0.0.1 --port 18080
```

## 构建检查

```powershell
npm run build
```

构建产物在：

```text
web-dashboard/dist
```

`dist/` 不进入 Git。

## 当前边界

- 第一版是电脑端开发控制台，不是树莓派常驻前端服务。
- 第一版继续使用 MJPEG，不切换 WebRTC。
- 第一版不做浏览器录音。
- 第一版设备控制按钮带确认弹窗，但是否真实执行取决于后端 Edge Bridge。
- 如果本地没有启动对应服务，页面会显示离线或请求失败。

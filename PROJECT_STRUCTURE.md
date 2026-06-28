# 项目结构说明

本文档从正式项目视角说明 `smartpi` 仓库的目录结构、模块职责和模块之间的关系，帮助你快速理解整套系统是如何组织的。

## 顶层布局

```text
Smart-pi-source/
  config/
  edge/
  openclaw/
  openclaw-runtime/
  openclaw-workspace/
  rag-chroma/
  yolo_clean/
  yolo-prj/
```

## 结构总览

- `config/`
  运行配置模板与静态映射文件

- `edge/`
  树莓派设备侧主控层，负责语音、传感器、边缘桥和摄像头检测流

- `openclaw/`
  OpenClaw 集成入口、skill 文档与本地调用脚本

- `openclaw-runtime/`
  运行态 skill 快照，用于对照项目定义与设备实际安装内容

- `openclaw-workspace/`
  OpenClaw 工作区公开文档

- `rag-chroma/`
  中医知识库 RAG 服务

- `yolo_clean/`
  视觉推理相关代码与兼容脚本

- `yolo-prj/`
  小型实验性视觉代码目录

## 目录详解

### `config/`

这是项目的运行配置目录，主要用于存放各服务的环境变量模板和静态映射文件。

当前主要内容：

- `voice_agent.env.example`
- `edge_bridge.env.example`
- `sensor_hub.env.example`
- `mjpeg_stream.env.example`
- `class_map.json`

其中：

- `voice_agent.env.example` 用于语音助手链路
- `edge_bridge.env.example` 用于边缘桥服务
- `sensor_hub.env.example` 用于传感器中枢
- `mjpeg_stream.env.example` 用于摄像头检测流
- `class_map.json` 用于视觉推理标签映射

这个目录是部署时最先需要关注的配置入口之一。

### `edge/`

这是 `smartpi` 的设备侧主控层，也是整套系统最核心的目录。

主要职责：

- 语音交互
- 设备动作控制
- 摄像头检测流
- 传感器采集
- systemd 服务化部署

关键文件包括：

- `smartpi_voice_agent.py`
- `smartpi_edge_bridge.py`
- `smartpi_sensor_hub.py`
- `pi_mjpeg_stream_server.py`
- `pi_usb_cam_edge_client.py`

关键脚本包括：

- `pi_run_voice_agent.sh`
- `pi_run_edge_bridge.sh`
- `pi_run_sensor_hub.sh`
- `pi_run_mjpeg_stream.sh`
- `pi_install_local_voice_stack.sh`
- `pi_install_openclaw.sh`
- `pi_install_smartpi_openclaw_skill.sh`

关键 service 文件包括：

- `smartpi-voice-agent.service`
- `smartpi-edge-bridge.service`
- `smartpi-sensor-hub.service`
- `smartpi-edge-stream.service`

如果把整个项目看作一套运行中的设备系统，那么 `edge/` 就是设备主链路的控制中心。

### `openclaw/`

这个目录包含项目侧的 OpenClaw 集成资产。

主要内容：

- `run_openclaw_message.sh`
- `smartpi-edge-control.md`
- `skills/smartpi-edge-control/SKILL.md`

它的作用是把 `smartpi` 的本地设备能力以 skill 的方式暴露给 OpenClaw，使智能体能够根据自然语言上下文触发设备动作。

### `openclaw-runtime/`

这个目录保存从运行环境中回收的 OpenClaw 已安装 skill 内容。

当前关键内容：

- `skills/smartpi-edge-control/SKILL.md`

它的意义不在于直接运行，而在于帮助开发者核对：

- 项目仓库中的 skill 定义
- 树莓派运行态实际安装的 skill 内容

是否一致。

### `openclaw-workspace/`

这个目录保存 OpenClaw 工作区公开文档，用来理解工作区约定和智能体上下文结构。

当前保留内容：

- `AGENTS.md`
- `BOOTSTRAP.md`
- `HEARTBEAT.md`
- `IDENTITY.md`
- `SOUL.md`
- `TOOLS.md`
- `USER.md`

这个目录更偏“理解智能体工作方式”，而不是直接承载设备业务逻辑。

### `rag-chroma/`

这是当前主用的中医知识库 RAG 服务目录。

它负责：

- 文档导入
- 文本切分
- 检索路由
- 混合召回
- reranker 重排
- 引用组织
- 问答 API 输出

典型子目录：

- `app/`
- `deploy/`
- `docs/`
- `scripts/`
- `tests/`

其中：

- `app/` 是 FastAPI 应用和检索逻辑主体
- `deploy/` 是树莓派部署脚本与 service 文件
- `docs/` 是 RAG 相关说明文档
- `scripts/` 是导入、查询、重建索引等工具
- `tests/` 是测试文件

这是知识层能力的核心目录。

### `yolo_clean/`

这个目录用于保存视觉推理相关代码与兼容脚本。

当前包含：

- ONNX 推理辅助代码
- 设备侧兼容脚本
- 部分旧 YOLO 实验代码

它在项目中承担“视觉模型与设备侧推理衔接”的角色，但内部仍然包含一定历史代码成分。

### `agent-orchestrator/`

7 Agent ?????????????????RAG ?????????????? dry-run ????????

???????????????????? Agent ????

### `web-dashboard/`

??? Web ??????Vue 3 + Vite + TypeScript?

????????RAG ???Agent?????????????????????? Mock API ?????

### `web-backend/`

Web ????????FastAPI + SQLite?

???????RAG ?????Agent ???????????????????????????scripts/manage_db.py??

### `yolo-prj/`

这个目录是较小的实验性视觉代码区域，适合作为轻量试验或临时验证使用。

它不是当前主链路的核心目录，但保留了部分实验上下文。

## 模块之间的关系

从运行链路看，各模块关系大致如下：

1. `edge/` 负责树莓派本地设备控制与语音主链路
2. `openclaw/` 负责把设备能力暴露给智能体
3. `rag-chroma/` 负责中医知识检索与回答生成
4. `config/` 负责为上述服务提供运行参数
5. `yolo_clean/` 为视觉识别链路提供模型推理相关代码

可以把它理解为：

- `edge/` 是设备执行层
- `openclaw/` 是智能体协同层
- `rag-chroma/` 是知识服务层
- `config/` 是配置支撑层
- `yolo_clean/` 是视觉模型支撑层

## 阅读顺序建议

如果你是第一次看这个仓库，推荐按下面顺序阅读：

1. [README.md](README.md)
2. `edge/`
3. `config/`
4. `rag-chroma/`
5. `openclaw/`
6. `DEPLOY_RASPBERRY_PI.md`
7. `web-dashboard/`
8. `web-backend/`

如果你主要关心某一部分，也可以按目标阅读：

- 想看设备主链路：先看 `edge/`
- 想看 RAG：先看 `rag-chroma/`
- 想看智能体集成：先看 `openclaw/`
- 想看树莓派部署：先看 `DEPLOY_RASPBERRY_PI.md`

## 当前结构特点

这个仓库的结构有几个明显特征：

- 以树莓派设备侧运行链路为中心
- 语音、视觉、知识检索不是分散脚本，而是协作模块
- 同时保留了运行主线代码和部分实验性视觉代码
- 已经具备 service 化部署基础
- 已经具备本地设备控制与知识服务分层

整体上，它更接近“真实运行中的边缘 AI 系统源码仓库”，而不是单文件演示项目。

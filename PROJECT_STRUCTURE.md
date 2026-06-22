# 项目结构说明

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

## 各目录职责

### `config/`

树莓派运行配置目录。

当前主要包含：

- `voice_agent.env`
- `voice_agent.env.example`
- `edge_bridge.env`
- `sensor_hub.env`
- `mjpeg_stream.env`
- `class_map.json`

GitHub 建议处理方式：

- 保留 `*.example`
- 真实 `*.env` 改为脱敏模板或忽略提交
- 像 `class_map.json` 这类静态映射文件可以保留

### `edge/`

这是 smartpi 设备侧最核心的边缘控制层。

关键文件包括：

- `smartpi_voice_agent.py`
- `smartpi_edge_bridge.py`
- `smartpi_sensor_hub.py`
- `pi_mjpeg_stream_server.py`
- `pi_usb_cam_edge_client.py`
- `pi_run_*.sh`
- `pi_install_*.sh`
- `*.service`

这一层承载了语音交互、设备动作控制、摄像头流服务和传感器采集，是整套系统的主控代码之一。

### `openclaw/`

项目侧 OpenClaw 集成资产目录。

关键内容包括：

- `run_openclaw_message.sh`
- `smartpi-edge-control.md`
- `skills/smartpi-edge-control/SKILL.md`

它用于说明 smartpi 如何调用 OpenClaw，以及项目侧技能如何组织。

### `openclaw-runtime/`

从树莓派运行环境中回收的 OpenClaw 已安装技能内容。

当前保留内容：

- `skills/smartpi-edge-control/SKILL.md`

它适合用来对照“项目中的技能定义”和“运行时实际安装的技能内容”是否一致。

### `openclaw-workspace/`

从树莓派 OpenClaw 工作区中回收的公开文档。

当前保留文件：

- `AGENTS.md`
- `BOOTSTRAP.md`
- `HEARTBEAT.md`
- `IDENTITY.md`
- `SOUL.md`
- `TOOLS.md`
- `USER.md`

恢复时明确排除了：

- `.git`
- workspace state
- 记忆数据库
- sessions

这部分适合帮助后续理解 OpenClaw 工作区的使用约定和智能体上下文组织方式。

### `rag-chroma/`

smartpi 当前主用的 RAG 服务目录。

典型子目录：

- `app/`
- `deploy/`
- `docs/`
- `scripts/`
- `tests/`

主要特点：

- Chroma 向量后端
- FastAPI 服务
- DashScope Embedding 与 LLM 接入
- 混合检索、重排、路由、导入流水线

如果后续 GitHub 只保留一个 RAG 模块，这个目录最适合作为主线版本。

### `yolo_clean/`

从树莓派回收并过滤后的 YOLO 相关源码目录。

当前内容是混合态，既包括：

- smartpi 相关兼容脚本
- ONNX 推理辅助代码
- 旧版 YOLO 实验代码

它已经比原始树莓派目录干净很多，但在正式公开前仍建议继续筛一轮。

### `yolo-prj/`

树莓派桌面上的一个小型 YOLO 试验目录。

这部分是可选内容，可以后续合并进 `yolo_clean/`，也可以单独归档。

## 有意不纳入仓库的内容

以下内容在这次回收中被明确排除，不作为源码仓库内容：

- 模型权重，例如 `.pt`、`.onnx`、`.torchscript`
- 本地虚拟环境
- 缓存目录
- 日志文件
- 采集图片、音频、视频
- 实际运行用的 `.env`
- OpenClaw 的记忆库、会话状态和设备状态

## 上传 GitHub 前建议继续做的整理

1. 保持顶层 `.gitignore`，避免误提交运行产物和敏感信息。
2. 把 `config/` 下真实配置替换成脱敏模板。
3. 确定是否还需要恢复并保留旧版 `rag/`。
4. 给 `yolo_clean/` 一个最终命名，并移除和主线无关的遗留实验代码。
5. 增加一份部署文档，说明：
   - 需要哪些模型
   - 需要哪些环境变量
   - 树莓派服务启动顺序
   - 硬件依赖关系

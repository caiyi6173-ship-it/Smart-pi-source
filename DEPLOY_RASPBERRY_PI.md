# 树莓派部署指南

本文档面向 `smartpi` 的树莓派部署，目标是把仓库中的主链路服务在 Raspberry Pi 上跑起来，包括：

- 摄像头检测流
- 传感器中枢
- 边缘桥
- 语音助手
- 可选 OpenClaw 集成
- 可选 RAG 服务

默认部署目录：

```bash
/home/pi/smartpi
```

## 1. 部署目标结构

部署完成后，建议目录结构如下：

```text
/home/pi/smartpi/
  config/
  edge/
  openclaw/
  rag-chroma/
  models/
  cache/
  data/
  venv/
```

## 2. 前置条件

建议环境：

- Raspberry Pi 5
- Raspberry Pi OS 64-bit
- Python 3
- `git`
- `ffmpeg`
- 可联网环境

可选硬件：

- USB 摄像头
- 麦克风
- 扬声器 / I2S 功放
- 体征传感器模块

## 3. 获取代码

```bash
cd /home/pi
git clone https://github.com/caiyi6173-ship-it/Smart-pi-source.git smartpi
cd /home/pi/smartpi
```

如果已经存在旧目录，建议先确认里面是否有运行中数据、模型和配置，再决定覆盖还是迁移。

## 4. 创建 Python 环境

主链路运行环境：

```bash
cd /home/pi/smartpi
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
```

如果后续要运行 `rag-chroma`，它会使用独立的 `.venv`。

## 5. 准备配置文件

复制模板：

```bash
cp config/voice_agent.env.example config/voice_agent.env
cp config/edge_bridge.env.example config/edge_bridge.env
cp config/sensor_hub.env.example config/sensor_hub.env
cp config/mjpeg_stream.env.example config/mjpeg_stream.env
```

最低建议检查这些配置项：

### `config/voice_agent.env`

- `DASHSCOPE_API_KEY`
- `WAKE_WORD`
- `ASSISTANT_NAME`
- `ENABLE_LOCAL_STT`
- `ENABLE_LOCAL_TTS`
- `ENABLE_OPENCLAW`
- `OPENCLAW_COMMAND`
- `PIPER_MODEL_PATH`
- `PIPER_CONFIG_PATH`
- `SHERPA_KWS_MODEL_DIR`

### `config/edge_bridge.env`

- `BACKEND_BASE_URL`
- `STREAM_BASE_URL`
- `SENSOR_BASE_URL`
- `VOICE_BASE_URL`
- `DEVICE_ID`
- `USER_ID`

### `config/sensor_hub.env`

- `DEVICE_ID`
- `BACKEND_URL`
- `SAMPLE_INTERVAL`
- `UPLOAD_INTERVAL`
- `MOCK_SENSORS`

### `config/mjpeg_stream.env`

- `PROFILE`

## 6. 准备模型与缓存目录

建议预建目录：

```bash
mkdir -p /home/pi/smartpi/models
mkdir -p /home/pi/smartpi/cache
mkdir -p /home/pi/smartpi/data/results
```

常见模型目录：

```text
/home/pi/smartpi/models/tongue_best.onnx
/home/pi/smartpi/models/piper/
/home/pi/smartpi/models/kws/
```

## 7. 安装本地语音链路

运行：

```bash
bash edge/pi_install_local_voice_stack.sh
```

它会尝试完成这些事情：

- 安装 `ffmpeg`
- 安装 `faster-whisper`
- 安装 `piper-tts`
- 安装 `sherpa-onnx`
- 下载 Piper 语音模型
- 下载 Whisper 模型
- 下载 KWS 模型

执行完成后，请把脚本输出中建议的参数同步回 `config/voice_agent.env`。

## 8. 安装 OpenClaw

如果你要启用智能体协同，再执行：

```bash
bash edge/pi_install_openclaw.sh
bash edge/pi_install_smartpi_openclaw_skill.sh
```

之后按提示完成：

1. `openclaw onboard --install-daemon`
2. Gateway 初始化
3. skill 安装验证

如需调整模型配置，可继续执行：

```bash
bash edge/pi_configure_openclaw_model.sh
```

## 9. 启动主链路服务

### 手动启动

传感器：

```bash
bash edge/pi_run_sensor_hub.sh
```

摄像头检测流：

```bash
bash edge/pi_run_mjpeg_stream.sh
```

边缘桥：

```bash
bash edge/pi_run_edge_bridge.sh
```

语音助手：

```bash
bash edge/pi_run_voice_agent.sh
```

### service 方式

仓库中已经提供这些 systemd 文件：

- `edge/smartpi-sensor-hub.service`
- `edge/smartpi-edge-stream.service`
- `edge/smartpi-edge-bridge.service`
- `edge/smartpi-voice-agent.service`

建议复制到系统目录：

```bash
sudo cp edge/smartpi-sensor-hub.service /etc/systemd/system/
sudo cp edge/smartpi-edge-stream.service /etc/systemd/system/
sudo cp edge/smartpi-edge-bridge.service /etc/systemd/system/
sudo cp edge/smartpi-voice-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
```

启用并启动：

```bash
sudo systemctl enable smartpi-sensor-hub.service
sudo systemctl enable smartpi-edge-stream.service
sudo systemctl enable smartpi-edge-bridge.service
sudo systemctl enable smartpi-voice-agent.service

sudo systemctl start smartpi-sensor-hub.service
sudo systemctl start smartpi-edge-stream.service
sudo systemctl start smartpi-edge-bridge.service
sudo systemctl start smartpi-voice-agent.service
```

## 10. 部署 RAG 服务

进入目录：

```bash
cd /home/pi/smartpi/rag-chroma
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

在 `.env` 中至少确认：

- `DASHSCOPE_API_KEY`
- `VECTOR_BACKEND`
- `CHROMA_PERSIST_DIR`
- `QDRANT_URL`
- `QDRANT_COLLECTION`

### 方式 A：直接启动

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8095
```

### 方式 B：service 方式

```bash
bash deploy/bootstrap_pi.sh /home/pi/smartpi/rag-chroma
sudo cp deploy/smartpi-rag-chroma.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable smartpi-rag-chroma.service
sudo systemctl start smartpi-rag-chroma.service
```

## 11. 推荐启动顺序

推荐顺序：

1. 确认模型、摄像头、音频设备、I2C 设备可用
2. 启动 `smartpi-sensor-hub`
3. 启动 `smartpi-edge-stream`
4. 启动 `smartpi-edge-bridge`
5. 启动 `smartpi-voice-agent`
6. 最后接入 `smartpi-rag-chroma`

## 12. 默认端口

| 服务 | 端口 |
| --- | --- |
| MJPEG 检测流 | `8081` |
| 传感器中枢 | `8091` |
| 边缘桥 | `8092` |
| 语音助手 | `8093` |
| RAG API | `8094` / `8095` |

## 13. 常用检查命令

查看服务状态：

```bash
sudo systemctl --no-pager --full status smartpi-sensor-hub.service
sudo systemctl --no-pager --full status smartpi-edge-stream.service
sudo systemctl --no-pager --full status smartpi-edge-bridge.service
sudo systemctl --no-pager --full status smartpi-voice-agent.service
sudo systemctl --no-pager --full status smartpi-rag-chroma.service
```

查看日志：

```bash
journalctl -u smartpi-sensor-hub.service -n 200 --no-pager
journalctl -u smartpi-edge-stream.service -n 200 --no-pager
journalctl -u smartpi-edge-bridge.service -n 200 --no-pager
journalctl -u smartpi-voice-agent.service -n 200 --no-pager
journalctl -u smartpi-rag-chroma.service -n 200 --no-pager
```

查看监听端口：

```bash
ss -ltnp
```

## 14. 常见问题

### 1. 摄像头打不开

检查：

- 摄像头是否被系统识别
- `/home/pi/smartpi/models/tongue_best.onnx` 是否存在
- `class_map.json` 是否存在

### 2. 语音助手没有声音

检查：

- 录音设备和播放设备名称
- `PIPER_MODEL_PATH` 和 `PIPER_CONFIG_PATH`
- `ffmpeg` / `ffplay` 是否正常

### 3. RAG 服务启动失败

检查：

- `.env` 是否完整
- `DASHSCOPE_API_KEY` 是否有效
- `chromadb` / `qdrant-client` 是否安装成功

### 4. OpenClaw 不触发动作

检查：

- `ENABLE_OPENCLAW=1`
- `OPENCLAW_COMMAND` 是否正确
- `smartpi-edge-control` skill 是否已安装

## 15. 安全提醒

- 不要把真实 `.env`、API Key、日志、缓存和模型权重提交到仓库。
- RAG 回答仅供中医知识参考，不能替代医生诊断。
- 涉及急症、孕产、儿童、严重慢病和药物冲突时，应优先建议线下就医。

# SmartPi 树莓派完整运行规则总控

本文档给树莓派部署和运行时使用。它回答一个问题：树莓派到底应该从哪里读代码、读配置、启动哪些服务、监听哪些端口、如何重建 RAG 知识库，以及出问题时看哪里。

## 1. 运行身份

树莓派上的标准项目路径统一为：

```bash
/home/pi/smartpi
```

对应本机开发目录：

```text
D:\RAG\Smart-pi-source
```

树莓派上不要使用 Windows 路径。所有 service、脚本、env 都默认按 `/home/pi/smartpi` 运行。

## 2. 组件总览

| 组件 | 作用 | 默认端口 | 树莓派状态 |
|---|---|---:|---|
| `rag-chroma` | 中医知识库 RAG API | `8095` | 建议常驻 |
| `agent-orchestrator` | 7 Agent 调度层 | `8096` | 建议常驻 |
| `smartpi_voice_agent.py` | 语音助手主入口 | `8093` | 建议常驻 |
| `edge bridge` | 本地设备桥 | `8092` / `18789` | 建议常驻 |
| `mjpeg stream` | 摄像头识别流 | `8081` | 按需常驻 |
| `sensor hub` | 传感器服务 | `8091` | 按需常驻 |
| `OpenClaw` | 智能体/技能扩展 | 无固定端口 | 可选 |

树莓派运行版默认 RAG 端口使用 `8095`，因为 `agent-orchestrator/.env.example` 已经指向：

```env
RAG_BASE_URL=http://127.0.0.1:8095
```

PC 本地开发可以继续使用 `8094`，但树莓派部署时应统一到 `8095`，避免和本地调试习惯混在一起。

## 3. 配置文件

树莓派至少需要这些运行配置：

```bash
/home/pi/smartpi/config/voice_agent.env
/home/pi/smartpi/config/edge_bridge.env
/home/pi/smartpi/config/sensor_hub.env
/home/pi/smartpi/config/mjpeg_stream.env
/home/pi/smartpi/rag-chroma/.env
/home/pi/smartpi/agent-orchestrator/.env
```

第一次部署时从模板复制：

```bash
cd /home/pi/smartpi

cp config/voice_agent.env.example config/voice_agent.env
cp config/edge_bridge.env.example config/edge_bridge.env
cp config/sensor_hub.env.example config/sensor_hub.env
cp config/mjpeg_stream.env.example config/mjpeg_stream.env

cp rag-chroma/deploy/pi.env.example rag-chroma/.env
cp agent-orchestrator/.env.example agent-orchestrator/.env
```

真实密钥只写入 `.env`，不要写入 `.env.example`。

## 4. 必填密钥和模型

`rag-chroma/.env` 至少确认：

```env
DASHSCOPE_API_KEY=你的真实 key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
LLM_MODEL=qwen3-max
```

如果使用云端 reranker：

```env
ENABLE_RERANK=true
RERANK_PROVIDER=dashscope
RERANK_MODEL=qwen3-rerank
```

如果暂时不用云端能力，可先留空 `DASHSCOPE_API_KEY`，系统会进入本地开发/占位模式，但这不代表正式 RAG 效果。

## 5. 向量库规则

树莓派第一版建议二选一：

### 方案 A：local 后端

适合快速验证。

```env
VECTOR_BACKEND=local
LOCAL_VECTOR_PATH=./data/local_vectors.json
```

优点：无需 Docker 和额外服务。

缺点：数据大后性能和并发能力有限。

### 方案 B：Chroma 后端

适合树莓派本地持久化运行。

```env
VECTOR_BACKEND=chroma
CHROMA_PATH=./data/chroma
```

使用 Chroma 时，必须在树莓派上重新 ingest。不要直接依赖 PC 的 `local_vectors.json`。

## 6. Python 环境

建议每个主要服务独立 venv。

RAG：

```bash
cd /home/pi/smartpi/rag-chroma
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

Agent Orchestrator：

```bash
cd /home/pi/smartpi/agent-orchestrator
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

Edge / voice 侧如果继续使用项目根目录 venv：

```bash
cd /home/pi/smartpi
python3 -m venv venv
./venv/bin/pip install --upgrade pip
```

语音、摄像头、YOLO 的依赖按 `DEPLOY_RASPBERRY_PI.md` 和 `edge/pi_install_*.sh` 执行。

## 7. RAG 知识库重建

每次修改这些内容后，都要在树莓派上重建索引：

- `rag-chroma/data/raw/`
- `rag-chroma/app/ingest/`
- `rag-chroma/app/retrieval/`
- chunk 参数
- embedding 维度
- vector backend

重建命令：

```bash
cd /home/pi/smartpi/rag-chroma
./.venv/bin/python scripts/rebuild_index.py --path data/raw --source-type mixed
```

重建后检查：

```bash
curl http://127.0.0.1:8095/health
```

如果服务未启动，可先用命令行方式临时启动：

```bash
cd /home/pi/smartpi/rag-chroma
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8095
```

## 8. Agent Orchestrator

配置：

```bash
cd /home/pi/smartpi/agent-orchestrator
cp .env.example .env
```

关键项：

```env
AGENT_HOST=127.0.0.1
AGENT_PORT=8096
RAG_BASE_URL=http://127.0.0.1:8095
EDGE_BRIDGE_BASE_URL=http://127.0.0.1:18789
DEVICE_DRY_RUN=true
```

树莓派上设备控制第一阶段必须保持：

```env
DEVICE_DRY_RUN=true
```

确认动作计划正确后，再考虑真实硬件执行。

临时启动：

```bash
cd /home/pi/smartpi/agent-orchestrator
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8096
```

## 9. systemd 服务

已有 service 文件：

```bash
edge/smartpi-sensor-hub.service
edge/smartpi-edge-stream.service
edge/smartpi-edge-bridge.service
edge/smartpi-voice-agent.service
rag-chroma/deploy/smartpi-rag-chroma.service
```

安装：

```bash
cd /home/pi/smartpi

sudo cp edge/smartpi-sensor-hub.service /etc/systemd/system/
sudo cp edge/smartpi-edge-stream.service /etc/systemd/system/
sudo cp edge/smartpi-edge-bridge.service /etc/systemd/system/
sudo cp edge/smartpi-voice-agent.service /etc/systemd/system/
sudo cp rag-chroma/deploy/smartpi-rag-chroma.service /etc/systemd/system/

sudo systemctl daemon-reload
```

启用：

```bash
sudo systemctl enable smartpi-rag-chroma.service
sudo systemctl enable smartpi-sensor-hub.service
sudo systemctl enable smartpi-edge-stream.service
sudo systemctl enable smartpi-edge-bridge.service
sudo systemctl enable smartpi-voice-agent.service
```

启动顺序建议：

```bash
sudo systemctl start smartpi-rag-chroma.service
sudo systemctl start smartpi-sensor-hub.service
sudo systemctl start smartpi-edge-stream.service
sudo systemctl start smartpi-edge-bridge.service
sudo systemctl start smartpi-voice-agent.service
```

`agent-orchestrator` 目前建议先手动运行或后续补 service 文件。启用语音侧 Agent 模式前，先确认 `http://127.0.0.1:8096/health` 可用。

## 10. 健康检查

端口检查：

```bash
ss -lntp | grep -E '8081|8091|8092|8093|8095|8096|18789'
```

RAG：

```bash
curl http://127.0.0.1:8095/health
```

Agent：

```bash
curl http://127.0.0.1:8096/health
```

RAG 查询：

```bash
curl -s http://127.0.0.1:8095/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"舌苔黄腻说明什么？","top_k":5,"include_chunks":true}'
```

设备 dry-run：

```bash
curl -s http://127.0.0.1:8096/api/v1/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"打开摄像头识别"}'
```

返回里应看到：

```text
dry_run=true
executed=false
```

## 11. 日志

systemd 状态：

```bash
sudo systemctl --no-pager --full status smartpi-rag-chroma.service
sudo systemctl --no-pager --full status smartpi-edge-bridge.service
sudo systemctl --no-pager --full status smartpi-edge-stream.service
sudo systemctl --no-pager --full status smartpi-sensor-hub.service
sudo systemctl --no-pager --full status smartpi-voice-agent.service
```

journal 日志：

```bash
journalctl -u smartpi-rag-chroma.service -n 200 --no-pager
journalctl -u smartpi-edge-bridge.service -n 200 --no-pager
journalctl -u smartpi-edge-stream.service -n 200 --no-pager
journalctl -u smartpi-sensor-hub.service -n 200 --no-pager
journalctl -u smartpi-voice-agent.service -n 200 --no-pager
```

项目日志：

```bash
ls -lah /home/pi/smartpi/data/results
tail -n 200 /home/pi/smartpi/data/results/rag_chroma_api.log
tail -n 200 /home/pi/smartpi/data/results/voice_agent.log
tail -n 200 /home/pi/smartpi/data/results/edge_bridge.log
```

## 12. 摄像头和音频

摄像头检查：

```bash
ls /dev/video*
v4l2-ctl --list-devices
```

音频设备检查：

```bash
arecord -l
aplay -l
```

如果设备名不是 `default`，同步修改：

```bash
/home/pi/smartpi/config/voice_agent.env
```

重点变量：

```env
RECORD_DEVICE=default
PLAYBACK_DEVICE=default
```

## 13. OpenClaw / edge bridge

语音助手默认通过 edge bridge 和 OpenClaw 触发设备动作。

关键配置：

```env
BRIDGE_BASE_URL=http://127.0.0.1:8092
ENABLE_OPENCLAW=1
OPENCLAW_COMMAND=/home/pi/smartpi/openclaw/run_openclaw_message.sh {text}
```

Agent Orchestrator 侧：

```env
EDGE_BRIDGE_BASE_URL=http://127.0.0.1:18789
DEVICE_DRY_RUN=true
```

没有确认硬件安全前，不要关闭 dry-run。

## 14. 更新流程

从 PC 同步新代码到树莓派后，按这个顺序处理：

```bash
cd /home/pi/smartpi
git status

# 如果 Python 依赖变了
cd /home/pi/smartpi/rag-chroma
./.venv/bin/pip install -r requirements.txt

cd /home/pi/smartpi/agent-orchestrator
./.venv/bin/pip install -r requirements.txt

# 如果 RAG 数据、切分、检索逻辑变了
cd /home/pi/smartpi/rag-chroma
./.venv/bin/python scripts/rebuild_index.py --path data/raw --source-type mixed

# 重启服务
sudo systemctl restart smartpi-rag-chroma.service
sudo systemctl restart smartpi-edge-bridge.service
sudo systemctl restart smartpi-voice-agent.service
```

最后执行健康检查和 dry-run smoke。

## 15. 当前还需要补齐的运行规则

当前仓库还缺一个正式的：

```bash
smartpi-agent-orchestrator.service
```

因此 Agent Orchestrator 目前更适合先手动启动验证。等 RAG 和设备 dry-run 都稳定后，再补 systemd 常驻服务。

## 16. 安全规则

- `.env`、API Key、日志、缓存、真实采集数据不要提交 Git。
- RAG 回答仅供中医知识参考，不能替代医生诊断。
- 设备动作先使用 dry-run，确认 action plan 后再接真实硬件。
- 儿童、孕产、急症、严重慢病、用药冲突必须提示线下就医。

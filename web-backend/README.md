# smartpi Web Backend

电脑端 Web 控制台的业务后端，用于保存审计日志、RAG 问答历史、Agent 运行记录、设备动作和运行配置。

它不替代 RAG 向量库。RAG 的 chunk、embedding 和检索索引仍由 `rag-chroma` 管理；本服务只保存 Web 控制台需要的业务数据。

## 技术栈

```text
FastAPI
SQLite
Python sqlite3
Pydantic
Uvicorn
```

## 启动

```powershell
cd D:\RAG\Smart-pi-source\web-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 18080 --reload
```

访问：

```text
http://127.0.0.1:18080/health
http://127.0.0.1:18080/docs
```

## 数据库

默认数据库文件：

```text
web-backend/data/smartpi_web.db
```

可通过环境变量修改：

```env
SMARTPI_WEB_DB=data/smartpi_web.db
```

`.db` 文件不会进入 Git。

## 数据库管理命令

统一入口：

```powershell
python scripts\manage_db.py <command>
```

查看表统计：

```powershell
python scripts\manage_db.py stats
```

备份数据库：

```powershell
python scripts\manage_db.py backup --output-dir backups
```

导出 JSON：

```powershell
python scripts\manage_db.py export --output exports\smartpi_web_export.json
python scripts\manage_db.py export --table audit_logs --output exports\audit_logs.json
```

清理演示 / mock / smoke 数据：

```powershell
python scripts\manage_db.py clear-demo
```

清空全部业务数据必须显式确认：

```powershell
python scripts\manage_db.py clear-demo --all --yes
```

整理 SQLite 空间：

```powershell
python scripts\manage_db.py vacuum
```

如果要操作非默认数据库：

```powershell
python scripts\manage_db.py --db data\smartpi_web.db stats
```

## API

```text
GET  /health

POST /api/v1/audit-logs
GET  /api/v1/audit-logs

POST /api/v1/device-actions
GET  /api/v1/device-actions

POST /api/v1/rag/messages
GET  /api/v1/rag/messages

POST /api/v1/agent/runs
GET  /api/v1/agent/runs

POST /api/v1/service-snapshots
GET  /api/v1/service-snapshots

PUT  /api/v1/settings/{key}
GET  /api/v1/settings
```

## 第一版边界

- 不做登录鉴权。
- 不代理 RAG / Agent / Edge 请求。
- 不执行硬件动作。
- 不保存密钥。
- 不替代 Chroma / Qdrant。

后续可以把 Web Dashboard 的操作日志、RAG 问答结果、Agent dry-run 动作自动写入本服务。

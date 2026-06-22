# smartpi RAG

独立的中医知识库 RAG 服务，默认运行在 `:8094`，可被 smartpi 语音助手或 OpenClaw 后续调用。

工程支持三种向量后端：

- `local`：本地 JSON 向量库，适合 Windows/无 Docker 开发验证。
- `qdrant`：正式部署推荐，适合树莓派 Docker。
- `chroma`：轻量持久化备选。

## Quick Start

```powershell
cd D:\RAG\Smart-pi-source\rag-chroma
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

在 `.env` 中填写：

```env
DASHSCOPE_API_KEY=sk-...
```

没有 Docker 或还没有 API Key 时，可以先用本地开发模式：

```env
VECTOR_BACKEND=local
DASHSCOPE_API_KEY=
```

这样系统会使用确定性的本地假向量和占位回答，便于先跑通导入、检索、API。

启动开发 API：

```powershell
.\scripts\start_dev.ps1
```

另开一个 PowerShell 导入样例资料：

```powershell
.\scripts\ingest_sample.ps1
python scripts\query_cli.py "舌苔黄腻说明什么" --include-chunks
```

正式部署时启动 Qdrant：

```powershell
docker compose -f deploy\docker-compose.yml up -d qdrant
```

正式启动 API：

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8094 --reload
```

导入资料：

```powershell
python scripts\ingest.py data\raw --source-type mixed
```

查询：

```powershell
python scripts\query_cli.py "舌苔黄腻说明什么"
```

## API

- `GET /health`
- `POST /api/v1/ingest`
- `POST /api/v1/query`
- `POST /api/v1/retrieve`
- `GET /api/v1/documents`
- `DELETE /api/v1/documents/{document_id}`

## Retrieval

The retrieval layer now supports query rewrite, vector recall, BM25 lexical recall, reciprocal rank fusion, DashScope `qwen3-rerank` cloud reranking with local fallback, metadata filters, relevance thresholding, and no-answer abstention. See `docs/retrieval_pipeline.md`.

## Notes

- 没有配置 `DASHSCOPE_API_KEY` 时，服务会使用确定性的本地假向量和抽取式占位回答，便于开发和测试，但不能用于正式 RAG 效果评估。
- 所有生成回答都会包含医疗安全提示：仅供中医知识参考，不能替代医生诊断。

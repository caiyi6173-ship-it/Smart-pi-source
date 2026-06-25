# SmartPi 项目环境分离说明

本目录是树莓派运行环境项目：

```text
D:\RAG\Smart-pi-source
```

对应的 PC 开发环境项目位于：

```text
D:\RAG\Smart-pc
```

## 分离原则

- 两个目录保留同一套最新功能代码。
- `rag-chroma/` 在两个目录中分别存在，RAG 代码和索引互不共用。
- PC 目录用于 Windows 本地开发、测试、文档整理和离线 smoke。
- 树莓派目录用于同步到 Raspberry Pi 后部署、硬件联调和 systemd 常驻运行。
- 不要让两个目录共用同一个 `.env`、`data/chroma/` 或运行时服务目录。

## RAG 注意事项

如果修改了：

- `rag-chroma/app/ingest/`
- `rag-chroma/app/retrieval/`
- `rag-chroma/data/raw/`
- chunk 参数、embedding 参数、vector backend

需要分别在目标环境重新生成索引。

PC 本地可使用：

```powershell
cd D:\RAG\Smart-pc\rag-chroma
$env:VECTOR_BACKEND="local"
python scripts\rebuild_index.py --path data\raw --source-type mixed
```

树莓派环境应在树莓派上使用自己的 `.env` 和向量库后端重新 ingest，尤其是使用 Chroma 时，不应直接依赖 PC 的 `local_vectors.json`。

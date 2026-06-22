$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

python scripts/ingest.py data/raw --source-type mixed --tag demo
@'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
health = client.get("/health")
print("health", health.status_code, health.json())
query = client.post(
    "/api/v1/query",
    json={"question": "\u820c\u82d4\u9ec4\u817b\u8bf4\u660e\u4ec0\u4e48", "include_chunks": True},
)
print("query", query.status_code)
print(query.json()["answer"])
'@ | python -

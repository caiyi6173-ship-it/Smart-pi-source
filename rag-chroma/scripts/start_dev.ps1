$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

if (!(Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Created .env from .env.example. Default VECTOR_BACKEND is qdrant in example; set VECTOR_BACKEND=local for no-Docker development."
}

python -m uvicorn app.main:app --host 0.0.0.0 --port 8094 --reload


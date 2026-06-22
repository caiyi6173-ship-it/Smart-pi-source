$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

python scripts/ingest.py data/raw --source-type mixed --tag demo --tag tongue


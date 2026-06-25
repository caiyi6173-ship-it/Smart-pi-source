param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8096,
    [string]$RagBaseUrl = "http://127.0.0.1:8094",
    [string]$EdgeBridgeBaseUrl = "http://127.0.0.1:18789",
    [switch]$Reload,
    [switch]$SkipRagHealthCheck
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$env:RAG_BASE_URL = $RagBaseUrl
$env:EDGE_BRIDGE_BASE_URL = $EdgeBridgeBaseUrl
$env:DEVICE_DRY_RUN = "true"
$env:AGENT_HOST = $HostAddress
$env:AGENT_PORT = [string]$Port

Write-Host "SmartPI Agent Orchestrator local start"
Write-Host ("  host: {0}" -f $HostAddress)
Write-Host ("  port: {0}" -f $Port)
Write-Host ("  rag:  {0}" -f $RagBaseUrl)
Write-Host ("  edge: {0}" -f $EdgeBridgeBaseUrl)
Write-Host "  device dry-run: true"

if (-not $SkipRagHealthCheck) {
    try {
        $health = Invoke-RestMethod -Uri ($RagBaseUrl.TrimEnd("/") + "/health") -Method Get -TimeoutSec 5
        Write-Host ("RAG health: {0}" -f $health.status)
    } catch {
        Write-Warning ("RAG health check failed: {0}" -f $_.Exception.Message)
        Write-Warning "Agent can still start, but RAG questions will return a controlled no-answer until rag-chroma is available."
    }
}

$uvicornArgs = @("app.main:app", "--host", $HostAddress, "--port", [string]$Port)
if ($Reload) {
    $uvicornArgs += "--reload"
}

python -m uvicorn @uvicornArgs

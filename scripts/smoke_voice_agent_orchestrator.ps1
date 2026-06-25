param(
    [string]$AgentUrl = "http://127.0.0.1:8096",
    [string]$Message = "舌苔黄腻说明什么？"
)

$ErrorActionPreference = "Stop"

$payload = @{
    session_id = "voice-smoke"
    message = $Message
    input_type = "voice"
    user_context = @{
        source = "smoke_voice_agent_orchestrator"
        confirm_device_action = $false
    }
    options = @{
        include_trace = $true
        include_citations = $true
    }
} | ConvertTo-Json -Depth 8

$url = $AgentUrl.TrimEnd("/") + "/api/v1/agent/chat"
Write-Host ("POST {0}" -f $url)
$response = Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json; charset=utf-8" -Body $payload -TimeoutSec 120

Write-Host ("intent: {0}" -f $response.intent)
Write-Host ("risk: {0}" -f $response.risk_level)
Write-Host ("refused: {0}" -f $response.refused)
Write-Host ("citations: {0}" -f @($response.citations).Count)
Write-Host "trace:"
foreach ($step in $response.trace) {
    Write-Host ("  - {0} | {1} | {2}" -f $step.agent, $step.status, $step.summary)
}
Write-Host ""
Write-Host "answer:"
Write-Host $response.answer

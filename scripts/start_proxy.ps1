param(
    [int]$Port = 8765,
    [string]$HostName = "127.0.0.1",
    [string]$UpstreamBaseUrl = "http://127.0.0.1:8001/v1",
    [string]$Model = "Qwen3-Coder-Next",
    [string]$CaptureDir = "captures",
    [double]$StreamHeartbeatSeconds = 5.0,
    [ValidateSet("repair", "observe")]
    [string]$Mode = "repair",
    [ValidateSet("full", "spoon")]
    [string]$ContextPolicy = "full",
    [int]$ContextMaxChars = 60000,
    [int]$ContextRecentItems = 10
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $Root.Path

python -m open_gate.server `
    --host $HostName `
    --port $Port `
    --model $Model `
    --capture-dir $CaptureDir `
    --upstream-base-url $UpstreamBaseUrl `
    --stream-heartbeat-seconds $StreamHeartbeatSeconds `
    --normalization-mode $Mode `
    --context-policy $ContextPolicy `
    --context-max-chars $ContextMaxChars `
    --context-recent-items $ContextRecentItems

param(
    [int]$Port = 8765,
    [string]$HostName = "127.0.0.1",
    [string]$UpstreamBaseUrl = "http://127.0.0.1:8001/v1",
    [string]$Model = "auto",
    [string]$CaptureDir = "captures",
    [double]$UpstreamTimeoutSeconds = 420.0,
    [double]$StreamHeartbeatSeconds = 2.0,
    [ValidateSet("repair", "observe")]
    [string]$Mode = "repair",
    [ValidateSet("full", "spoon")]
    [string]$ContextPolicy = "spoon",
    [int]$ContextMaxChars = 60000,
    [int]$ContextRecentItems = 12,
    [ValidateSet("full", "auto", "digest")]
    [string]$InstructionPolicy = "auto",
    [ValidateSet("full", "auto", "compact")]
    [string]$ToolSchemaPolicy = "auto"
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
    --upstream-timeout $UpstreamTimeoutSeconds `
    --stream-heartbeat-seconds $StreamHeartbeatSeconds `
    --normalization-mode $Mode `
    --context-policy $ContextPolicy `
    --context-max-chars $ContextMaxChars `
    --context-recent-items $ContextRecentItems `
    --instruction-policy $InstructionPolicy `
    --tool-schema-policy $ToolSchemaPolicy

param(
    [int]$Port = 8765,
    [string]$HostName = "127.0.0.1",
    [string]$UpstreamBaseUrl = "http://127.0.0.1:8001/v1",
    [string]$Model = "Qwen3-Coder-Next",
    [string]$CaptureDir = "captures",
    [ValidateSet("repair", "observe")]
    [string]$Mode = "repair"
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
    --normalization-mode $Mode

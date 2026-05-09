param(
    [int]$Port = 8765,
    [string]$UpstreamBaseUrl = "http://127.0.0.1:8001/v1",
    [string]$Model = "Qwen3-Coder-Next",
    [string]$Suite = "fixtures\benchmarks\qwen_serious_tool_stress.json",
    [int]$Runs = 3,
    [string]$Label = "qwen_open_gate_serious_r3",
    [string]$Output = "runs\qwen_open_gate_serious_r3.json",
    [ValidateSet("repair", "observe")]
    [string]$Mode = "repair"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$serverJob = Start-Job -Name "open-gate-proxy" -ScriptBlock {
    param($RootPath, $PortNumber, $Upstream, $ProxyMode)
    Set-Location -LiteralPath $RootPath
    python -m open_gate.server `
        --host 127.0.0.1 `
        --port $PortNumber `
        --model "Qwen3-Coder-Next" `
        --upstream-base-url $Upstream `
        --normalization-mode $ProxyMode `
        --quiet
} -ArgumentList $Root.Path, $Port, $UpstreamBaseUrl, $Mode

try {
    Start-Sleep -Milliseconds 900
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health"
    Set-Location -LiteralPath $Root.Path
    python -m open_gate.benchmark `
        --base-url "http://127.0.0.1:$Port/v1" `
        --model $Model `
        --suite $Suite `
        --runs $Runs `
        --label $Label `
        --output $Output `
        --summary-only
}
finally {
    Stop-Job -Job $serverJob -ErrorAction SilentlyContinue
    Receive-Job -Job $serverJob -ErrorAction SilentlyContinue | Out-Null
    Remove-Job -Job $serverJob -Force -ErrorAction SilentlyContinue
}

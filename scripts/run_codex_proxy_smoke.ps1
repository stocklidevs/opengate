param(
    [int]$Port = 8765,
    [string]$UpstreamBaseUrl = "http://127.0.0.1:8001/v1",
    [string]$Model = "Qwen3-Coder-Next",
    [string]$CodexCwd = "C:\Users\example\source\repos\glm-test",
    [string]$Prompt = "Say hello in one short sentence.",
    [ValidateSet("repair", "observe")]
    [string]$Mode = "repair"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$serverJob = Start-Job -Name "open-gate-codex-proxy-smoke" -ScriptBlock {
    param($RootPath, $PortNumber, $Upstream, $ModelName, $ProxyMode)
    Set-Location -LiteralPath $RootPath
    python -m open_gate.server `
        --host 127.0.0.1 `
        --port $PortNumber `
        --model $ModelName `
        --upstream-base-url $Upstream `
        --normalization-mode $ProxyMode `
        --quiet
} -ArgumentList $Root.Path, $Port, $UpstreamBaseUrl, $Model, $Mode

try {
    Start-Sleep -Milliseconds 900
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health"

    codex exec `
        --skip-git-repo-check `
        --cd $CodexCwd `
        --sandbox read-only `
        --json `
        -m $Model `
        -c 'model_providers.open_gate_qwen.name="Open Gate Qwen"' `
        -c "model_providers.open_gate_qwen.base_url=`"http://127.0.0.1:$Port/v1`"" `
        -c 'model_providers.open_gate_qwen.wire_api="responses"' `
        -c 'model_provider="open_gate_qwen"' `
        $Prompt
}
finally {
    Stop-Job -Job $serverJob -ErrorAction SilentlyContinue
    Receive-Job -Job $serverJob -ErrorAction SilentlyContinue | Out-Null
    Remove-Job -Job $serverJob -Force -ErrorAction SilentlyContinue
}

param(
    [int]$Port = 8765,
    [string]$CodexCwd = "C:\Users\example\source\repos\glm-test"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$serverJob = Start-Job -Name "open-gate-codex-capture" -ScriptBlock {
    param($RootPath, $PortNumber)
    Set-Location -LiteralPath $RootPath
    python -m open_gate.server --host 127.0.0.1 --port $PortNumber --quiet
} -ArgumentList $Root.Path, $Port

try {
    Start-Sleep -Milliseconds 800
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health"

    codex exec `
        --skip-git-repo-check `
        --cd $CodexCwd `
        --sandbox read-only `
        --json `
        -m "open-gate-probe" `
        -c 'model_providers.open_gate_capture.name="Open Gate capture"' `
        -c "model_providers.open_gate_capture.base_url=`"http://127.0.0.1:$Port/v1`"" `
        -c 'model_providers.open_gate_capture.wire_api="responses"' `
        -c 'model_provider="open_gate_capture"' `
        "Say hello in one short sentence."
}
finally {
    Stop-Job -Job $serverJob -ErrorAction SilentlyContinue
    Remove-Job -Job $serverJob -Force -ErrorAction SilentlyContinue
}

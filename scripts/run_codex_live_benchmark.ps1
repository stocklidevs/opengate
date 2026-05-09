param(
    [int]$Port = 8765,
    [string]$UpstreamBaseUrl = "http://127.0.0.1:8001/v1",
    [string]$Model = "Qwen3-Coder-Next",
    [string]$CodexCwd = "C:\Users\example\source\repos\glm-test",
    [string]$Suite = "fixtures\codex_live\smoke.json",
    [ValidateSet("repair", "observe")]
    [string]$Mode = "repair",
    [int]$Runs = 1,
    [string]$Label = "codex_live_smoke",
    [string]$OutputRoot = "runs\codex-live",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $Root.Path

$suitePath = Resolve-Path $Suite
$suiteJson = Get-Content -Raw -LiteralPath $suitePath.Path | ConvertFrom-Json

if ($DryRun) {
    [ordered]@{
        mode = $Mode
        model = $Model
        upstream_base_url = $UpstreamBaseUrl
        codex_cwd = $CodexCwd
        suite = $suitePath.Path
        runs = $Runs
        cases = @($suiteJson.cases).Count
        would_write_under = (Join-Path $Root.Path $OutputRoot)
    } | ConvertTo-Json -Depth 4
    return
}

$runId = "{0}-{1}-{2}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), $Label, $Mode
$runDir = Join-Path $Root.Path (Join-Path $OutputRoot $runId)
$captureDir = Join-Path $runDir "captures"
New-Item -ItemType Directory -Force -Path $runDir, $captureDir | Out-Null

$manifest = [ordered]@{
    label = $Label
    run_id = $runId
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    mode = $Mode
    model = $Model
    upstream_base_url = $UpstreamBaseUrl
    codex_cwd = $CodexCwd
    suite = $suitePath.Path
    runs = $Runs
    capture_dir = $captureDir
    cases = @()
}

$serverJob = Start-Job -Name "open-gate-codex-live-$Mode" -ScriptBlock {
    param($RootPath, $PortNumber, $Upstream, $ModelName, $CapturePath, $ProxyMode)
    Set-Location -LiteralPath $RootPath
    python -m open_gate `
        --host 127.0.0.1 `
        --port $PortNumber `
        --model $ModelName `
        --capture-dir $CapturePath `
        --upstream $Upstream `
        --normalization-mode $ProxyMode `
        --quiet
} -ArgumentList $Root.Path, $Port, $UpstreamBaseUrl, $Model, $captureDir, $Mode

try {
    Start-Sleep -Milliseconds 900
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health"
    $manifest["health"] = $health

    for ($runIndex = 0; $runIndex -lt $Runs; $runIndex++) {
        foreach ($case in @($suiteJson.cases)) {
            $caseId = [string]$case.id
            $safeCaseId = $caseId -replace '[^A-Za-z0-9_.-]', '_'
            $outputFile = Join-Path $runDir ("codex-r{0:D2}-{1}.jsonl" -f $runIndex, $safeCaseId)
            $prompt = [string]$case.prompt
            $started = Get-Date

            $codexArgs = @(
                "exec",
                "--skip-git-repo-check",
                "--cd", $CodexCwd,
                "--sandbox", "read-only",
                "--json",
                "-m", $Model,
                "-c", 'model_providers.open_gate_qwen.name="Open Gate Qwen"',
                "-c", "model_providers.open_gate_qwen.base_url=`"http://127.0.0.1:$Port/v1`"",
                "-c", 'model_providers.open_gate_qwen.wire_api="responses"',
                "-c", 'model_provider="open_gate_qwen"',
                $prompt
            )

            $previousErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                $output = & codex @codexArgs 2>&1
                $exitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }
            $output | Set-Content -LiteralPath $outputFile -Encoding UTF8
            $finished = Get-Date

            $manifest.cases += [ordered]@{
                run_index = $runIndex
                case_id = $caseId
                category = $case.category
                expected_tools = $case.expected_tools
                expect_no_tool = [bool]$case.expect_no_tool
                prompt = $prompt
                exit_code = $exitCode
                duration_seconds = [math]::Round(($finished - $started).TotalSeconds, 3)
                output_file = $outputFile
            }
        }
    }
}
finally {
    Stop-Job -Job $serverJob -ErrorAction SilentlyContinue
    Receive-Job -Job $serverJob -ErrorAction SilentlyContinue | Out-Null
    Remove-Job -Job $serverJob -Force -ErrorAction SilentlyContinue
    $manifest["completed_at"] = (Get-Date).ToUniversalTime().ToString("o")
    $manifestPath = Join-Path $runDir "manifest.json"
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
}

$reportPath = Join-Path $runDir "report.json"
python -m open_gate.codex_report $captureDir --codex-dir $runDir --pretty | Set-Content -LiteralPath $reportPath -Encoding UTF8

[ordered]@{
    run_dir = $runDir
    manifest = (Join-Path $runDir "manifest.json")
    report = $reportPath
} | ConvertTo-Json -Depth 4

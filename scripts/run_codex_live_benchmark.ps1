param(
    [int]$Port = 8765,
    [string]$UpstreamBaseUrl = "http://127.0.0.1:8001/v1",
    [string]$Model = "Qwen3-Coder-Next",
    [string]$CodexCwd = "C:\Users\example\source\repos\glm-test",
    [string]$Suite = "fixtures\codex_live\smoke.json",
    [ValidateSet("repair", "observe")]
    [string]$Mode = "repair",
    [ValidateSet("full", "spoon")]
    [string]$ContextPolicy = "full",
    [int]$ContextMaxChars = 60000,
    [int]$ContextRecentItems = 10,
    [ValidateSet("full", "auto", "digest")]
    [string]$InstructionPolicy = "auto",
    [ValidateSet("full", "auto", "compact")]
    [string]$ToolSchemaPolicy = "auto",
    [ValidateSet("read-only", "workspace-write", "danger-full-access")]
    [string]$Sandbox = "read-only",
    [switch]$FailOnPromptSandboxMismatch,
    [int]$CaseTimeoutSeconds = 420,
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

function Get-CodexPromptSandbox {
    param(
        [string]$CaseCwd,
        [string]$SandboxMode
    )

    $previousLocation = Get-Location
    try {
        Set-Location -LiteralPath $CaseCwd
        $output = & codex debug prompt-input -c "sandbox_mode=`"$SandboxMode`"" -- "Open Gate sandbox preflight" 2>&1
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
        $text = ($output | Out-String).Trim()
        $match = [regex]::Match($text, 'sandbox_mode`\s+is\s+`(?<mode>read-only|workspace-write|danger-full-access)`')
        $visible = if ($match.Success) { $match.Groups["mode"].Value } else { $null }
        return [ordered]@{
            ok = ($exitCode -eq 0 -and $null -ne $visible)
            requested = $SandboxMode
            visible = $visible
            matches = ($visible -eq $SandboxMode)
            exit_code = $exitCode
            warning = if ($visible -ne $SandboxMode) { "Codex prompt-visible sandbox does not match requested sandbox." } else { $null }
        }
    }
    catch {
        return [ordered]@{
            ok = $false
            requested = $SandboxMode
            visible = $null
            matches = $false
            exit_code = 1
            warning = [string]$_
        }
    }
    finally {
        Set-Location -LiteralPath $previousLocation.Path
    }
}

if ($DryRun) {
    [ordered]@{
        mode = $Mode
        context_policy = $ContextPolicy
        context_max_chars = $ContextMaxChars
        context_recent_items = $ContextRecentItems
        instruction_policy = $InstructionPolicy
        tool_schema_policy = $ToolSchemaPolicy
        sandbox = $Sandbox
        fail_on_prompt_sandbox_mismatch = [bool]$FailOnPromptSandboxMismatch
        case_timeout_seconds = $CaseTimeoutSeconds
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
    context_policy = $ContextPolicy
    context_max_chars = $ContextMaxChars
    context_recent_items = $ContextRecentItems
    instruction_policy = $InstructionPolicy
    tool_schema_policy = $ToolSchemaPolicy
    sandbox = $Sandbox
    fail_on_prompt_sandbox_mismatch = [bool]$FailOnPromptSandboxMismatch
    case_timeout_seconds = $CaseTimeoutSeconds
    model = $Model
    upstream_base_url = $UpstreamBaseUrl
    codex_cwd = $CodexCwd
    suite = $suitePath.Path
    runs = $Runs
    capture_dir = $captureDir
    cases = @()
}

$serverJob = Start-Job -Name "open-gate-codex-live-$Mode" -ScriptBlock {
    param($RootPath, $PortNumber, $Upstream, $ModelName, $CapturePath, $ProxyMode, $CtxPolicy, $CtxMaxChars, $CtxRecentItems, $InstrPolicy, $SchemaPolicy)
    Set-Location -LiteralPath $RootPath
    python -m open_gate `
        --host 127.0.0.1 `
        --port $PortNumber `
        --model $ModelName `
        --capture-dir $CapturePath `
        --upstream $Upstream `
        --normalization-mode $ProxyMode `
        --context-policy $CtxPolicy `
        --context-max-chars $CtxMaxChars `
        --context-recent-items $CtxRecentItems `
        --instruction-policy $InstrPolicy `
        --tool-schema-policy $SchemaPolicy `
        --quiet
} -ArgumentList $Root.Path, $Port, $UpstreamBaseUrl, $Model, $captureDir, $Mode, $ContextPolicy, $ContextMaxChars, $ContextRecentItems, $InstructionPolicy, $ToolSchemaPolicy

try {
    Start-Sleep -Milliseconds 900
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health"
    $manifest["health"] = $health

    for ($runIndex = 0; $runIndex -lt $Runs; $runIndex++) {
        foreach ($case in @($suiteJson.cases)) {
            $caseId = [string]$case.id
            $safeCaseId = $caseId -replace '[^A-Za-z0-9_.-]', '_'
            $outputFile = Join-Path $runDir ("codex-r{0:D2}-{1}.jsonl" -f $runIndex, $safeCaseId)
            $lastMessageFile = Join-Path $runDir ("last-r{0:D2}-{1}.txt" -f $runIndex, $safeCaseId)
            $prompt = [string]$case.prompt
            $caseCwd = $CodexCwd
            if ($case.PSObject.Properties.Name -contains "cwd" -and -not [string]::IsNullOrWhiteSpace([string]$case.cwd)) {
                $requestedCwd = [string]$case.cwd
                if ([System.IO.Path]::IsPathRooted($requestedCwd)) {
                    $caseCwd = $requestedCwd
                }
                else {
                    $caseCwd = Join-Path $CodexCwd $requestedCwd
                }
                New-Item -ItemType Directory -Force -Path $caseCwd | Out-Null
            }
            $started = Get-Date
            $promptSandbox = Get-CodexPromptSandbox -CaseCwd $caseCwd -SandboxMode $Sandbox

            if ($FailOnPromptSandboxMismatch -and -not [bool]$promptSandbox.matches) {
                $message = "Open Gate live harness skipped $caseId because Codex prompt-visible sandbox is '$($promptSandbox.visible)' while '$Sandbox' was requested."
                $message | Set-Content -LiteralPath $outputFile -Encoding UTF8
                $message | Set-Content -LiteralPath $lastMessageFile -Encoding UTF8
                $finished = Get-Date
                $manifest.cases += [ordered]@{
                    run_index = $runIndex
                    case_id = $caseId
                    category = $case.category
                    expected_tools = $case.expected_tools
                    expect_no_tool = [bool]$case.expect_no_tool
                    prompt = $prompt
                    cwd = $caseCwd
                    sandbox = $Sandbox
                    prompt_sandbox = $promptSandbox
                    timeout_seconds = $CaseTimeoutSeconds
                    timed_out = $false
                    skipped = $true
                    exit_code = 125
                    duration_seconds = [math]::Round(($finished - $started).TotalSeconds, 3)
                    output_file = $outputFile
                    last_message_file = $lastMessageFile
                }
                continue
            }

            $codexArgs = @(
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "--cd", $caseCwd,
                "--sandbox", $Sandbox,
                "--json",
                "--output-last-message", $lastMessageFile,
                "-m", $Model,
                "-c", "sandbox_mode=`"$Sandbox`"",
                "-c", 'model_providers.open_gate_qwen.name="Open Gate Qwen"',
                "-c", "model_providers.open_gate_qwen.base_url=`"http://127.0.0.1:$Port/v1`"",
                "-c", 'model_providers.open_gate_qwen.wire_api="responses"',
                "-c", 'model_provider="open_gate_qwen"',
                $prompt
            )

            $codexJob = Start-Job -Name "open-gate-codex-case-$safeCaseId" -ScriptBlock {
                param([string[]]$InnerArgs)
                try {
                    $output = & codex @InnerArgs 2>&1
                    $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
                    [pscustomobject]@{
                        ExitCode = $exitCode
                        Output = @($output | ForEach-Object { [string]$_ })
                    }
                }
                catch {
                    [pscustomobject]@{
                        ExitCode = 1
                        Output = @([string]$_)
                    }
                }
            } -ArgumentList (,$codexArgs)

            $timedOut = $false
            $completed = Wait-Job -Job $codexJob -Timeout $CaseTimeoutSeconds
            if ($null -eq $completed) {
                $timedOut = $true
                Stop-Job -Job $codexJob -ErrorAction SilentlyContinue
                $output = @("Open Gate live harness timed out after $CaseTimeoutSeconds seconds.")
                $exitCode = 124
            }
            else {
                $jobResult = Receive-Job -Job $codexJob -ErrorAction SilentlyContinue
                $exitCode = if ($null -ne $jobResult.ExitCode) { [int]$jobResult.ExitCode } else { 1 }
                $output = @($jobResult.Output | ForEach-Object { [string]$_ })
            }
            Remove-Job -Job $codexJob -Force -ErrorAction SilentlyContinue
            $output | Set-Content -LiteralPath $outputFile -Encoding UTF8
            $finished = Get-Date

            $manifest.cases += [ordered]@{
                run_index = $runIndex
                case_id = $caseId
                category = $case.category
                expected_tools = $case.expected_tools
                expect_no_tool = [bool]$case.expect_no_tool
                prompt = $prompt
                cwd = $caseCwd
                sandbox = $Sandbox
                prompt_sandbox = $promptSandbox
                timeout_seconds = $CaseTimeoutSeconds
                timed_out = $timedOut
                skipped = $false
                exit_code = $exitCode
                duration_seconds = [math]::Round(($finished - $started).TotalSeconds, 3)
                output_file = $outputFile
                last_message_file = $lastMessageFile
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

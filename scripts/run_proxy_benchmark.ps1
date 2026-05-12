param(
    [int]$Port = 8765,
    [string]$UpstreamBaseUrl = "http://127.0.0.1:8001/v1",
    [string]$Model = "Qwen3-Coder-Next",
    [string]$Suite = "fixtures\benchmarks\qwen_serious_tool_stress.json",
    [int]$Runs = 3,
    [string]$Label = "qwen_open_gate_serious_r3",
    [string]$Output = "runs\qwen_open_gate_serious_r3.json",
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
    [ValidateSet("auto", "off")]
    [string]$CapabilityProbe = "auto",
    [double]$CapabilityProbeTimeout = 8,
    [string]$CaptureDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

if (-not $CaptureDir) {
    $CaptureDir = Join-Path (Join-Path (Join-Path $Root.Path "runs") $Label) "captures"
}
elseif (-not [System.IO.Path]::IsPathRooted($CaptureDir)) {
    $CaptureDir = Join-Path $Root.Path $CaptureDir
}
$null = New-Item -ItemType Directory -Force -Path $CaptureDir

$existingListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existingListener) {
    $owners = ($existingListener | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    throw "Port $Port is already in use by PID(s) $owners. Stop the existing proxy or choose a different -Port; refusing to benchmark against a stale server."
}

$serverJob = Start-Job -Name "open-gate-proxy" -ScriptBlock {
    param($RootPath, $PortNumber, $Upstream, $ModelName, $ProxyMode, $CtxPolicy, $CtxMaxChars, $CtxRecentItems, $InstrPolicy, $SchemaPolicy, $CapabilityProbeMode, $CapabilityProbeSeconds, $CapturePath)
    Set-Location -LiteralPath $RootPath
    python -m open_gate.server `
        --host 127.0.0.1 `
        --port $PortNumber `
        --capture-dir $CapturePath `
        --model $ModelName `
        --upstream-base-url $Upstream `
        --normalization-mode $ProxyMode `
        --context-policy $CtxPolicy `
        --context-max-chars $CtxMaxChars `
        --context-recent-items $CtxRecentItems `
        --instruction-policy $InstrPolicy `
        --tool-schema-policy $SchemaPolicy `
        --capability-probe $CapabilityProbeMode `
        --capability-probe-timeout $CapabilityProbeSeconds `
        --quiet
} -ArgumentList $Root.Path, $Port, $UpstreamBaseUrl, $Model, $Mode, $ContextPolicy, $ContextMaxChars, $ContextRecentItems, $InstructionPolicy, $ToolSchemaPolicy, $CapabilityProbe, $CapabilityProbeTimeout, $CaptureDir

try {
    $health = $null
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 250
        if ($serverJob.State -ne "Running") {
            $jobOutput = Receive-Job -Job $serverJob -Keep -ErrorAction SilentlyContinue | Out-String
            throw "OpenGate proxy exited before it became healthy. Job state: $($serverJob.State). Output: $jobOutput"
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health"
            break
        }
        catch {
        }
    }
    if (-not $health) {
        throw "OpenGate proxy did not become healthy on port $Port within 90 seconds."
    }
    if ($health.service -ne "open-gate") {
        throw "Unexpected service on port ${Port}: $($health.service)"
    }
    if ($health.model -ne $Model) {
        throw "OpenGate health reported model '$($health.model)' but benchmark requested '$Model'."
    }
    if ($health.normalization_mode -ne $Mode) {
        throw "OpenGate health reported normalization '$($health.normalization_mode)' but benchmark requested '$Mode'."
    }
    if ($health.context_policy -ne $ContextPolicy) {
        throw "OpenGate health reported context policy '$($health.context_policy)' but benchmark requested '$ContextPolicy'."
    }
    if ($health.instruction_policy -ne $InstructionPolicy) {
        throw "OpenGate health reported instruction policy '$($health.instruction_policy)' but benchmark requested '$InstructionPolicy'."
    }
    if ($health.tool_schema_policy -ne $ToolSchemaPolicy) {
        throw "OpenGate health reported tool schema policy '$($health.tool_schema_policy)' but benchmark requested '$ToolSchemaPolicy'."
    }
    if ($health.capability_probe -ne $CapabilityProbe) {
        throw "OpenGate health reported capability probe '$($health.capability_probe)' but benchmark requested '$CapabilityProbe'."
    }

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
    if ($serverJob.State -eq "Running") {
        Stop-Job -Job $serverJob -ErrorAction SilentlyContinue
    }
    Receive-Job -Job $serverJob -ErrorAction SilentlyContinue | Out-Null
    Remove-Job -Job $serverJob -Force -ErrorAction SilentlyContinue
}

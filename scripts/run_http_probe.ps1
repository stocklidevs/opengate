param(
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$serverJob = Start-Job -Name "open-gate-capture" -ScriptBlock {
    param($RootPath, $PortNumber)
    Set-Location -LiteralPath $RootPath
    python -m open_gate.server --host 127.0.0.1 --port $PortNumber --quiet
} -ArgumentList $Root.Path, $Port

try {
    Start-Sleep -Milliseconds 800
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health"
    $models = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/models"
    $body = @{
        model = "open-gate-probe"
        input = "Say hello from the probe."
        stream = $false
    } | ConvertTo-Json -Depth 8
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/responses" -Method Post -ContentType "application/json" -Body $body

    [pscustomobject]@{
        health = $health.ok
        model = $models.data[0].id
        response_id = $response.id
        output_text = $response.output[0].content[0].text
    } | ConvertTo-Json -Depth 8
}
finally {
    Stop-Job -Job $serverJob -ErrorAction SilentlyContinue
    Remove-Job -Job $serverJob -Force -ErrorAction SilentlyContinue
}

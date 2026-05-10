param(
    [int]$Loops = 3,
    [int]$AdversarialIterations = 300,
    [int]$Seed = 6047
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $Root.Path

for ($i = 1; $i -le $Loops; $i++) {
    Write-Host "Open Gate validation loop $i/$Loops"
    python -m unittest discover -s tests
    python -m open_gate.adversarial --iterations $AdversarialIterations --seed ($Seed + $i) --quiet
}

Write-Host "Open Gate validation loop passed: $Loops loop(s), $AdversarialIterations adversarial iteration(s) per loop."

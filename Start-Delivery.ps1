param([switch]$VerifyOnly)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = @('.venv-validation\Scripts\python.exe', '.venv-training\Scripts\python.exe', '.venv-delivery\Scripts\python.exe') | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $pythonPath) {
    & py -3 -m venv .venv-delivery
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ is required. Install Python before retrying.' }
    $pythonPath = '.venv-delivery\Scripts\python.exe'
    & $pythonPath -m pip install -r requirements-validation.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; no startup success claimed.' }
}
if ($VerifyOnly) {
    & $pythonPath scripts/delivery.py verify --files
    if ($LASTEXITCODE -ne 0) { throw 'Delivery verification failed.' }
    exit 0
}
try {
    $live = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/health' -TimeoutSec 3
} catch { $live = $null }
if ($live) {
    if ($live.data.status -ne 'ready' -or $live.data.graphId -ne 'ai-literature-63686318d85cccb07afb') { throw 'Port 8765 is occupied by a different or unready graph.' }
    try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/delivery-demo' -TimeoutSec 3 -UseBasicParsing }
    catch { throw 'V1 search is healthy but running the old entry. Close its terminal and restart with Start-Delivery.cmd for the delivery evidence pages.' }
    Write-Host 'Frozen V1 already running: http://127.0.0.1:8765/'
    exit 0
}
if (-not (Get-NetTCPConnection -LocalPort 7474 -State Listen -ErrorAction SilentlyContinue)) {
    throw 'Start the AI-Literature-KG instance in Neo4j Desktop first (HTTP 7474). License acceptance, if requested, must be performed by the user.'
}
Write-Host 'Starting frozen V1. Enter the Neo4j password when prompted; it is not saved. Keep this window open.'
& $pythonPath scripts/delivery.py serve --port 8765
if ($LASTEXITCODE -ne 0) { throw 'V1 startup failed. Check Neo4j, password and pinned files; no offline success fallback.' }

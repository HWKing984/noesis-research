param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$captureFolder = (Resolve-Path -LiteralPath $OutputDirectory).Path
$edgeBrowser = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path -LiteralPath $edgeBrowser)) { throw 'Edge unavailable' }
$captureRecord = Join-Path $captureFolder 'captures.json'
if (Test-Path -LiteralPath $captureRecord) { throw 'Preserve previous captures' }
$captureProfile = Join-Path ([IO.Path]::GetTempPath()) ('course-app-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $captureProfile | Out-Null
$captureState = @{status='running';url='http://127.0.0.1:8765/';kind='actual_live_application_screenshot';renderer='installed_Edge_headless';captures=@();passwordRecorded=$false}
try {
    foreach ($captureWidth in @(1440,768,375)) {
        $captureTarget = Join-Path $captureFolder "app_$captureWidth.png"
        if (Test-Path -LiteralPath $captureTarget) { throw 'Refuse screenshot overwrite' }
        $captureArgs = @('--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--force-device-scale-factor=1','--hide-scrollbars',"--user-data-dir=$captureProfile","--window-size=$captureWidth,1700",'--virtual-time-budget=3000',"--screenshot=$captureTarget",$captureState.url)
        $captureProcess = Start-Process -FilePath $edgeBrowser -ArgumentList $captureArgs -WindowStyle Hidden -PassThru
        if (-not $captureProcess.WaitForExit(30000) -or $captureProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $captureTarget)) { throw 'Actual browser capture failed' }
        $captureBytes = [IO.File]::ReadAllBytes($captureTarget)
        if ($captureBytes.Length -lt 24 -or [BitConverter]::ToString($captureBytes[0..7]).Replace('-','') -ne '89504E470D0A1A0A') { throw 'Invalid PNG' }
        $captureState.captures += @{file="app_$captureWidth.png";sha256=(Get-FileHash -LiteralPath $captureTarget -Algorithm SHA256).Hash.ToLowerInvariant();requestedWindowWidth=$captureWidth;bytes=$captureBytes.Length;capturedAtUTC=(Get-Date).ToUniversalTime().ToString('o')}
    }
    $captureState.status='completed'
} catch { $captureState.status='failed';$captureState.error=$_.Exception.Message;throw }
finally { $captureState | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $captureRecord -Encoding utf8 }

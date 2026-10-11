param([Parameter(Mandatory=$true)][string]$EvidenceDirectory)
$ErrorActionPreference = 'Stop'
$folder = (Resolve-Path -LiteralPath $EvidenceDirectory).Path
$browser = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path -LiteralPath $browser)) { throw 'Installed Edge unavailable; no invented screenshots.' }
$manifest = Get-Content -LiteralPath (Join-Path $folder 'manifest.json') -Raw | ConvertFrom-Json
if ($manifest.kind -ne 'real_artifact_visualization_not_original_console_ui') { throw 'Unexpected evidence bundle.' }
foreach ($item in $manifest.filesSha256.PSObject.Properties) {
    $relative = $item.Name
    $resolved = [IO.Path]::GetFullPath((Join-Path $folder $relative))
    if (-not $resolved.StartsWith($folder + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe evidence manifest path.' }
    if ((Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value) { throw "Evidence changed: $relative" }
}
$captureManifest = Join-Path $folder 'captures.json'
if (Test-Path -LiteralPath $captureManifest) { throw 'Preserve existing capture records; choose a new evidence bundle.' }
$profile = Join-Path ([IO.Path]::GetTempPath()) ('AI-Literature-KG-capture-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $profile | Out-Null
$captures = @()
$state = @{status='running'; kind='actual_browser_render_capture'; renderer='installed_Microsoft_Edge_headless'; generatedFromRealArtifacts=$true; originalConsoleScreenshot=$false; browserVersion=(Get-Item -LiteralPath $browser).VersionInfo.FileVersion; viewportWidth=1280; captures=@(); temporaryProfile=$profile}
try {
    $pages = @(@{name='01_data';height=1100}, @{name='02_training';height=1450}, @{name='03_predictions';height=1300}, @{name='04_traceability';height=1800})
    if ($manifest.filesSha256.PSObject.Properties.Name -contains '05_development.html') { $pages += @{name='05_development';height=2300} }
    $pages += @{name='06_final_test';height=1900}
    $pages += @{name='07_relation_development';height=2600}
    $pages += @{name='08_relation_test';height=2300}
    $pages += @{name='09_annotation_expansion';height=2300}
    $pages = @($pages | Where-Object { $manifest.filesSha256.PSObject.Properties.Name -contains ($_.name + '.html') })
    if ($pages.Count -eq 0) { throw 'No supported evidence page; do not record empty success.' }
    foreach ($entry in $pages) {
        $source = Join-Path $folder ($entry.name + '.html')
        $target = Join-Path $folder ($entry.name + '.png')
        if (Test-Path -LiteralPath $target) { throw "Refuse to overwrite screenshot: $target" }
        $url = ([uri]$source).AbsoluteUri
        $arguments = @('--headless=new','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check','--hide-scrollbars','--force-device-scale-factor=1',"--window-size=1280,$($entry.height)","--screenshot=$target","--user-data-dir=$profile",$url)
        $process = Start-Process -FilePath $browser -ArgumentList $arguments -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit(30000)) { throw 'Browser capture timed out; inspect the isolated profile, no success recorded.' }
        if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $target)) { throw "Browser did not produce $($entry.name).png" }
        $bytes = [IO.File]::ReadAllBytes($target)
        if ($bytes.Length -lt 24 -or [Convert]::ToHexString($bytes[0..7]) -ne '89504E470D0A1A0A') { throw 'Invalid PNG output.' }
        $captures += @{image=($entry.name+'.png');sourcePage=($entry.name+'.html');sourcePageSha256=$manifest.filesSha256.($entry.name+'.html');sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant();bytes=$bytes.Length;capturedAt=(Get-Date).ToUniversalTime().ToString('o');viewportHeight=$entry.height;url=$url;commandArguments=$arguments;originalConsoleScreenshot=$false}
        $state.captures=$captures
        Write-Output "Captured $($entry.name).png ($($bytes.Length) bytes)."
    }
    $state.status='completed'
} catch {
    $state.status='failed'
    $state.error=$_.Exception.Message
    throw
} finally {
    $state.finishedAt=(Get-Date).ToUniversalTime().ToString('o')
    $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $captureManifest -Encoding utf8
}

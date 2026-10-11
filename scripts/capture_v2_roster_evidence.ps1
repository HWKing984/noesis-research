param([Parameter(Mandatory=$true)][string]$EvidenceDirectory)
$ErrorActionPreference = 'Stop'
$folder = (Resolve-Path -LiteralPath $EvidenceDirectory).Path
$browser = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path -LiteralPath $browser)) { throw 'Installed Edge unavailable; no invented screenshots.' }
$manifest = Get-Content -LiteralPath (Join-Path $folder 'manifest.json') -Raw | ConvertFrom-Json
if ($manifest.kind -ne 'verified_artifact_evidence_page_not_original_application_ui') { throw 'Unexpected evidence bundle.' }
foreach ($item in $manifest.filesSha256.PSObject.Properties) {
    $resolved = [IO.Path]::GetFullPath((Join-Path $folder $item.Name))
    if (-not $resolved.StartsWith($folder + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe evidence manifest path.' }
    if ((Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value) { throw 'Evidence changed.' }
}
$source = Join-Path $folder '10_roster_and_dev.html'
$target = Join-Path $folder '10_roster_and_dev.png'
$captureManifest = Join-Path $folder 'captures.json'
if ((Test-Path -LiteralPath $target) -or (Test-Path -LiteralPath $captureManifest)) { throw 'Preserve previous capture.' }
$profile = Join-Path ([IO.Path]::GetTempPath()) ('AI-Literature-KG-roster-capture-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $profile | Out-Null
$state = @{status='running';kind='actual_browser_render_capture';renderer='installed_Microsoft_Edge_headless';originalConsoleScreenshot=$false;browserVersion=(Get-Item -LiteralPath $browser).VersionInfo.FileVersion;temporaryProfile=$profile}
try {
    $url = ([uri]$source).AbsoluteUri
    $arguments = @('--headless=new','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check','--hide-scrollbars','--force-device-scale-factor=1','--window-size=1280,2000',"--screenshot=$target","--user-data-dir=$profile",$url)
    $process = Start-Process -FilePath $browser -ArgumentList $arguments -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(30000)) { throw 'Browser capture timed out.' }
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $target)) { throw 'Browser did not produce capture.' }
    $bytes = [IO.File]::ReadAllBytes($target)
    if ($bytes.Length -lt 24 -or [Convert]::ToHexString($bytes[0..7]) -ne '89504E470D0A1A0A') { throw 'Invalid PNG output.' }
    $state.captures=@(@{image='10_roster_and_dev.png';sourcePage='10_roster_and_dev.html';sourcePageSha256=$manifest.filesSha256.('10_roster_and_dev.html');sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant();bytes=$bytes.Length;capturedAt=(Get-Date).ToUniversalTime().ToString('o');viewportWidth=1280;viewportHeight=2000;url=$url;commandArguments=$arguments;originalConsoleScreenshot=$false})
    $state.status='completed'
    Write-Output "Captured real browser evidence ($($bytes.Length) bytes)."
} catch {
    $state.status='failed';$state.error=$_.Exception.Message;throw
} finally {
    $state.finishedAt=(Get-Date).ToUniversalTime().ToString('o')
    $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $captureManifest -Encoding utf8
}

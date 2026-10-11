$ErrorActionPreference = 'Stop'
$courseRoot = 'D:\a-open_source\neo4j'
$evidencePath = Join-Path $courseRoot 'docs\evidence\20261007_round29'
$edgePath = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$targetURL = 'http://127.0.0.1:8766/#paper=conf%2F3dim%2FVavilalaVF25&view=paper'
if (-not (Test-Path -LiteralPath $edgePath)) { throw 'Actual browser unavailable' }
New-Item -ItemType Directory -Path $evidencePath -Force | Out-Null
$screens = @(@{ Width=1440;Height=1100;Name='01_graph_desktop' },@{ Width=768;Height=1100;Name='02_graph_tablet' },@{ Width=375;Height=1100;Name='03_graph_mobile' })
foreach ($screen in $screens) {
    $targetPath = Join-Path $evidencePath ($screen.Name + '.png')
    if (Test-Path -LiteralPath $targetPath) { throw 'Preserve native screenshot' }
    $profilePath = Join-Path ([IO.Path]::GetTempPath()) ('course-system29-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $profilePath | Out-Null
    $argsList = @('--headless=new','--disable-gpu','--hide-scrollbars','--no-first-run','--virtual-time-budget=5000',
        "--user-data-dir=$profilePath","--window-size=$($screen.Width),$($screen.Height)","--screenshot=$targetPath",$targetURL)
    $process = Start-Process -FilePath $edgePath -ArgumentList $argsList -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(25000)) { throw 'Actual capture timed out; no success claimed' }
    if (-not (Test-Path -LiteralPath $targetPath) -or (Get-Item -LiteralPath $targetPath).Length -lt 1000) { throw 'Missing or empty native capture' }
    [pscustomobject]@{ Screenshot=$targetPath;Width=$screen.Width;Height=$screen.Height;LiveURL=$targetURL }
}

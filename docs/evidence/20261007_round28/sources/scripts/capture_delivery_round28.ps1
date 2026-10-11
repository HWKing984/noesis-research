$ErrorActionPreference = 'Stop'
$courseRoot = 'D:\a-open_source\neo4j'
$evidencePath = Join-Path $courseRoot 'docs\evidence\20261007_round28'
$edgePath = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path -LiteralPath $edgePath)) { throw 'No actual browser renderer available' }
$captures = @(
    @{ Source='docs/evidence/20261007_round28/01_expanded_training.html'; Name='01_expanded_training'; Height=3000 },
    @{ Source='docs/course_complete_report_20261007.html'; Name='02_report_preview'; Height=1500 }
)
foreach ($capture in $captures) {
    $sourcePath = (Resolve-Path -LiteralPath (Join-Path $courseRoot $capture.Source)).Path
    $targetPath = Join-Path $evidencePath ($capture.Name + '.png')
    if (Test-Path -LiteralPath $targetPath) { throw 'Preserve existing native screenshot' }
    $profilePath = Join-Path ([IO.Path]::GetTempPath()) ('course-delivery28-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $profilePath | Out-Null
    $argsList = @('--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
        "--user-data-dir=$profilePath", "--window-size=1280,$($capture.Height)",
        "--screenshot=$targetPath", ([uri]$sourcePath).AbsoluteUri)
    $process = Start-Process -FilePath $edgePath -ArgumentList $argsList -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(25000)) { throw 'Capture timed out; no success claimed' }
    if (-not (Test-Path -LiteralPath $targetPath) -or (Get-Item -LiteralPath $targetPath).Length -lt 1000) { throw 'Screenshot missing or empty' }
    [pscustomobject]@{ Screenshot=$targetPath; Source=$sourcePath; Bytes=(Get-Item -LiteralPath $targetPath).Length; OriginalTrainingConsole=$false }
}

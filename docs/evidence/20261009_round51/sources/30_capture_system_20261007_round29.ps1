param(
    [string]$EvidencePath = 'D:\a-open_source\neo4j\docs\evidence\20261007_round29',
    [string]$TargetURL = 'http://127.0.0.1:8765/#paper=conf%2F3dim%2FVavilalaVF25&view=paper',
    [string]$Suffix = 'live',
    [switch]$Workflow
)
$ErrorActionPreference = 'Stop'
$edgePath = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path -LiteralPath $edgePath)) { throw 'Actual browser unavailable' }
New-Item -ItemType Directory -Path $evidencePath -Force | Out-Null
$profilePath = Join-Path ([IO.Path]::GetTempPath()) ('course-system29-cdp-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $profilePath | Out-Null
$process = Start-Process -FilePath $edgePath -ArgumentList @('--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=9229',"--user-data-dir=$profilePath",'about:blank') -WindowStyle Hidden -PassThru
$socket = [Net.WebSockets.ClientWebSocket]::new()
$script:commandId = 0
function Send-CDP($method, $parameters) {
    $script:commandId++
    $message = @{ id=$script:commandId; method=$method; params=$parameters } | ConvertTo-Json -Depth 10 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($message)
    $socket.SendAsync([ArraySegment[byte]]::new($bytes),[Net.WebSockets.WebSocketMessageType]::Text,$true,[Threading.CancellationToken]::None).GetAwaiter().GetResult()
    do {
        $stream = [IO.MemoryStream]::new()
        do {
            $buffer = [byte[]]::new(65536)
            $task = $socket.ReceiveAsync([ArraySegment[byte]]::new($buffer),[Threading.CancellationToken]::None)
            if (-not $task.Wait(20000)) { throw 'CDP response timed out' }
            $response = $task.Result
            $stream.Write($buffer,0,$response.Count)
        } until ($response.EndOfMessage)
        $reply = [Text.Encoding]::UTF8.GetString($stream.ToArray()) | ConvertFrom-Json
        $stream.Dispose()
    } until ($reply.id -eq $script:commandId)
    if ($reply.error) { throw ($reply.error | ConvertTo-Json -Compress) }
    return $reply.result
}
try {
    $pages = $null
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        try { $pages = Invoke-RestMethod 'http://127.0.0.1:9229/json/list'; break } catch { Start-Sleep -Milliseconds 200 }
    }
    if (-not $pages) { throw 'Actual browser debugging endpoint unavailable' }
    $socket.ConnectAsync([Uri]($pages | Where-Object type -eq 'page' | Select-Object -First 1).webSocketDebuggerUrl,[Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null
    Send-CDP 'Page.enable' @{} | Out-Null
    $records = @()
    foreach ($screen in @(@{Width=1440;Name='04_graph_desktop'},@{Width=768;Name='05_graph_tablet'},@{Width=375;Name='06_graph_mobile'})) {
        $targetPath = Join-Path $evidencePath ($screen.Name+'_'+$Suffix+'.png')
        if (Test-Path -LiteralPath $targetPath) { throw 'Preserve existing screenshot' }
        Send-CDP 'Emulation.setDeviceMetricsOverride' @{width=$screen.Width;height=1100;deviceScaleFactor=1;mobile=$false} | Out-Null
        Send-CDP 'Page.navigate' @{url=$targetURL} | Out-Null
        $ready = $false
        for ($attempt=0; $attempt -lt 40; $attempt++) {
            $state = Send-CDP 'Runtime.evaluate' @{expression="Boolean(document.querySelector('#graph-view svg') && document.getElementById('graph-status').textContent.includes('10节点'))";returnByValue=$true}
            if ($state.result.value) { $ready=$true; break }
            Start-Sleep -Milliseconds 200
        }
        if (-not $ready) { throw 'Real graph did not load; no successful screenshot claimed' }
        if ($Workflow -and $screen.Width -eq 1440) {
            Send-CDP 'Runtime.evaluate' @{expression="document.querySelectorAll('*').forEach(e=>e.style.scrollBehavior='auto');document.getElementById('detail-body').scrollIntoView({block:'start',behavior:'instant'})"} | Out-Null
            $identityCapture = Send-CDP 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$false}
            $identityPath = Join-Path $evidencePath '08_author_identity.png'
            if (Test-Path -LiteralPath $identityPath) { throw 'Preserve existing identity screenshot' }
            [IO.File]::WriteAllBytes($identityPath,[Convert]::FromBase64String($identityCapture.data))
            $downloadPath = Join-Path $evidencePath 'downloads'
            if (Test-Path -LiteralPath $downloadPath) { throw 'Preserve existing downloads' }
            New-Item -ItemType Directory -Path $downloadPath | Out-Null
            Send-CDP 'Browser.setDownloadBehavior' @{behavior='allow';downloadPath=$downloadPath;eventsEnabled=$true} | Out-Null
            Send-CDP 'Runtime.evaluate' @{expression="[...document.querySelectorAll('#detail-body button')].find(b=>b.textContent==='加入候选文献清单').click();document.getElementById('selection-json').click();document.getElementById('selection-text').click()"} | Out-Null
            for ($attempt=0; $attempt -lt 40; $attempt++) {
                if ((Test-Path -LiteralPath (Join-Path $downloadPath 'ai-literature-candidates.json')) -and (Test-Path -LiteralPath (Join-Path $downloadPath 'ai-literature-reference-drafts.txt'))) { break }
                Start-Sleep -Milliseconds 200
            }
            $saved = Get-Content -LiteralPath (Join-Path $downloadPath 'ai-literature-candidates.json') -Raw | ConvertFrom-Json
            $draft = Get-Content -LiteralPath (Join-Path $downloadPath 'ai-literature-reference-drafts.txt') -Raw
            if ($saved.items.Count -ne 1 -or $saved.items[0].data.publication.publicationId -ne 'conf/3dim/VavilalaVF25' -or $saved.items[0].data.assertions.Count -ne 1 -or $draft -notmatch 'Denoising Monte Carlo Renders') { throw 'Downloaded exports do not match actual detail' }
            Send-CDP 'Runtime.evaluate' @{expression="document.querySelectorAll('*').forEach(e=>e.style.scrollBehavior='auto');document.getElementById('selection-title').scrollIntoView({block:'start',behavior:'instant'})"} | Out-Null
            $capture = Send-CDP 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$false}
            [IO.File]::WriteAllBytes((Join-Path $evidencePath '07_selection_downloads.png'),[Convert]::FromBase64String($capture.data))
            $records += [pscustomobject]@{Workflow='actual_live_detail_add_and_native_button_download';JSONItems=$saved.items.Count;Assertions=$saved.items[0].data.assertions.Count;Source=$saved.items[0].source;Screenshot='07_selection_downloads.png'}
        }
        Send-CDP 'Runtime.evaluate' @{expression="document.documentElement.style.scrollBehavior='auto';document.querySelectorAll('*').forEach(e=>e.style.scrollBehavior='auto');document.getElementById('graph-panel').scrollIntoView({block:'start',behavior:'instant'})"} | Out-Null
        Start-Sleep -Milliseconds 300
        $metrics = Send-CDP 'Runtime.evaluate' @{expression="JSON.stringify({width:innerWidth,height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth,status:document.getElementById('graph-status').textContent})";returnByValue=$true}
        $capture = Send-CDP 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$false}
        [IO.File]::WriteAllBytes($targetPath,[Convert]::FromBase64String($capture.data))
        $records += [pscustomobject]@{Screenshot=$targetPath;LiveURL=$targetURL;Observed=($metrics.result.value|ConvertFrom-Json)}
    }
    if ($Workflow) {
        $receiptPath = Join-Path $evidencePath 'capture_receipt.json'
        if (Test-Path -LiteralPath $receiptPath) { throw 'Preserve existing capture receipt' }
        [IO.File]::WriteAllText($receiptPath,($records | ConvertTo-Json -Depth 5))
    }
    $records | ConvertTo-Json -Depth 5
} finally {
    try { Send-CDP 'Browser.close' @{} | Out-Null } catch {}
    $socket.Dispose()
}

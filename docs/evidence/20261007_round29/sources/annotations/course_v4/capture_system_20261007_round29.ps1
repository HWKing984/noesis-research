$ErrorActionPreference = 'Stop'
$evidencePath = 'D:\a-open_source\neo4j\docs\evidence\20261007_round29'
$edgePath = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$targetURL = 'http://127.0.0.1:8765/#paper=conf%2F3dim%2FVavilalaVF25&view=paper'
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
    $socket.ConnectAsync([Uri]($pages | Where-Object type -eq 'page' | Select-Object -First 1).webSocketDebuggerUrl,[Threading.CancellationToken]::None).GetAwaiter().GetResult()
    Send-CDP 'Page.enable' @{} | Out-Null
    $records = @()
    foreach ($screen in @(@{Width=1440;Name='04_graph_desktop_live'},@{Width=768;Name='05_graph_tablet_live'},@{Width=375;Name='06_graph_mobile_live'})) {
        $targetPath = Join-Path $evidencePath ($screen.Name+'.png')
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
        Send-CDP 'Runtime.evaluate' @{expression="document.documentElement.style.scrollBehavior='auto';document.querySelectorAll('*').forEach(e=>e.style.scrollBehavior='auto');document.getElementById('graph-panel').scrollIntoView({block:'start',behavior:'instant'})"} | Out-Null
        Start-Sleep -Milliseconds 300
        $metrics = Send-CDP 'Runtime.evaluate' @{expression="JSON.stringify({width:innerWidth,height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth,status:document.getElementById('graph-status').textContent})";returnByValue=$true}
        $capture = Send-CDP 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$false}
        [IO.File]::WriteAllBytes($targetPath,[Convert]::FromBase64String($capture.data))
        $records += [pscustomobject]@{Screenshot=$targetPath;LiveURL=$targetURL;Observed=($metrics.result.value|ConvertFrom-Json)}
    }
    $records | ConvertTo-Json -Depth 5
} finally {
    try { Send-CDP 'Browser.close' @{} | Out-Null } catch {}
    $socket.Dispose()
}

# Exact CDP viewports: --window-size alone may crop Edge's minimum-width window.
$ErrorActionPreference='Stop'
$folder='D:\a-open_source\neo4j\docs\evidence\20261009_search_repair_cdp'
if(Test-Path -LiteralPath $folder){throw 'Preserve previous captures'}
New-Item -ItemType Directory -Path $folder | Out-Null
$profile=Join-Path ([IO.Path]::GetTempPath()) ('search-qa-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $profile | Out-Null
if(Get-NetTCPConnection -LocalPort 9231 -State Listen -ErrorAction SilentlyContinue){throw 'QA browser port in use'}
$browser=Start-Process -FilePath 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' -ArgumentList @('--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=9231',"--user-data-dir=$profile",'about:blank') -WindowStyle Hidden -PassThru
$socket=[Net.WebSockets.ClientWebSocket]::new(); $script:sequence=0
$state=@{status='running';captures=@();exceptions=@();networkErrors=@();baselineComparison='INCONCLUSIVE_no_baseline';WCAG='not_fully_audited';INP='not_measured'}
function Send-CDP($method,$parameters){
    $script:sequence++; $bytes=[Text.Encoding]::UTF8.GetBytes((@{id=$script:sequence;method=$method;params=$parameters}|ConvertTo-Json -Depth 12 -Compress))
    $socket.SendAsync([ArraySegment[byte]]::new($bytes),[Net.WebSockets.WebSocketMessageType]::Text,$true,[Threading.CancellationToken]::None).GetAwaiter().GetResult()
    do{
        $stream=[IO.MemoryStream]::new()
        do{
            $buffer=[byte[]]::new(65536);$task=$socket.ReceiveAsync([ArraySegment[byte]]::new($buffer),[Threading.CancellationToken]::None)
            if(-not $task.Wait(15000)){throw 'CDP timeout'}
            $response=$task.Result;$stream.Write($buffer,0,$response.Count)
        }until($response.EndOfMessage)
        $reply=[Text.Encoding]::UTF8.GetString($stream.ToArray())|ConvertFrom-Json;$stream.Dispose()
        if($reply.method -eq 'Runtime.exceptionThrown'){$state.exceptions+= $reply.params}
        if($reply.method -eq 'Network.responseReceived' -and $reply.params.response.status -ge 400){$state.networkErrors+= $reply.params.response.url}
    }until($reply.id -eq $script:sequence)
    if($reply.error){throw ($reply.error|ConvertTo-Json -Compress)}
    return $reply.result
}
try{
    $pages=$null
    for($i=0;$i -lt 30;$i++){try{$pages=Invoke-RestMethod http://127.0.0.1:9231/json/list;break}catch{Start-Sleep -Milliseconds 200}}
    if(-not $pages){throw 'QA browser unavailable'}
    $socket.ConnectAsync([Uri]($pages|Where-Object type -eq 'page'|Select-Object -First 1).webSocketDebuggerUrl,[Threading.CancellationToken]::None).GetAwaiter().GetResult()|Out-Null
    Send-CDP 'Page.enable' @{}|Out-Null;Send-CDP 'Runtime.enable' @{}|Out-Null;Send-CDP 'Network.enable' @{}|Out-Null
    foreach($width in 1440,768,375){
        Send-CDP 'Emulation.setDeviceMetricsOverride' @{width=$width;height=1100;deviceScaleFactor=1;mobile=$false}|Out-Null
        Send-CDP 'Page.navigate' @{url='http://127.0.0.1:8765/'}|Out-Null
        $ready=$false
        for($i=0;$i -lt 100;$i++){
            $r=Send-CDP 'Runtime.evaluate' @{expression="Boolean(document.getElementById('status')?.textContent.includes('已就绪'))";returnByValue=$true}
            if($r.result.value){$ready=$true;break};Start-Sleep -Milliseconds 100
        }
        if(-not $ready){throw 'Live health not ready'}
        Send-CDP 'Runtime.evaluate' @{expression="const f=document.getElementById('search');f.elements.method.value='neural reranking';f.elements.task.value='subjective quality of machine translation';f.elements.dataset.value='naist';f.requestSubmit();"}|Out-Null
        $ready=$false
        for($i=0;$i -lt 150;$i++){
            $r=Send-CDP 'Runtime.evaluate' @{expression="Boolean(!document.getElementById('submit').disabled && document.querySelector('#results h3')?.textContent.includes('Neural Reranking'))";returnByValue=$true}
            if($r.result.value){$ready=$true;break};Start-Sleep -Milliseconds 100
        }
        if(-not $ready){throw 'Live joint search did not complete'}
        $metrics=Send-CDP 'Runtime.evaluate' @{expression="JSON.stringify({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,overflow:document.documentElement.scrollWidth>innerWidth,error:document.getElementById('error').textContent,results:[...document.querySelectorAll('#results h3')].map(e=>e.textContent),labels:[...document.querySelectorAll('input,select')].every(e=>e.labels.length>0)})";returnByValue=$true}
        $observed=$metrics.result.value|ConvertFrom-Json
        if($observed.width -ne $width -or $observed.overflow -or $observed.error -or -not $observed.labels){throw ('Viewport check failed: '+$metrics.result.value)}
        $layout=Send-CDP 'Page.getLayoutMetrics' @{};$size=$layout.cssContentSize
        $shot=Send-CDP 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$true;clip=@{x=0;y=0;width=$size.width;height=$size.height;scale=1}}
        $path=Join-Path $folder "search_$width.png";[IO.File]::WriteAllBytes($path,[Convert]::FromBase64String($shot.data))
        if((Get-Item -LiteralPath $path).Length -lt 1000){throw 'Empty screenshot'}
        $state.captures+=@{file=$path;observed=$observed;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    if($state.exceptions.Count -or $state.networkErrors.Count){throw 'Browser errors occurred'}
    $state.status='passed'
}catch{$state.status='failed';$state.error=$_.Exception.Message;throw}
finally{
    [IO.File]::WriteAllText((Join-Path $folder 'captures.json'),($state|ConvertTo-Json -Depth 10))
    try{Send-CDP 'Browser.close' @{}|Out-Null}catch{};$socket.Dispose()
}
$state|ConvertTo-Json -Depth 8

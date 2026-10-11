# Reuse the pinned CDP helper; keep all historical captures immutable.
$ErrorActionPreference='Stop'
$sourcePath=Join-Path $PSScriptRoot 'capture_search_repair_20261009.ps1'
if((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'df4320949071270c807a11c908c31f1a3dcdf9af7345adf726c1d4902cbb4564'){throw 'Historical capture helper drift'}
$health=Invoke-RestMethod http://127.0.0.1:8765/api/health
if($health.data.status -ne 'ready' -or $health.data.graphId -ne 'ai-literature-63686318d85cccb07afb'){throw 'Wrong live graph'}
$folder='D:\a-open_source\neo4j\docs\evidence\20261010_v1_demo_workflow_ready'
$extra=@'
    $state.liveGraphId='ai-literature-63686318d85cccb07afb'
    $state.capturedAtUTC=(Get-Date).ToUniversalTime().ToString('o')
    function Wait-DOM($condition){
        for($attempt=0;$attempt -lt 150;$attempt++){
            $result=Send-CDP 'Runtime.evaluate' @{expression=$condition;returnByValue=$true}
            if($result.result.value){return};Start-Sleep -Milliseconds 100
        }
        throw ('DOM did not become ready: '+$condition)
    }
    function Save-View($name,$element){
        $layout=Send-CDP 'Runtime.evaluate' @{expression="JSON.stringify(document.querySelector('$element').getBoundingClientRect().toJSON())";returnByValue=$true}
        $rect=$layout.result.value|ConvertFrom-Json
        $scroll=Send-CDP 'Runtime.evaluate' @{expression='scrollY';returnByValue=$true}
        $shot=Send-CDP 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$true;clip=@{x=$rect.x;y=($rect.y+$scroll.result.value);width=$rect.width;height=$rect.height;scale=1}}
        $path=Join-Path $folder $name;[IO.File]::WriteAllBytes($path,[Convert]::FromBase64String($shot.data))
        if((Get-Item -LiteralPath $path).Length -lt 1000){throw 'Empty workflow capture'}
        $state.captures+=@{file=$path;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    Send-CDP 'Emulation.setDeviceMetricsOverride' @{width=1440;height=1100;deviceScaleFactor=1;mobile=$false}|Out-Null
    Send-CDP 'Runtime.evaluate' @{expression="document.querySelector('#results button').click()"}|Out-Null
    Wait-DOM "!document.getElementById('detail').hidden && document.querySelector('#detail-body h3')?.textContent.includes('Integrating Attention Mechanisms')"
    Save-View '04_detail.png' '#detail'
    Send-CDP 'Runtime.evaluate' @{expression="[...document.querySelectorAll('#detail-body button')].find(b=>b.textContent==='加入候选文献清单').click()"}|Out-Null
    foreach($mode in 'paper','coauthors','methods'){
        Send-CDP 'Runtime.evaluate' @{expression="document.getElementById('graph-$mode').click()"}|Out-Null
        Wait-DOM "Boolean(document.querySelector('#graph-view svg') && /^\d+节点/.test(document.getElementById('graph-status').textContent))"
        $metrics=Send-CDP 'Runtime.evaluate' @{expression="JSON.stringify({mode:'$mode',status:document.getElementById('graph-status').textContent,nodes:document.querySelectorAll('#graph-view svg circle').length,fragment:location.hash})";returnByValue=$true}
        $observed=$metrics.result.value|ConvertFrom-Json
        if($observed.nodes -lt 1){throw 'Empty graph'}
        $state.graphViews+=@($observed)
        Save-View "05_graph_$mode.png" '#graph-panel'
    }
    Send-CDP 'Browser.setDownloadBehavior' @{behavior='allow';downloadPath=$folder}|Out-Null
    foreach($kind in 'json','text'){
        Send-CDP 'Runtime.evaluate' @{expression="document.getElementById('selection-$kind').click()"}|Out-Null
    }
    $jsonPath=Join-Path $folder 'ai-literature-candidates.json'
    $textPath=Join-Path $folder 'ai-literature-reference-drafts.txt'
    for($attempt=0;$attempt -lt 100;$attempt++){
        if((Test-Path -LiteralPath $jsonPath) -and (Test-Path -LiteralPath $textPath)){break};Start-Sleep -Milliseconds 100
    }
    $export=Get-Content -LiteralPath $jsonPath -Raw|ConvertFrom-Json
    $text=Get-Content -LiteralPath $textPath -Raw
    if($export.items.Count -ne 1 -or $export.items[0].data.publication.publicationId -ne 'conf/seeda/VonitsanosESKM25' -or $export.items[0].graphId -ne $state.liveGraphId -or $export.items[0].data.assertions.Count -ne 2 -or -not $text.Contains('Integrating Attention Mechanisms')){throw 'Downloaded evidence mismatch'}
    $state.downloads=@($jsonPath,$textPath)|ForEach-Object {@{file=$_;bytes=(Get-Item -LiteralPath $_).Length;sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()}}
    Save-View '06_selection.png' '[aria-labelledby="selection-title"]'
'@
$source=Get-Content -LiteralPath $sourcePath -Raw
$changes=@(
 @('D:\a-open_source\neo4j\docs\evidence\20261009_search_repair_cdp',$folder),
 @("f.elements.method.value='neural reranking';f.elements.task.value='subjective quality of machine translation';f.elements.dataset.value='naist';","f.elements.q.value='Integrating Attention Mechanisms into Convolutional Neural Networks for Image Classification';f.elements.method.value='卷积神经网络';"),
 @(".includes('Neural Reranking')",".includes('Integrating Attention Mechanisms')"),
 @('    if($state.exceptions.Count -or $state.networkErrors.Count)',($extra+"`n    if(`$state.exceptions.Count -or `$state.networkErrors.Count)"))
)
foreach($change in $changes){
 if($source.Split(@($change[0]),[StringSplitOptions]::None).Length -ne 2){throw 'Capture replacement must match exactly once'}
 $source=$source.Replace($change[0],$change[1])
}
& ([ScriptBlock]::Create($source))

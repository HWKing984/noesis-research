# Reuse the verified CDP capture without altering its historical source or images.
$ErrorActionPreference='Stop'
$sourcePath=Join-Path $PSScriptRoot 'capture_search_repair_20261009.ps1'
$sourceSha='df4320949071270c807a11c908c31f1a3dcdf9af7345adf726c1d4902cbb4564'
if((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceSha){throw 'Historical capture helper drift'}
$health=Invoke-RestMethod http://127.0.0.1:8765/api/health
if($health.data.graphId -ne 'ai-literature-63686318d85cccb07afb' -or $health.data.conceptVocabulary.version -ne 'typed_controlled_aliases_v3'){throw 'Wrong live graph or vocabulary'}
$folder='D:\a-open_source\neo4j\docs\evidence\20261010_round58_live_cdp_v3config'
$source=Get-Content -LiteralPath $sourcePath -Raw
$changes=@(
 @('D:\a-open_source\neo4j\docs\evidence\20261009_search_repair_cdp',$folder),
 @("f.elements.method.value='neural reranking';f.elements.task.value='subjective quality of machine translation';f.elements.dataset.value='naist';","f.elements.method.value='LoRA';"),
 @(".includes('Neural Reranking')",".includes('Low-Rank Adaptation')")
)
foreach($change in $changes){
 if($source.Split(@($change[0]),[StringSplitOptions]::None).Length -ne 2){throw 'Capture replacement must match exactly once'}
 $source=$source.Replace($change[0],$change[1])
}
& ([ScriptBlock]::Create($source))
$recordPath=Join-Path $folder 'captures.json';$record=Get-Content -LiteralPath $recordPath -Raw|ConvertFrom-Json -AsHashtable
$record.liveGraphId=$health.data.graphId;$record.appCodeSha256=$health.data.appCodeSha256
$record.vocabulary=$health.data.conceptVocabulary;$record.helperSha256=$sourceSha
$record.wrapperSha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$record.capturedAtUTC=(Get-Date).ToUniversalTime().ToString('o')
[IO.File]::WriteAllText($recordPath,($record|ConvertTo-Json -Depth 12))

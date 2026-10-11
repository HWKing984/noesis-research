// Browser smoke against v2. Synthetic reviewer values never modify dataset files.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require(process.argv[2]||'playwright');
const root=path.resolve(__dirname,'..'),data=process.argv[3]?path.resolve(process.argv[3]):path.join(root,'kg_datasets/dblp/ner_v2');
const schema=JSON.parse(fs.readFileSync(path.join(root,'schemas/annotation_v2.schema.json'),'utf8'));
const mutable=schema['x-annotation'].mutable_fields;
async function downloadRows(page){const promise=page.waitForEvent('download');await page.locator('#export').click();const download=await promise,stream=await download.createReadStream(),chunks=[];for await(const chunk of stream)chunks.push(chunk);return Buffer.concat(chunks).toString().trim().split('\n').map(JSON.parse)}
async function upload(page,rows){await page.locator('#import').setInputFiles({name:'fixture.jsonl',mimeType:'application/x-ndjson',buffer:Buffer.from(rows.map(x=>JSON.stringify(x)).join('\n'))})}
(async()=>{const browser=await chromium.launch({headless:true});try{
 const context=await browser.newContext({acceptDownloads:true}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 await page.goto(pathToFileURL(path.join(data,'pilot_review.html')).href);
 assert.deepEqual(await page.locator('#label option').allTextContents(),schema.$defs.entity.properties.label.enum);
 assert.deepEqual(await page.locator('#domainLabel option').allTextContents(),schema.$defs.domain.properties.label.enum);
 await page.locator('#review').click();assert.match(await page.locator('#error').textContent(),/实际人工标注者/);
 const baseline=await downloadRows(page);assert.equal(baseline.length,200);
 for(const [key,value] of [['year',2021],['type','inproceedings'],['doi','10.1000/changed'],['topics',['changed']],['intendedSplit','test'],['samplingStratum',{changed:true}],['ambiguityFlags',['changed']]]){
  const changed=structuredClone(baseline);changed[0][key]=equalValue(changed[0][key],value)?'tampered':value;await upload(page,changed);
  await page.waitForFunction(()=>document.getElementById('error').textContent.includes('元数据/分区/来源不一致'));
 }
 await page.locator('#reviewer').fill('BROWSER-TEST-FIXTURE');await page.locator('#review').click();
 let progress=await downloadRows(page);assert.equal(progress[0].entity_review.status,'reviewed');assert.equal(progress[0].relation_review.status,'draft');
 await page.locator('#notes').fill('fixture edit');await page.locator('#next').click();await page.locator('#prev').click();
 progress=await downloadRows(page);assert.equal(progress[0].entity_review.status,'draft');assert.equal(progress[0].notes,'fixture edit');
 await page.reload();await upload(page,progress);await page.waitForFunction(()=>document.getElementById('notes').value==='fixture edit');
 const withPairs=progress.findIndex(r=>r.entities.some(e=>e.label==='METHOD')&&r.entities.some(e=>['TASK','DATASET'].includes(e.label)));
 assert(withPairs>=0);await page.locator('#jump').fill(String(withPairs+1));await page.locator('#go').click();
 await page.locator('#reviewer').fill('BROWSER-TEST-FIXTURE');await page.locator('#review').click();await page.locator('#relationReview').click();assert.match(await page.locator('#error').textContent(),/关系未完成/);
 const count=await page.locator('.relation-select').count();for(let i=0;i<count;i++){
  await page.locator('.relation-select').nth(i).selectOption('UNRESOLVED');await page.locator('.reason').nth(i).fill('insufficient title context');
 }await page.locator('#relationReview').click();assert.match(await page.locator('#error').textContent(),/关系未完成/);
 for(let i=0;i<count;i++){await page.locator('.relation-select').nth(i).selectOption('NO_RELATION');await page.locator('.reason').nth(i).fill('SYNTHETIC structural negative fixture')}
 await page.locator('#relationReview').click();progress=await downloadRows(page);assert.equal(progress[withPairs].relation_review.status,'reviewed');
 const corrupt=structuredClone(progress);corrupt[withPairs].relation_review={status:'reviewed',reviewer:' ',reviewed_at:'bad',source:'human_reviewed'};await upload(page,corrupt);await page.waitForFunction(()=>document.getElementById('error').textContent.includes('复核声明'));
 await page.goto(pathToFileURL(path.join(data,'blind_50_a.html')).href);let blind=await downloadRows(page);assert.equal(blind.length,50);assert(blind.every(r=>!r.entities.length&&!r.domains.length&&!r.relations.length));
 await page.goto(pathToFileURL(path.join(data,'blind_50_b.html')).href);const second=await downloadRows(page);assert.deepEqual(second,blind);
 // Unicode fixture uses authoritative schema and one synthetic record, never saved.
 const fixture=structuredClone(baseline[0]);fixture.text='😀 BERT for QA';fixture.title=fixture.text;fixture.entities=[];fixture.domains=[];fixture.relations=[];
 const template=fs.readFileSync(path.join(root,'docs/review_v2_template.html'),'utf8'),js=fs.readFileSync(path.join(root,'docs/review_v2.js'),'utf8'),fixturePage=await context.newPage();fixturePage.on('pageerror',e=>errors.push(e.message));fixturePage.on('dialog',d=>d.accept());
 await fixturePage.setContent(template.replace('__PILOT_JSON__',JSON.stringify([fixture])).replace('__SCHEMA_JSON__',JSON.stringify(schema)).replace('__PAGE_JSON__',JSON.stringify({title:'fixture',download:'fixture.jsonl',schemaSha256:fixture.schemaSha256,blind:true})).replace('__REVIEW_JS__',js));
 await fixturePage.evaluate(()=>{const node=document.getElementById('title').firstChild,range=document.createRange();range.setStart(node,3);range.setEnd(node,7);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);document.getElementById('title').dispatchEvent(new MouseEvent('mouseup',{bubbles:true}))});
 await fixturePage.locator('#add').click();assert.match(await fixturePage.locator('#spans').textContent(),/\[2,6\) METHOD: BERT/);await fixturePage.locator('#title mark').click();assert.equal(await fixturePage.locator('#title mark').count(),0);
 await page.goto(pathToFileURL(path.join(data,'rare_review.html')).href);assert.equal((await downloadRows(page)).length,100);
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,checks:['schema-derived enums','seven metadata tamper cases rejected','entity review does not complete relation review','notes invalidate review','export/import roundtrip','incomplete/unresolved relation gold rejected','explicit candidate decisions accepted','invalid review import rejected','two truly blank blind pages','Unicode selection and entity deletion','rare page load','no page errors'],real_dataset_modified:false},null,2));
 }finally{await browser.close()}})().catch(error=>{console.error(error);process.exitCode=1});
function equalValue(a,b){return JSON.stringify(a)===JSON.stringify(b)}

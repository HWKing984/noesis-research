// Optional real-browser smoke: node tests/test_pilot_review.cjs <playwright module path>
// Reviewer values below are synthetic fixtures, never saved as project gold data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.argv[2] || 'playwright');

(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const context = await browser.newContext({acceptDownloads: true});
    let page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    const root = path.resolve(__dirname, '..');
    await page.goto(pathToFileURL(path.join(root, 'kg_datasets/dblp/ner_v1/pilot_review.html')).href);
    assert.match(await page.locator('#progress').textContent(), /1 \/ 200.*人工复核 0 条/);
    await page.locator('#review').click();
    assert.match(await page.locator('#error').textContent(), /实际人工标注者/);
    await page.locator('#reviewer').fill('browser-smoke-fixture-not-real-review');
    await page.locator('#review').click();
    assert.match(await page.locator('#progress').textContent(), /人工复核 1 条/);
    await page.locator('#notes').fill('test edit invalidates review');
    await page.locator('#next').click();
    assert.match(await page.locator('#progress').textContent(), /2 \/ 200.*人工复核 0 条/);
    await page.locator('#prev').click();
    assert.equal(await page.locator('#notes').inputValue(), 'test edit invalidates review');
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#export').click();
    const download = await downloadPromise;
    const stream = await download.createReadStream();
    const chunks = [];
    for await (const chunk of stream) chunks.push(chunk);
    const exported = Buffer.concat(chunks);
    const exportedRows = exported.toString().trim().split('\n').map(JSON.parse);
    assert.equal(exportedRows.length, 200);
    assert(exportedRows.every(row => row.review_status === 'draft'));
    await page.reload();
    await page.locator('#import').setInputFiles({name:'test-progress.jsonl', mimeType:'application/x-ndjson', buffer:exported});
    await page.waitForFunction(() => document.getElementById('notes').value === 'test edit invalidates review');
    exportedRows[0].text += 'changed source';
    await page.locator('#import').setInputFiles({name:'invalid.jsonl', mimeType:'application/x-ndjson', buffer:Buffer.from(exportedRows.map(JSON.stringify).join('\n'))});
    await page.waitForFunction(() => document.getElementById('error').textContent.includes('不是同一版本'));

    // Separate, synthetic page verifies UTF-16 DOM selection -> Unicode codepoints.
    const fixture = {publicationId:'browser-fixture',text:'😀 BERT for QA',year:2020,type:'article',topics:['test'],
      entities:[],relations:[],review_status:'draft',annotation_source:'draft_dictionary_v1',reviewer:'',reviewed_at:'',
      schemaVersion:'v1-candidate',groupId:'test',sourceCsvSha256:'test',notes:''};
    const template = fs.readFileSync(path.join(root,'docs/pilot_review_template.html'),'utf8');
    page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    await page.setContent(template.replace('__PILOT_JSON__', JSON.stringify([fixture])));
    await page.evaluate(() => {
      const node = document.getElementById('title').firstChild;
      const range = document.createRange();range.setStart(node,3);range.setEnd(node,7);
      const selection = window.getSelection();selection.removeAllRanges();selection.addRange(range);
      document.getElementById('title').dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
    });
    await page.locator('#add').click();
    assert.match(await page.locator('#spans').textContent(), /\[2,6\) METHOD: BERT/);
    await page.locator('#title mark').click();
    assert.equal(await page.locator('#title mark').count(), 0);
    await page.goto(pathToFileURL(path.join(root,'kg_datasets/dblp/ner_v1/rare_train_candidates/rare_candidates_review.html')).href);
    assert.match(await page.locator('#progress').textContent(), /1 \/ 100.*人工复核 0 条/);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({passed:true,mode:'headless chromium',checks:[
      'load 200-title pilot','explicit reviewer required','editing clears reviewed status','navigation preserves edits',
      'JSONL export and restore','mismatched source rejected','Unicode codepoint selection','remove entity',
      'load 100 rare candidates','no page errors'],
      fixtures_only:true,real_annotations_modified:false}, null, 2));
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exitCode=1;});

'use strict';
const schema=JSON.parse(document.getElementById('schema-data').textContent);
const config=JSON.parse(document.getElementById('page-data').textContent);
const originals=JSON.parse(document.getElementById('pilot-data').textContent);
const annotation=schema['x-annotation'];
const labels=schema.$defs.entity.properties.label.enum;
const domainLabels=schema.$defs.domain.properties.label.enum;
const immutable=Object.keys(schema.properties).filter(k=>!annotation.mutable_fields.includes(k));
const $=id=>document.getElementById(id), cp=text=>Array.from(text);
let rows=structuredClone(originals),index=0,selected=null;
function canonical(value){if(Array.isArray(value))return value.map(canonical);if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])]));return value}
function equal(a,b){return JSON.stringify(canonical(a))===JSON.stringify(canonical(b))}
function freshReview(){return {status:'draft',reviewer:'',reviewed_at:'',source:'draft'}}
function message(text=''){$('error').textContent=text}
function exactKeys(value,keys){return value&&typeof value==='object'&&!Array.isArray(value)&&equal(Object.keys(value).sort(),[...keys].sort())}
function validSpan(span,text){return exactKeys(span,['start','end','text'])&&Number.isInteger(span.start)&&Number.isInteger(span.end)&&span.start>=0&&span.start<span.end&&span.end<=cp(text).length&&cp(text).slice(span.start,span.end).join('')===span.text}
function validReview(review){
 if(!exactKeys(review,Object.keys(schema.$defs.review.properties))||!schema.$defs.review.properties.status.enum.includes(review.status)||typeof review.reviewer!=='string'||typeof review.reviewed_at!=='string')return false;
 if(review.status!=='reviewed')return review.reviewer===''&&review.reviewed_at===''&&review.source==='draft';
 const stamp=review.reviewed_at,match=/^(\d{4})-(\d{2})-(\d{2})T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.exec(stamp);
 return !!review.reviewer.trim()&&review.source==='human_reviewed'&&!!match&&Number(match[2])>=1&&Number(match[2])<=12&&Number(match[3])>=1&&Number(match[3])<=new Date(Date.UTC(Number(match[1]),Number(match[2]),0)).getUTCDate()&&Number.isFinite(Date.parse(stamp));
}
function candidates(r){const pairs=[];r.entities.forEach((head,h)=>r.entities.forEach((tail,t)=>{for(const [label,pair] of Object.entries(annotation.positive_relation_pairs))if(head.label===pair[0]&&tail.label===pair[1])pairs.push({head:h,tail:t,label})}));return pairs}
function errorsFor(r,original){
 const errors=[];
 if(!exactKeys(r,Object.keys(schema.properties)))return ['记录字段不符合schema'];
 if(immutable.some(k=>!equal(r[k],original[k]))||r.schemaSha256!==config.schemaSha256)return ['不是同一版本的试标包：元数据/分区/来源不一致'];
 if(!Array.isArray(r.entities)||!Array.isArray(r.domains)||!Array.isArray(r.relations)||typeof r.notes!=='string')return ['标注结构无效'];
 if(['entity_review','relation_review','domain_review'].some(k=>!validReview(r[k])))return ['复核声明、标注者或时间无效'];
 let end=0;
 for(const e of r.entities){if(!exactKeys(e,Object.keys(schema.$defs.entity.properties))||!labels.includes(e.label)||!schema.$defs.entity.properties.origin.enum.includes(e.origin)||!validSpan({start:e.start,end:e.end,text:e.text},r.text)||e.start<end)return ['实体类别/边界/顺序无效'];end=e.end}
 const seenDomains=new Set();
 for(const d of r.domains){if(!exactKeys(d,Object.keys(schema.$defs.domain.properties))||!domainLabels.includes(d.label)||seenDomains.has(d.label)||!schema.$defs.domain.properties.origin.enum.includes(d.origin)||!validSpan(d.evidence,r.text))return ['领域类别/证据无效'];seenDomains.add(d.label)}
 const pairs=candidates(r), seenPairs=new Set();
 for(const relation of r.relations){const pair=pairs.find(p=>p.head===relation.head&&p.tail===relation.tail),key=relation.head+':'+relation.tail;
  if(!exactKeys(relation,Object.keys(schema.$defs.relation.properties))||!pair||seenPairs.has(key)||![pair.label,annotation.negative_relation_label,annotation.unresolved_relation_label].includes(relation.label)||typeof relation.reason!=='string')return ['关系方向/类别/字段无效'];seenPairs.add(key);
  if(relation.label!==annotation.unresolved_relation_label&&(relation.evidence===null||!validSpan(relation.evidence,r.text)))return ['已判定关系缺少有效证据'];
  if(relation.evidence!==null){const e=relation.evidence;if(!validSpan(e,r.text)||e.start>Math.min(r.entities[pair.head].start,r.entities[pair.tail].start)||e.end<Math.max(r.entities[pair.head].end,r.entities[pair.tail].end))return ['关系证据必须覆盖两个实体']}
  if([annotation.negative_relation_label,annotation.unresolved_relation_label].includes(relation.label)&&!relation.reason.trim())return ['负例或未解决项必须说明理由'];
 }
 if(r.relation_review.status==='reviewed'&&(r.entity_review.status!=='reviewed'||seenPairs.size!==pairs.length||r.relations.some(x=>x.label===annotation.unresolved_relation_label)))errors.push('关系未完成：请先复核实体、判断全部候选对并裁决未解决项');
 return errors;
}
function invalidateEntity(r){r.entity_review=freshReview();r.relation_review=freshReview();r.relations=[]}
function sign(field){const r=rows[index],name=$('reviewer').value.trim();if(!name)return message('请填写实际人工标注者');
 const proposed=structuredClone(r);proposed[field]={status:'reviewed',reviewer:name,reviewed_at:new Date().toISOString(),source:'human_reviewed'};
 const errors=errorsFor(proposed,originals[index]);if(errors.length)return message(errors.join('；'));rows[index]=proposed;render()}
function option(value,text=value){const item=document.createElement('option');item.value=value;item.textContent=text;return item}
function render(){if(!rows.length){document.querySelector('.card').hidden=true;$('progress').textContent='当前包无候选样本';return}const r=rows[index];selected=null;$('jump').value=index+1;$('jump').max=rows.length;
 $('progress').textContent=`${index+1} / ${rows.length} · 实体复核 ${rows.filter(x=>x.entity_review.status==='reviewed').length} · 领域复核 ${rows.filter(x=>x.domain_review.status==='reviewed').length} · 关系复核 ${rows.filter(x=>x.relation_review.status==='reviewed').length}`;
 $('meta').textContent=`${r.publicationId} · ${r.year} · ${r.type} · ${r.topics.join(', ')} · 分区 ${r.intendedSplit}`;
 const box=$('title');box.replaceChildren();let cursor=0;const chars=cp(r.text);
 r.entities.forEach((e,i)=>{box.append(document.createTextNode(chars.slice(cursor,e.start).join('')));const mark=document.createElement('mark');mark.textContent=e.text;mark.dataset.label=e.label;mark.title=e.label+' · 点击删除';mark.onclick=()=>{if(confirm('删除实体：'+e.text+'？')){r.entities.splice(i,1);invalidateEntity(r);render()}};box.append(mark);cursor=e.end});box.append(document.createTextNode(chars.slice(cursor).join('')));
 $('spans').textContent=r.entities.map(e=>`[${e.start},${e.end}) ${e.label}: ${e.text}`).join(' | ')||'当前无实体。请检查未知模型/任务/数据集名称，不能按词典无命中认定真负例。';
 $('domains').replaceChildren();r.domains.forEach((d,i)=>{const line=document.createElement('div');line.textContent=`${d.label}: [${d.evidence.start},${d.evidence.end}) ${d.evidence.text} `;const remove=document.createElement('button');remove.textContent='删除领域';remove.onclick=()=>{r.domains.splice(i,1);r.domain_review=freshReview();render()};line.append(remove);$('domains').append(line)});
 $('pairs').replaceChildren();const pairs=candidates(r);
 if(!pairs.length)$('pairs').textContent='暂无合法候选对；实体复核后才能确认此情况。';
 for(const pair of pairs){const current=r.relations.find(x=>x.head===pair.head&&x.tail===pair.tail),line=document.createElement('div');line.className='pair';
  const label=document.createElement('div');label.textContent=`${r.entities[pair.head].text} → ${r.entities[pair.tail].text}`;
  const select=document.createElement('select');select.className='relation-select';select.dataset.head=pair.head;select.dataset.tail=pair.tail;
  select.append(option('','未判定'),option(pair.label),option(annotation.negative_relation_label),option(annotation.unresolved_relation_label));select.value=current?.label||'';
  const reason=document.createElement('input');reason.className='reason';reason.placeholder='判断依据 / 未解决原因（负例和未解决项必填）';reason.value=current?.reason||'';
  select.onchange=()=>{r.relations=r.relations.filter(x=>x.head!==pair.head||x.tail!==pair.tail);if(select.value)r.relations.push({head:pair.head,tail:pair.tail,label:select.value,evidence:select.value===annotation.unresolved_relation_label?null:{start:0,end:cp(r.text).length,text:r.text},reason:reason.value});r.relation_review=freshReview();render()};
  reason.oninput=()=>{const rel=r.relations.find(x=>x.head===pair.head&&x.tail===pair.tail);if(rel)rel.reason=reason.value;r.relation_review=freshReview()};line.append(label,select,reason);$('pairs').append(line);
 }
 $('notes').value=r.notes;message();
}
$('heading').textContent=config.title;$('warning').textContent=config.blind?'独立盲标副本：内嵌数据不含词典答案。请独立标注，不与另一标注者讨论答案；两人完成后再比较并裁决。':'全部初始标注是词典草稿，尚无人工金标准。请逐条补漏、改边界、删除误标。';
for(const label of labels)$('label').append(option(label));for(const label of domainLabels)$('domainLabel').append(option(label));
$('title').addEventListener('mouseup',()=>{const s=window.getSelection();if(!s.rangeCount||s.isCollapsed)return;const range=s.getRangeAt(0),box=$('title');if(!box.contains(range.startContainer)||!box.contains(range.endContainer))return;
 const prefix=document.createRange();prefix.selectNodeContents(box);prefix.setEnd(range.startContainer,range.startOffset);let start=cp(prefix.toString()).length,end=start+cp(range.toString()).length,chars=cp(rows[index].text);while(start<end&&/\s/.test(chars[start]))start++;while(end>start&&/\s/.test(chars[end-1]))end--;selected={start,end}});
$('add').onclick=()=>{const r=rows[index];if(!selected||selected.start===selected.end)return message('请先选中原文');const {start,end}=selected;if(r.entities.some(e=>start<e.end&&e.start<end))return message('实体不能重叠，请先删除原标注');r.entities.push({start,end,text:cp(r.text).slice(start,end).join(''),label:$('label').value,origin:'human'});r.entities.sort((a,b)=>a.start-b.start);invalidateEntity(r);render()};
$('domainAdd').onclick=()=>{const r=rows[index];if(!selected||selected.start===selected.end)return message('请先选择领域证据文字');const label=$('domainLabel').value;if(r.domains.some(d=>d.label===label))return message('本论文已有此领域标签');r.domains.push({label,evidence:{...selected,text:cp(r.text).slice(selected.start,selected.end).join('')},origin:'human'});r.domain_review=freshReview();render()};
$('clear').onclick=()=>{if(confirm('清空实体？')){rows[index].entities=[];invalidateEntity(rows[index]);render()}};
$('review').onclick=()=>sign('entity_review');$('domainReview').onclick=()=>sign('domain_review');$('relationReview').onclick=()=>sign('relation_review');
$('draft').onclick=()=>{invalidateEntity(rows[index]);render()};$('notes').oninput=()=>{const r=rows[index];r.notes=$('notes').value;for(const key of ['entity_review','domain_review','relation_review'])r[key]=freshReview();$('progress').textContent='备注已修改，三项需分别重新确认'};
$('prev').onclick=()=>{index=Math.max(0,index-1);render()};$('next').onclick=()=>{index=Math.min(rows.length-1,index+1);render()};$('go').onclick=()=>{const n=Number($('jump').value);if(Number.isInteger(n)&&n>=1&&n<=rows.length){index=n-1;render()}else message('编号无效')};
$('export').onclick=()=>{const url=URL.createObjectURL(new Blob([rows.map(r=>JSON.stringify(r)).join('\n')+'\n'],{type:'application/x-ndjson;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=config.download;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
$('import').onchange=async event=>{try{const file=event.target.files[0];if(!file)return;const data=(await file.text()).replace(/^\uFEFF/,'').split(/\r?\n/).filter(x=>x.trim()).map(JSON.parse);if(data.length!==originals.length)throw Error('记录数量不同');const map=new Map(data.map(r=>[r.publicationId,r]));if(map.size!==data.length)throw Error('重复ID');
 for(const original of originals){const r=map.get(original.publicationId);if(!r)throw Error('论文ID不匹配');const errors=errorsFor(r,original);if(errors.length)throw Error(errors.join('；'))}
 rows=originals.map(o=>map.get(o.publicationId));render();message('进度已恢复；正式使用前仍需Python完整校验');}catch(error){message('无法导入：'+error.message)}finally{event.target.value=''}};
render();

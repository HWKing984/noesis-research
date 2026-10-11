// Native Node check of the shipped inline script, with only browser I/O stubbed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
class Element {
  constructor(tag='div') { this.tagName=tag;this.children=[];this.style={};this.dataset={};this.hidden=false;this.disabled=false;this.textContent='';this.attrs={}; }
  append(...items) { for(const item of items){item.parent=this;this.children.push(item);} }
  replaceChildren(...items) { this.children=[];this.append(...items); }
  setAttribute(key,value) { this.attrs[key]=String(value); }
  after(item) { this.parent?.append(item); }
  remove() { if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this); }
  scrollIntoView() {}
  click() { this.onclick?.(); }
}
const elements = new Map();
const document = {
  getElementById(id) { if(!elements.has(id))elements.set(id,new Element());return elements.get(id); },
  createElement(tag) { return new Element(tag); },
  createElementNS(ns,tag) { return new Element(tag); },
  createTextNode(text) { const e=new Element('#text');e.textContent=text;return e; },
  querySelectorAll() { return []; },
  body:new Element('body'),
};
const location={pathname:'/',search:'',hash:''};
const context=vm.createContext({document,location,URLSearchParams,URL,Blob,structuredClone,Date,console,setTimeout,
  history:{replaceState(_state,_title,value){location.hash=value.startsWith('#')?value:'';}},
  window:{addEventListener(){}},fetch:()=>new Promise(()=>{}),
});
const html=fs.readFileSync(path.join(__dirname,'../resources/course_literature.html'),'utf8');
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
const run=source=>vm.runInContext(source,context);
const data={publication:{publicationId:'paper/one',graphId:'scope',title:'<script>not executable</script>',year:2025,dblpUrl:'https://dblp.org/rec/paper/one'},
  authors:[{name:'Original author',position:1}],venues:[{name:'AAAI'}],mentions:[],assertions:[{assertion:{predicate:'USED_FOR',confidence:.7,evidence:'Literal title'}}],
  citationDraft:'Original draft',notice:'candidate'};
context.sample=data;
(async()=>{
  assert.equal(run("exportSelection('json')"),null);
  run('addSelection(sample);addSelection(sample)');
  assert.equal(run('selection.size'),1);
  const exported=JSON.parse(run("exportSelection('json').text"));
  assert.equal(exported.items[0].data.publication.title,data.publication.title);
  assert.equal(exported.items[0].data.assertions[0].assertion.evidence,'Literal title');
  assert.equal(exported.items[0].source,'live_neo4j_detail_snapshot');
  assert.match(exported.notice,/不是.*必引/);
  data.publication.title='changed outside';
  assert.notEqual(run("selection.get('paper/one').data.publication.title"),data.publication.title);
  assert.match(run("exportSelection('text').text"),/Original draft/);
  for(let i=0;i<49;i++){context.sample=structuredClone(data);context.sample.publication.publicationId='paper/'+i;run('addSelection(sample)');}
  context.sample=structuredClone(data);context.sample.publication.publicationId='over-limit';run('addSelection(sample)');
  assert.equal(run('selection.size'),50);assert.equal(run("selection.has('over-limit')"),false);
  assert.match(document.getElementById('selection-status').textContent,/50篇上限/);
  const article=document.getElementById('selection-list').children[0];
  article.children[2].children[1].click();assert.equal(run('selection.size'),49);
  run("setFragment('paper/one','methods');$('search').onreset()");
  assert.equal(location.hash,'');assert.equal(run('selection.size'),49);
  assert.equal(document.getElementById('graph-paths-panel').hidden,true);
  // A slow search must not disable submit or replace a newer detail response.
  context.detailResponse={data:{...structuredClone(data),assertions:[]}};
  run("active=new URLSearchParams();request=path=>path.startsWith('/api/publications?')?new Promise(resolve=>globalThis.finishSearch=resolve):Promise.resolve(detailResponse)");
  const slow=run('search()');assert.equal(document.getElementById('submit').disabled,true);
  await run("detail('paper/one')");
  assert.equal(document.getElementById('submit').disabled,false);
  assert.match(location.hash,/paper=paper%2Fone/);
  context.searchResponse={data:[],meta:{hasNext:false}};run('finishSearch(searchResponse)');await slow;
  assert.equal(document.getElementById('detail').hidden,false);
  assert.equal(document.getElementById('submit').disabled,false);
  context.graph={rootId:'p',nodes:[{kind:'Publication',props:{id:'p',title:'Root'}},{kind:'Person',props:{id:'a',name:'Author'}},{kind:'Publication',props:{id:'q',title:'Other',publicationId:'other'}}],
    edges:[{id:'e1',source:'a',target:'p',kind:'AUTHORED'},{id:'e2',source:'a',target:'q',kind:'AUTHORED'}],paths:[{nodes:['p','a','q'],edges:['e1','e2']}]};
  run('drawPaths(graph)');
  const row=document.getElementById('graph-paths').children[0];
  assert.match(row.children[1].textContent,/←AUTHORED/);
  assert.match(row.children[3].textContent,/AUTHORED→/);
  assert.equal(row.children[5].textContent,'打开关联论文证据');
  assert.equal(document.getElementById('graph-paths-panel').hidden,false);
  console.log('PASS: bounded snapshot export, literal text, remove/reset, stale search, permalink and directed path explanations');
})().catch(error=>{console.error(error);process.exitCode=1;});

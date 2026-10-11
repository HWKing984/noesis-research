"""Assemble a bounded submission from existing artifacts, with actual weights."""
import argparse
import base64
import csv
import html
import json
import platform
import zipfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import course_quality_app as app
from build_course_report import render

ROOT = app.g.ROOT
OUT = ROOT/'docs/delivery'
V2 = ROOT/'outputs/v2_textscope_once_20261011_run'
CONTROL = ROOT/'outputs/v2_targeted_controls_20261011'
DATA = ROOT/'kg_datasets/dblp/course_v2_train65_dev20_textscope_20261011_final'
CSS = 'body{font:16px/1.7 Microsoft YaHei,Arial;margin:24px auto;max-width:1120px;padding:0 24px;color:#172638}h1,h2{color:#123f66}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bccbd7;padding:8px}th{background:#eaf2f7}pre{white-space:pre-wrap;background:#f1f4f7;padding:12px}a{color:#175baa}mark{padding:2px;border-radius:4px}.METHOD{background:#bfdbfe}.TASK{background:#bbf7d0}.DATASET{background:#fde68a}article{border-top:2px solid #dde5ed;margin-top:28px;padding-top:18px}svg{width:100%;height:240px;background:#f7fafc}label{display:block}button{padding:10px;margin:8px}p{overflow-wrap:anywhere}@media print{button{display:none}article{break-before:page}svg{break-inside:avoid}}'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(name, value):
    app.g.c.write_json(OUT/name, value)


def page(title, body):
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+CSS+'</style><main>'+body+'</main></html>'


def highlight(text, entities):
    end = 0; pieces = []
    for e in sorted(entities, key=lambda e:e['start']):
        if (e['label'] not in ('METHOD','TASK','DATASET') or not end <= e['start'] < e['end'] <= len(text)
                or text[e['start']:e['end']] != e['text']):
            raise ValueError('Invalid demonstration entity span')
        pieces += [html.escape(text[end:e['start']]), '<mark class="'+e['label']+'" title="'+e['label']+'">'+html.escape(e['text'])+'</mark>']
        end = e['end']
    return ''.join(pieces)+html.escape(text[end:])


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    models = []
    for kind in ('ner', 're'):
        lock = read(ROOT/f'annotations/course_v4/{kind}_test_selection_20261006.json')
        path = ROOT/lock['developmentRun']/lock['checkpoint']
        if app.g.c.file_sha256(path/'model.safetensors') != lock['weightsSha256']:
            raise ValueError('V1 weights differ from production lock')
        models.append({'name':'V1_'+kind.upper(), 'path':path.relative_to(ROOT).as_posix(),
                       'production':True, 'weightsSha256':lock['weightsSha256'], 'bytes':(path/'model.safetensors').stat().st_size})
    for name, path in [('V2_NER',V2/'ner/best_model'), ('V2_RE',V2/'re/best_model'), ('V2_WEIGHTED_RE',CONTROL/'weighted_re/best_model')]:
        models.append({'name':name, 'path':path.relative_to(ROOT).as_posix(), 'production':False,
                       'weightsSha256':app.g.c.file_sha256(path/'model.safetensors'), 'bytes':(path/'model.safetensors').stat().st_size})
    save('models.json', {'models':models,'productionReplacementAllowed':False,'test20BodyIncluded':False})
    save('environment.json', {'python':platform.python_version(),'platform':platform.platform(),
                             'packages':{n:version(n) for n in ('torch','transformers','tokenizers','safetensors','numpy','jsonschema','lxml')}})
    demos = []
    def api(path, **params):
        with urlopen('http://127.0.0.1:8765'+path+'?'+urlencode(params), timeout=30) as response:
            return json.load(response)['data']
    chosen = ['conf/seeda/VonitsanosESKM25']
    for q in ('Knowledge Graph', 'Diffusion', 'Reinforcement Learning', 'Neural Reranking'):
        rows = api('/api/publications', q=q, limit=5)
        chosen.append(next(r['publicationId'] for r in rows if r['publicationId'] not in chosen))
    for pid in chosen:
        detail = api('/api/publication', id=pid)
        paper = detail['publication']; text = paper['title']
        demos.append({'publicationId':pid,'sampleId':paper.get('modelSampleId',pid), 'text':text,
                      'textSha256':app.g.digest(text),'liveDetail':detail})
    save('v1_demo_papers.json', demos)
    ner_test = read(ROOT/'kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09/test_result.json')
    re_test = read(ROOT/'kg_datasets/dblp/course_v4_runs/re_final_test_20261006_17/test_result.json')
    save('experiment_comparison.json', {'V1_title_historical_AI_test':{'NER':ner_test,'RE':re_test},
                                      'referenceProvenance':read(OUT/'human_review_confirmation.json'),
                                      'V2_abstract_AI_dev':read(V2/'results.json'),
                                      'V2_bounded_controls_AI_dev':read(CONTROL/'results.json'),
                                      'crossTaskRankingAllowed':False,'fullV2PipelineF1':None,'test20Evaluated':False})
    abstracts = app.g.c.read_jsonl(DATA/'train_ner.jsonl')
    relations = app.g.c.read_jsonl(DATA/'train_re_scored.jsonl')
    names = {'2107.03374':'Codex：Evaluating Large Language Models Trained on Code',
             '1606.05250':'SQuAD：100,000+ Questions for Machine Comprehension of Text',
             '1905.00537':'SuperGLUE：A Stickier Benchmark for General-Purpose Language Understanding Systems'}
    selected = [next(r for r in abstracts if r['arxivId']==id_) for id_ in names]
    provenance = read(OUT/'human_review_confirmation.json')
    if provenance['confirmationSource'] != 'explicit_user_chat' or provenance['scope']['demoPapers'] != list(names):
        raise ValueError('Demonstration human-review confirmation does not match frozen papers')
    home = (ROOT/'resources/course_literature.html').read_text(encoding='utf-8')
    if home.count('（AI参考、') != 2:
        raise ValueError('Frozen home page reference wording changed')
    (OUT/'v1-home.html').write_text(home.replace('（AI参考、','（AI初标后用户逐条人工审核、'),encoding='utf-8')
    body = '<h1>冻结交付演示：V1 正式系统 / V2 摘要实验</h1><p><a href="/">打开 V1 实时检索</a> · <a href="/delivery-report">实验报告</a></p><p>蓝色 METHOD，绿色 TASK，黄色 DATASET。以下摘要实体及关系来自封存参考标签：AI 辅助初标、用户逐条人工审核，已裁决范围内作为人工复核金标准；不是当前生产模型输出。选择样例用于说明，不用于估计总体准确率。</p><h2>V1：五篇真实 Neo4j 文献</h2>'
    for d in demos:
        body += '<p><a href="/#paper='+urlencode({'id':d['publicationId']})[3:]+'&view=paper">'+html.escape(d['text'])+'</a> — '+html.escape(d['publicationId'])+'</p>'
    reviewed = []
    for doc in selected:
        rows = [r for r in relations if r['arxivId']==doc['arxivId']]
        positives = [r for r in rows if r['label']!='NO_RELATION']
        notes = {
            '2107.03374':'Codex 的研究模型、独立生产版本和泛称 GPT 不混同；HumanEval 上的性能可归属研究模型，GPT 不自动继承。重复采样的效果证据保留原文上下文，不凭共现连边。',
            '1606.05250':'SQuAD 名称及缩写、reading comprehension、logistic regression 的跨度可核对。模型 F1=51.0% 是论文作者报告的结果，不是本项目抽取成绩。冻结标签可能漏掉 answer the questions，候选修订未用于训练，交付不改标签。',
            '1905.00537':'pretraining / transfer learning 与 language understanding 是背景用途；摘要提出 SuperGLUE，但未表达这些方法在 SuperGLUE 上的评测，不自动生成 EVALUATED_ON。'}
        body += '<article id="abstract-'+doc['arxivId']+'"><h2>'+html.escape(names[doc['arxivId']])+'</h2><p>来源：<a href="'+html.escape(doc['sourceURL'],quote=True)+'">'+html.escape(doc['sourceURL'])+'</a> · train 演示样例，非独立测试</p><p>'+highlight(doc['text'],doc['entities'])+'</p><p><strong>原文核对说明：</strong>'+notes[doc['arxivId']]+'</p><details open><summary>已裁决关系与原文证据（用户逐条审核的人工参考）</summary>'
        unique = {}
        for r in rows:
            unique.setdefault((r['head']['text'],r['tail']['text'],r['label']),r)
        for r in unique.values():
            evidence = r['evidence']
            spans = evidence if isinstance(evidence,list) else [evidence]
            for span in spans:
                if isinstance(span,dict) and 'start' in span and doc['text'][span['start']:span['end']] != span['text']:
                    raise ValueError('Relation evidence span mismatch')
            body += '<p><b>'+html.escape(r['head']['text']+' → '+r['label']+' → '+r['tail']['text'])+'</b><br>'+html.escape(str(r.get('reason','')))+'</p><pre>'+html.escape(json.dumps(evidence,ensure_ascii=False,indent=2))+'</pre>'
        body += '</details><h3>人工复核参考关系示意图（离线证据，不写入生产）</h3><svg viewBox="0 0 1000 240" role="img" aria-label="参考关系示意图"><defs><marker id="arrow'+doc['arxivId']+'" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#476580"/></marker></defs>'
        for i,r in enumerate(list({(r['head']['text'],r['tail']['text'],r['label']):r for r in positives}.values())[:3]):
            y = 42+i*72
            body += f'<rect x="10" y="{y-23}" width="325" height="48" rx="8" fill="#bfdbfe"/><rect x="660" y="{y-23}" width="330" height="48" rx="8" fill="'+('#fde68a' if r['tail']['label']=='DATASET' else '#bbf7d0')+f'"/><line x1="336" y1="{y}" x2="657" y2="{y}" stroke="#476580" marker-end="url(#arrow'+doc['arxivId']+f')"/><text x="24" y="{y+5}" font-size="14">'+html.escape(r['head']['text'][:43])+f'</text><text x="440" y="{y-8}" font-size="14">'+r['label']+f'</text><text x="674" y="{y+5}" font-size="14">'+html.escape(r['tail']['text'][:44])+'</text>'
        body += '</svg><p>人工审核状态：用户已在聊天中确认逐条审核，记录见 human_review_confirmation.json。</p><label><input type="checkbox" checked disabled data-paper="'+doc['arxivId']+'">已按用户聊天确认记录本篇人工审核（不是代替用户点击）</label></article>'
        reviewed.append({'arxivId':doc['arxivId'],'textSha256':doc['textSha256'],'sourceReadBy':'AI assistant',
                         'humanReviewed':True,'confirmationSource':'explicit_user_chat','note':notes[doc['arxivId']],'relations':rows})
    body += '<button id="export">导出人工审核确认清单</button><script>document.getElementById("export").onclick=()=>{let rows=[...document.querySelectorAll("input[data-paper]")].map(e=>({arxivId:e.dataset.paper,humanConfirmed:e.checked}));let a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify({scope:"human_reviewed_demonstration_subset_of_frozen_Train65",confirmationSource:"explicit_user_chat",confirmationDate:"2026-10-11",exportedAt:new Date().toISOString(),papers:rows},null,2)],{type:"application/json"}));a.download="demo-human-review.json";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};</script>'
    (OUT/'demo.html').write_text(page('AI-Literature-KG 交付演示',body),encoding='utf-8')
    save('demo_source_review.json', reviewed)
    report()
    print('Delivery files prepared, model weights:', sum(r['bytes'] for r in models), flush=True)


def report():
    source = OUT/'report.md'
    if source.exists():
        body = render(source.read_text(encoding='utf-8'))
        body += '<h2>附：本次真实浏览器截图</h2>'
        for name, caption in [('02_chinese_search.png','V1 中文检索（历史截图，标签来源以当前确认记录为准）'),('03_entities_evidence.png','V1 实体及候选关系证据'),
                              ('04_graph_paper.png','V1 真实 Neo4j 局部图'),('05_abstract_1606.05250_final.png','V2 冻结人工复核参考高亮及关系证据')]:
            image = OUT/name
            if image.exists():
                body += '<figure style="margin:20px 0;break-inside:avoid"><figcaption>'+caption+'</figcaption><img style="width:100%;height:auto" src="data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode()+'"></figure>'
        (OUT/'report.html').write_text(page('AI-Literature-KG 交付报告',body),encoding='utf-8')


def package():
    report()
    paths = set()
    def add(path):
        if path.is_dir():
            for file in path.rglob('*'):
                if file.is_file() and '__pycache__' not in file.parts and file.suffix not in ('.pyc', '.zip'):
                    paths.add(file)
        elif path.is_file():
            paths.add(path)
        else:
            raise FileNotFoundError(path)
    for name in ('README.md','Start-Delivery.ps1','Start-Delivery.cmd','Verify-Delivery.cmd',
                 'requirements-validation.txt','requirements-training.txt','requirements-training.lock.txt',
                 'pytest.ini','scripts','resources','schemas','tests','docs/delivery'):
        add(ROOT/name)
    # All source scripts are small; data and weights are an explicit allowlist.
    add(app.g.configured_bundle(app.CONFIG))
    vocabulary = read(ROOT/'resources/course_concept_v3.json')
    for name in vocabulary['sourceBindings']:
        add(ROOT/name)
    add(ROOT/vocabulary['candidateEvidence'])
    add(ROOT/'kg_datasets/dblp/processed_ai')
    add(DATA)
    for row in read(OUT/'models.json')['models']:
        add(ROOT/row['path'])
    for folder in (V2, CONTROL):
        for file in folder.rglob('*'):
            if (file.is_file() and file.suffix in ('.json','.jsonl','.md','.html') and 'sources' not in file.parts
                    and file.name not in ('candidate_train_ner.jsonl','candidate_train_all_pairs.jsonl',
                                          'new_unresolved_train_pairs.jsonl','train_revision_candidates.json')):
                add(file)
    for folder in ('ner_development_20261006_08','re_entity_development_20261006_15',
                   'ner_final_test_20261006_09','re_final_test_20261006_17'):
        for file in (ROOT/'kg_datasets/dblp/course_v4_runs'/folder).glob('*'):
            if file.is_file() and file.suffix in ('.json','.jsonl'):
                add(file)
    for name in ('ner_test_selection_20261006.json','re_test_selection_20261006.json'):
        add(ROOT/'annotations/course_v4'/name)
    add(ROOT/'kg_datasets/dblp/course_abstract_boundary_inputs_20261009_52/manifest.json')
    for name in ('course_v4_ner_test.md','course_v4_relation_test.md','course_v1_demo_20261010.md',
                 'course_delivery_frozen_20261010.md'):
        add(ROOT/'docs'/name)
    add(ROOT/'docs/archive/README_history_frozen_20261011.md')
    for file in (ROOT/'docs/evidence/20261010_v1_demo_workflow_ready').glob('*'):
        add(file)
    paths.discard(OUT/'manifest.json')
    frozen = {'createdUTC':datetime.now(timezone.utc).isoformat(),'deadline':'2026-10-13',
              'productionGraph':app.g.configured_bundle(app.CONFIG).name,'productionReplacementAllowed':False,
              'test20BodyIncluded':False,'newTrainingPerformed':False,
              'filesSha256':{p.relative_to(ROOT).as_posix():app.g.c.file_sha256(p) for p in sorted(paths)}}
    if any('test20' in name.lower() and name.endswith('.jsonl') for name in frozen['filesSha256']):
        raise ValueError('Sealed test inclusion forbidden')
    save('manifest.json', frozen)
    paths.add(OUT/'manifest.json')
    archive = ROOT/'outputs/AI-Literature-KG_20261013_FINAL.zip'
    if archive.exists():
        raise FileExistsError('Preserve previously submitted ZIP')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
        for p in sorted(paths):
            z.write(p,p.relative_to(ROOT).as_posix())
    # Re-read every member, including actual weights, not just the directory or CRC.
    import hashlib
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist()) != len(paths):
            raise ValueError('ZIP member count mismatch')
        for name, expected in frozen['filesSha256'].items():
            digest = hashlib.sha256()
            with z.open(name) as stream:
                while chunk := stream.read(1024*1024):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ValueError('ZIP content hash mismatch: '+name)
    receipt = {'archive':archive.name,'bytes':archive.stat().st_size,'sha256':app.g.c.file_sha256(archive),
               'members':len(paths),'allMemberSHA256Verified':True,'actualModelsIncluded':5,'secretsIncluded':False,
               'environmentBundled':False,'neo4jDistributionBundled':False}
    app.g.c.write_json(archive.with_suffix('.receipt.json'),receipt)
    print(json.dumps(receipt,indent=2),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','report','package'))
    {'prepare':prepare,'report':report,'package':package}[parser.parse_args().action]()

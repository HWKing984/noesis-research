"""Build a reviewable AI-supervised abstract experiment, without fitting a model.

All negative rules are explicit source-read decisions. Unmatched pairs stay masked.
The old V2 definition, original ZIPs, dev drafts, test text and V1 are not mutated.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import html
import io
import itertools
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT_ZIP = Path('D:/Users/Y7000P/Downloads/v2_train65_direct_semantic_fixed_20261011.zip')
EXPECTED_ZIP_SHA = 'd4cfd083ffba6947a46fdb497ac6aca3b1845e0ee3dd8b3926d9e09104e1557b'
DEV_BASE = ROOT / 'kg_datasets/dblp/course_v2_train65_workset_20261011/dev_intake'
DECISIONS = ROOT / 'annotations/course_v2'
ROSTER = ROOT / 'kg_datasets/dblp/course_v2_sampling_20261011_roster_locked_v2/selected_members.json'
OUTPUT = ROOT / 'kg_datasets/dblp/course_v2_train65_dev20_textscope_20261011_final'
LABELS = {'METHOD', 'TASK', 'DATASET'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jl(data: bytes) -> list[dict]:
    return [json.loads(x) for x in data.decode('utf-8-sig').splitlines() if x.strip()]


def jb(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def jlb(rows) -> bytes:
    return ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows).encode('utf-8')


def span(text: str, literal: str) -> dict:
    matches = list(re.finditer(re.escape(literal), text))
    if len(matches) != 1:
        raise ValueError(f'Expected unique evidence literal ({len(matches)}): {literal}')
    m = matches[0]
    return {'start': m.start(), 'end': m.end(), 'text': m.group()}


def validate(row: dict):
    if sha(row['text'].encode()) != row['textSha256']:
        raise ValueError('Source changed: ' + row['arxivId'])
    if row['entities'] != sorted(row['entities'], key=lambda e: (e['start'], e['end'])):
        raise ValueError('Unsorted entities: ' + row['arxivId'])
    seen, end = set(), -1
    for e in row['entities']:
        if (e['entityId'] in seen or e['label'] not in LABELS or e['start'] < end
                or not 0 <= e['start'] < e['end'] <= len(row['text'])
                or row['text'][e['start']:e['end']] != e['text']):
            raise ValueError('Entity binding/overlap: ' + row['arxivId'] + ':' + e['entityId'])
        seen.add(e['entityId'])
        end = e['end']


def revise(row: dict, decision: dict) -> tuple[dict, list[dict]]:
    row = copy.deepcopy(row)
    old = {e['entityId']: copy.deepcopy(e) for e in row['entities']}
    current = copy.deepcopy(old)
    for eid in decision.get('remove', []):
        current.pop(eid)
    for r in decision.get('relabel', []):
        for eid in r['ids']:
            current[eid]['label'] = r['label']
            current[eid]['provenance'] = 'ai_whole_abstract_review_textscope_v2'
    for r in decision.get('replace', []):
        before = current[r['id']]
        hits = [m for m in re.finditer(re.escape(r['text']), row['text'])
                if m.start() <= before['start'] and before['end'] <= m.end()]
        if len(hits) != 1:
            raise ValueError('Replacement is not uniquely attached: ' + row['arxivId'] + ':' + r['id'])
        m = hits[0]
        current[r['id']] = {**before, 'start': m.start(), 'end': m.end(), 'text': m.group(),
                              'label': r.get('label', before['label']),
                              'provenance': 'ai_whole_abstract_review_textscope_v2'}
    next_id = max((int(eid[1:]) for eid in old), default=0) + 1
    urls = [m.span() for m in re.finditer(r'https?://\S+', row['text'])]
    for label, literals in decision.get('add', {}).items():
        for literal in literals:
            hits = list(re.finditer(r'(?<!\w)' + re.escape(literal) + r'(?!\w)', row['text']))
            if not hits:
                raise ValueError('Addition literal missing: ' + row['arxivId'] + ':' + literal)
            for m in hits:
                if any(a <= m.start() < b for a, b in urls):
                    continue
                if any(m.start() < e['end'] and e['start'] < m.end() for e in current.values()):
                    # Declared flat scope: a contained mention is not a second nested entity.
                    continue
                current[f'e{next_id}'] = {'entityId': f'e{next_id}', 'start': m.start(), 'end': m.end(),
                                         'text': m.group(), 'label': label,
                                         'provenance': 'ai_whole_abstract_review_textscope_v2'}
                next_id += 1
    row['entities'] = sorted(current.values(), key=lambda e: (e['start'], e['end']))
    row.setdefault('sampleId', 'v2-dev-' + sha((row['arxivId'] + row['textSha256']).encode())[:20])
    row.update(labelSource='codex_ai_source_read_weak_reference',
               annotationStatus='source_read_review_pending_user_acceptance',
               referenceComplete=True, independentHumanGold=False,
               trainingAuthorized=False, evaluationAuthorized=False,
               sourceReviewReason=decision['reason'],
               entityScope='flat_contiguous_named_method_task_dataset_priority_no_url_no_title')
    validate(row)
    events = [{'arxivId': row['arxivId'], 'split': row['split'], 'entityId': eid,
               'before': old.get(eid), 'after': current.get(eid), 'reason': decision['reason']}
              for eid in sorted(set(old) | set(current)) if old.get(eid) != current.get(eid)]
    if [e['entityId'] for e in row['entities'] if e['entityId'] in old] != [e['entityId'] for e in old.values() if e['entityId'] in current]:
        events.append({'arxivId': row['arxivId'], 'split': row['split'], 'action': 'SORT_BY_START_END',
                       'before': list(old), 'after': [e['entityId'] for e in row['entities']],
                       'reason': 'Actual SciBERT BIO encoder requires source-ordered entities.'})
    return row, events


def select(row: dict, selectors: list[str]) -> list[dict]:
    result = []
    for selector in selectors:
        matches = [e for e in row['entities'] if
                   (selector.startswith('$') and e['label'] == selector[1:])
                   or e['entityId'] == selector or e['text'].casefold() == selector.casefold()]
        if not matches:
            raise ValueError(f"Empty selector {row['arxivId']}: {selector}")
        for e in matches:
            if e not in result:
                result.append(e)
    return result


def relation_key(r: dict):
    return r['arxivId'], r['head']['entityId'], r['tail']['entityId']


def adjudicate(row: dict, decision: dict, previous: list[dict], retain: bool) -> list[dict]:
    em = {e['entityId']: e for e in row['entities']}
    known = {}
    if retain:
        for old in previous:
            q = copy.deepcopy(old)
            q['head'], q['tail'] = copy.deepcopy(em[old['head']['entityId']]), copy.deepcopy(em[old['tail']['entityId']])
            q['sourceReviewDecision'] = 'Retained after complete-source read: ' + decision['reason']
            q['negativeBasis'] = None
            known[(q['head']['entityId'], q['tail']['entityId'])] = q
    for index, rule in enumerate(decision.get('rules', [])):
        proof = span(row['text'], rule['evidence']) if 'evidence' in rule else None
        for h, t in itertools.product(select(row, rule['heads']), select(row, rule['tails'])):
            label = rule['label']
            if h['label'] != 'METHOD' or t['label'] not in {'TASK', 'DATASET'}:
                raise ValueError('Invalid rule endpoint: ' + row['arxivId'])
            if label in {'USED_FOR', 'EVALUATED_ON'} and t['label'] != {'USED_FOR': 'TASK', 'EVALUATED_ON': 'DATASET'}[label]:
                raise ValueError('Invalid positive schema')
            key = h['entityId'], t['entityId']
            if key in known and known[key]['label'] == label and retain:
                # Preserve earlier minimal predicates/coreference rather than replacing them with a looser new scope.
                known[key]['sourceReviewDecision'] = decision['reason'] + ' | ' + rule.get('reason', rule.get('evidence', ''))
                continue
            if label in {'NO_RELATION', 'UNRESOLVED'} and not rule.get('reason'):
                raise ValueError('Non-positive ruling must have source-specific rationale')
            actor_in_proof = bool(proof and h['start'] >= proof['start'] and h['end'] <= proof['end'])
            target_in_proof = bool(proof and t['start'] >= proof['start'] and t['end'] <= proof['end'])
            known[key] = {
                'head': copy.deepcopy(h), 'tail': copy.deepcopy(t), 'label': label,
                'evidence': proof,
                'contextEvidence': [dict(h, role='actor_mention'), dict(t, role='target_mention')],
                'relationEvidenceLevel': 'direct' if actor_in_proof and target_in_proof else 'discourse_inferred',
                'reason': rule.get('reason', decision['reason']),
                'taskRole': rule.get('role'),
                'supportGroup': row['arxivId'] + ':textscope:' + sha((str(index) + ':' + t['text'].casefold() + ':' + label).encode())[:12],
                'negativeBasis': 'REVIEWED_NOT_EXPRESSED_IN_WHOLE_ABSTRACT' if label == 'NO_RELATION' else None,
                'sourceReviewDecision': decision['reason'],
                'decisionRule': f"{row['split']}:{row['arxivId']}:{index}"
            }
    result = []
    for h, t in itertools.product(row['entities'], repeat=2):
        if h['label'] != 'METHOD' or t['label'] not in {'TASK', 'DATASET'}:
            continue
        q = known.get((h['entityId'], t['entityId']))
        if q is None:
            q = {'head': copy.deepcopy(h), 'tail': copy.deepcopy(t), 'label': 'UNRESOLVED',
                 'evidence': None, 'contextEvidence': [dict(h, role='actor_mention'), dict(t, role='target_mention')],
                 'reason': decision.get('unresolvedReason',
                     'Complete-source review does not settle this class/instance, component/whole, or discourse attribution. ' + decision['reason']),
                 'negativeBasis': None, 'supportGroup': None, 'decisionRule': 'source_read_masked_remainder'}
        q = copy.deepcopy(q)
        q.update({k: row[k] for k in ['arxivId', 'sampleId', 'publicationId', 'groupId', 'sourceURL', 'split', 'text', 'textSha256', 'textKind']})
        q.update(pairId=row['sampleId'] + ':' + h['entityId'] + ':' + t['entityId'],
                 labelSource='codex_ai_source_read_weak_reference', independentHumanGold=False,
                 annotationStatus='adjudicated_pending_user_acceptance',
                 adjudicated=True, trainingAuthorized=False, evaluationAuthorized=False,
                 masked=q['label'] == 'UNRESOLVED', referenceComplete=q['label'] != 'UNRESOLVED',
                 scopeVersion='whole_abstract_expressed_relation_v2')
        result.append(q)
    if len({relation_key(r) for r in result}) != len(result):
        raise ValueError('Duplicate pair')
    return result


def csv_bytes(rows: list[dict], columns: list[str]) -> bytes:
    buffer = io.StringIO(newline='')
    w = csv.DictWriter(buffer, fieldnames=columns, extrasaction='ignore')
    w.writeheader()
    w.writerows(rows)
    return ('\ufeff' + buffer.getvalue()).encode('utf-8')


def review_html(docs: list[dict], pairs: list[dict], summary: dict) -> bytes:
    esc = html.escape
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>V2 训练65 + 验证20 · 原文审核</title>',
             '<style>body{font:16px/1.7 system-ui;margin:24px auto;max-width:1350px;padding:20px;background:#f3f6fa;color:#17212f}article{background:#fff;margin:25px 0;padding:22px;border-radius:12px}mark{padding:2px;border-radius:3px}.METHOD{background:#cce7ff}.TASK{background:#dcf5d5}.DATASET{background:#ffe5bd}.warning{background:#fff0d1;padding:18px;border-left:5px solid #b66c00}table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #dae2ec;padding:7px;vertical-align:top}pre{white-space:pre-wrap}summary{cursor:pointer}input,select{font:inherit;padding:8px;margin:8px}tr[data-label="UNRESOLVED"]{color:#657286}.negative{color:#9c2525}.abstract{line-height:2.1;white-space:pre-wrap}</style>',
             '<h1>V2 训练65 / 验证20 · 可核对原文标注</h1><p class="warning">这是 AI 源文复核，不是独立人工金标准。负例只表示完整摘要范围内未表达该关系，不否定现实世界或全文关系。未决项继续掩码；没有训练、推理或新 F1，test20 正文未读取。先审核本包，再批准一次微调。</p>',
             '<p>METHOD 蓝色 / TASK 绿色 / DATASET 橙色。证据为原文连续跨度；跨句/别名仍是 AI 归属解释。</p>',
             '<input id="search" placeholder="搜索论文 ID 或原文"><select id="label"><option value="ALL">所有关系</option><option>NO_RELATION</option><option>USED_FOR</option><option>EVALUATED_ON</option><option>UNRESOLVED</option></select>',
             '<pre>' + esc(json.dumps(summary, ensure_ascii=False, indent=2)) + '</pre>']
    for d in docs:
        aid = d['arxivId']; dp = [p for p in pairs if p['arxivId'] == aid]; text_parts=[]; cursor=0
        for e in d['entities']:
            text_parts.append(esc(d['text'][cursor:e['start']]))
            text_parts.append('<mark class="' + e['label'] + '" title="' + esc(f"{e['entityId']} {e['start']}:{e['end']}") + '">' + esc(e['text']) + '</mark>')
            cursor=e['end']
        text_parts.append(esc(d['text'][cursor:]))
        parts += ['<article><h2>' + esc(d['split'] + ' · ' + aid) + '</h2><p>' + esc(d['sourceReviewReason']) + '</p>',
                  '<div class="abstract">' + ''.join(text_parts) + '</div><details><summary>全部候选对 · ' + str(len(dp)) + ' · ' + esc(str(dict(Counter(p['label'] for p in dp)))) + '</summary>',
                  '<table><thead><tr><th>头 → 尾</th><th>标签</th><th>证据 / 摘要范围判定</th></tr></thead><tbody>']
        for p in dp:
            evidence = p.get('evidence') or {}
            proof = evidence.get('text', '无确定归属，保留掩码')
            parts.append('<tr data-label="' + p['label'] + '"><td>' + esc(p['head']['entityId'] + ' ' + p['head']['text'] + ' → ' + p['tail']['entityId'] + ' ' + p['tail']['text']) + '</td><td>' + p['label'] + '</td><td>' + esc(proof) + '<br>' + esc(p.get('reason', p.get('sourceReviewDecision',''))) + '</td></tr>')
        parts += ['</tbody></table></details></article>']
    parts.append('<script>const run=()=>{const s=document.querySelector("#search").value.toLowerCase(),l=document.querySelector("#label").value;document.querySelectorAll("article").forEach(a=>a.hidden=!a.textContent.toLowerCase().includes(s));document.querySelectorAll("tr[data-label]").forEach(r=>r.hidden=l!=="ALL"&&r.dataset.label!==l)};document.querySelector("#search").addEventListener("input",run);document.querySelector("#label").addEventListener("change",run);</script></html>')
    return ''.join(parts).encode('utf-8')


def main():
    if OUTPUT.exists():
        raise FileExistsError('Preserve previous output: ' + str(OUTPUT))
    inputs = {str(INPUT_ZIP): INPUT_ZIP.read_bytes(), str(ROSTER): ROSTER.read_bytes(),
              str(Path(__file__).resolve()): Path(__file__).read_bytes(),
              str(ROOT/'scripts/course_v2_textscope_metrics.py'): (ROOT/'scripts/course_v2_textscope_metrics.py').read_bytes()}
    if sha(inputs[str(INPUT_ZIP)]) != EXPECTED_ZIP_SHA:
        raise ValueError('Reviewed parent ZIP changed')
    with zipfile.ZipFile(INPUT_ZIP) as z:
        m=json.loads(z.read('revised/manifest.json'))
        for name, digest in m['files'].items():
            if sha(z.read('revised/' + name)) != digest:
                raise ValueError('Parent ZIP member hash mismatch')
        train=jl(z.read('revised/train65_ner_candidates.jsonl'))
        train_previous=jl(z.read('revised/train65_positive_candidates.jsonl'))
    for name in ['dev20_ner_ai_draft.jsonl', 'dev20_re_positive_ai_draft.jsonl']:
        p=DEV_BASE / name; inputs[str(p)] = p.read_bytes()
    dev=jl(inputs[str(DEV_BASE/'dev20_ner_ai_draft.jsonl')])
    dev_previous=jl(inputs[str(DEV_BASE/'dev20_re_positive_ai_draft.jsonl')])
    books={}
    for split, count in [('train',65),('dev',20)]:
        p=DECISIONS / f'{split}{count}_textscope_review_20261011.json'
        inputs[str(p)] = p.read_bytes(); book=json.loads(inputs[str(p)])
        books[split]={d['arxivId']:d for d in book['documents']}
    roster=json.loads(inputs[str(ROSTER)])
    if {d['arxivId'] for d in dev} != {r['arxivId'] for r in roster if r['split']=='dev'}:
        raise ValueError('Fixed dev roster mismatch')
    if {d['arxivId'] for d in train} & {r['arxivId'] for r in roster}:
        raise ValueError('Train/dev/test identity collision')
    all_docs=[]; all_pairs=[]; events=[]; relation_changes=[]
    for split, rows, previous in [('train',train,train_previous),('dev',dev,dev_previous)]:
        if len(rows) != {'train':65,'dev':20}[split] or set(books[split]) != {d['arxivId'] for d in rows}:
            raise ValueError('Source-read decisions do not cover the exact roster')
        for original in rows:
            d, changes=revise(original,books[split][original['arxivId']]); events.extend(changes)
            old=[r for r in previous if r['arxivId']==d['arxivId']]
            ps=adjudicate(d,books[split][d['arxivId']],old,split=='train')
            d['relationReferenceComplete']=not any(p['masked'] for p in ps)
            d['relationAdjudicationComplete']=True
            all_docs.append(d); all_pairs.extend(ps)
            current={relation_key(r):r for r in ps}
            for r in old:
                q=current.get(relation_key(r)); now=q['label'] if q else 'ENDPOINT_REMOVED_OR_RETYPED'
                if now != r['label']:
                    relation_changes.append({'action':'REVISE_OR_MASK_OLD_POSITIVE','arxivId':d['arxivId'],'split':split,
                                             'before':r,'after':q,'reason':books[split][d['arxivId']]['reason']})
            oldkeys={relation_key(r) for r in old}
            for r in ps:
                if r['label']!='UNRESOLVED' and relation_key(r) not in oldkeys:
                    relation_changes.append({'action':'SOURCE_READ_NEW_ADJUDICATION','arxivId':d['arxivId'],'split':split,
                                             'after':{k:v for k,v in r.items() if k!='text'},'reason':r.get('reason',r.get('sourceReviewDecision'))})
    protected=[('1903.10404',h,'e4') for h in ['e1','e7','e9']]+[('2503.03790','e11','e14'),('2503.03790','e13','e12')]
    lookup={relation_key(p):p for p in all_pairs}
    if any(lookup[k]['label']!='UNRESOLVED' for k in protected):
        raise ValueError('Historical ambiguous role-contrast pairs must remain masked')
    # This is encoding validation only. No model weights, prediction, gradients or optimizer are loaded.
    import train_course_ner as ner
    import train_course_relation as relation
    tokenizer=relation.prepare_tokenizer(ROOT/'kg_datasets/models/scibert_24f92d32')
    max_ner=max_re=0
    for d in all_docs:
        enc=ner.encode_row(tokenizer,d,512); max_ner=max(max_ner,len(enc['features']['input_ids']))
        dec=ner.decode_bio([0 if x==-100 else x for x in enc['features']['labels']],enc['offsets'],d['text'])
        keys=lambda es:sorted((e['start'],e['end'],e['label'],e['text']) for e in es)
        if keys(dec['entities'])!=keys(d['entities']) or dec['invalidTransitions']:
            raise ValueError('BIO roundtrip changed entity boundaries: '+d['arxivId'])
    for p in all_pairs:
        if not p['masked']:
            enc=relation.encode_pair(tokenizer,p,512); max_re=max(max_re,len(enc['features']['input_ids']))
    summary={'version':'whole_abstract_expressed_relation_v2_review_20261011',
             'labelSource':'AI source-read weak reference pending user acceptance','trainingExecuted':False,
             'modelWeightsLoaded':False,'newF1':None,'testBodyRead':False,'productionModified':False,
             'trainingAuthorized':False,'relationAdjudicationComplete':True,
             'historicalFiveAmbiguousPairsStillMasked':True,'splits':{},
             'encoding':{'documentsPassed':len(all_docs),'scoredPairsPassed':sum(not p['masked'] for p in all_pairs),
                         'maxNERtokens':max_ner,'maxREtokens':max_re,'truncation':False}}
    payload={}
    for split in ['train','dev']:
        ds=[d for d in all_docs if d['split']==split]; ps=[p for p in all_pairs if p['split']==split]
        counts=Counter(p['label'] for p in ps)
        summary['splits'][split]={'documents':len(ds),'entities':sum(len(d['entities']) for d in ds),
            'entityLabels':dict(Counter(e['label'] for d in ds for e in d['entities'])),
            'pairLabels':dict(counts),'legalPairs':len(ps),'scoredPairs':sum(not p['masked'] for p in ps),
            'scoredPairCoverage':sum(not p['masked'] for p in ps)/len(ps) if ps else 1.0,
            'fullyScorableRelationDocuments':sum(d['relationReferenceComplete'] for d in ds),
            'sourcesByLabel':{l:len({p['arxivId'] for p in ps if p['label']==l}) for l in ['USED_FOR','EVALUATED_ON','NO_RELATION']},
            'distinctEvidenceScopes':len({(p['arxivId'],p['label'],(p.get('evidence') or {}).get('start'),(p.get('evidence') or {}).get('end')) for p in ps if not p['masked']}),
            'relationReferenceComplete':counts['UNRESOLVED']==0}
        payload[f'{split}_ner.jsonl']=jlb(ds)
        payload[f'{split}_re_scored.jsonl']=jlb([p for p in ps if not p['masked']])
        payload[f'{split}_all_pairs.jsonl']=jlb(ps)
        payload[f'{split}_members.json']=jb([{k:d[k] for k in ['arxivId','publicationId','groupId','sampleId','textSha256','split']} for d in ds])
    protocol={
        'version':'whole_abstract_expressed_relation_v2','parentProtocolUnchanged':'resources/course_v2_supervision_protocol_v1.json',
        'userRequestedChange':'Review complete abstracts; NO_RELATION may mean an explicitly adjudicated absence of the target relation in that source, without requiring an explicit denial sentence.',
        'positiveSchema':{'USED_FOR':'METHOD -> TASK, with source-local actor/predicate attribution and declared purpose role.',
                          'EVALUATED_ON':'METHOD -> DATASET, attributed evaluation; use as construction/training data is not itself evaluation.'},
        'NO_RELATION':'An explicit per-document source-read rule confirms that the whole abstract does not express the positive relation for these endpoints, after checking actor/object role, aliases, pronouns and context. Not a full-text or real-world denial.',
        'UNRESOLVED':'Uncertain implicit contribution, component/whole transfer, or class/instance/coreference remains masked. No bulk conversion, including the five protected historical contrasts.',
        'entityScope':'Flat contiguous METHOD/TASK/DATASET; no entities from titles or URLs; named-entity overlaps are not duplicated. Shared-object coordinated tasks may stay one continuous span; no character-length deletion rule.',
        'weakReference':True,'independentHumanGold':False,'reviewCompletedBy':'AI, not independent verification',
        'trainRosterSize':65,'devRosterSize':20,'testRosterSize':20,
        'testTextRead':False,'trainingAllowed':False,'automaticPromotionAllowed':False,
        'evaluation':'Strict NER relative to this AI reference. RE reports scored-scope P/R/F1, masked prediction counts, coverage and conservative full-universe bounds; partial-reference scores are not complete end-to-end F1.',
        'nextAction':'User reviews labels and accepts this snapshot; then explicitly authorize one SciBERT exploratory run with frozen train/dev identities and test text sealed.'}
    payload['protocol.json']=jb(protocol)
    payload['entity_revision_ledger.jsonl']=jlb(events)
    payload['relation_revision_ledger.jsonl']=jlb(relation_changes)
    payload['summary.json']=jb(summary)
    payload['training_plan.json']=jb({'status':'awaiting_user_label_review','model':'allenai/scibert_scivocab_uncased',
        'revision':'24f92d32b1bfb0bcaf9ab193ff3ad01e87732fc1','maxLength':512,'seed':20261011,
        'architecture':{'NER':'SciBERT + BIO classifier','RE':'SciBERT + existing entity-marker classifier, three classes'},
        'train':'train_ner.jsonl / train_re_scored.jsonl','dev':'dev_ner.jsonl / dev_re_scored.jsonl',
        'unknownPairs':'excluded from loss, counted as masked during scoring',
        'sampling':'one mention per source/evidence-group per epoch; rotate aliases deterministically; report selected class counts',
        'selection':'fixed dev only; NER strict F1, RE scored-scope F1 with coverage/bounds; do not call this a formal complete-pipeline improvement',
        'stop':'one exploratory run per NER/RE; no test-informed tuning; production remains unchanged',
        'trainingAuthorized':False})
    review_rows=[]
    for p in all_pairs:
        proof=p.get('evidence') or {}
        review_rows.append({'split':p['split'],'arxivId':p['arxivId'],'headId':p['head']['entityId'],'head':p['head']['text'],
                           'tailId':p['tail']['entityId'],'tail':p['tail']['text'],'label':p['label'],'masked':p['masked'],
                           'evidenceStart':proof.get('start'),'evidenceEnd':proof.get('end'),'evidence':proof.get('text',''),
                           'negativeBasis':p.get('negativeBasis'),'reason':p.get('reason',p.get('sourceReviewDecision'))})
    payload['relation_review.csv']=csv_bytes(review_rows,list(review_rows[0]))
    payload['negative_review.csv']=csv_bytes([r for r in review_rows if r['label']=='NO_RELATION'],list(review_rows[0]))
    payload['review85.html']=review_html(all_docs,all_pairs,summary)
    payload['build_v2_textscope_review.py']=inputs[str(Path(__file__).resolve())]
    payload['course_v2_textscope_metrics.py']=inputs[str(ROOT/'scripts/course_v2_textscope_metrics.py')]
    for split,count in [('train',65),('dev',20)]:
        payload[f'{split}{count}_source_read_decisions.json']=inputs[str(DECISIONS/f'{split}{count}_textscope_review_20261011.json')]
    note='# V2 训练65 + 验证20：摘要表达关系审核包\n\n这是 AI 原文复核工作集；保留旧版本，不训练、不读 test20、不修改生产。\n\n'
    note+='新的 NO_RELATION 只表示完整摘要范围内经逐篇裁决未表达该关系；它与旧版“必须明确否定”不是同一个任务口径。未决项不作负例。\n\n'
    note+='先打开 review85.html；negative_review.csv 可集中审核负例；relation_review.csv 含全部候选对。JSONL 可供现有 SciBERT 编码函数直接读取。\n\n'
    note+='65 篇训练身份已经在本实验 train_members.json 中固定，dev20 与既有固定名单一致。旧12篇身份锁未改；这里是新的65篇实验快照，不声称旧锁自动批准了新增论文。\n\n'
    note+='NER 实体列表已排序并通过实际 BIO 往返编码；RE 已判样本均通过实际实体标记编码，无截断、无权重加载。\n\n'
    note+='## 评测边界\n\n每个候选对都有裁决：正例、摘要范围负例或不确定掩码。裁决完成不等于所有参考确定。仍有掩码时，只能报告已裁决范围的条件分数、覆盖率、未知预测数和完整总体上下界，不能报告完整端到端 F1。\n\n'
    note+='test20 正文仍封存。先审核/接受本快照，再启动一次探索性训练；AI 参考不是独立人工金标准，编码通过不意味着语义正确或模型准确率提升。\n\n'
    note+='## 统计\n\n```json\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n```\n'
    payload['README.md']=note.encode('utf-8')
    inputs_sha={p:sha(b) for p,b in inputs.items()}
    if any(sha(Path(p).read_bytes())!=h for p,h in inputs_sha.items()):
        raise ValueError('Input changed during preparation')
    manifest={'version':summary['version'],'inputs':inputs_sha,'files':{n:sha(b) for n,b in payload.items()},
              'trainCohortSha256':sha(payload['train_members.json']),'devCohortSha256':sha(payload['dev_members.json']),
              'trainingAuthorized':False,'testBodyRead':False,'productionModified':False}
    payload['manifest.json']=jb(manifest)
    OUTPUT.mkdir(parents=True)
    for name,data in payload.items():
        (OUTPUT/name).write_bytes(data)
    archive=ROOT/'outputs/v2_train65_dev20_textscope_review_20261011_final.zip'
    if archive.exists():
        raise FileExistsError('Existing review archive')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in payload.items():
            z.writestr('v2_train65_dev20_textscope_review_20261011/'+name,data)
    print(json.dumps({'output':str(OUTPUT),'archive':str(archive),'archiveSha256':sha(archive.read_bytes()),'summary':summary},ensure_ascii=True))


if __name__=='__main__':
    main()

"""Preserve v2 and AI source files; build v3 policy fixtures and genuinely blank human-review inputs."""
import argparse
import copy
import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from annotation_v3 import ROOT, SCHEMA, SCHEMA_SHA256, RULES, RULES_SHA256, new_review, read_jsonl, span_error, validate_records
from prepare_ner import digest, write_json, write_jsonl
from prepare_revision_v2 import safe_json

SOURCE_FILES = {'pilot20_boundary_review.json':'source_review_sha256',
                'pilot20_boundary_review.csv':'source_csv_sha256',
                'AI-Literature-KG-pilot20-boundary-review.md':'source_markdown_sha256'}


def import_stress_review(source, previous):
    for name, key in SOURCE_FILES.items():
        if digest(source / name) != RULES[key]:
            raise ValueError('Preserved stress source hash mismatch: ' + name)
    if digest(previous / 'blind_50_reference.jsonl') != RULES['source_blind_reference_sha256']:
        raise ValueError('Independent blind reference hash mismatch')
    review = json.loads((source / 'pilot20_boundary_review.json').read_text(encoding='utf-8-sig'))
    if review['status'] != 'independent_rule_stress_test_not_human_gold':
        raise ValueError('Source must retain explicit AI-not-human status')
    blind = read_jsonl(previous / 'blind_50_reference.jsonl')
    pilot = {r['publicationId']:r for r in read_jsonl(previous / 'pilot_200.jsonl')}
    with (source / 'pilot20_boundary_review.csv').open(encoding='utf-8-sig', newline='') as stream:
        csv_rows = list(csv.DictReader(stream))
    if len(csv_rows) != len(review['items']) or len({r['publicationId'] for r in csv_rows}) != len(csv_rows):
        raise ValueError('CSV review IDs/count mismatch')
    csv_by_id = {r['publicationId']:r for r in csv_rows}
    counts, baseline, matched, seen = Counter(), 0, 0, set()
    for item in review['items']:
        pid, index = item['publicationId'], item['blind_index']
        if pid in seen or type(index) is not int or not 1 <= index <= len(blind):
            raise ValueError('Duplicate review ID or invalid blind index')
        seen.add(pid)
        reference = blind[index-1]
        if reference['publicationId'] != pid or reference['text'] != item['title'] or reference['intendedSplit'] != 'train':
            raise ValueError('Review source differs from training-side blind reference')
        actual = [{k:e[k] for k in ('start','end','text','label')} for e in pilot[pid]['entities']]
        if actual != item['current_draft_entities']:
            raise ValueError('Submitted baseline differs from independent v2 pilot')
        row = csv_by_id.get(pid)
        if row is None or row['title'] != item['title'] or int(row['blind_index']) != index or row['boundary_review'] != item['boundary_review']:
            raise ValueError('CSV and JSON basic review fields disagree')
        def view(entities, confidence=False):
            return '; '.join(f"{e['label']}[{e['start']},{e['end']}): {e['text']}" + (f" ({e['confidence']})" if confidence else '') for e in entities) or 'NONE'
        if row['proposed_entities'] != view(item['proposed_entities'], True) or row['current_draft_entities'] != view(actual):
            raise ValueError('CSV and JSON entity views disagree')
        baseline += len(actual)
        keys = {(e['start'],e['end'],e['label']) for e in actual}
        end = 0
        for e in item['proposed_entities']:
            if span_error(e, item['title']) or e['start'] < end or e['label'] not in SCHEMA['$defs']['entity']['properties']['label']['enum']:
                raise ValueError('Invalid source proposal span/order/label')
            end = e['end']
            counts[e['label']] += 1
            matched += (e['start'],e['end'],e['label']) in keys
    if {r['blind_index'] for r in review['items']} != {r['blind_index'] for r in RULES['case_decisions']}:
        raise ValueError('Policy fixture case set differs from source')
    return {'items':review['items'],'stats':{'documents':len(seen),'proposed_entities':sum(counts.values()),
            'proposed_by_label':dict(counts),'baseline_entities':baseline,'strict_matches':matched}}


def convert_record(old, source_hash):
    if any(old[name]['status'] != 'draft' for name in ('entity_review','relation_review','domain_review')):
        raise ValueError('Do not silently migrate actual reviewed progress')
    if old['notes'] or any(e['origin']=='human' for e in old['entities']) or any(d['origin']=='human' for d in old['domains']):
        raise ValueError('Human edits require explicit migration, not draft regeneration')
    row = copy.deepcopy(old)
    row.update(schemaVersion=SCHEMA['properties']['schemaVersion']['const'], schemaSha256=SCHEMA_SHA256,
               boundaryRulesSha256=RULES_SHA256,
               initialDraftProvenance={'kind':'dictionary','inputReferenceSha256':source_hash,'aiReviewSha256':None})
    for e in row['entities']:
        e.update(origin='draft_dictionary_v3', mentionForm='single')
    for d in row['domains']:
        d['origin']='draft_dictionary_v3'
    return row


def apply_case_decision(original, item, decision):
    row = copy.deepcopy(original)
    proposals = decision.get('replace_entities', item['proposed_entities'])
    if len(proposals) != len(decision['forms']):
        raise ValueError('Decision forms must cover all proposal spans')
    row['entities'] = [{**{k:e[k] for k in ('start','end','text','label')}, 'origin':'ai_suggestion','mentionForm':form}
                       for e,form in zip(proposals, decision['forms'])]
    row['initialDraftProvenance'].update(kind='ai_rule_stress_test',aiReviewSha256=RULES['source_review_sha256'])
    row['relations']=[]
    for field in ('entity_review','relation_review','domain_review'):
        row[field]=new_review()
    row['notes']='AI压力测试候选，非人工gold。' + item['boundary_review'] + '\n候选政策：' + decision.get('note','按v3边界规则保留候选；需真实人工复核。')
    if not validate_records([row])['valid']:
        raise ValueError('Invalid adopted policy fixture')
    return row


def make_blind(original, source_hash):
    row = copy.deepcopy(original)
    row['entities'],row['domains'],row['relations'],row['notes']=[],[],[],''
    row['initialDraftProvenance']={'kind':'blind','inputReferenceSha256':source_hash,'aiReviewSha256':None}
    for field in ('entity_review','relation_review','domain_review'):
        row[field]=new_review()
    return row


def render_page(rows, *, title, download, blind=False):
    return ((ROOT / 'docs/review_v3_template.html').read_text(encoding='utf-8')
            .replace('__PILOT_JSON__',safe_json(rows)).replace('__SCHEMA_JSON__',safe_json(SCHEMA))
            .replace('__PAGE_JSON__',safe_json({'title':title,'download':download,'blind':blind,'schemaSha256':SCHEMA_SHA256}))
            .replace('__REVIEW_JS__',(ROOT / 'docs/review_v3.js').read_text(encoding='utf-8')))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-data',type=Path,default=ROOT / 'kg_datasets/dblp/ner_v2_1')
    parser.add_argument('--review-dir',type=Path,default=Path('D:/Users/Y7000P/Downloads'))
    parser.add_argument('--output',type=Path,default=ROOT / 'kg_datasets/dblp/ner_v3')
    args=parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Preserve prior artifacts; choose a new output version')
    source = import_stress_review(args.review_dir,args.previous_data)
    pilot_hash=digest(args.previous_data / 'pilot_200.jsonl')
    pilot=[convert_record(r,pilot_hash) for r in read_jsonl(args.previous_data / 'pilot_200.jsonl')]
    by_id={r['publicationId']:r for r in pilot}
    decisions={r['blind_index']:r for r in RULES['case_decisions']}
    adopted=[]
    for item in source['items']:
        row=apply_case_decision(by_id[item['publicationId']],item,decisions[item['blind_index']])
        by_id[row['publicationId']]=row
        adopted.append(row)
    pilot=[by_id[r['publicationId']] for r in pilot]
    rare_hash=digest(args.previous_data / 'rare_candidates_train.jsonl')
    rare=[convert_record(r,rare_hash) for r in read_jsonl(args.previous_data / 'rare_candidates_train.jsonl')]
    blind_hash=digest(args.previous_data / 'blind_50_reference.jsonl')
    blind=[make_blind(convert_record(r,blind_hash),blind_hash) for r in read_jsonl(args.previous_data / 'blind_50_reference.jsonl')]
    blank_by_id={r['publicationId']:r for r in blind}
    blind20=[blank_by_id[r['publicationId']] for r in adopted]
    groups=[pilot,rare,blind,adopted,blind20]
    if not all(validate_records(rows,reference=rows)['valid'] for rows in groups):
        raise ValueError('Invalid generated v3 draft package')
    args.output.mkdir(parents=True)
    (args.output / 'source_review').mkdir()
    for name in SOURCE_FILES:
        shutil.copy2(args.review_dir / name,args.output / 'source_review' / name)
    (args.output / 'legacy_reference').mkdir()
    for name in ('pilot_200.jsonl','blind_50_reference.jsonl','rare_candidates_train.jsonl'):
        shutil.copy2(args.previous_data / name,args.output / 'legacy_reference' / name)
    for name,rows in (('pilot_200.jsonl',pilot),('rare_candidates_train.jsonl',rare),('blind_50_reference.jsonl',blind),
                      ('pilot20_ai_candidates.jsonl',adopted),('pilot20_blind_reference.jsonl',blind20)):
        write_jsonl(args.output / name,rows)
    for name,rows,title,blank in [('pilot_review.html',pilot,'v3 · 200篇候选试标',False),
        ('rare_review.html',rare,'v3 · 100篇训练侧稀有候选',False),('blind_50_a.html',blind,'v3 · 50篇独立盲标A',True),
        ('blind_50_b.html',blind,'v3 · 50篇独立盲标B',True),('pilot20_ai_review.html',adopted,'v3 · 20篇AI压力测试候选（非gold）',False),
        ('pilot20_blind_review.html',blind20,'v3 · 20篇空白人工试标（无AI答案）',True)]:
        (args.output / name).write_text(render_page(rows,title=title,download=name.removesuffix('.html')+'_progress.jsonl',blind=blank),encoding='utf-8')
    write_json(args.output / 'boundary_decisions.json',RULES)
    summary={'status':'candidate_pending_human_pilot','source_review':source['stats'],
             'adopted_candidates':validate_records(adopted,reference=adopted),
             'pilot':validate_records(pilot,reference=pilot),'rare':validate_records(rare,reference=rare),
             'blank20':len(blind20),'blank50':len(blind),'human_completed':0,'training_started':False,
             'changed_case':6,'change_notice':'46 source proposals retained; 45 policy candidates after composite merge, not semantic accuracy/F1',
             'limitations':['Only 20 deliberately selected training-side cases; no population accuracy or model F1',
                            'The unchanged dictionary remains incomplete on the other titles',
                            'No human gold, no scope freeze, no automatic canonical split or graph write']}
    write_json(args.output / 'summary.json',summary)
    write_json(args.output / 'manifest.json',{'generated_at_utc':datetime.now(UTC).isoformat(),'schema_sha256':SCHEMA_SHA256,
          'rules_sha256':RULES_SHA256,'status':'candidate','outputs_sha256':{p.relative_to(args.output).as_posix():digest(p) for p in sorted(args.output.rglob('*')) if p.is_file()}})
    print(json.dumps({'pilot':len(pilot),'ai_cases':len(adopted),'source_spans':source['stats']['proposed_entities'],
                     'adopted_spans':sum(len(r['entities']) for r in adopted),'blind20':len(blind20)},ensure_ascii=False))


if __name__=='__main__':
    main()

"""Frozen title-only NER->RE batch inference; no labels, fitting, scoring or DB writes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_weak as c
import train_course_ner as ner
import train_course_relation as relation
from evaluate_course_relation import candidate_rows, predict

ROOT = Path(__file__).resolve().parents[1]
WEAK = ROOT / 'kg_datasets/dblp/course_v4_weak'
CACHE_NER = ROOT / 'kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09'
CACHE_RE = ROOT / 'kg_datasets/dblp/course_v4_runs/re_final_test_20261006_17'
LOCK_SHA = {'ner':'cf30fe489da3eb4aa22c309687e86fc711b9db564586d371e4792be8902ba96d',
            're':'e4010d162f525221de7da30cf4c412892564a1da894d1271a72f1ddfa1893978'}
CACHE_SHA = {CACHE_NER:'0e64965da7f521cebded4bf01afc6cfe3d40aeb84685bec5e1fce9d56d1a1602',
             CACHE_RE:'ce9697e286c4532d9e6b18b114b7d96eae65432e5b4f3cadfbc4629b0d4191af'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def load_sources():
    manifest = ner.verify_files(WEAK)
    publication_file = ROOT / 'kg_datasets/dblp/processed_ai/publications.csv'
    if c.file_sha256(publication_file)!=manifest['inputSha256'][publication_file.relative_to(ROOT).as_posix()]:
        raise ValueError('Bibliography differs from sealed corpus')
    splits = c.read_jsonl(WEAK / 'corpus_split_manifest.jsonl')
    groups = {r['publicationId']:r for r in splits}
    refs = {r['publicationId']:r for r in c.read_jsonl(WEAK / 'references.jsonl')}
    if len(groups)!=len(splits) or len(groups)!=20000: raise ValueError('Corpus IDs incomplete or duplicate')
    docs = []
    with publication_file.open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            pid,text = row['publicationId:ID(Publication)'],row['title']
            group = groups[pid]
            if not text.strip() or group['split'] not in ('train','dev','test'): raise ValueError('Invalid title/split')
            ref = refs.get(pid)
            text_sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
            if ref is not None and (ref['text']!=text or ref['textSha256']!=text_sha):
                raise ValueError('Canonical title changed')
            docs.append({'sampleId':ref['sampleId'] if ref else 'corpus-'+c.canonical_sha256(pid)[:20],
                'publicationId':pid,'text':text,'textSha256':text_sha,
                'split':group['split'],'groupId':group['groupId']})
    if len(docs)!=20000 or len({d['sampleId'] for d in docs})!=20000 or {d['publicationId'] for d in docs}!=set(groups):
        raise ValueError('Corpus identity not one-to-one')
    lookup = {d['sampleId']:d for d in docs}
    paths = [publication_file,WEAK / 'manifest.json',WEAK / 'corpus_split_manifest.jsonl',WEAK / 'references.jsonl',
             c.CONFIG_PATH,c.SCHEMA_PATH]
    locks = {}
    for kind,digest in LOCK_SHA.items():
        path = ROOT / f'annotations/course_v4/{kind}_test_selection_20261006.json'
        if c.file_sha256(path)!=digest: raise ValueError('Frozen selection changed')
        lock = read(path); development = ROOT / lock['developmentRun']
        ner.verify_files(development)
        if c.file_sha256(development / 'manifest.json')!=lock['developmentManifestSha256']:
            raise ValueError('Frozen development artifact changed')
        weights = development / lock['checkpoint'] / 'model.safetensors'
        if c.file_sha256(weights)!=lock['weightsSha256']: raise ValueError('Frozen weights changed')
        locks[kind] = lock
        paths += [path,development / 'manifest.json',weights]
    for folder,digest in CACHE_SHA.items():
        ner.verify_files(folder)
        if c.file_sha256(folder / 'manifest.json')!=digest: raise ValueError('Frozen cache changed')
        paths.append(folder / 'manifest.json')
    if read(CACHE_NER / 'test_result.json')['weightsSha256']!=locks['ner']['weightsSha256']:
        raise ValueError('Cache belongs to different NER model')
    cached_ner = {}
    for r in c.read_jsonl(CACHE_NER / 'test_predictions.jsonl'):
        sid = r['sampleId']
        if sid not in lookup or sid in cached_ner: raise ValueError('Unknown/duplicate cached document')
        cached_ner[sid] = r['predictedEntities']  # Never use referenceEntities for production.
        candidate_rows(lookup[sid],cached_ner[sid])
    cached_re = {p['pairId']:p for p in c.read_jsonl(CACHE_RE / 'pipeline_predictions.jsonl')}
    re_docs = {d['sampleId'] for d in c.read_jsonl(CACHE_RE / 'test_documents.jsonl')}
    expected = {relation.pair_id(p) for sid in re_docs for p in candidate_rows(lookup[sid],cached_ner[sid])}
    if len(cached_ner)!=144 or len(cached_re)!=148 or set(cached_re)!=expected:
        raise ValueError('Cached coverage differs from preserved final inference')
    paths += [CACHE_NER / 'test_predictions.jsonl',CACHE_RE / 'pipeline_predictions.jsonl',CACHE_RE / 'test_documents.jsonl']
    paths += [ROOT / 'scripts' / n for n in ('infer_course_corpus.py','train_course_ner.py','train_course_relation.py',
        'course_relation_model.py','evaluate_course_relation.py','course_weak.py')]
    return docs,locks,cached_ner,cached_re,{p.relative_to(ROOT).as_posix():c.file_sha256(p) for p in paths}


def encode_title(tokenizer,doc,max_length):
    if set(doc)!= {'sampleId','text','textSha256'}: raise ValueError('Production model input must contain only anonymous title fields')
    encoded = dict(tokenizer(doc['text'],return_offsets_mapping=True,truncation=False))
    offsets = encoded.pop('offset_mapping')
    if len(encoded['input_ids'])>max_length: return None,len(encoded['input_ids'])
    if 'labels' in encoded: raise ValueError('Labels leaked into NER inference')
    return {'sampleId':doc['sampleId'],'offsets':offsets,'features':encoded},len(encoded['input_ids'])


def run(output,limit=20000,device_name='cuda',chunk_size=256):
    if type(limit) is not int or not 1<=limit<=20000 or not 1<=chunk_size<=512:
        raise ValueError('Invalid document/chunk limit')
    if output.exists(): raise FileExistsError('Preserve production run; choose new output')
    docs,locks,cache_ner,cache_re,bindings = load_sources()
    docs = docs[:limit]
    output.mkdir(parents=True,exist_ok=False)
    created = datetime.now(UTC).isoformat(); started = time.monotonic()
    status = {'status':'running','createdAtUTC':created,'documentsRequested':len(docs),'processed':0,
              'trainingStarted':False,'evaluationExecuted':False,'databaseWriteExecuted':False}
    c.write_json(output / 'status.json',status)
    c.write_jsonl(output / 'documents.jsonl',docs)
    c.write_jsonl(output / 'model_inputs.jsonl',[{k:d[k] for k in ('sampleId','text','textSha256')} for d in docs])
    for p in bindings:
        if p.startswith('scripts/'):
            shutil.copyfile(ROOT / p,output / Path(p).name)
    try:
        os.environ.setdefault('HF_HUB_OFFLINE','1')
        os.environ.setdefault('TOKENIZERS_PARALLELISM','false')
        os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
        import torch
        import transformers
        from transformers import BertTokenizerFast,BertForTokenClassification,DataCollatorWithPadding
        if device_name=='cuda' and not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no silent CPU fallback')
        device = torch.device(device_name)
        torch.manual_seed(20261006); torch.set_num_threads(4); torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
        np = ROOT / locks['ner']['developmentRun'] / locks['ner']['checkpoint']
        rp = ROOT / locks['re']['developmentRun'] / locks['re']['checkpoint']
        nt = BertTokenizerFast.from_pretrained(np,local_files_only=True,do_lower_case=True)
        nm,info = BertForTokenClassification.from_pretrained(np,local_files_only=True,use_safetensors=True,
            attn_implementation='eager',output_loading_info=True)
        if any(info[k] for k in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs')):
            raise ValueError('Incomplete NER weights')
        if [nm.config.id2label[i] for i in range(len(c.CONFIG['bioLabels']))]!=c.CONFIG['bioLabels']:
            raise ValueError('NER BIO class order changed')
        nm.to(device).requires_grad_(False).eval()
        rt = relation.prepare_tokenizer(rp)
        rm = relation.load_relation_model(rp,rt).to(device).requires_grad_(False).eval()
        nc,rc = DataCollatorWithPadding(nt,return_tensors='pt'),DataCollatorWithPadding(rt,return_tensors='pt')
        max_length = read(ROOT / locks['ner']['developmentRun'] / 'status.json')['config']['max_length']
        re_length = locks['re']['config']['max_length']
        batch_size = locks['re']['config']['batch_size']
        c.write_json(output / 'runtime.json',{'torch':torch.__version__,'transformers':transformers.__version__,
            'device':str(device),'gpu':torch.cuda.get_device_name(device) if device.type=='cuda' else None,
            'batchSize':batch_size,'chunkSize':chunk_size,'NERMaxLength':max_length,'REMaxLength':re_length,
            'deterministicAlgorithms':True,'gradientEnabledForModels':False,'confidenceCalibrated':False})
        parts = output / 'chunks'; parts.mkdir()
        for offset in range(0,len(docs),chunk_size):
            part = docs[offset:offset+chunk_size]; result = {}; records = []; rejected_pairs = []
            for d in part:
                sid = d['sampleId']
                if sid in cache_ner:
                    result[sid] = {'sampleId':sid,'status':'cached','predictedEntities':cache_ner[sid],
                        'cacheManifestSha256':CACHE_SHA[CACHE_NER],'invalidTransitions':None}
                    continue
                encoded,length = encode_title(nt,{k:d[k] for k in ('sampleId','text','textSha256')},max_length)
                if encoded is None:
                    result[sid] = {'sampleId':sid,'status':'rejected','predictedEntities':[],
                        'reason':'Title exceeds frozen token limit; no truncation','tokens':length,'invalidTransitions':None}
                else: records.append(encoded)
            texts = {d['sampleId']:d['text'] for d in part}
            with torch.inference_mode():
                for start in range(0,len(records),batch_size):
                    batch_records = records[start:start+batch_size]
                    inputs = {k:v.to(device) for k,v in nc([r['features'] for r in batch_records]).items()}
                    if 'labels' in inputs: raise ValueError('NER received labels')
                    logits = nm(**inputs).logits
                    if logits.shape[:2]!=inputs['input_ids'].shape or logits.shape[2]!=len(c.CONFIG['bioLabels']) or not torch.isfinite(logits).all():
                        raise ValueError('Invalid NER shape or nonfinite logits')
                    for r,tags in zip(batch_records,logits.argmax(-1).cpu().tolist()):
                        decoded = ner.decode_bio(tags[:len(r['offsets'])],r['offsets'],texts[r['sampleId']])
                        result[r['sampleId']] = {'sampleId':r['sampleId'],'status':'inferred',
                            'predictedEntities':decoded['entities'],'invalidTransitions':decoded['invalidTransitions']}
            pairs = []; predicted = []
            for d in part:
                r = result[d['sampleId']]
                if r['status']=='rejected': continue
                for p in candidate_rows(d,r['predictedEntities']):
                    pid = relation.pair_id(p)
                    if pid in cache_re:
                        saved = cache_re[pid]
                        if any(saved[k]!=p[k] for k in ('sampleId','text','textSha256','head','tail')):
                            raise ValueError('Cached RE endpoints/title changed')
                        predicted.append(saved | {'inferenceSource':'cached','cacheManifestSha256':CACHE_SHA[CACHE_RE]})
                    else:
                        try: relation.encode_pair(rt,p,re_length)
                        except ValueError as e:
                            if str(e)!='Marked title exceeds token limit; truncation forbidden': raise
                            rejected_pairs.append(p | {'pairId':pid,'reason':str(e),'status':'rejected'})
                        else: pairs.append(p)
            predicted += [p | {'inferenceSource':'inferred'} for p in predict(rm,rt,pairs,re_length,rc,device,batch_size)]
            ordered = [result[d['sampleId']] for d in part]
            name = f'{offset//chunk_size:04d}'
            c.write_jsonl(parts / f'{name}_ner.jsonl',ordered)
            c.write_jsonl(parts / f'{name}_re.jsonl',predicted)
            c.write_jsonl(parts / f'{name}_re_rejected.jsonl',rejected_pairs)
            status.update(processed=offset+len(part),elapsedSeconds=time.monotonic()-started)
            c.write_json(output / 'status.json',status)
            print(json.dumps({'processed':status['processed'],'total':len(docs),'elapsedSeconds':round(status['elapsedSeconds'],2)}),flush=True)
        nr = [r for p in sorted(parts.glob('*_ner.jsonl')) for r in c.read_jsonl(p)]
        rr = [r for p in sorted(parts.glob('*_re.jsonl')) for r in c.read_jsonl(p)]
        rejected = [r for p in sorted(parts.glob('*_re_rejected.jsonl')) for r in c.read_jsonl(p)]
        if [r['sampleId'] for r in nr]!=[d['sampleId'] for d in docs]: raise ValueError('Output documents incomplete')
        expected = {relation.pair_id(p) for d,r in zip(docs,nr) if r['status']!='rejected' for p in candidate_rows(d,r['predictedEntities'])}
        if len(rr)+len(rejected)!=len(expected) or {p['pairId'] for p in rr+rejected}!=expected:
            raise ValueError('Missing/duplicate production relation decision')
        if any(c.file_sha256(ROOT / p)!=sha for p,sha in bindings.items()): raise ValueError('Source changed during inference')
        c.write_jsonl(output / 'ner_predictions.jsonl',nr)
        c.write_jsonl(output / 'relation_predictions.jsonl',rr)
        c.write_jsonl(output / 'rejected_pairs.jsonl',rejected)
        elapsed = time.monotonic()-started
        summary = {'documentsRequested':len(docs),'NERStatuses':dict(Counter(r['status'] for r in nr)),
            'entitySupport':dict(Counter(e['label'] for r in nr for e in r['predictedEntities'])),
            'invalidBIOTransitions':sum(r['invalidTransitions'] or 0 for r in nr),'relationCandidatePairs':len(expected),
            'relationPredictions':len(rr),'relationSources':dict(Counter(p['inferenceSource'] for p in rr)),
            'relationSupport':dict(Counter(p['label'] for p in rr)),'rejectedPairs':len(rejected),
            'NERWeightsSha256':locks['ner']['weightsSha256'],'REWeightsSha256':locks['re']['weightsSha256'],
            'elapsedSeconds':elapsed,'documentsPerSecond':len(docs)/elapsed,'qualityPromotionPassed':False,
            'notice':'Counts are model candidates, not precision/recall or verified facts; no new evaluation, tuning or training. Token-limit rejects remain explicit.'}
        c.write_json(output / 'summary.json',summary)
        status.update(status='completed',finishedAtUTC=datetime.now(UTC).isoformat(),elapsedSeconds=elapsed)
        c.write_json(output / 'status.json',status)
    except Exception as e:
        status.update(status='failed',errorType=type(e).__name__,error=str(e),finishedAtUTC=datetime.now(UTC).isoformat())
        c.write_json(output / 'status.json',status)
        raise
    finally:
        c.write_json(output / 'manifest.json',{'kind':'frozen_title_only_corpus_inference','status':status['status'],
            'inputSha256':bindings,'createdAtUTC':created,'weightsUnchanged':status['status']=='completed',
            'trainingExecuted':False,'evaluationExecuted':False,'databaseWriteExecuted':False,
            'filesSha256':{p.relative_to(output).as_posix():c.file_sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    return summary


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=20000)
    parser.add_argument('--device',choices=('cpu','cuda'),default='cuda')
    args = parser.parse_args()
    print(json.dumps(run(args.output,args.limit,args.device),ensure_ascii=False,indent=2))

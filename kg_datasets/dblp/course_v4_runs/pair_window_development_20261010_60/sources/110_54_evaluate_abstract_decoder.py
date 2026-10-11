"""Fixed frozen46 decoder comparison; shared legal BIO and RE evaluators, no fit."""
import argparse
import os
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import train_benchmark_abstract_models as training
from course_abstract_v1 import read, seal
from course_bio_constraints import legal_bio_labels

c, g, ner, relation, prior = training.c, training.g, training.ner, training.re_model, training.prior
CONTRACT = c.ROOT/'resources/course_abstract_decoder_v1.json'


def load_inputs():
    config = read(CONTRACT)
    if config['version'] != 'abstract_frozen_decoder_v1' or config['maxTokens'] != 512 or any(config[k] is not False for k in ('trainingAllowed', 'labelMutationAllowed', 'testContentAccessAllowed', 'automaticPromotionAllowed')): raise ValueError('Decoder contract drift')
    if c.file_sha256(c.ROOT/config['dataContract']) != config['dataContractSha256'] or c.file_sha256(c.ROOT/'scripts/course_bio_constraints.py') != config['decoderSha256']: raise ValueError('Shared source drift')
    data_config, parent, _, data = training.load_inputs(); folder = c.ROOT/config['run']; manifest = g.verified_files(folder, config['runManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Frozen run input drift')
    for task in ('NER', 'RE'):
        if manifest['filesSha256'][config[task]['checkpoint']+'/model.safetensors'] != config[task]['weightsSha256']: raise ValueError('Selected weights changed')
    if len(data['dev']['ner']) != config['expected']['nerDev'] or len(data['dev']['full_relation']) != config['expected']['completeDev']: raise ValueError('Decoder cohort drift')
    return config, data_config, parent, data


def decode_modes(logits, offsets, text):
    argmax = [max(range(len(token)), key=token.__getitem__) for token in logits]
    legal = legal_bio_labels(logits, offsets)
    result = {name: ner.decode_bio(tags, offsets, text) | {'tags': tags} for name, tags in (('argmax', argmax), ('constrained', legal))}
    if result['constrained']['invalidTransitions']: raise ValueError('Legal BIO still violates original-text decoding')
    return result


def error_summary(documents, refs, predictions):
    gold = {(relation.pair_key(p), p['label']) for p in refs if p['label'] != 'NO_RELATION'}
    entities = {d['sampleId']: {(e['start'], e['end'], e['label']) for e in d['entities']} for d in documents}
    counts = Counter(); rows = []
    for p in predictions:
        if p['label'] == 'NO_RELATION' or (relation.pair_key(p), p['label']) in gold: continue
        roles = [role for role in ('head','tail') if (p[role]['start'],p[role]['end'],p[role]['label']) not in entities[p['sampleId']]]
        cause = '+'.join(roles) if roles else 'relation_only'; counts[cause] += 1
        rows.append({'sampleId': p['sampleId'], 'pairId': p['pairId'], 'label': p['label'], 'head': p['head'], 'tail': p['tail'], 'endpointMismatch': cause})
    return dict(counts), rows


def run(output):
    if output.exists(): raise FileExistsError('Preserve decoder experiment; no overwrite/retry')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Output outside runs')
    config, data_config, parent, data = load_inputs(); frozen = c.ROOT/config['run']
    paths = [CONTRACT, Path(__file__), Path(training.__file__), c.ROOT/config['dataContract'], frozen/'manifest.json', c.ROOT/data_config['snapshot']/'manifest.json', c.CONFIG_PATH, c.SCHEMA_PATH]
    paths += [c.ROOT/'scripts'/name for name in ('course_bio_constraints.py','train_revised_abstract_models.py','train_course_ner.py','train_course_relation.py','course_relation_model.py','evaluate_course_relation.py','infer_course_corpus.py','train_abstract_relation.py','course_weak.py','course_graph.py','course_abstract_v1.py','course_abstract_relation.py')]
    paths += [c.ROOT/'tests/test_abstract_decoder.py', c.ROOT/'resources/course_graph_runtime.json', c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl']
    for task in ('NER','RE'):
        paths += [frozen/config[task]['checkpoint']/name for name in ('model.safetensors','config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','vocab.txt')]
    hashes = {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in paths}; output.mkdir(parents=True)
    c.write_json(output/'selection_lock.json', {'lockedAtUTC': datetime.now(UTC).isoformat(), 'contract': config, 'inputSha256': hashes, 'testContentConsumed': False})
    state = {'status':'running', 'startedAtUTC':datetime.now(UTC).isoformat(), 'trainingExecuted':False, 'testEvaluated':False, 'modelPromoted':False}; c.write_json(output/'status.json', state); started = time.perf_counter()
    try:
        os.environ.setdefault('HF_HUB_OFFLINE','1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
        import torch
        import transformers
        from transformers import BertTokenizerFast, DataCollatorWithPadding
        device = prior.setup(parent['NERTraining']); tokenizer = BertTokenizerFast.from_pretrained(frozen/config['NER']['checkpoint'], local_files_only=True, do_lower_case=True)
        model = prior.load_ner(frozen/config['NER']['checkpoint'], parent['bioLabels'], device).requires_grad_(False).eval(); collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
        rows = data['dev']['ner']; records = [prior.encode_title(tokenizer, {k:d[k] for k in ('sampleId','text','textSha256')}, config['maxTokens'])[0] for d in rows]
        if any(r is None or 'labels' in r['features'] for r in records): raise ValueError('NER overlength/label leakage')
        decoded = {'argmax':[], 'constrained':[]}; invalid = Counter(); logits_records = []; changed = []
        with torch.inference_mode():
            for start in range(0,len(rows),2):
                chunk = records[start:start+2]; batch = {k:v.to(device) for k,v in collator([r['features'] for r in chunk]).items()}; scores = model(**batch).logits
                if not torch.isfinite(scores).all() or scores.shape[-1] != 7: raise ValueError('Invalid NER scores')
                for d, record, logits in zip(rows[start:start+2], chunk, scores.cpu().tolist()):
                    logits = logits[:len(record['offsets'])]; modes = decode_modes(logits, record['offsets'], d['text'])
                    logits_records.append({'sampleId':d['sampleId'], 'textSha256':d['textSha256'], 'offsets':record['offsets'], 'logits':logits})
                    for mode in decoded: decoded[mode].append(modes[mode]['entities']); invalid[mode] += modes[mode]['invalidTransitions']
                    changed.append({'sampleId':d['sampleId'], 'changedTokens':sum(a != b and tuple(o) != (0,0) for a,b,o in zip(modes['argmax']['tags'],modes['constrained']['tags'],record['offsets'])), 'entitiesChanged':modes['argmax']['entities'] != modes['constrained']['entities']})
        if decoded['argmax'] != [r['predictedEntities'] for r in c.read_jsonl(frozen/'new_ner_dev_predictions.jsonl')]: raise ValueError('Frozen argmax NER serving parity failed')
        del model; torch.cuda.empty_cache()
        ner_metrics = {k:ner.score_rows(rows,p, evaluation_target=prior.TARGET) for k,p in decoded.items()}; full = data['dev']['full_relation']; ids = {d['sampleId'] for d in full}; refs = [p for p in data['dev']['relation'] if p['sampleId'] in ids]
        if len(refs) != config['expected']['fullPairs']: raise ValueError('Full-pair scope drift')
        rt = relation.prepare_tokenizer(frozen/config['RE']['checkpoint']); rm = relation.load_relation_model(frozen/config['RE']['checkpoint'],rt,'entity_markers').to(device).requires_grad_(False).eval(); rc = DataCollatorWithPadding(rt,return_tensors='pt'); pipelines = {}
        for mode, predictions in decoded.items():
            by_id = {d['sampleId']:p for d,p in zip(rows,predictions)}; pairs = [p for d in full for p in prior.candidate_rows(d,by_id[d['sampleId']])]; scored = prior.predict(rm,rt,pairs,512,rc,device,4)
            metrics = prior.dev_scope(prior.score_pipeline(full,refs,scored), 'complete_document_exposed_dev_AI_reference_not_final_test')
            causes, false = error_summary(full,refs,scored); missed = [e for d in full for e in prior.diagnose(d,by_id[d['sampleId']],[p for p in refs if p['sampleId']==d['sampleId']],[p for p in scored if p['sampleId']==d['sampleId']])]
            if len(false) != metrics['positiveMicro']['predicted']-metrics['positiveMicro']['truePositive'] or len(missed) != metrics['positiveMicro']['reference']-metrics['positiveMicro']['truePositive']: raise ValueError('FP/FN accounting drift')
            metrics.update(endpointMismatch=causes, missedReferencePrimaryCauses=dict(Counter(e['primaryCause'] for e in missed))); pipelines[mode] = metrics
            c.write_jsonl(output/(mode+'_ner_dev_predictions.jsonl'), [{'sampleId':d['sampleId'], 'referenceEntities':d['entities'], 'predictedEntities':p} for d,p in zip(rows,predictions)])
            c.write_jsonl(output/(mode+'_pipeline_predictions.jsonl'),scored); c.write_jsonl(output/(mode+'_false_relations.jsonl'),false); c.write_jsonl(output/(mode+'_missed_relations.jsonl'),missed)
        old = read(frozen/'pipeline_development_result.json')
        if pipelines['argmax']['positiveMicro'] != old['pipelineMetrics']['new_NER_new_RE']['positiveMicro'] or [(p['pairId'],p['label']) for p in c.read_jsonl(output/'argmax_pipeline_predictions.jsonl')] != [(p['pairId'],p['label']) for p in c.read_jsonl(frozen/'new_NER_new_RE_predictions.jsonl')]: raise ValueError('Argmax RE serving parity failed')
        comparison = {'pipelineMetrics':{'old_NER_old_RE':old['pipelineMetrics']['old_NER_old_RE'], 'new_NER_new_RE':pipelines['constrained']}}
        gates = prior.gate_results(parent,data,comparison,ner_metrics['constrained']); checks = gates['checks']
        checks.update(DATASETRecallAgainst46=ner_metrics['argmax']['perClass']['DATASET']['recall']-ner_metrics['constrained']['perClass']['DATASET']['recall'] <= parent['promotionGates']['maxAbsoluteRecallRegression'], NERMicroF1Against46=ner_metrics['constrained']['micro']['f1'] >= ner_metrics['argmax']['micro']['f1'])
        gates.update(developmentGatesPassed=all(checks.values()), blockedBy=[k for k,v in checks.items() if not v]); del rm; torch.cuda.empty_cache()
        c.write_jsonl(output/'dev_logits.jsonl',logits_records); c.write_jsonl(output/'decoder_changes.jsonl',changed); c.write_jsonl(output/'pipeline_dev_documents.jsonl',full); c.write_jsonl(output/'pipeline_dev_reference_pairs.jsonl',refs)
        c.write_json(output/'development_result.json', {'passed':True, 'version':config['version'], 'documents':len(rows), 'metrics':ner_metrics, 'invalidTransitions':dict(invalid), 'pipelineMetrics':pipelines, 'frozen42Pipeline':old['pipelineMetrics']['old_NER_old_RE']['positiveMicro'], 'gates':gates,
            'servingParity':True,'labelFreeInference':True,'weightsUnchanged':True,'trainingExecuted':False,'testEvaluated':False,'qualityPromotionPassed':False,'modelPromoted':False,'notice':'Previously exposed AI-reference dev decoder experiment. Legal BIO does not establish semantic accuracy or readiness.'})
        c.write_json(output/'environment.json', {'torch':torch.__version__,'transformers':transformers.__version__,'gpu':torch.cuda.get_device_name(device),'cuda':torch.version.cuda})
        archive = output/'sources'; archive.mkdir()
        for i,p in enumerate(paths):
            if p.suffix != '.safetensors' and p.name != 'test_references.jsonl': shutil.copy2(p,archive/(str(i)+'_'+p.name))
        if any(c.file_sha256(c.ROOT/p) != sha for p,sha in hashes.items()): raise ValueError('Decoder input/code/weights drift')
        state.update(status='completed',finishedAtUTC=datetime.now(UTC).isoformat(),elapsedSeconds=time.perf_counter()-started); c.write_json(output/'status.json',state); seal(output,paths)
        print({'completed':True,'invalid':dict(invalid),'NERf1':{k:v['micro']['f1'] for k,v in ner_metrics.items()},'pipelineF1':{k:v['positiveMicro']['f1'] for k,v in pipelines.items()},'blockedBy':gates['blockedBy']},flush=True)
    except Exception as error:
        c.write_json(output/'status.json',state | {'status':'failed_no_synthetic_fallback','errorType':type(error).__name__,'error':str(error)}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action',choices=('preflight','evaluate')); parser.add_argument('--output',type=Path); args=parser.parse_args()
    if args.action == 'preflight': print({'loaded':True,'NERdev':len(load_inputs()[3]['dev']['ner']),'trainingAllowed':False,'testAccessed':False})
    elif args.output is None: parser.error('New output required')
    else: run(args.output.resolve())

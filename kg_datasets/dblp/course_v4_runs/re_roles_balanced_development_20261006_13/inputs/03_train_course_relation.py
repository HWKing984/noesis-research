"""Train/dev SciBERT relation classification using reviewed reference entity pairs.

No test tokenization or final-test claims. Evidence/reasons are provenance, never
model features. Frozen NER artifacts and existing annotation snapshots stay intact.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import course_weak as c
import train_course_ner as ner

LABELS = [x for x in c.CONFIG['relationLabels'] if x != 'UNRESOLVED']
MARKERS = {'headOpen':'[unused0]', 'headClose':'[unused1]', 'TASK':'[unused2]',
           'DATASET':'[unused3]', 'tailClose':'[unused4]'}


@dataclass(frozen=True)
class RelationConfig:
    seed: int = 20261006
    batch_size: int = 8
    learning_rate: float = 2e-5
    max_length: int = 128
    epochs: int = 6
    balanced_loss: bool = False


def allowed_labels(tail_type: str) -> list[str]:
    labels = [label for label, types in c.CONFIG['relationPairs'].items() if types == ['METHOD', tail_type]]
    if len(labels) != 1:
        raise ValueError('Unsupported directed entity pair type')
    return labels + ['NO_RELATION']


def pair_key(row: dict) -> tuple:
    return (row['sampleId'], row['head']['start'], row['head']['end'],
            row['tail']['start'], row['tail']['end'])


def pair_id(row: dict) -> str:
    return 'pair-' + c.canonical_sha256(pair_key(row))[:24]


def mark_pair(row: dict) -> str:
    text, head, tail = row['text'], row['head'], row['tail']
    if (head['label'] != 'METHOD' or tail['label'] not in ('TASK','DATASET')
            or c.span_errors(head,text) or c.span_errors(tail,text)
            or max(head['start'],tail['start']) < min(head['end'],tail['end'])
            or any(token.casefold() in text.casefold() for token in MARKERS.values())):
        raise ValueError('Invalid directed pair, literal span or reserved marker injection')
    edits = [(head,MARKERS['headOpen'],MARKERS['headClose']),
             (tail,MARKERS[tail['label']],MARKERS['tailClose'])]
    for entity, opening, closing in sorted(edits, key=lambda x:x[0]['start'], reverse=True):
        start, end = entity['start'], entity['end']
        text = text[:start] + ' ' + opening + ' ' + text[start:end] + ' ' + closing + ' ' + text[end:]
    return text


def load_relation_snapshot(dataset: Path, snapshot: Path):
    _, summary = ner.load_snapshot(dataset,snapshot)
    receipts = c.read_jsonl(snapshot / 'receipts.jsonl')
    splits = {}
    for split in ('train','dev'):
        expected = []
        for receipt in receipts:
            ref, annotation = receipt['reference'], receipt['annotation']
            if ref['split'] != split or not c.eligible_tasks(receipt,ref)['relation']:
                continue
            entities = {e['entityId']:e for e in annotation['entities']}
            common = {'sampleId':ref['sampleId'], 'text':ref['text'], 'textSha256':ref['textSha256'],
                      'referenceSha256':c.canonical_sha256(ref), 'annotationSha256':receipt['contentSha256'], 'labelSource':'ai_pseudo'}
            for pair in annotation['relations']:
                expected.append(common | {'head':entities[pair['head']], 'tail':entities[pair['tail']],
                                'label':pair['label'], 'evidence':pair['evidence'], 'reason':pair['reason']})
        rows = c.read_jsonl(snapshot / f'relation_inputs_{split}.jsonl')
        if not rows or rows != expected or len({pair_key(r) for r in rows}) != len(rows):
            raise ValueError('Relation inputs differ from complete reviewed receipts: ' + split)
        for row in rows:
            mark_pair(row)
        splits[split] = rows
    ner.verify_files(snapshot)
    return splits, summary


def score_relations(rows: list[dict], predictions: list[str]) -> dict:
    if not rows or len(rows) != len(predictions) or len({pair_key(r) for r in rows}) != len(rows):
        raise ValueError('Relation predictions require unique complete pair coverage')
    for row, prediction in zip(rows,predictions):
        if row['label'] not in allowed_labels(row['tail']['label']) or prediction not in allowed_labels(row['tail']['label']):
            raise ValueError('Unknown, unresolved or type-incompatible relation label')
    matrix = [[0]*len(LABELS) for _ in LABELS]
    for row, pred in zip(rows,predictions):
        matrix[LABELS.index(row['label'])][LABELS.index(pred)] += 1
    reference = [pair_key(r)+(r['label'],) for r in rows]
    predicted = [pair_key(r)+(p,) for r,p in zip(rows,predictions)]
    per_class = {label:c.entity_agreement([p for p in predicted if p[-1]==label],
                                         [e for e in reference if e[-1]==label]) for label in LABELS}
    supported = [label for label in c.CONFIG['relationPairs'] if per_class[label]['reference']]
    return {'evaluationTarget':c.CONFIG['evaluationTarget'], 'entityScope':'reviewed_reference_entities',
            'accuracy':sum(r['label']==p for r,p in zip(rows,predictions))/len(rows),
            'positiveMicro':c.entity_agreement([p for p in predicted if p[-1]!='NO_RELATION'],
                                                [e for e in reference if e[-1]!='NO_RELATION']),
            'positiveMacroF1':sum(per_class[label]['f1'] for label in supported)/len(supported) if supported else None,
            'supportedPositiveClasses':supported, 'perClass':per_class,
            'confusionLabels':LABELS, 'confusionMatrix':matrix,
            'confusionAxes':'rows_reference_columns_prediction'}


def type_majority(train: list[dict]) -> dict:
    result = {}
    for kind in ('TASK','DATASET'):
        counts = Counter(r['label'] for r in train if r['tail']['label']==kind)
        result[kind] = max(allowed_labels(kind),key=lambda label:counts[label]) if counts else 'NO_RELATION'
    return result


def class_weights(train: list[dict], balanced: bool) -> list[float]:
    if not balanced:
        return [1.0]*len(LABELS)
    counts = Counter(r['label'] for r in train)
    if any(counts[label]==0 for label in LABELS):
        raise ValueError('Balanced loss requires nonzero train class support')
    return [len(train)/(len(LABELS)*counts[label]) for label in LABELS]


def prepare_tokenizer(path: Path):
    from transformers import BertTokenizerFast
    tokenizer = BertTokenizerFast.from_pretrained(path,local_files_only=True,do_lower_case=True)
    size = len(tokenizer)
    ids = [tokenizer.convert_tokens_to_ids(token) for token in MARKERS.values()]
    if tokenizer.unk_token_id in ids or len(set(ids)) != len(ids):
        raise ValueError('Pinned vocabulary lacks distinct reserved entity markers')
    tokenizer.add_special_tokens({'additional_special_tokens':list(MARKERS.values())})
    if len(tokenizer) != size:
        raise ValueError('Markers must reuse pinned unused vocabulary, not resize weights')
    return tokenizer


def encode_pair(tokenizer, row: dict, max_length: int) -> dict:
    marked = mark_pair(row)
    original = tokenizer(row['text'],return_offsets_mapping=True,truncation=False)
    c.align_bio(original['offset_mapping'], sorted([row['head'],row['tail']],key=lambda e:e['start']),row['text'])
    if row['label'] not in allowed_labels(row['tail']['label']):
        raise ValueError('Unresolved or incompatible training target')
    features = dict(tokenizer(marked,truncation=False))
    if len(features['input_ids']) > max_length:
        raise ValueError('Marked title exceeds token limit; truncation forbidden')
    required = [MARKERS['headOpen'],MARKERS['headClose'],MARKERS[row['tail']['label']],MARKERS['tailClose']]
    if any(features['input_ids'].count(tokenizer.convert_tokens_to_ids(token)) != 1 for token in required):
        raise ValueError('Entity marker missing or not atomic in tokenization')
    features['labels'] = LABELS.index(row['label'])
    return {'pairId':pair_id(row), 'tailType':row['tail']['label'], 'markedText':marked, 'features':features}


def forward_batch(model, records, collator, device):
    import torch
    batch = {key:value.to(device) for key,value in collator([r['features'] for r in records]).items()}
    targets = batch.pop('labels')
    logits = model(**batch).logits
    if logits.shape != (len(records),len(LABELS)) or not torch.isfinite(logits).all():
        raise ValueError('Invalid relation logit shape or nonfinite values')
    allowed = torch.tensor([[label in allowed_labels(r['tailType']) for label in LABELS] for r in records],device=device)
    # Schema restriction is identical in training and serving; no reference relation is used in this mask.
    return logits.masked_fill(~allowed,-1e9), targets


def evaluate_model(model, rows, records, collator, device, batch_size):
    import torch
    if [r['pairId'] for r in records] != [pair_id(row) for row in rows]:
        raise ValueError('Relation encoded input order differs from evaluation pairs')
    model.eval()
    predictions, probabilities, total_loss = [], [], 0.0
    with torch.no_grad():
        for start in range(0,len(records),batch_size):
            part = records[start:start+batch_size]
            logits, targets = forward_batch(model,part,collator,device)
            loss = torch.nn.functional.cross_entropy(logits,targets)
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite relation evaluation loss')
            total_loss += float(loss)*len(part)
            predictions.extend(LABELS[i] for i in logits.argmax(-1).cpu().tolist())
            probabilities.extend(logits.softmax(-1).cpu().tolist())
    return {'loss':total_loss/len(rows), 'metrics':score_relations(rows,predictions),
            'predictions':predictions, 'probabilities':probabilities}


def run(dataset: Path, snapshot: Path, model_path: Path, output: Path,
        config: RelationConfig, device_name: str = 'auto') -> dict:
    if output.exists():
        raise FileExistsError('Preserve relation run; use a new output directory')
    if (device_name not in ('auto','cpu','cuda') or type(config.balanced_loss) is not bool or any(type(n) is not int or n<=0 for n in
            (config.seed,config.epochs,config.batch_size,config.max_length)) or config.max_length<2
            or not math.isfinite(config.learning_rate) or config.learning_rate<=0):
        raise ValueError('Invalid relation configuration or device')
    output.mkdir(parents=True,exist_ok=False)
    started = time.perf_counter()
    state = {'status':'running', 'mode':'fit-dev', 'trainingStarted':False, 'testEvaluated':False,
             'testTokenized':False, 'humanGold':False, 'devUsedForGradient':False,
             'createdAt':datetime.now(UTC).isoformat(), 'config':asdict(config),
             'evaluationScope':'reference_entities_dev_selected_ai_reference_not_final_test'}
    c.write_json(output / 'status.json',state)
    try:
        paths = [dataset / 'manifest.json', snapshot / 'manifest.json', model_path / 'manifest.json',
                 Path(__file__), Path(ner.__file__), Path(c.__file__), c.CONFIG_PATH, c.SCHEMA_PATH,
                 Path(sys.modules['import_course_ai'].__file__), Path(sys.modules['prepare_course_weak'].__file__)]
        hashes = {str(p.resolve()):c.file_sha256(p) for p in paths}
        (output / 'inputs').mkdir()
        archived = {}
        for i,path in enumerate(paths):
            dest = output / 'inputs' / f'{i:02d}_{path.name}'
            shutil.copyfile(path,dest)
            if c.file_sha256(dest) != hashes[str(path.resolve())]:
                raise ValueError('Relation source changed during archival')
            archived[str(path.resolve())] = dest.relative_to(output).as_posix()
        splits, summary = load_relation_snapshot(dataset,snapshot)
        mm = ner.verify_files(model_path)
        if (mm.get('modelId') != 'allenai/scibert_scivocab_uncased'
                or mm.get('revision') != '24f92d32b1bfb0bcaf9ab193ff3ad01e87732fc1'
                or mm['filesSha256'].get('pytorch_model.bin') != 'e492944d88ac97dee6baa547671d3c526a3d067676883efb058311f4e5882e1a'):
            raise ValueError('Relation model must start from pinned SciBERT base, not NER/test weights')
        if any(summary['relationSupport'][s][label] == 0 for s in ('train','dev') for label in LABELS):
            raise ValueError('Development relations require reported train/dev class coverage')
        tokenizer = prepare_tokenizer(model_path)
        weights = class_weights(splits['train'],config.balanced_loss)
        encoded, rejected = {}, []
        for split, rows in splits.items():
            encoded[split] = []
            for row in rows:
                try:
                    encoded[split].append(encode_pair(tokenizer,row,config.max_length))
                except ValueError as error:
                    rejected.append({'pairId':pair_id(row), 'split':split, 'reason':str(error)})
        c.write_json(output / 'preflight.json', {'valid':not rejected, 'rejected':rejected,
                     'pairCounts':{s:len(r) for s,r in splits.items()},
                     'documentCounts':{s:len({r['sampleId'] for r in rows}) for s,rows in splits.items()},
                     'maxTokens':{s:max((len(r['features']['input_ids']) for r in rows),default=0) for s,rows in encoded.items()},
                     'classSupport':{s:summary['relationSupport'][s] for s in splits}, 'markers':MARKERS,
                     'formalRelationReadiness':summary['relationTrainingReady'], 'testTokenized':False, 'trainLossWeights':dict(zip(LABELS,weights))})
        if rejected:
            raise ValueError('Relation tokenizer alignment failed; no silent filtering')
        baseline = type_majority(splits['train'])
        baseline_predictions = [baseline[r['tail']['label']] for r in splits['dev']]
        c.write_json(output / 'baseline_dev_metrics.json',score_relations(splits['dev'],baseline_predictions) |
                     {'method':'tail_type_majority_from_train_only', 'mapping':baseline, 'humanGold':False})
        c.write_jsonl(output / 'baseline_dev_predictions.jsonl',[
            {'pairId':pair_id(row),'predictedLabel':p} for row,p in zip(splits['dev'],baseline_predictions)])
        os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
        import numpy as np
        import torch
        from transformers import BertForSequenceClassification, DataCollatorWithPadding
        random.seed(config.seed)
        np.random.seed(config.seed)
        torch.manual_seed(config.seed)
        torch.cuda.manual_seed_all(config.seed)
        torch.set_num_threads(4)
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        device = torch.device(('cuda' if torch.cuda.is_available() else 'cpu') if device_name=='auto' else device_name)
        if device.type=='cuda' and not torch.cuda.is_available():
            raise ValueError('CUDA requested but unavailable; no silent fallback')
        model = BertForSequenceClassification.from_pretrained(model_path,local_files_only=True,weights_only=True,
            num_labels=len(LABELS),id2label=dict(enumerate(LABELS)),label2id={label:i for i,label in enumerate(LABELS)},
            attn_implementation='eager').to(device)
        before_head = model.classifier.weight.detach().cpu().clone()
        before_encoder = model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu().clone()
        collator = DataCollatorWithPadding(tokenizer,return_tensors='pt')
        evaluate = lambda current:evaluate_model(current,splits['dev'],encoded['dev'],collator,device,config.batch_size)
        initial = evaluate(model)
        optimizer = torch.optim.AdamW(model.parameters(),lr=config.learning_rate,weight_decay=0.01)
        loss_weights = torch.tensor(weights,dtype=torch.float32,device=device) if config.balanced_loss else None
        state.update(trainingStarted=True,device=str(device),cudaVersion=torch.version.cuda,
                     gpu=torch.cuda.get_device_name(device) if device.type=='cuda' else None)
        c.write_json(output / 'status.json',state)
        for split,rows in splits.items():
            c.write_jsonl(output / f'{split}_inputs.jsonl',rows)
            c.write_jsonl(output / f'{split}_encoded.jsonl',encoded[split])
        generator = random.Random(config.seed)
        best_score, best_path, best_eval, epochs, step = None, None, None, [], 0
        with (output / 'steps.jsonl').open('x',encoding='utf-8') as stream:
            for epoch in range(1,config.epochs+1):
                order = list(range(len(encoded['train'])))
                generator.shuffle(order)
                for start in range(0,len(order),config.batch_size):
                    indices = order[start:start+config.batch_size]
                    part = [encoded['train'][i] for i in indices]
                    model.train()
                    optimizer.zero_grad(set_to_none=True)
                    logits, targets = forward_batch(model,part,collator,device)
                    loss = torch.nn.functional.cross_entropy(logits,targets,weight=loss_weights)
                    if not torch.isfinite(loss):
                        raise ValueError('Nonfinite relation training loss')
                    loss.backward()
                    norm = torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
                    if not torch.isfinite(norm):
                        raise ValueError('Nonfinite relation gradient')
                    optimizer.step()
                    step += 1
                    log = {'step':step,'epoch':epoch,'loss':float(loss.detach()),'gradientNorm':float(norm),
                           'pairIds':[r['pairId'] for r in part], 'sampleIds':[splits['train'][i]['sampleId'] for i in indices]}
                    stream.write(json.dumps(log,allow_nan=False)+'\n')
                    stream.flush()
                    if step==1 or step%20==0:
                        print(json.dumps({'step':step,'loss':log['loss']}),flush=True)
                validation = evaluate(model)
                score = validation['metrics']['positiveMacroF1']
                improved = ner.dev_checkpoint_improved(score,best_score)
                if improved:
                    best_score, best_eval = score, validation
                    best_path = output / f'checkpoint_epoch_{epoch:02d}'
                    model.save_pretrained(best_path,safe_serialization=True)
                    tokenizer.save_pretrained(best_path)
                epochs.append({'epoch':epoch,'step':step,'dev':{k:v for k,v in validation.items() if k not in ('predictions','probabilities')},
                               'checkpointImproved':improved})
                c.write_json(output / 'epochs.json',epochs)
                print(json.dumps(epochs[-1],allow_nan=False),flush=True)
        del optimizer, model
        if device.type=='cuda':
            torch.cuda.empty_cache()
        restored = BertForSequenceClassification.from_pretrained(best_path,local_files_only=True,
                    use_safetensors=True,attn_implementation='eager').to(device)
        restored_tokenizer = prepare_tokenizer(best_path)
        reload_encoded = [encode_pair(restored_tokenizer,row,config.max_length) for row in splits['dev']]
        recheck = evaluate_model(restored,splits['dev'],reload_encoded,DataCollatorWithPadding(restored_tokenizer,return_tensors='pt'),device,config.batch_size)
        equal = recheck['predictions']==best_eval['predictions'] and reload_encoded==encoded['dev']
        head_changed = not torch.equal(before_head,restored.classifier.weight.detach().cpu())
        encoder_changed = not torch.equal(before_encoder,restored.bert.encoder.layer[0].attention.self.query.weight.detach().cpu())
        predictions = [{'pairId':pair_id(row),'sampleId':row['sampleId'],'head':row['head'],'tail':row['tail'],
                        'referenceLabel':row['label'],'predictedLabel':p,'probabilities':dict(zip(LABELS,probs))}
                       for row,p,probs in zip(splits['dev'],best_eval['predictions'],best_eval['probabilities'])]
        errors = [p for p in predictions if p['referenceLabel']!=p['predictedLabel']]
        c.write_jsonl(output / 'dev_predictions.jsonl',predictions)
        c.write_jsonl(output / 'dev_errors.jsonl',errors)
        result = {'evaluationScope':state['evaluationScope'],'selection':'dev_positive_macro_f1_earliest_tie',
                  'bestCheckpoint':best_path.relative_to(output).as_posix(), 'epochs':config.epochs, 'steps':step,
                  'initialDev':{k:v for k,v in initial.items() if k not in ('predictions','probabilities')},
                  'bestDev':{k:v for k,v in best_eval.items() if k not in ('predictions','probabilities')},
                  'baselineDev':score_relations(splits['dev'],baseline_predictions),
                  'errorPairs':len(errors), 'classifierChanged':head_changed,'encoderChanged':encoder_changed,
                  'reloadPredictionsIdentical':equal,'passed':equal and head_changed and encoder_changed,
                  'testEvaluated':False,'testTokenized':False,'devUsedForGradient':False,'humanGold':False,
                  'endToEndEvaluated':False, 'formalRelationReadiness':summary['relationTrainingReady'],
                  'notice':'Reference-entity dev selection only; imbalanced AI labels and tiny rare-class support. Not final test, end-to-end accuracy or evidence of semantic gold quality.'}
        c.write_json(output / 'development_result.json',result)
        if any(c.file_sha256(Path(path))!=digest for path,digest in hashes.items()):
            raise ValueError('Relation input or source drift during training')
        ner.verify_files(snapshot)
        ner.verify_files(model_path)
        state.update(status='completed' if result['passed'] else 'training_gate_failed',
                     finishedAt=datetime.now(UTC).isoformat(),elapsedSeconds=time.perf_counter()-started)
        c.write_json(output / 'status.json',state)
        c.write_json(output / 'manifest.json', {'inputSha256':hashes,'archivedInputs':archived,'modelProvenance':mm,
                     'python':sys.version, 'packages':{name:version(name) for name in ('torch','transformers','tokenizers','safetensors','numpy','jsonschema')},
                     'config':asdict(config),'labels':LABELS,'markers':MARKERS,'typeMask':'candidate_positive_or_NO_RELATION',
                     'selection':'dev_positive_macro_f1_earliest_tie','trainLossWeights':dict(zip(LABELS,weights)), 'resumeSupported':False,
                     'filesSha256':{p.relative_to(output).as_posix():c.file_sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}})
        return state
    except Exception as error:
        state.update(status='failed',errorType=type(error).__name__,error=str(error),elapsedSeconds=time.perf_counter()-started)
        c.write_json(output / 'status.json',state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','snapshot','model','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    for name,default in asdict(RelationConfig()).items():
        if isinstance(default,bool):
            parser.add_argument('--'+name.replace('_','-'),action=argparse.BooleanOptionalAction,default=default)
        else:
            parser.add_argument('--'+name.replace('_','-'),type=type(default),default=default)
    args = parser.parse_args()
    state = run(args.dataset,args.snapshot,args.model,args.output,
                RelationConfig(**{key:getattr(args,key) for key in asdict(RelationConfig())}),args.device)
    print(json.dumps(state,ensure_ascii=False,indent=2),flush=True)
    if state['status']!='completed':
        raise SystemExit(1)


if __name__=='__main__':
    main()

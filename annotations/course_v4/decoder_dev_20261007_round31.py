"""One predeclared decoder comparison on existing dev only; no final-test access."""
import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import course_graph as g
import train_course_ner as ner
from infer_course_corpus import encode_title
from course_bio_constraints import legal_bio_labels


def main(output):
    if output.exists():raise FileExistsError('Preserve decoder experiment')
    folder=ROOT/'kg_datasets/dblp/course_v4_runs/ner_expanded_development_20261007_28'
    manifest=g.verified_files(folder)
    dev_result=json.loads((folder/'development_result.json').read_text(encoding='utf-8'))
    checkpoint=folder/dev_result['bestCheckpoint'];weights=checkpoint/'model.safetensors'
    data=ROOT/'kg_datasets/dblp/course_v4_training_inputs_17/ner_inputs_dev.jsonl'
    inputs=[folder/'manifest.json',weights,data,Path(__file__),ROOT/'scripts/course_bio_constraints.py',g.c.CONFIG_PATH]
    hashes={p.relative_to(ROOT).as_posix():g.c.file_sha256(p) for p in inputs}
    output.mkdir(parents=True)
    g.c.write_json(output/'selection_lock.json',{'lockedAtUTC':datetime.now(UTC).isoformat(),'inputSha256':hashes,
        'hypothesis':'legal maximum-emission BIO paths reduce orphan I errors without train/test labels in inference',
        'selection':'dev micro F1 nonregression and DATASET dev F1 at least production; support3 is not reliable evaluation',
        'testAccessed':False,'trainingExecuted':False,'automaticProductionPromotion':False})
    state={'status':'running','testAccessed':False,'trainingExecuted':False};g.c.write_json(output/'status.json',state)
    try:
        os.environ.setdefault('HF_HUB_OFFLINE','1');os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
        os.environ.setdefault('TOKENIZERS_PARALLELISM','false')
        import torch
        from transformers import BertTokenizerFast,BertForTokenClassification,DataCollatorWithPadding
        if not torch.cuda.is_available():raise ValueError('CUDA unavailable; no silent fallback')
        torch.set_num_threads(4);torch.manual_seed(20261006);torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        tokenizer=BertTokenizerFast.from_pretrained(checkpoint,local_files_only=True,do_lower_case=True)
        model,info=BertForTokenClassification.from_pretrained(checkpoint,local_files_only=True,use_safetensors=True,attn_implementation='eager',output_loading_info=True)
        if any(info[k] for k in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs')):raise ValueError('Incomplete checkpoint')
        if [model.config.id2label[i] for i in range(7)]!=g.c.CONFIG['bioLabels']:raise ValueError('BIO class order drifted')
        model.to('cuda').requires_grad_(False).eval();collator=DataCollatorWithPadding(tokenizer,return_tensors='pt')
        rows=g.c.read_jsonl(data);records=[]
        for row in rows:
            encoded,_=encode_title(tokenizer,g.c.model_payload(row),manifest['config']['max_length'])
            if encoded is None:raise ValueError('Dev title over limit; no truncation')
            records.append(encoded)
        predictions={'argmax':[],'constrained':[]};invalid={'argmax':0,'constrained':0};saved=[]
        with torch.inference_mode():
            for start in range(0,len(rows),8):
                chunk=records[start:start+8]
                features={k:v.to('cuda') for k,v in collator([r['features'] for r in chunk]).items()}
                if 'labels' in features:raise ValueError('Labels entered inference')
                scores=model(**features).logits.cpu().tolist()
                for record,row,logits in zip(chunk,rows[start:start+8],scores):
                    logits=logits[:len(record['offsets'])]
                    item={'sampleId':row['sampleId'],'textSha256':row['textSha256']}
                    for mode in predictions:
                        tags=[max(range(7),key=lambda j:token[j]) for token in logits] if mode=='argmax' else legal_bio_labels(logits,record['offsets'])
                        decoded=ner.decode_bio(tags,record['offsets'],row['text'])
                        predictions[mode].append(decoded['entities']);invalid[mode]+=decoded['invalidTransitions'];item[mode]=decoded['entities']
                    saved.append(item)
        prior=g.c.read_jsonl(folder/'dev_predictions.jsonl')
        if [p['predictedEntities'] for p in prior]!=predictions['argmax']:raise ValueError('Existing decoder serving parity failed')
        metrics={m:ner.score_rows(rows,p,evaluation_target=g.c.CONFIG['evaluationTarget']) for m,p in predictions.items()}
        assert invalid['constrained']==0
        result={'documents':len(rows),'metrics':metrics,'invalidTransitions':invalid,'weightsUnchanged':g.c.file_sha256(weights)==hashes[weights.relative_to(ROOT).as_posix()],
            'servingParity':True,'humanGold':False,'testEvaluated':False,'trainingExecuted':False,'modelPromoted':False,
            'notice':'Dev experiment only. BIO validity does not prove correct boundaries or semantics; no closed test was reused.'}
        if not result['weightsUnchanged'] or any(p.requires_grad or p.grad is not None for p in model.parameters()):raise ValueError('Frozen model changed')
        if any(g.c.file_sha256(ROOT/p)!=sha for p,sha in hashes.items()):raise ValueError('Experiment sources drifted')
        g.c.write_jsonl(output/'dev_predictions.jsonl',saved);g.c.write_json(output/'development_result.json',result)
        state.update(status='completed',finishedAtUTC=datetime.now(UTC).isoformat());g.c.write_json(output/'status.json',state)
        g.c.write_json(output/'manifest.json',{'inputSha256':hashes,'filesSha256':{p.name:g.c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
        print(json.dumps({'documents':len(rows),'F1':{m:s['micro']['f1'] for m,s in metrics.items()},'invalidTransitions':invalid,'modelPromoted':False}))
    except Exception as error:
        state.update(status='failed',errorType=type(error).__name__,error=str(error));g.c.write_json(output/'status.json',state);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args().output.resolve())

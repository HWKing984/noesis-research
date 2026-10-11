"""Runnable Torch contract check; tiny synthetic tensors are not course labels."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import torch
from transformers import BertConfig, BertForSequenceClassification
from safetensors.torch import load_file, save_file
import train_course_relation as r
from course_relation_model import BertForEntityPairClassification


def check():
    torch.manual_seed(20261006)
    torch.set_num_threads(1)
    config = BertConfig(vocab_size=48, hidden_size=16, num_hidden_layers=1,
                        num_attention_heads=2, intermediate_size=24, num_labels=3,
                        id2label=dict(enumerate(r.LABELS)), label2id={v:i for i,v in enumerate(r.LABELS)},
                        relation_representation='entity_markers', relation_marker_ids=[1,2,3,4,5])
    config._attn_implementation = 'eager'
    model = BertForEntityPairClassification(config).eval()
    # Both text orders: representation is always METHOD head then typed tail.
    ids = torch.tensor([[10,1,11,2,3,12,5,13,0], [10,4,14,5,1,15,2,13,0]])
    mask = (ids != 0).long()
    batch = {'input_ids':ids, 'attention_mask':mask}
    captured = []
    hook = model.classifier.register_forward_pre_hook(lambda module,args:captured.append(args[0].detach().clone()))
    with torch.no_grad():
        hidden = model.bert(**batch,return_dict=True).last_hidden_state
        logits = model(**batch).logits
    hook.remove()
    expected = torch.cat((hidden[torch.arange(2),torch.tensor([1,4])],
                          hidden[torch.arange(2),torch.tensor([4,1])]),dim=-1)
    assert logits.shape == (2,3) and torch.isfinite(logits).all()
    assert torch.equal(captured[0],expected) and model.classifier.in_features==32
    records = [{'features':{'input_ids':ids[i].tolist(),'attention_mask':mask[i].tolist(),'labels':i},
                'tailType':kind} for i,kind in enumerate(('TASK','DATASET'))]
    seen = []
    pre = model.register_forward_pre_hook(lambda module,args,kwargs:seen.append(set(kwargs)),with_kwargs=True)
    def collate(features):
        return {key:torch.tensor([f[key] for f in features]) for key in features[0]}
    masked, targets = r.forward_batch(model,records,collate,torch.device('cpu'))
    pre.remove()
    assert seen == [{'input_ids','attention_mask'}] and targets.tolist()==[0,1]
    assert masked[0,1]==-1e9 and masked[1,0]==-1e9
    loss = torch.nn.functional.cross_entropy(masked,targets)
    loss.backward()
    assert model.classifier.weight.grad.abs().sum()>0
    assert model.bert.encoder.layer[0].attention.self.query.weight.grad.abs().sum()>0
    for action in (lambda:BertForEntityPairClassification(BertConfig.from_dict(config.to_dict()|{'relation_representation':'cls'})),
                   lambda:model(input_ids=ids[0],attention_mask=mask[0])):
        try:
            action()
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid model config or batch shape accepted')
    invalid = [ids.clone() for _ in range(5)]
    invalid[0][0,1]=11  # missing head
    invalid[1][0,7]=1   # duplicate head
    invalid[2][0,7]=4   # two different tail openings
    invalid[3][0,2]=5   # duplicate tail close
    invalid[4][0,3], invalid[4][0,7] = 13, 2  # crossed head/tail intervals
    for bad in invalid:
        try:
            model(input_ids=bad,attention_mask=mask)
        except ValueError:
            pass
        else:
            raise AssertionError('Malformed pair accepted')
    hidden_marker = mask.clone()
    hidden_marker[0,1]=0
    try:
        model(input_ids=ids,attention_mask=hidden_marker)
    except ValueError:
        pass
    else:
        raise AssertionError('Masked entity marker accepted')
    class Tokenizer:
        def convert_tokens_to_ids(self, token):
            return list(r.MARKERS.values()).index(token)+1
    with TemporaryDirectory(prefix='relation-entity-check-') as folder:
        path = Path(folder)
        model.save_pretrained(path,safe_serialization=True)
        restored = r.load_relation_model(path,Tokenizer())
        assert restored.config.relation_representation=='entity_markers'
        assert restored.config.relation_marker_ids==[1,2,3,4,5]
        with torch.no_grad():
            assert torch.equal(logits,restored.eval()(**batch).logits)
        for representation, tokenizer in [('cls',Tokenizer()), ('entity_markers',type('BadTokenizer',(),{'convert_tokens_to_ids':lambda self,t:8})())]:
            try:
                r.load_relation_model(path,tokenizer,representation)
            except ValueError:
                pass
            else:
                raise AssertionError('Checkpoint architecture/tokenizer mismatch accepted')
        corrupted = {key:value.clone() for key,value in load_file(str(path/'model.safetensors')).items()}
        corrupted.pop('classifier.weight')
        broken = path/'missing_head'
        model.config.save_pretrained(broken)
        save_file(corrupted,str(broken/'model.safetensors'),metadata={'format':'pt'})
        try:
            r.load_relation_model(broken,Tokenizer())
        except ValueError:
            pass
        else:
            raise AssertionError('Missing trained classifier was silently initialized')
        legacy_config = BertConfig.from_dict(config.to_dict())
        del legacy_config.relation_representation, legacy_config.relation_marker_ids
        legacy_config._attn_implementation='eager'
        legacy = BertForSequenceClassification(legacy_config).eval()
        legacy_path = path/'legacy_cls'
        legacy.save_pretrained(legacy_path,safe_serialization=True)
        assert isinstance(r.load_relation_model(legacy_path,Tokenizer()),BertForSequenceClassification)
        swapped = json.loads((legacy_path/'config.json').read_text())
        swapped['id2label']['0'], swapped['id2label']['1'] = swapped['id2label']['1'], swapped['id2label']['0']
        r.c.write_json(legacy_path/'config.json',swapped)
        try:
            r.load_relation_model(legacy_path,Tokenizer())
        except ValueError:
            pass
        else:
            raise AssertionError('Legacy checkpoint label mapping was silently overwritten')
    records_without_labels = [{**record,'features':{key:value for key,value in record['features'].items() if key!='labels'}} for record in records]
    with torch.no_grad():
        predicted_logits, absent = r.forward_batch(model,records_without_labels,collate,torch.device('cpu'))
    assert absent is None and torch.equal(predicted_logits,masked.detach())
    for invalid_records in ([],[records[0],records_without_labels[1]],
                            [records[0]|{'tailType':'DATASET'}]):
        try:
            r.forward_batch(model,invalid_records,collate,torch.device('cpu'))
        except ValueError:
            pass
        else:
            raise AssertionError('Empty/mixed-label/type-marker mismatch accepted')
    return {'status':'passed','scope':'synthetic_cpu_model_contract_not_quality',
            'orderedMarkerGather':True,'bothTextOrders':True,'noTargetsInForward':True,
            'typeMask':True,'encoderAndHeadGradients':True,'safeReloadIdentical':True,
            'malformedMarkerCasesRejected':6,'checkpointMismatchCasesRejected':2,
            'invalidConfigAndBatchShapeRejected':True,'unlabeledInferenceParity':True,
            'missingTrainedWeightsRejected':True,'legacyLabelMismatchRejected':True,
            'emptyMixedAndTypeMismatchedBatchesRejected':True}


if __name__=='__main__':
    result = check()
    if len(sys.argv)>1:
        r.c.write_json(Path(sys.argv[1]),result)
    print(json.dumps(result))

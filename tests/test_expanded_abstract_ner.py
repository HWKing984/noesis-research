"""One runnable train expansion/split/receipt/checkpoint-contract check; no test text or training."""
import copy
import sys
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import course_weak as c
from collect_train_abstracts import selection
from course_abstract_v1 import read
from train_expanded_abstract_ner import load_inputs,new_row,additions

def test_data_only_expansion_preserves_source_roles_and_dev_and_rejects_bad_receipts():
    config,parent,selected=selection()
    assert len(selected)==24 and all(r['split']=='train' for r in selected)
    assert len({r['groupId'] for r in selected})==24 and config['crawlDelaySeconds']>=15 and not config['automaticPromotionAllowed']
    source=ROOT/'kg_datasets/dblp/course_abstract_train_sources_20261008_37';reviewed=ROOT/'kg_datasets/dblp/course_abstract_expansion_reviewed_20261008_37'
    _,_,rows=load_inputs(ROOT/'kg_datasets/dblp/course_abstract_expansion_inputs_20261008_37',source,reviewed)
    assert len(rows['train'])==48 and len(rows['dev'])==16
    groups=[r['groupId'] for split in rows.values() for r in split];assert len(set(groups))==len(groups)
    summary=read(source/'summary.json');assert summary['fetched']==24 and summary['usableTrainAbstracts']==21 and summary['excluded']==3
    starts=[datetime.fromisoformat(r['startedAtUTC']) for r in read(source/'requests.json')]
    assert all((b-a).total_seconds()>=15 for a,b in zip(starts,starts[1:]))
    pairs=additions(source,reviewed);assert len(pairs)==21 and sum(c.eligible_tasks(a,r)['ner'] for r,a in pairs)==19
    ref,receipt=pairs[0];bad=copy.deepcopy(receipt);bad['annotation']['entities'][0]['end']-=1
    assert new_row(ref,bad,ROOT/config['parentContract']) is None
    assert parent['NERTraining']['epochs']==6 and parent['NERTraining']['initialWeightsSha256']=='968a594de551a1ab77a263a725fcdf487b8c559539f7452e2edeb8cf62c8d996'
    assert all(p['label']=='UNRESOLVED' for _,a in pairs for p in a['annotation']['relations'])

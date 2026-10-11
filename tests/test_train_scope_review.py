"""One source-bound review check; synthetic rejection cases are not model evaluations."""
import copy
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import review_train_entity_scope as scope
import patch_train_method_inventory as inventory


def test_source_scope_unknowns_and_span_rejudgment():
    with patch.object(scope.c, 'read_jsonl', wraps=scope.c.read_jsonl) as reads:
        config, refs, receipts, source = scope.load_inputs()
    assert {p.args[0].name for p in reads.call_args_list} == {'train_references.jsonl', 'train_reviewed_receipts.jsonl'}
    lookup = {r['arxivId']: (r, a) for r, a in zip(refs, receipts)}; decisions = {d['arxivId']: d for d in source['documents']}
    assert not config['trainingAllowed'] and len(decisions) == 11
    for arxiv, expected in [('2009.03300', 0), ('2312.14977', 0), ('2105.15057', 24), ('2507.22101', 30)]:
        ann = scope.response_for(decisions[arxiv], *lookup[arxiv])
        assert len(ann['relations']) == expected and all(p['label'] == 'UNRESOLVED' for p in ann['relations'])
        assert ann['relationStatus'] == ('unresolved' if expected else 'complete')
    neural = scope.response_for(decisions['2105.15057'], *lookup['2105.15057'])
    assert any(e['text'] == 'DNN' and e['start'] == 922 for e in neural['entities'])
    physical = scope.response_for(decisions['2312.14977'], *lookup['2312.14977'])
    assert not any(e['start'] == 841 for e in physical['entities'])
    edit = decisions['2510.26830']; ann = scope.response_for(edit, *lookup['2510.26830'])
    assert ann['entities'][2] == edit['after'] and lookup['2510.26830'][1]['annotation']['entities'][2] == edit['before']
    assert [p['label'] for p in ann['relations']] == [p['label'] for p in lookup['2510.26830'][1]['annotation']['relations']]
    omitted = copy.deepcopy(edit); omitted['touchingPairs'].pop()
    with pytest.raises(ValueError, match='Every touching'): scope.response_for(omitted, *lookup[edit['arxivId']])
    fabricated = copy.deepcopy(edit); fabricated['touchingPairs'][2]['label'] = 'USED_FOR'
    with pytest.raises(ValueError, match='unknown promotion'): scope.response_for(fabricated, *lookup[edit['arxivId']])
    shared_head = copy.deepcopy(decisions['1804.07461']); shared_head['action'] = 'admit'; shared_head['entities'] = []
    with pytest.raises(ValueError, match='shared-head'): scope.response_for(shared_head, *lookup[shared_head['arxivId']])
    with pytest.raises(FileExistsError): scope.generate(Path(__file__).parent.resolve())
    repair = inventory.read(inventory.CONTRACT); ref, prior = lookup[repair['arxivId']]
    fixed, mapping = inventory.add_method(ref, prior, repair)
    assert len(fixed['entities']) == 19 and fixed['entities'][0]['text'] == 'large-scale language models'
    old_pairs = {(p['head'], p['tail']): p for p in prior['annotation']['relations']}
    new_pairs = {(p['head'], p['tail']): p for p in fixed['relations']}
    assert len(new_pairs) == 60 and len(old_pairs) == 45
    for (h, t), p in old_pairs.items():
        assert new_pairs[(mapping[h], mapping[t])] == p | {'head': mapping[h], 'tail': mapping[t]}
    assert len([p for p in fixed['relations'] if p['head'] == 'e1']) == 15
    assert all(p['label'] == 'UNRESOLVED' for p in fixed['relations'] if p['head'] == 'e1')
    overlap = copy.deepcopy(repair); overlap['addEntity'] = {k: prior['annotation']['entities'][0][k] for k in ('start', 'end', 'text', 'label')}; overlap['addEntity']['label'] = 'METHOD'
    with pytest.raises(ValueError, match='overlapping'): inventory.add_method(ref, prior, overlap)
    with pytest.raises(FileExistsError): inventory.build(Path(__file__).parent.resolve())

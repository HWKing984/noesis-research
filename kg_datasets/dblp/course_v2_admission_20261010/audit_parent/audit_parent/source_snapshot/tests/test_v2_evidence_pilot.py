import copy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import prepare_v2_evidence_pilot as v2


def source():
    config = v2.read(v2.CONTRACT); folder = v2.c.ROOT/config['abstractSource']
    return v2.c.read_jsonl(folder/'references.jsonl'), v2.c.read_jsonl(folder/'reviewed_receipts.jsonl')


def test_inventory_is_source_bound_and_unknown_never_negative():
    refs, receipts = source(); docs, excluded, counts = v2.inventory(refs, receipts)
    assert len(docs) == 65 and len(excluded) == 5
    assert counts['entitySupport'] == {'METHOD': 458, 'TASK': 260, 'DATASET': 69}
    assert counts['relationSupport'] == {'USED_FOR': 307, 'EVALUATED_ON': 64, 'NO_RELATION': 37, 'UNRESOLVED': 1949}
    pilot = v2.select_pilot(docs, v2.read(v2.CONTRACT)['pilotStrata'])
    assert len(pilot) == len({r['arxivId'] for r, _, _ in pilot}) == 12
    assert v2.Counter(s for _, _, s in pilot) == {'evaluation_positive': 4, 'explicit_negative': 4, 'dataset_unresolved': 4}
    assert all(r['split'] == 'train' for r, _, _ in pilot)


@pytest.mark.parametrize('fault', ['heldout', 'hash', 'kind', 'receipt', 'duplicate'])
def test_bad_training_sources_fail_closed(fault):
    refs, receipts = source(); refs = copy.deepcopy(refs); receipts = copy.deepcopy(receipts)
    if fault == 'heldout': refs[0]['split'] = 'test'
    elif fault == 'hash': refs[0]['textSha256'] = '0'*64
    elif fault == 'kind': refs[0]['textKind'] = 'title'
    elif fault == 'receipt': receipts[0]['annotation']['relations'][0]['label'] = 'NO_RELATION'
    else: refs[1] = refs[0]; receipts[1] = receipts[0]
    with pytest.raises(ValueError): v2.inventory(refs, receipts)


@pytest.mark.parametrize('fault', ['group', 'paper', 'arxiv', 'external'])
def test_metadata_conflicts_rejected(fault):
    ref = {'split': 'train', 'publicationId': 'paper', 'groupId': 'group', 'arxivId': '1234.56789'}
    splits = [{'publicationId': 'paper', 'groupId': 'group', 'split': 'train'}]; selected = []; supplement = []
    if fault == 'group': ref['groupId'] = 'other'
    elif fault == 'paper': splits[0]['split'] = 'dev'
    elif fault == 'arxiv': supplement = [{'arxivId': ref['arxivId']}]
    else: splits = []
    with pytest.raises(ValueError): v2.check_isolation([ref], splits, selected, supplement)


def test_metadata_checks_use_no_heldout_text_and_output_guards(tmp_path):
    with patch.object(v2.c, 'ROOT', tmp_path/'root'):
        with pytest.raises(ValueError, match='outside datasets'): v2.prepare(tmp_path/'outside')
    with pytest.raises(FileExistsError): v2.prepare(tmp_path)
    refs, receipts = source(); config = v2.read(v2.CONTRACT)
    with patch.object(v2.c, 'read_jsonl', wraps=v2.c.read_jsonl) as reads:
        isolation = v2.check_isolation(refs, v2.c.read_jsonl(v2.c.ROOT/config['splitMetadata']),
            v2.read(v2.c.ROOT/config['abstractSelectionMetadata'])['selected'], v2.read(v2.c.ROOT/config['supplementMetadata'])['seeds'])
    assert isolation['publicationGroupAndArxivMetadataConflicts'] == 0
    assert all('dev_' not in p.args[0].name and 'test_' not in p.args[0].name for p in reads.call_args_list)
    assert not isolation['reservedTestTextOverlapChecked']


@pytest.mark.parametrize('fault', [None, 'reference_hash', 'split', 'literal', 'unresolved'])
def test_encoded_title_rows_use_canonical_train_references(fault):
    config = v2.read(v2.CONTRACT); folder = v2.c.ROOT/config['titleSource']
    ner = v2.c.read_jsonl(folder/'ner_inputs_train.jsonl'); pairs = v2.c.read_jsonl(folder/'relation_inputs_train.jsonl')
    refs = v2.c.read_jsonl(v2.c.ROOT/config['titleTrainReferences'])
    split_rows = v2.c.read_jsonl(v2.c.ROOT/config['splitMetadata'])
    assert 'split' not in ner[0] and 'textKind' not in pairs[0]
    if fault is None:
        counts = v2.title_inventory(ner, pairs, refs, split_rows)
        assert counts['NERDocuments'] == 1219 and counts['relationPairs'] == 975
        assert counts['entitySupport'] == {'METHOD': 1545, 'TASK': 1039, 'DATASET': 12}
        assert counts['relationSupport'] == {'USED_FOR': 937, 'EVALUATED_ON': 3, 'NO_RELATION': 35}
        return
    if fault == 'reference_hash': ner[0]['referenceSha256'] = '0'*64
    elif fault == 'split': refs[0]['split'] = 'dev'
    elif fault == 'literal': ner[0]['entities'][0]['text'] = 'invented'
    else: pairs[0]['label'] = 'UNRESOLVED'
    with pytest.raises(ValueError): v2.title_inventory(ner, pairs, refs, split_rows)

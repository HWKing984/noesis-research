"""One bounded source/identity check; not a model-quality evaluation."""
import copy
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import expand_train_benchmarks as expansion


def test_train_benchmark_identity_and_scope():
    with patch.object(expansion.c, 'read_jsonl', wraps=expansion.c.read_jsonl) as reads:
        config, _, refs, receipts = expansion.locked()
    assert {p.args[0].name for p in reads.call_args_list} == {'train_references.jsonl', 'train_reviewed_receipts.jsonl', 'corpus_manifest.jsonl', 'corpus_split_manifest.jsonl'}
    assert len(config['seeds']) == 4 and len(refs) == len(receipts) == 58 and all(r['split'] == 'train' for r in refs)
    seeds = copy.deepcopy(config['seeds']); seed = seeds[0]
    with pytest.raises(ValueError, match='Existing paper'): expansion.reject_identity_overlap(seeds, [{'publicationId': 'journals/corr/abs-'+seed['arxivId'].replace('.', '-'), 'text': 'different display'}], [])
    with pytest.raises(ValueError, match='Existing paper'): expansion.reject_identity_overlap(seeds, [{'publicationId': 'conf/held-out/alternate', 'text': seed['title'].upper()+' .', 'split': 'test'}], [])
    with pytest.raises(ValueError, match='Existing paper'): expansion.reject_identity_overlap(seeds, [], [{'publicationId': 'arxiv:'+seed['arxivId'], 'title': seed['title']}])
    with pytest.raises(ValueError, match='Malformed'): expansion.reject_identity_overlap(seeds+[seed], [], [])
    with pytest.raises(FileExistsError): expansion.collect(Path(__file__).parent.resolve())
    with pytest.raises(FileExistsError): expansion.snapshot(Path('missing'), Path('missing'), Path(__file__).parent.resolve())

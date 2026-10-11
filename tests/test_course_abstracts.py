"""Small source/split/offset checks; none of these certify semantic labels."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import course_weak as c
import course_graph as g
from collect_course_abstracts import plan_sources
from compile_course_ai import literal_span
from collect_course_abstract_pages import parse_page

def test_locked_abstract_cohort_and_source_offsets_never_reuse_title_labels():
    selected,cached,_,summary=plan_sources()
    assert summary['selectedCounts']=={'train':60,'dev':20,'test':20}
    assert len({r['groupId'] for r in selected})==100
    splits={r['publicationId']:r for r in c.read_jsonl(ROOT/'kg_datasets/dblp/course_v4_weak/corpus_split_manifest.jsonl')}
    prior=[ROOT/'kg_datasets/dblp'/p/'references.jsonl' for p in ('course_v4_weak','course_v4_holdout_20261007_29')]
    excluded={splits[r['publicationId']]['groupId'] for p in prior for r in c.read_jsonl(p)}
    assert not {r['groupId'] for r in selected}&excluded
    assert not {r['arxivId'] for r in selected}&{r['arxivId'] for r in cached}
    assert all(splits[r['publicationId']]['split']==r['split'] for r in selected)
    sources=ROOT/'kg_datasets/dblp/course_abstract_sources_20261008_32'
    pilot=ROOT/'kg_datasets/dblp/course_abstract_pilot_20261008_32'
    g.verified_files(sources);g.verified_files(pilot)
    abstracts={r['arxivId']:r for r in c.read_jsonl(sources/'abstracts.jsonl')}
    refs=c.read_jsonl(pilot/'references.jsonl');receipts=c.read_jsonl(pilot/'generation_receipts.jsonl')
    for ref,receipt in zip(refs,receipts):
        parent=abstracts[ref['arxivId']];span=ref['sourceOffset']
        assert parent['abstract'][span['start']:span['end']]==ref['text']
        assert ref['split']=='train' and ref['textKind']=='abstract_excerpt'
        assert not c.validate_receipt(receipt,ref)
        assert not c.eligible_tasks(receipt,ref)['ner'] # No self-review yet in generation.
        for entity in receipt['annotation']['entities']:
            assert parent['abstract'][span['start']+entity['start']:span['start']+entity['end']]==entity['text']
        changed=copy.deepcopy(receipt['annotation']);changed['textSha256']='0'*64
        assert c.validate_response(changed,ref)
    with pytest.raises(ValueError):literal_span({'text':'GLUE','label':'DATASET'},'SuperGLUE after GLUE')
    assert literal_span({'text':'GLUE','label':'DATASET','occurrence':2},'SuperGLUE after GLUE')['start']==16
    requested={'arxivId':'2107.03374'}
    html=b'<meta name="citation_title" content="A &amp; B"><meta name="citation_arxiv_id" content="2107.03374v2"><meta name="citation_abstract" content="Original &lt;formula&gt; text.">'
    assert parse_page(html,requested)==('A & B','Original <formula> text.')
    with pytest.raises(ValueError):parse_page(html,{'arxivId':'9999.99999'})
    with pytest.raises(ValueError):parse_page(html+b'<meta name="citation_abstract" content="invented">',requested)
    with pytest.raises(ValueError):parse_page(b'<meta name="description" content="snippet">',requested)

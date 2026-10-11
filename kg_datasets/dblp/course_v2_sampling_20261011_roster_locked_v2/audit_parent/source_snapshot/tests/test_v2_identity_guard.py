import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import course_v2_identity as g
import harden_v2_identity as v

EMPTY = {'byPublication': {}, 'blockedPublications': {}}


@pytest.fixture(scope='module')
def historical():
    config = v.read(v.CONTRACT); parent = v.ROOT/config['parent']
    return v.rows(parent/'historical_exclusions.jsonl'), g.alias_index(v.metadata(v.ROOT/config['metadataSource']))


@pytest.mark.parametrize('value', ['2107.03374', 'arxiv:2107.03374v1', 'arXiv:2107.03374V2',
    ' ARXIV:2107.03374v12 ', 'journals/corr/abs-2107-03374v2',
    'https://arxiv.org/abs/2107.03374v2', 'https://ARXIV.ORG/pdf/2107.03374v2.pdf',
    'http://export.arxiv.org/pdf/2107.03374'])
def test_modern_aliases_are_one_paper(value):
    assert g.canonical_arxiv(value) == '2107.03374'


@pytest.mark.parametrize('value', [None, 12, '', ' ', 'cs/9901001', '0703.0001', '0700.0001', '2113.00001',
    '2107.00000', '2107.1234', '1412.12345', '1501.1234', '2107.03374v0', '2107.03374v01',
    '２１０７.０３３７４', '2107.03374v٢', 'arXiv: arxiv:2107.03374', 'journals/corr/abs-2107-invalid',
    'https://arxiv.org.evil/abs/2107.03374', 'https://arxiv.org@evil/abs/2107.03374',
    'https://user@arxiv.org/abs/2107.03374', 'https://arxiv.org:443/abs/2107.03374',
    'https://arxiv.org/abs/2107.03374?q=1', 'https://arxiv.org/abs/2107.03374#x',
    'https://arxiv.org/abs/2107%2e03374', 'https://arxiv.org/list/2107.03374',
    'https://arxiv.org/abs/2107.03374.pdf', 'https://arxiv.org/abs/2107.03374/'])
def test_unverifiable_or_malformed_arxiv_is_not_silently_admitted(value):
    with pytest.raises(ValueError): g.canonical_arxiv(value)


def test_format_boundary_and_identity_agreement():
    assert g.canonical_arxiv('0704.0001v1') == '0704.0001'
    assert g.canonical_arxiv('1412.9999') == '1412.9999'
    assert g.canonical_arxiv('1501.00001') == '1501.00001'
    row = {'publicationId': 'journals/corr/abs-2107-03374', 'groupId': 'group:a',
           'arxivId': 'ARXIV:2107.03374v2', 'sourceURL': 'https://arxiv.org/abs/2107.03374v1'}
    canonical = g.identity(row, EMPTY)
    assert canonical['canonicalPaperId'] == 'arxiv:2107.03374'
    assert g.identity(row | canonical, EMPTY) == canonical
    with pytest.raises(ValueError): g.identity(row | {'arxivId': '2107.00001'}, EMPTY)
    with pytest.raises(ValueError): g.identity({'canonicalArxivId': '2107.03374'}, EMPTY)
    with pytest.raises(ValueError): g.identity(row | {'canonicalPaperId': 'arxiv:2107.00001'}, EMPTY)


def test_real_history_attacks_and_source_url_aliases(historical):
    excluded, aliases = historical; result = v.regression(excluded, aliases)
    assert all(not r['before']['rejected'] and r['after']['rejected'] for r in result[:4])
    assert result[4]['before']['rejected'] and result[4]['after']['rejected']
    assert not result[5]['after']['rejected'] and result[5]['actualPaperExistenceVerified'] is False
    assert aliases['byPublication']['journals/corr/Abdelsamea15'] == '1511.00111'
    assert aliases['byPublication']['journals/corr/000117b'] == '1707.09725'
    assert aliases['coverage'] == {'sourceRows': 20000, 'canonicalArxivRows': 5425, 'uniqueCanonicalArxivIds': 5425,
        'fromEncodedKeyRows': 5253, 'fromURLOnlyRows': 172, 'keyAndURLAgreeRows': 1540,
        'noArxivMappingRows': 14575, 'quarantinedRows': 0}
    coverage = v.coverage(excluded, aliases)
    assert coverage['historicalMetadataRows'] == 20138 and coverage['historicalRowsWithCanonicalArxiv'] == 5563
    assert coverage['exhaustiveCrossSourceIsolationProven'] is False


@pytest.mark.parametrize('conflict', ['group', 'publication', 'version', 'text_hash', 'exposed',
    'text', 'abstract', 'fullText', 'body', 'missing', 'unknown_split', 'missing_canonical', 'invalid_hash'])
def test_metadata_partition_fail_closed(conflict):
    a = {'publicationId': 'paper:a', 'groupId': 'group:a', 'arxivId': '2601.00001v1', 'textSha256': 'a'*64, 'split': 'train'}
    b = {'publicationId': 'paper:b', 'groupId': 'group:b', 'arxivId': '2601.00002', 'textSha256': 'b'*64, 'split': 'test'}
    excluded = []
    if conflict == 'group': b['groupId'] = a['groupId']
    elif conflict == 'publication': b['publicationId'] = a['publicationId']
    elif conflict == 'version': b['arxivId'] = 'ARXIV:2601.00001v2'
    elif conflict == 'text_hash': b['textSha256'] = 'A'*64
    elif conflict == 'exposed': excluded = [b]
    elif conflict in ('text', 'abstract', 'fullText', 'body'): b[conflict] = 'sealed body'
    elif conflict == 'missing': del b['groupId']
    elif conflict == 'unknown_split': b['split'] = 'validation-ish'
    elif conflict == 'missing_canonical': del b['arxivId']
    elif conflict == 'invalid_hash': b['textSha256'] = 'bad'
    with pytest.raises(ValueError): g.validate_partition([a, b], excluded, EMPTY)


def test_train_exposure_preserved_but_duplicate_alias_inventory_rejected():
    a = {'publicationId': 'paper:a', 'groupId': 'group:a', 'arxivId': '2601.00001', 'split': 'train'}
    assert g.validate_partition([a], [a], EMPTY) == {'train': 1}
    assert g.validate_partition([a], [{'arxivId': '2601.00001', 'origin': 'legacy_metadata'}], EMPTY) == {'train': 1}
    b = a | {'publicationId': 'paper:b', 'groupId': 'group:b', 'arxivId': 'arXiv:2601.00001v2'}
    with pytest.raises(ValueError, match='Duplicate paper'): g.validate_partition([a, b], [], EMPTY)
    with pytest.raises(ValueError, match='Metadata-only exclusions'): g.validate_partition([a], [a | {'abstract': 'sealed body'}], EMPTY)
    with pytest.raises(ValueError, match='Missing exclusion'): g.validate_partition([a], [{}], EMPTY)


@pytest.mark.parametrize('kind', ['conflict', 'invalid_url', 'legacy', 'duplicate', 'bad_urls', 'bad_publication'])
def test_source_aliases_never_guess_identity(kind):
    row = {'publicationId': 'journals/corr/abs-2107-03374', 'sourceURLs': ['https://arxiv.org/abs/2107.03374']}
    if kind == 'conflict': row['sourceURLs'] = ['https://arxiv.org/abs/2107.00001']
    elif kind == 'invalid_url': row['sourceURLs'] = ['https://arxiv.org/abs/bad']
    elif kind == 'legacy': row = {'publicationId': 'legacy:a', 'sourceURLs': ['https://arxiv.org/abs/cs/9901001']}
    elif kind == 'duplicate':
        with pytest.raises(ValueError): g.alias_index([row, row])
        return
    elif kind == 'bad_urls':
        with pytest.raises(ValueError): g.alias_index([row | {'sourceURLs': [None]}])
        return
    elif kind == 'bad_publication':
        with pytest.raises(ValueError): g.alias_index([row | {'publicationId': ' padded '}])
        return
    aliases = g.alias_index([row]); assert aliases['coverage']['quarantinedRows'] == 1
    with pytest.raises(ValueError): g.identity({'publicationId': row['publicationId']}, aliases)
    with pytest.raises(ValueError): g.validate_partition([{'publicationId': 'new', 'groupId': 'g', 'arxivId': '2601.00001', 'split': 'dev'}], [], aliases)


BASE = {'positivePairs': 10, 'negativePairs': 2, 'unresolvedPairs': 0, 'totalPairs': 12,
        'sourcePapers': 10, 'referenceComplete': True}


@pytest.mark.parametrize('case', ['no_positive', 'no_negative', 'unresolved', 'incomplete', 'empty'])
def test_incomplete_evaluation_never_defaults_to_pass(case):
    ref = BASE.copy()
    if case == 'no_positive': ref.update(positivePairs=0, sourcePapers=0, totalPairs=2)
    elif case == 'no_negative': ref.update(negativePairs=0, totalPairs=10)
    elif case == 'unresolved': ref.update(unresolvedPairs=1, totalPairs=13)
    elif case == 'incomplete': ref['referenceComplete'] = False
    elif case == 'empty': ref.update(positivePairs=0, negativePairs=0, totalPairs=0, sourcePapers=0)
    result = g.evaluation_readiness(ref)
    assert result['status'] == result['promotionStatus'] == 'not_evaluable' and result['reasons']
    assert all(x is None for x in result['metrics'].values())


@pytest.mark.parametrize('fault', ['missing', 'negative', 'bool_count', 'bad_total', 'source_overcount', 'bad_flag'])
def test_reference_counts_cannot_be_fabricated(fault):
    ref = BASE.copy()
    if fault == 'missing': del ref['totalPairs']
    elif fault == 'negative': ref['negativePairs'] = -1
    elif fault == 'bool_count': ref['positivePairs'] = True
    elif fault == 'bad_total': ref['totalPairs'] = 999
    elif fault == 'source_overcount': ref['sourcePapers'] = 11
    elif fault == 'bad_flag': ref['referenceComplete'] = 'true'
    with pytest.raises(ValueError): g.evaluation_readiness(ref)


def test_rare_sources_and_complete_references_are_not_automatic_promotion():
    rare = g.evaluation_readiness(BASE | {'sourcePapers': 3})
    assert rare['status'] == 'reference_ready_for_scoring'
    assert rare['sourceSupportStatus'] == 'insufficient_source_support' and rare['promotionStatus'] == 'not_evaluable'
    ready = g.evaluation_readiness(BASE)
    assert ready['sourceSupportStatus'] == 'support_gate_met'
    assert ready['promotionStatus'] == 'requires_frozen_comparable_predictions' and ready['metrics']['f1'] is None


def test_real_build_isolated_replay_conservation_and_resigned_wrong_summary(tmp_path):
    output = tmp_path/'bundle'; summary = v.build(output)
    assert summary['RECandidatePairs'] == 85 and summary['relationSupport']['NO_RELATION'] == 0
    assert summary['evaluationReadiness'] == {'USED_FOR': 'not_evaluable', 'EVALUATED_ON': 'not_evaluable'}
    result = v.verify(output)
    process = subprocess.run([sys.executable, '-I', str(output/'source_snapshot/scripts/harden_v2_identity.py'),
        '--verify', str(output)], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert json.loads(process.stdout) == result and result['semanticAccuracyCertified'] is False
    with pytest.raises(FileExistsError): v.build(output)
    import course_weak as c
    manifest = v.read(output/'manifest.json')
    for name, fault, expected in [('identity_alias_index.json', lambda d: d['byPublication'].pop('journals/corr/Abdelsamea15'), 'alias_index_recomputed'),
        ('evaluation_readiness.json', lambda d: d['relations']['EVALUATED_ON'].update(status='passed'), 'evaluation_readiness_recomputed')]:
        original = (output/name).read_bytes(); changed = v.read(output/name); fault(changed)
        c.write_json(output/name, changed); altered = json.loads(json.dumps(manifest)); altered['filesSha256'][name] = v.sha(output/name)
        c.write_json(output/'manifest.json', altered)
        with pytest.raises(ValueError, match='identity_'+expected): v.verify(output)
        (output/name).write_bytes(original); c.write_json(output/'manifest.json', manifest)
    data = v.read(output/'summary.json'); data['acceptedNegativePairs'] = 5
    c.write_json(output/'summary.json', data)
    manifest = v.read(output/'manifest.json'); manifest['filesSha256']['summary.json'] = v.sha(output/'summary.json')
    c.write_json(output/'manifest.json', manifest)
    with pytest.raises(ValueError, match='identity_summary_recomputed'): v.verify(output)


def test_missing_or_failed_junit_never_creates_output(tmp_path):
    output = tmp_path/'bundle'
    with pytest.raises(FileNotFoundError): v.build(output, tmp_path/'missing.xml')
    assert not output.exists()
    evidence = tmp_path/'failed.xml'; evidence.write_text('<testsuites><testsuite failures="1"><testcase classname="tests.test_v2_identity_guard"/></testsuite></testsuites>', encoding='utf-8')
    with pytest.raises(ValueError): v.build(output, evidence)
    assert not output.exists()


def test_valid_junit_and_source_url_array_split(tmp_path):
    evidence = tmp_path/'passing.xml'
    evidence.write_text('<testsuites><testsuite failures="0" errors="0" skipped="0"><testcase classname="tests.test_v2_identity_guard"/></testsuite></testsuites>', encoding='utf-8')
    assert v.passing_junit(evidence) == 1
    source = tmp_path/'metadata.csv'
    source.write_text('publicationId:ID(Publication),urls:string[]\nnamed:key,https://example.org/a;https://arxiv.org/abs/2107.03374\n', encoding='utf-8')
    assert g.alias_index(v.metadata(source))['byPublication'] == {'named:key': '2107.03374'}

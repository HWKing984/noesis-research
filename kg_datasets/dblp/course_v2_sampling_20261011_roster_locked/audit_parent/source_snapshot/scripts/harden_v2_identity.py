"""Data-only identity repair; replay frozen supervision without changing labels or V1."""
import argparse
import csv
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import course_v2_identity as guard
import finalize_v2_supervision as previous

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT/'resources/course_v2_identity_guard_v1.json'
OUTPUT = ROOT/'kg_datasets/dblp/course_v2_identity_guard_20261010'
CORE = ('references.jsonl', 'generation_receipts.jsonl', 'reviewed_receipts.jsonl',
        'relation_ledger.jsonl', 'ner_candidates.jsonl', 're_candidates.jsonl')
read, rows, sha = previous.read, previous.rows, previous.sha


def metadata(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return [{'publicationId': r['publicationId:ID(Publication)'],
                 'sourceURLs': re.split(r';(?=https?://)', r['urls:string[]']) if r['urls:string[]'] else []}
                for r in csv.DictReader(stream)]


def regression(excluded, aliases):
    fixtures = [('case_prefix_mixed_case', 'arXiv:2107.03374v2', True),
        ('case_prefix_caps', 'ARXIV:2107.03374v2', True),
        ('case_corpus_dblp_alias', 'arxiv:1708.00052', True),
        ('case_named_dblp_url_alias', 'arxiv:1511.00111', True),
        ('control_lowercase_prefix', 'arxiv:2107.03374v2', True),
        ('control_fresh_synthetic', 'arxiv:2610.88888', False)]
    results = []
    for name, arxiv, expected in fixtures:
        assignment = {'publicationId': 'guard-fixture:'+name, 'groupId': 'guard-fixture-group:'+name,
                      'arxivId': arxiv, 'split': 'test'}
        record = {'test': name, 'metadata': assignment, 'expectedReject': expected,
                  'syntheticMetadataOnly': True, 'actualPaperExistenceVerified': False}
        for label, validator in (('before', lambda: previous.validate_partition([assignment], excluded)),
                                 ('after', lambda: guard.validate_partition([assignment], excluded, aliases))):
            try: validator(); record[label] = {'rejected': False, 'reason': None}
            except ValueError as error: record[label] = {'rejected': True, 'reason': str(error)}
        if record['after']['rejected'] is not expected: raise ValueError('Identity regression '+name)
        results.append(record)
    return results


def readiness(ledger):
    result = {}
    for label, tail_type in (('USED_FOR', 'TASK'), ('EVALUATED_ON', 'DATASET')):
        subset = [r for r in ledger if r['tail']['label'] == tail_type]
        counts = Counter(r['label'] for r in subset)
        result[label] = guard.evaluation_readiness({'positivePairs': counts[label], 'negativePairs': counts['NO_RELATION'],
            'unresolvedPairs': counts['UNRESOLVED'], 'totalPairs': len(subset),
            'sourcePapers': len({r['arxivId'] for r in subset if r['label'] == label}), 'referenceComplete': False})
    return {'kind': 'training_side_reference_readiness_not_evaluation_scores',
            'newValidationDocuments': 0, 'newTestDocuments': 0, 'relations': result}


def coverage(excluded, aliases):
    normalized = [guard.identity(r, aliases) for r in excluded]
    return aliases['coverage'] | {'historicalMetadataRows': len(excluded),
        'historicalRowsWithCanonicalArxiv': sum('canonicalArxivId' in r for r in normalized),
        'historicalUniqueCanonicalArxivIds': len({r['canonicalArxivId'] for r in normalized if 'canonicalArxivId' in r}),
        'historicalRowsWithoutArxivMapping': sum('canonicalArxivId' not in r for r in normalized),
        'historicalOrigins': dict(Counter(r['origin'] for r in excluded)), 'exhaustiveCrossSourceIsolationProven': False}


def passing_junit(path):
    root = ET.parse(path).getroot(); suites = list(root.iter('testsuite')); cases = list(root.iter('testcase'))
    if (not suites or not cases or any(int(s.get(k, '0')) for s in suites for k in ('errors', 'failures', 'skipped'))
            or any(t.find(k) is not None for t in cases for k in ('error', 'failure', 'skipped'))
            or 'tests.test_v2_identity_guard' not in {t.get('classname') for t in cases}):
        raise ValueError('Identity JUnit is not passing')
    return len(cases)


def build(output=OUTPUT, test_evidence=None):
    output = Path(output)
    if output.exists(): raise FileExistsError(output)
    if test_evidence is not None: passing_junit(test_evidence)
    config = read(CONTRACT); parent = ROOT/config['parent']
    if (config['version'] != 'course_v2_identity_guard_v1' or any(config[k] is not False for k in previous.FLAGS)
            or config['minimumReferencePapers'] != guard.MIN_REFERENCE_PAPERS): raise ValueError('Data-only contract drift')
    if sha(parent/'manifest.json') != config['parentManifestSha256']: raise ValueError('Parent binding drift')
    replay = previous.verify(parent); protection = read(parent/'production_protection.json')
    inputs = [CONTRACT, Path(__file__), ROOT/'scripts/course_v2_identity.py', ROOT/'tests/test_v2_identity_guard.py',
              ROOT/'docs/course_v2_identity_scope_v1.md', parent/'manifest.json', ROOT/config['metadataSource']]
    for field in ('externalAudit', 'externalResults', 'metadataSource'):
        path = Path(config[field]); path = path if path.is_absolute() else ROOT/path
        if sha(path) != config[field+'Sha256']: raise ValueError('Review/metadata drift '+field)
        if path not in inputs: inputs.append(path)
    for path, digest in read(parent/'manifest.json')['inputSha256'].items():
        if sha(Path(path) if Path(path).is_absolute() else ROOT/path) != digest: raise ValueError('Parent source drift')
    if any(sha(ROOT/p) != h for p, h in protection.items()): raise ValueError('V1 drift')
    source = metadata(ROOT/config['metadataSource']); aliases = guard.alias_index(source)
    old_excluded = rows(parent/'historical_exclusions.jsonl')
    if {r['publicationId'] for r in source} != {r['publicationId'] for r in old_excluded if r['origin'] == 'historical_corpus'}:
        raise ValueError('Metadata corpus binding drift')
    excluded = [r | guard.identity(r, aliases) for r in old_excluded]
    assignments = [r | guard.identity(r, aliases) for r in read(parent/'split_lock.json')['assignments']]
    guard.validate_partition(assignments, excluded, aliases)
    index_coverage = coverage(old_excluded, aliases); attacks = regression(old_excluded, aliases)
    state = readiness(rows(parent/'relation_ledger.jsonl')); stamp = datetime.now(UTC).isoformat()
    summary = read(parent/'summary.json') | {'status': 'identity_guard_fixed_missing_negatives_and_new_evaluation_not_training_ready',
        'createdAtUTC': stamp, 'identityCoverage': index_coverage, 'activePartitionGuard': config['activePartitionGuard'],
        'identityRegressionCases': len(attacks), 'evaluationReadiness': {k: v['status'] for k, v in state['relations'].items()},
        'notice': config['scopeLimit']}
    hashes = {p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p): sha(p) for p in inputs}
    import course_weak as c
    import export_course_evidence as evidence
    output.mkdir(parents=True)
    shutil.copytree(parent, output/'audit_parent')
    for name in CORE: shutil.copy2(parent/name, output/name)
    for name in ('production_protection.json',): shutil.copy2(parent/name, output/name)
    for field in ('externalAudit', 'externalResults'): shutil.copy2(config[field], output/Path(config[field]).name)
    (output/'metadata_sources').mkdir(); shutil.copy2(ROOT/config['metadataSource'], output/'metadata_sources/publications.csv')
    c.write_jsonl(output/'historical_exclusions.jsonl', excluded)
    lock = read(parent/'split_lock.json') | {'assignments': assignments, 'activePartitionGuard': config['activePartitionGuard'],
        'exclusionsSha256': sha(output/'historical_exclusions.jsonl'), 'aliasIndexFile': 'identity_alias_index.json'}
    for name, value in (('contract', config), ('split_lock', lock), ('summary', summary), ('parent_replay', replay),
        ('identity_alias_index', aliases), ('identity_coverage', index_coverage), ('identity_regression', attacks), ('evaluation_readiness', state)):
        c.write_json(output/(name+'.json'), value)
    snapshot = output/'source_snapshot'; shutil.copytree(parent/'source_snapshot', snapshot)
    bindings = read(snapshot/'source_bindings.json')
    for path in inputs[:5]:
        relative = path.relative_to(ROOT).as_posix(); target = snapshot/relative
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target); bindings[relative] = sha(path)
    c.write_json(snapshot/'source_bindings.json', bindings)
    if test_evidence is not None:
        (output/'check_history').mkdir(); shutil.copy2(test_evidence, output/'check_history/identity_checks.xml')
    body = '<p>仅修复身份与评测准入；未训练、未推理、未改标签或V1。所有新验证/测试成员为空。</p>'
    body += evidence.table(['历史书目身份映射', '行数'], [[k, index_coverage[k]] for k in
        ('sourceRows', 'canonicalArxivRows', 'fromEncodedKeyRows', 'fromURLOnlyRows', 'noArxivMappingRows', 'quarantinedRows')])
    body += evidence.table(['回归用例（仅合成身份元数据）', '旧拒绝', '新拒绝'], [[r['test'], r['before']['rejected'], r['after']['rejected']] for r in attacks])
    body += evidence.table(['训练侧参考完整性检查，不是模型评分', '正例', '负例', '未决', '来源篇数', '状态'],
        [[k, v['positivePairs'], v['negativePairs'], v['unresolvedPairs'], v['sourcePapers'], v['status']] for k, v in state['relations'].items()])
    body += f'<p>{index_coverage["noArxivMappingRows"]:,}条书目缺少已知arXiv映射，不代表它们不存在arXiv版本；本次没有证明全量跨来源去重。缺负例/参考不完整/覆盖不全不默认通过，P/R/F1均为null。</p>'
    (output/'09_annotation_expansion.html').write_text(evidence.page('V2身份隔离修复与不可评状态', body, stamp,
        ['identity_coverage.json', 'identity_regression.json', 'evaluation_readiness.json', 'split_lock.json']), encoding='utf-8')
    if (any(sha(ROOT/p) != h for p, h in protection.items()) or
            any(sha(Path(p) if Path(p).is_absolute() else ROOT/p) != h for p, h in hashes.items())):
        raise ValueError('Input or V1 drift')
    c.write_json(output/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'inputSha256': hashes,
        'filesSha256': {p.relative_to(output).as_posix(): sha(p) for p in output.rglob('*') if p.is_file()}})
    verify(output); return summary


def verify(bundle):
    """Portable stdlib-only replay; no live production or semantic certification."""
    bundle = Path(bundle).resolve(); config = read(bundle/'contract.json'); manifest = read(bundle/'manifest.json'); parent = bundle/'audit_parent'
    if sha(parent/'manifest.json') != config['parentManifestSha256']: raise ValueError('Parent manifest binding')
    result = previous.verify(parent); passed = set(result['categories'])

    def check(condition, name):
        if not condition: raise ValueError('identity_'+name)
        passed.add('identity_'+name)

    for name, digest in manifest['filesSha256'].items():
        path = (bundle/name).resolve()
        check(path.is_relative_to(bundle) and sha(path) == digest, 'file_hashes')
    check(config['version'] == 'course_v2_identity_guard_v1' and all(config[k] is False for k in previous.FLAGS)
          and config['minimumReferencePapers'] == guard.MIN_REFERENCE_PAPERS, 'authorization')
    for field in ('externalAudit', 'externalResults'):
        check(sha(bundle/Path(config[field]).name) == config[field+'Sha256'], 'external_review_binding')
    check(sha(bundle/'source_snapshot/resources/course_v2_identity_guard_v1.json') ==
          manifest['inputSha256']['resources/course_v2_identity_guard_v1.json'] and
          read(bundle/'source_snapshot/resources/course_v2_identity_guard_v1.json') == config, 'contract_binding')
    for name in CORE: check(sha(bundle/name) == sha(parent/name), 'labels_receipts_exports_unchanged')
    check(sha(bundle/'metadata_sources/publications.csv') == config['metadataSourceSha256'], 'source_csv_binding')
    source = metadata(bundle/'metadata_sources/publications.csv'); aliases = guard.alias_index(source)
    old_excluded = rows(parent/'historical_exclusions.jsonl')
    check({r['publicationId'] for r in source} == {r['publicationId'] for r in old_excluded if r['origin'] == 'historical_corpus'}, 'metadata_corpus_binding')
    check(read(bundle/'identity_alias_index.json') == aliases, 'alias_index_recomputed')
    index_coverage = coverage(old_excluded, aliases)
    check(read(bundle/'identity_coverage.json') == index_coverage, 'coverage_recomputed')
    excluded = rows(bundle/'historical_exclusions.jsonl')
    check(excluded == [r | guard.identity(r, aliases) for r in old_excluded], 'history_canonicalization')
    lock = read(bundle/'split_lock.json'); old_lock = read(parent/'split_lock.json')
    assignments = [r | guard.identity(r, aliases) for r in old_lock['assignments']]
    check(lock == old_lock | {'assignments': assignments, 'activePartitionGuard': config['activePartitionGuard'],
        'exclusionsSha256': sha(bundle/'historical_exclusions.jsonl'), 'aliasIndexFile': 'identity_alias_index.json'}, 'split_lock_conservation')
    check(guard.validate_partition(lock['assignments'], excluded, aliases) == {'train': 12}, 'active_guard_executed')
    attacks = regression(old_excluded, aliases)
    check(read(bundle/'identity_regression.json') == attacks, 'bypass_replay')
    check(all(not r['before']['rejected'] and r['after']['rejected'] for r in attacks[:4]), 'four_bypasses_closed')
    state = readiness(rows(bundle/'relation_ledger.jsonl'))
    check(read(bundle/'evaluation_readiness.json') == state, 'evaluation_readiness_recomputed')
    check(all(v['status'] == v['promotionStatus'] == 'not_evaluable' and all(x is None for x in v['metrics'].values())
          for v in state['relations'].values()), 'no_default_pass_or_scores')
    summary = read(bundle/'summary.json')
    expected = read(parent/'summary.json') | {'status': 'identity_guard_fixed_missing_negatives_and_new_evaluation_not_training_ready',
        'createdAtUTC': summary['createdAtUTC'], 'identityCoverage': index_coverage, 'activePartitionGuard': config['activePartitionGuard'],
        'identityRegressionCases': len(attacks), 'evaluationReadiness': {k: v['status'] for k, v in state['relations'].items()}, 'notice': config['scopeLimit']}
    check(summary == expected, 'summary_recomputed')
    check(read(bundle/'parent_replay.json') == result, 'parent_replay_binding')
    check(read(bundle/'production_protection.json') == read(parent/'production_protection.json'), 'protection_record_not_live_proof')
    for name, digest in read(bundle/'source_snapshot/source_bindings.json').items():
        path = (bundle/'source_snapshot'/name).resolve()
        check(path.is_relative_to(bundle/'source_snapshot') and sha(path) == digest, 'source_snapshot_binding')
        if name in manifest['inputSha256']: check(digest == manifest['inputSha256'][name], 'source_input_binding')
    if (bundle/'check_history/identity_checks.xml').exists(): passing_junit(bundle/'check_history/identity_checks.xml'); passed.add('identity_junit_passing')
    return {'status': 'passed', 'assertionCategories': len(passed), 'categories': sorted(passed),
        'semanticAccuracyCertified': False, 'liveProductionVerified': False, 'newModelMetrics': False,
        'evaluationInventoryLocked': False, 'acceptedNegativePairs': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, default=OUTPUT); parser.add_argument('--test-evidence', type=Path); parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if not args.verify and args.test_evidence is None: parser.error('Build requires completed passing --test-evidence; verification is stdlib-only.')
    print(json.dumps(verify(args.verify) if args.verify else build(args.output, args.test_evidence), ensure_ascii=False, indent=2))

"""One revised-input check; synthetic gates are in-memory, not model experiment results."""
import copy
import subprocess
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import course_weak as c
import train_revised_abstract_models as revised
from course_abstract_relation import rows_for
from evaluate_course_relation import score_pipeline


def test_revised_snapshot_is_bound_unknown_masked_and_promotion_blocked():
    config, parent, parent_re, data = revised.load_inputs()
    folder = ROOT/config['snapshot']; manifest = revised.g.verified_files(folder, config['snapshotManifestSha256'])
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    assert config['automaticPromotionAllowed'] is False and config['reportExpansionPaused'] is True
    assert 'reserved' in config['testPolicy'] and 'No final-test' in config['testPolicy']
    assert parent['promotionGates']['automaticPromotionAllowed'] is False and parent_re['automaticPromotionAllowed'] is False
    assert parent['promotionGates']['minimumReferenceEVALUATED_ONDev'] == 10 and parent['promotionGates']['minimumDocumentCoverage'] == 0.8
    for settings, batch in ((parent['NERTraining'], 2), (parent_re['RETraining'], 4)):
        assert settings['seed'] == 20261008 and settings['epochs'] == 6 and settings['batchSize'] == batch and settings['learningRate'] == 2e-5
    cohorts = {}
    for split in ('train', 'dev'):
        refs = c.read_jsonl(folder/(split+'_references.jsonl')); receipts = c.read_jsonl(folder/(split+'_reviewed_receipts.jsonl')); cohorts[split] = (refs, receipts)
        rebuilt = rows_for(refs, receipts)
        assert len(refs) == len(receipts) == (58 if split == 'train' else 19)
        assert rebuilt[4:] == ((1578, 1845) if split == 'train' else (99, 432))
        for name, expected in zip(('ner', 'relation', 'full_relation', 'excluded_ner'), rebuilt[:4]):
            assert data[split][name] == expected == c.read_jsonl(folder/(name+'_'+split+'.jsonl'))
        assert tuple(len(data[split][name]) for name in ('ner', 'relation', 'full_relation', 'excluded_ner')) == ((50, 267, 6, 8) if split == 'train' else (16, 333, 7, 3))
        assert Counter(p['label'] for p in data[split]['relation']) == config['expected'][split]['support']
        assert all(r['contractSha256'] == config['REParentSha256'] != config['revisionContractSha256'] and r['split'] == split for name in ('ner', 'relation', 'full_relation') for r in data[split][name])
        assert all(p['label'] != 'UNRESOLVED' for p in data[split]['relation'])
    assert not {r['groupId'] for r in cohorts['train'][0]} & {r['groupId'] for r in cohorts['dev'][0]}
    full = data['dev']['full_relation']; ids = {d['sampleId'] for d in full}
    refs = [p for p in data['dev']['relation'] if p['sampleId'] in ids]
    assert len(refs) == 107 and Counter(p['label'] for p in refs) == {'USED_FOR': 84, 'NO_RELATION': 23}
    assert sum(not any(p['sampleId'] == d['sampleId'] for p in refs) for d in full) == 1
    oracle = score_pipeline(full, refs, refs)
    assert oracle['positiveMicro']['truePositive'] == oracle['positiveMicro']['predicted'] == oracle['positiveMicro']['reference'] == 84
    assert oracle['perClass']['EVALUATED_ON']['reference'] == 0 and oracle['perClass']['EVALUATED_ON']['f1'] is None
    baseline = c.entity_agreement([('p', i) for i in range(84)], [('p', i) for i in range(42)]+[('r', i) for i in range(42)])
    comparison = {'pipelineMetrics': {'old_NER_old_RE': {'positiveMicro': baseline}, 'new_NER_new_RE': oracle}}
    gates = revised.gate_results(parent, data, comparison, {'perClass': {'DATASET': {'reference': 15}}})
    assert not gates['developmentGatesPassed'] and set(gates['blockedBy']) == {'completeReferenceEVALUATED_ONSupport', 'completeDocumentCoverage'}
    assert gates['parentGates'] == parent['promotionGates'] and not any(gates[k] for k in ('qualityPromotionPassed', 'modelPromoted', 'finalTestExecuted', 'finalRareSupportKnown'))
    raw = {'metrics': copy.deepcopy(oracle), 'predictions': refs[:1], 'probabilities': [[0.1, 0.8, 0.1]]}; original_raw = copy.deepcopy(raw)
    cleaned = revised.clean(raw)
    assert raw == original_raw and 'predictions' not in cleaned and 'probabilities' not in cleaned
    assert cleaned['metrics']['evaluationTarget'] == cleaned['metrics']['positiveMicro']['evaluationTarget'] == revised.TARGET
    assert all(m['evaluationTarget'] == revised.TARGET for m in cleaned['metrics']['perClass'].values())
    assert cleaned['metrics']['positiveMicro']['truePositive'] == 84 and cleaned['metrics']['perClass']['EVALUATED_ON']['f1'] is None
    scoped = revised.dev_scope(raw['metrics'], 'complete_exposed_dev_not_final_test')
    assert scoped['positiveMicro']['evaluationTarget'] == scoped['perClass']['EVALUATED_ON']['evaluationTarget'] == 'complete_exposed_dev_not_final_test' and raw == original_raw

    def rejects_load():
        try: revised.load_inputs()
        except ValueError: return
        raise AssertionError('An unbound or mutated revised input was accepted')

    real_read = revised.read; real_jsonl = c.read_jsonl; real_verified = revised.g.verified_files
    bad_config = copy.deepcopy(config); bad_config['snapshotManifestSha256'] = '0'*64
    with patch.object(revised, 'read', side_effect=lambda p: bad_config if p == revised.CONTRACT else real_read(p)):
        rejects_load()
    bad_manifest = copy.deepcopy(manifest); bad_manifest['inputSha256'][config['revisionContract']] = '0'*64
    with patch.object(revised.g, 'verified_files', side_effect=lambda p, *a: bad_manifest if p == folder else real_verified(p, *a)):
        rejects_load()
    bad_rows = copy.deepcopy(data['train']['ner']); bad_rows[0]['contractSha256'] = config['revisionContractSha256']
    with patch.object(c, 'read_jsonl', side_effect=lambda p: bad_rows if p == folder/'ner_train.jsonl' else real_jsonl(p)):
        rejects_load()
    bad_refs = copy.deepcopy(cohorts['dev'][0]); bad_refs[0]['split'] = 'train'
    with patch.object(c, 'read_jsonl', side_effect=lambda p: bad_refs if p == folder/'dev_references.jsonl' else real_jsonl(p)):
        rejects_load()
    bad_receipts = copy.deepcopy(cohorts['train'][1]); bad_receipts[0]['review'] = None
    with patch.object(c, 'read_jsonl', side_effect=lambda p: bad_receipts if p == folder/'train_reviewed_receipts.jsonl' else real_jsonl(p)):
        rejects_load()

    # Deliberately rebind a valid in-memory receipt/rows to reach the cross-split guard; no artifact is written.
    revision, original = revised.source_cohorts(); original = copy.deepcopy(original)
    grouped_refs, grouped_receipts = copy.deepcopy(cohorts['dev'])
    grouped_refs[0]['groupId'] = cohorts['train'][0][0]['groupId']; altered_ref = grouped_refs[0]; receipt = grouped_receipts[0]
    receipt['reference'] = copy.deepcopy(altered_ref)
    receipt['initialContentSha256'] = c.content_sha256(receipt['initialAnnotation'], altered_ref)
    receipt['annotation']['reviewOfSha256'] = receipt['initialContentSha256']; receipt['contentSha256'] = c.content_sha256(receipt['annotation'], altered_ref)
    receipt['review']['inputContentSha256'] = receipt['initialContentSha256']; receipt['review']['contentSha256'] = receipt['contentSha256']
    assert not c.validate_receipt(receipt, altered_ref)
    original['dev'][0][0]['groupId'] = altered_ref['groupId']
    replacements = {folder/'dev_references.jsonl': grouped_refs, folder/'dev_reviewed_receipts.jsonl': grouped_receipts}
    for name, rows in zip(('ner', 'relation', 'full_relation', 'excluded_ner'), rows_for(grouped_refs, grouped_receipts)[:4]): replacements[folder/(name+'_dev.jsonl')] = rows
    with patch.object(revised, 'source_cohorts', return_value=(revision, original)), patch.object(c, 'read_jsonl', side_effect=lambda p: replacements[p] if p in replacements else real_jsonl(p)):
        rejects_load()
    with patch.object(revised, 'load_inputs', side_effect=AssertionError('Existing-output guard must precede loading')), patch.dict(sys.modules, {'torch': None, 'transformers': None}):
        try: revised.run(folder)
        except FileExistsError: pass
        else: raise AssertionError('Existing output directory was accepted')
    cli = subprocess.run([sys.executable, str(ROOT/'scripts/train_revised_abstract_models.py'), 'preflight', '--test'], capture_output=True, text=True, timeout=15)
    assert cli.returncode == 2 and 'unrecognized arguments: --test' in cli.stderr

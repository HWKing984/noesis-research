"""Evidence rendering guards, not invented training or annotation results."""
import sys
import json
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import export_course_evidence as evidence


def test_highlight_escapes_source_and_preserves_unicode_offsets():
    text = '😀 <BERT> & NER'
    entities = [{'start': 3, 'end': 7, 'text': 'BERT', 'label': 'METHOD'}]
    output = evidence.highlight(text, entities)
    assert output.startswith('😀 &lt;') and '&gt; &amp; NER' in output
    assert 'class="METHOD"' in output
    with pytest.raises(ValueError):
        evidence.highlight(text, [{'start': 3, 'end': 7, 'text': 'BERT', 'label': 'onclick'}])
    with pytest.raises(ValueError):
        evidence.highlight(text, entities + entities)


def test_loss_plot_rejects_invented_missing_nonfinite_or_zero_steps():
    steps = [{'step': 1, 'loss': 2.0}, {'step': 2, 'loss': 0.01}]
    assert 'step 2' in evidence.loss_curve(steps)
    for invalid in ([steps[0]], [{'step': 1, 'loss': 2.0}, {'step': 3, 'loss': 0.1}],
                    [{'step': 1, 'loss': 2.0}, {'step': 2, 'loss': float('nan')}],
                    [{'step': 1, 'loss': 2.0}, {'step': 2, 'loss': 0.0}]):
        with pytest.raises(ValueError):
            evidence.loss_curve(invalid)


def test_report_page_explicitly_discloses_rendering_and_escapes_provenance():
    page = evidence.page('<title>', '<p>actual results</p>', '2026-10-06', ['<script>'])
    assert '&lt;title&gt;' in page and '&lt;script&gt;' in page
    assert '不是原始终端' in page and '不是人工 gold' in page


def test_actual_final_test_evidence_is_source_bound_and_does_not_overwrite(tmp_path):
    root = Path(__file__).resolve().parents[1]
    dataset = root / 'kg_datasets/dblp/course_v4_weak'
    snapshot = root / 'kg_datasets/dblp/course_v4_training_inputs_09'
    run = root / 'kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09'
    tests = root / 'kg_datasets/dblp/course_v4_runs/tests_20261006_round08_final.xml'
    output = tmp_path / 'actual_test_evidence'
    report = evidence.build_test(dataset, snapshot, run, tests, output)
    page = (output / '06_final_test.html').read_text(encoding='utf-8')
    assert report['pages'] == ['06_final_test.html'] and '74.37%' in page and '144 / 56' in page
    assert '不是人工gold' in page and '56 篇未决排除' in page
    before = evidence.c.file_sha256(output / 'manifest.json')
    with pytest.raises(FileExistsError):
        evidence.build_test(dataset, snapshot, run, tests, output)
    assert evidence.c.file_sha256(output / 'manifest.json') == before


def test_test_evidence_recomputes_scores_instead_of_trusting_resealed_json(tmp_path):
    root = Path(__file__).resolve().parents[1]
    run = tmp_path / 'resealed'
    shutil.copytree(root / 'kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09', run)
    result = json.loads((run / 'test_result.json').read_text())
    result['test']['metrics']['micro']['f1'] = 1.0
    evidence.c.write_json(run / 'test_result.json', result)
    manifest = json.loads((run / 'manifest.json').read_text())
    manifest['filesSha256']['test_result.json'] = evidence.c.file_sha256(run / 'test_result.json')
    evidence.c.write_json(run / 'manifest.json', manifest)
    output = tmp_path / 'must_not_exist'
    with pytest.raises(ValueError, match='predictions or scope'):
        evidence.build_test(root / 'kg_datasets/dblp/course_v4_weak', root / 'kg_datasets/dblp/course_v4_training_inputs_09',
                            run, root / 'kg_datasets/dblp/course_v4_runs/tests_20261006_round08_final.xml', output)
    assert not output.exists()


def test_relation_evidence_requires_real_sealed_runs_and_never_creates_empty_success(tmp_path):
    output = tmp_path / 'must_not_exist'
    with pytest.raises(ValueError,match='nonempty'):
        evidence.build_relation(tmp_path,tmp_path,[],tmp_path/'absent.xml',output)
    with pytest.raises(FileNotFoundError):
        evidence.build_relation(tmp_path,tmp_path,[tmp_path/'absent_run'],tmp_path/'absent.xml',output)
    assert not output.exists()


def test_actual_relation_evidence_discloses_baseline_tie_and_rejects_wrong_snapshot(tmp_path):
    root = Path(__file__).resolve().parents[1]
    dataset = root / 'kg_datasets/dblp/course_v4_weak'
    snapshot = root / 'kg_datasets/dblp/course_v4_training_inputs_09'
    runs = [root / 'kg_datasets/dblp/course_v4_runs' / name for name in
            ('re_development_20261006_10','re_balanced_development_20261006_11')]
    tests = root / 'kg_datasets/dblp/course_v4_runs/tests_20261006_round09_evidence.xml'
    output = tmp_path / 'actual_relation_evidence'
    report = evidence.build_relation(dataset,snapshot,runs,tests,output)
    page = (output / '07_relation_development.html').read_text(encoding='utf-8')
    assert report['pages']==['07_relation_development.html']
    assert '98.43%' in page and '2组模型选中轮预测均与类型多数基线相同' in page
    assert '5条负例全误报' in page and '未晋级为确证图谱事实' in page
    with pytest.raises(FileExistsError):
        evidence.build_relation(dataset,snapshot,runs,tests,output)
    bad = tmp_path / 'wrong_snapshot'
    with pytest.raises(ValueError,match='development artifacts'):
        evidence.build_relation(dataset,root/'kg_datasets/dblp/course_v4_training_inputs_08',runs,tests,bad)
    assert not bad.exists()


def test_relation_evidence_counts_follow_new_role_snapshot_not_old_fixed_numbers(tmp_path):
    root = Path(__file__).resolve().parents[1]
    dataset = root / 'kg_datasets/dblp/course_v4_weak'
    snapshot = root / 'kg_datasets/dblp/course_v4_training_inputs_10'
    run = root / 'kg_datasets/dblp/course_v4_runs/re_roles_development_20261006_12'
    output = tmp_path / 'new_role_counts'
    evidence.build_relation(dataset, snapshot, [run], root / 'kg_datasets/dblp/course_v4_runs/tests_20261006_round11_handoff.xml', output)
    page = (output / '07_relation_development.html').read_text(encoding='utf-8')
    assert '343条train实体对来自264篇题名' in page
    assert '162条dev实体对来自113篇题名' in page
    assert '258步' in page and '240步' not in page
    assert '315条train' not in page and '247篇题名' not in page


def test_actual_allclass_selection_evidence_reports_the_negative_tradeoff(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    dataset = root / 'kg_datasets/dblp/course_v4_weak'
    snapshot = root / 'kg_datasets/dblp/course_v4_training_inputs_10'
    runs = [root / 'kg_datasets/dblp/course_v4_runs' / name for name in (
        're_roles_development_20261006_12', 're_roles_balanced_development_20261006_13',
        're_roles_allclass_development_20261006_14')]
    tests = root / 'kg_datasets/dblp/course_v4_runs/tests_20261006_round11_handoff.xml'
    output = tmp_path / 'allclass_evidence'
    evidence.build_relation(dataset, snapshot, runs, tests, output)
    page = (output / '07_relation_development.html').read_text(encoding='utf-8')
    assert '按dev三类macro' in page and 'checkpoint_epoch_02' in page
    assert '75.66%' in page and '负例正确识别1/5条' in page
    assert 'Secflh' in page and '未晋级为确证图谱事实' in page
    verify = evidence.verify_files
    def mismatched_rule(folder):
        manifest = verify(folder)
        if folder == runs[-1]:
            manifest['selection'] = 'dev_positive_macro_f1_earliest_tie'
        return manifest
    monkeypatch.setattr(evidence, 'verify_files', mismatched_rule)
    bad = tmp_path / 'mismatched_rule'
    with pytest.raises(ValueError, match='sealed config'):
        evidence.build_relation(dataset, snapshot, runs, tests, bad)
    assert not bad.exists()


def test_relation_evidence_binds_representation_to_saved_checkpoint(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    run = root / 'kg_datasets/dblp/course_v4_runs/re_roles_allclass_development_20261006_14'
    verify = evidence.verify_files
    def incompatible_representation(folder):
        manifest = verify(folder)
        manifest['config']['representation'] = 'entity_markers'
        return manifest
    monkeypatch.setattr(evidence,'verify_files',incompatible_representation)
    output = tmp_path / 'must_not_exist'
    with pytest.raises(ValueError, match='representation'):
        evidence.build_relation(root/'kg_datasets/dblp/course_v4_weak',root/'kg_datasets/dblp/course_v4_training_inputs_10',
                                [run],root/'kg_datasets/dblp/course_v4_runs/tests_20261006_round14_final.xml',output)
    assert not output.exists()


def test_actual_entity_pair_experiment_evidence_keeps_rare_class_loss(tmp_path):
    root = Path(__file__).resolve().parents[1]
    runs = [root/'kg_datasets/dblp/course_v4_runs'/name for name in (
        're_roles_allclass_development_20261006_14','re_entity_development_20261006_15')]
    output = tmp_path/'entity_comparison'
    evidence.build_relation(root/'kg_datasets/dblp/course_v4_weak',root/'kg_datasets/dblp/course_v4_training_inputs_10',
                            runs,root/'kg_datasets/dblp/course_v4_runs/tests_20261006_round14_final.xml',output)
    page = (output/'07_relation_development.html').read_text(encoding='utf-8')
    assert 'pooled CLS' in page and '头→尾标记' in page
    assert 'checkpoint_epoch_03' in page and '77.56%' in page
    assert '负例正确识别3/5条' in page and '50.00%' in page
    assert '99.05%' in page and '未晋级为确证图谱事实' in page


def test_relation_evidence_rejects_invalid_probability_even_when_label_metric_matches(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    run = root/'kg_datasets/dblp/course_v4_runs/re_entity_development_20261006_15'
    read = evidence.c.read_jsonl
    def malformed(path):
        rows = read(path)
        if path==run/'dev_predictions.jsonl':
            rows[0]['probabilities']['USED_FOR']=-1.0
        return rows
    monkeypatch.setattr(evidence.c,'read_jsonl',malformed)
    output=tmp_path/'never'
    with pytest.raises(ValueError,match='probabilit'):
        evidence.build_relation(root/'kg_datasets/dblp/course_v4_weak',root/'kg_datasets/dblp/course_v4_training_inputs_10',
                                [run],root/'kg_datasets/dblp/course_v4_runs/tests_20261006_round15_final.xml',output)
    assert not output.exists()


def test_final_evidence_rejects_resealed_wrong_test_coverage(tmp_path):
    root = Path(__file__).resolve().parents[1]
    clone=tmp_path/'resealed_test'
    shutil.copytree(root/'kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09',clone)
    result=json.loads((clone/'test_result.json').read_text())
    result.update(queueReviewed=999,documents=999,eligibleCoverage=1.0)
    evidence.c.write_json(clone/'test_result.json',result)
    manifest=json.loads((clone/'manifest.json').read_text())
    manifest['filesSha256']['test_result.json']=evidence.c.file_sha256(clone/'test_result.json')
    evidence.c.write_json(clone/'manifest.json',manifest)
    output=tmp_path/'never'
    with pytest.raises(ValueError,match='predictions or scope'):
        evidence.build_test(root/'kg_datasets/dblp/course_v4_weak',root/'kg_datasets/dblp/course_v4_training_inputs_09',
                            clone,root/'kg_datasets/dblp/course_v4_runs/tests_20261006_round15_final.xml',output)
    assert not output.exists()

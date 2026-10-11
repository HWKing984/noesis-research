"""Recompute source-only amendments and create an honest browser evidence page."""
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import revise_source_annotations as revision
from export_course_evidence import page, table
from course_abstract_v1 import read, seal

c, g = revision.c, revision.g
SOURCE = ROOT/'kg_datasets/dblp/course_abstract_supplement_reviewed_20261009_49'
NEW = ROOT/'kg_datasets/dblp/course_abstract_supplement_relations_20261010_59_v2'
TRAIN = ROOT/'kg_datasets/dblp/course_diverse_train_roles_20261010_56_final'
OUTPUT = ROOT/'docs/evidence/20261010_round59_source_revision'


def main():
    if OUTPUT.exists(): raise FileExistsError('Preserve source amendment evidence')
    paths = [Path(__file__), revision.CONTRACT, NEW/'manifest.json', SOURCE/'manifest.json', TRAIN/'manifest.json',
             ROOT/'annotations/course_v4/train_task_review_20261010_59.md',
             ROOT/'annotations/course_v4/supplement_relation_review_20261010_59.md',
             ROOT/'scripts/export_course_evidence.py', ROOT/'scripts/capture_course_evidence.ps1',
             ROOT/'resources/course_graph_quality_v3_runtime.json']
    hashes = {p: c.file_sha256(p) for p in paths}
    for folder in (SOURCE, NEW, TRAIN):
        manifest = g.verified_files(folder)
        assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    refs = c.read_jsonl(NEW/'references.jsonl'); old = c.read_jsonl(SOURCE/'reviewed_receipts.jsonl'); current = c.read_jsonl(NEW/'reviewed_receipts.jsonl')
    assert refs == c.read_jsonl(SOURCE/'references.jsonl') and len(refs) == len(old) == len(current) == 8
    new_labels = Counter(); inherited = 0; changed_docs = []
    for ref, prior, after in zip(refs, old, current):
        assert not c.validate_receipt(after, ref) and after['review'] is not None
        assert all(after['annotation'][k] == prior['annotation'][k] for k in revision.role.NER_FIELDS)
        old_pairs = {(p['head'], p['tail']): p for p in prior['annotation']['relations']}
        assert len(old_pairs) == len(after['annotation']['relations'])
        for pair in after['annotation']['relations']:
            previous = old_pairs[(pair['head'], pair['tail'])]
            if previous['label'] != 'UNRESOLVED': assert pair == previous; inherited += 1
            elif pair['label'] != 'UNRESOLVED': new_labels[pair['label']] += 1
            else: assert pair == previous and pair['evidence'] is None
        if after != prior: changed_docs.append(ref['arxivId'])
    assert inherited == 88 and changed_docs == ['2003.10555', '2006.03654']
    assert new_labels == {'USED_FOR': 11, 'EVALUATED_ON': 3, 'NO_RELATION': 9}
    docs, pairs, full, excluded, unknown, total = revision.role.rows_for(refs, current)
    assert (len(docs), len(pairs), len(full), len(excluded), unknown, total) == (7, 111, 0, 1, 367, 478)
    for name, expected in (('ner_dev', docs), ('relation_dev', pairs), ('full_relation_dev', full), ('excluded_ner', excluded)):
        assert c.read_jsonl(NEW/(name+'.jsonl')) == expected
    summary = read(NEW/'summary.json')
    assert summary['strictBIOPassed'] and summary['maxMarkedTokens'] == 428
    assert all(summary[k] is False for k in ('trainingExecuted', 'inferenceExecuted', 'testContentConsumed', 'NERChanged', 'independentHumanGold', 'modelPromoted', 'qualityPromotionPassed'))
    train_refs = c.read_jsonl(TRAIN/'references.jsonl'); train_receipts = c.read_jsonl(TRAIN/'reviewed_receipts.jsonl'); inconsistent = []
    assert len(train_refs) == len(train_receipts) == 70
    for ref, receipt in zip(train_refs, train_receipts):
        assert ref['split'] == 'train' and not c.validate_receipt(receipt, ref)
        if not c.eligible_tasks(receipt, ref)['ner']: continue
        tasks = [e for e in receipt['annotation']['entities'] if e['label'] == 'TASK']
        for entity in tasks:
            for occurrence in re.finditer(re.escape(entity['text']), ref['text'], re.I):
                for other in tasks:
                    if occurrence.start() <= other['start'] < other['end'] <= occurrence.end() and (other['start'], other['end']) != occurrence.span(): inconsistent.append(ref['sampleId'])
    assert not inconsistent
    with urlopen('http://127.0.0.1:8765/api/health', timeout=15) as response: health = json.load(response)['data']
    assert health['status'] == 'ready' and health['graphId'] == 'ai-literature-63686318d85cccb07afb' and health['scope']['bibliographyTitles'] == 20000
    assert all(c.file_sha256(p) == sha for p, sha in hashes.items())
    OUTPUT.mkdir(parents=True); stamp = datetime.now(UTC).isoformat()
    checked = {'status': 'passed', 'checkedAtUTC': stamp, 'inheritedRelationsExact': inherited, 'addedSupport': dict(new_labels), 'summary': summary,
               'trainSourceReceiptsChecked': 70, 'eligibleTrainNER': 65, 'literalTaskInconsistencies': 0,
               'reservedTestParsed': False, 'trainingExecuted': False, 'modelPromoted': False,
               'liveStatus': health['status'], 'liveGraphId': health['graphId'], 'livePapers': 20000,
               'limits': 'Same-session AI source reference, not independent gold; no new accuracy score; complete rare-relation support remains0.'}
    c.write_json(OUTPUT/'check.json', checked)
    examples = c.read_jsonl(NEW/'additional_relation_dev.jsonl')
    selected = [next(p for p in examples if p['label'] == label) for label in ('USED_FOR', 'EVALUATED_ON', 'NO_RELATION')]
    body = ('<p>本轮没有训练、推理、改生产模型或消费预留最终测试。70条训练源收据检查、65篇可用NER：同文TASK字面长短一致性检查0项；3处范围候选暂缓，不能当作全部标签语义正确。</p>'
            + table(('补充开发8篇固定队列', '旧49版', '新59版'), [('NER可用/隔离', '7 / 1', '7 / 1'), ('已判关系', 88, 111), ('USED_FOR / EVALUATED_ON / NO_RELATION', '70 / 14 / 4', '81 / 17 / 13'), ('未决 / 全候选', '390 / 478', '367 / 478'), ('完整文档 / 完整EVAL支持', '0 / 0', '0 / 0')])
            + '<h2>23条有源证据的新增判断</h2><p>11条用途、3条评测、9条局部角色对照负例。拒绝另2条省略模型归属候选，继续未决。SuperGLUE仅同一数据集提及共指，不转移单模型/集成模型成绩；多条提及边不是多份独立实验。</p>'
            + table(('类别', '头实体 → 尾实体', '源文判断理由'), [(p['label'], p['head']['text']+' → '+p['tail']['text'], p['reason']) for p in selected])
            + '<h2>真正检查了什么</h2><p>88条旧关系全文证据/标签逐项不变；所有NER、原文与其余6篇收据不变；367未决对无负例填充。7篇真实BIO往返和111个实体标记关系编码通过，最长428子词；输入在读取前绑定哈希，变化时拒绝成功封存。</p>'
            + '<p>第58轮生产图和应用已恢复：20,000文献，graphId ai-literature-63686318d85cccb07afb。摘要模型仍未晋级；本页没有新的准确率或F1，完整稀有关系评测支持仍未解决。</p>')
    (OUTPUT/'09_annotation_expansion.html').write_text(page('第59轮：源证据补充与训练边界复核', body, stamp, [str(NEW/'manifest.json'), str(OUTPUT/'check.json')]), encoding='utf-8')
    seal(OUTPUT, paths)
    manifest = read(OUTPUT/'manifest.json'); manifest['kind'] = 'real_artifact_visualization_not_original_console_ui'; c.write_json(OUTPUT/'manifest.json', manifest)
    print({'check': 'passed', 'knownPairs': len(pairs), 'reservedTestParsed': False})


if __name__ == '__main__': main()

"""Audit saved abstract NER development artifacts and capture them; no fit, test inference or DB write."""
import argparse
import json
import math
import shutil
import sys
from collections import Counter
from datetime import UTC,datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import course_graph as g
import course_weak as c
import train_course_ner as ner
from course_abstract_v1 import CONTRACT,TRAIN,read
from train_abstract_ner import load_inputs
from export_course_evidence import page,table,highlight,loss_curve

RUNS=ROOT/'kg_datasets/dblp/course_v4_runs'
RUN=RUNS/'abstract_ner_development_20261008_35'
DEV=ROOT/'kg_datasets/dblp/course_abstract_dev_reviewed_20261008_35'
SNAPSHOT=ROOT/'kg_datasets/dblp/course_abstract_v1_inputs_20261008_35'
EVIDENCE=ROOT/'docs/evidence/20261008_round35'

def checked():
    previous=read(RUNS/'verification_20261008_round34.json')
    assert previous['passed'] and all(c.file_sha256(ROOT/p)==sha for p,sha in previous['immutableSourceSha256'].items())
    g.verified_files(ROOT/'docs/evidence/20261008_round34',previous['evidenceManifestSha256'])
    assert c.file_sha256(ROOT/'docs/evidence/20261008_round34/captures.json')==previous['capturesSha256']
    active=g.configured_bundle();assert c.file_sha256(active/'manifest.json')==previous['audit']['graphManifestSha256']
    for name in ('ner_final_test_20261006_09','re_final_test_20261006_17','refresh_final_test_20261007_29'):g.verified_files(RUNS/name)
    suite=ElementTree.parse(RUNS/'tests_20261008_round35_all.xml').getroot().find('testsuite')
    assert suite.get('tests')=='363' and all(suite.get(k)=='0' for k in ('errors','failures','skipped'))
    config,rows=load_inputs(SNAPSHOT,DEV)
    for folder in (TRAIN,DEV,RUN):
        manifest=g.verified_files(folder)
        assert all(c.file_sha256(ROOT/p)==sha for p,sha in manifest['inputSha256'].items())
    result=read(RUN/'development_result.json');state=read(RUN/'status.json');summary=read(SNAPSHOT/'summary.json')
    assert result['passed'] and state['status']=='completed' and state['trainingStarted']
    assert result['classifierAndEncoderChanged'] and result['reloadPredictionsIdentical'] and not result['devUsedForGradient']
    assert result['bestCheckpoint']=='checkpoint_epoch_04' and result['epochs']==6 and result['steps']==state['steps']==90
    assert all(result[k] is False for k in ('testEvaluated','testTokenized','modelPromoted','qualityPromotionPassed'))
    assert state['settings']==config['NERTraining'] and state['testEvaluated'] is False and state['testTokenized'] is False
    assert c.file_sha256(RUN/result['bestCheckpoint']/'model.safetensors')!=config['NERTraining']['initialWeightsSha256']
    predictions=c.read_jsonl(RUN/'dev_predictions.jsonl')
    assert [p['sampleId'] for p in predictions]==[r['sampleId'] for r in rows['dev']]
    assert all(p['referenceEntities']==r['entities'] for p,r in zip(predictions,rows['dev']))
    score=ner.score_rows(rows['dev'],[p['predictedEntities'] for p in predictions],evaluation_target='dev_ai_reference_agreement_not_human_gold')
    assert score==result['bestDev']['metrics']
    spans=lambda entities:{(e['start'],e['end'],e['label']) for e in entities}
    assert c.read_jsonl(RUN/'dev_errors.jsonl')==[p for p in predictions if spans(p['referenceEntities'])!=spans(p['predictedEntities'])]
    steps=c.read_jsonl(RUN/'steps.jsonl');epochs=read(RUN/'epochs.json');train_ids={r['sampleId'] for r in rows['train']}
    assert [s['step'] for s in steps]==list(range(1,91)) and len(epochs)==6
    for epoch in range(1,7):
        ids=[sample for s in steps if s['epoch']==epoch for sample in s['sampleIds']]
        assert len(ids)==29 and set(ids)==train_ids
    assert all(math.isfinite(s['loss']) and math.isfinite(s['gradientNorm']) for s in steps)
    scores=[e['dev']['metrics']['micro']['f1'] for e in epochs]
    assert [e['epoch'] for e in epochs]==list(range(1,7)) and scores.index(max(scores))==3 and result['bestDev']==epochs[3]['dev']
    assert len(rows['train'])==29 and len(rows['dev'])==16 and summary['entitySupport']['dev']['DATASET']==15
    dataset_docs=[r for r in rows['dev'] if any(e['label']=='DATASET' for e in r['entities'])]
    assert len(dataset_docs)==4 and not summary['relationTrainingReady'] and not c.read_jsonl(SNAPSHOT/'relation_dev.jsonl')
    assert len(c.read_jsonl(SNAPSHOT/'relation_train.jsonl'))==17 and all(r['label']!='NO_RELATION' for r in c.read_jsonl(SNAPSHOT/'relation_train.jsonl'))
    counts={label:{'FP':m['predicted']-m['truePositive'],'FN':m['reference']-m['truePositive']} for label,m in score['perClass'].items()}
    audit={'passed':True,'engineeringTests':363,'trainDocuments':29,'devDocuments':16,'devQueueDocuments':19,'datasetReferenceDocuments':len(dataset_docs),
        'strictCounts':counts,'allEntityAgreementDocuments':len(predictions)-len(c.read_jsonl(RUN/'dev_errors.jsonl')),
        'devMetricsRecomputedFromSavedSpans':True,'eachEpochTrainCoverageVerified':True,'modelRetrained':True,'relationTrained':False,
        'testEvaluated':False,'testContentConsumed':False,'modelPromoted':False,'qualityPromotionPassed':False,'databaseWritten':False,'serviceRestarted':False,
        'productionGraphManifestSha256':c.file_sha256(active/'manifest.json'),'runManifestSha256':c.file_sha256(RUN/'manifest.json'),
        'bestWeightsSha256':c.file_sha256(RUN/result['bestCheckpoint']/'model.safetensors'),'evaluationTarget':'dev_ai_reference_not_human_gold',
        'scope':'Offline candidate and immutable artifacts audited. No new live browser acceptance or pipeline/final-test performance; source integrity hashing does not consume test text semantically.'}
    return previous,rows,result,steps,epochs,audit

def main(action):
    previous,rows,result,steps,epochs,audit=checked()
    if action=='prepare':
        if EVIDENCE.exists():raise FileExistsError('Preserve evidence')
        sources=EVIDENCE/'sources';sources.mkdir(parents=True)
        try:
            paths=[Path(__file__),CONTRACT,ROOT/'README.md',ROOT/'docs/system_status_round35.md',ROOT/'docs/model_optimization_abstract_v1.md',
                ROOT/'scripts/course_abstract_v1.py',ROOT/'scripts/train_abstract_ner.py',ROOT/'tests/test_abstract_v1.py',
                ROOT/'annotations/course_v4/abstract_dev_decisions_20261008_35.json',ROOT/'annotations/course_v4/abstract_dev_reviews_20261008_35.json',RUNS/'tests_20261008_round35_all.xml']
            paths += [folder/name for folder,names in ((DEV,('summary.json','manifest.json','generation_receipts.jsonl','reviewed_receipts.jsonl')),
                (SNAPSHOT,('summary.json','manifest.json','excluded_ner_train.jsonl','excluded_ner_dev.jsonl')),
                (RUN,('manifest.json','status.json','development_result.json','baseline_dev.json','dictionary_dev.json','steps.jsonl','epochs.json','dev_predictions.jsonl','dev_errors.jsonl'))) for name in names]
            for path in paths:
                target=sources/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
            c.write_json(EVIDENCE/'audit_state.json',audit)
            body='<h2>同一摘要dev上的NER对照 · 不是最终测试</h2>'+table(['模型','Precision','Recall','F1','TP / 预测 / 参考'],
                [[name,f"{m['precision']:.2%}",f"{m['recall']:.2%}",f"{m['f1']:.2%}",f"{m['truePositive']} / {m['predicted']} / {m['reference']}"] for name,m in
                [('旧题名权重迁移',result['baselineDev']['metrics']['micro']),('train词典',result['dictionaryDev']['micro']),('新摘要NER · epoch4',result['bestDev']['metrics']['micro'])]])
            body+='<h2>逐类表现与已知缺陷</h2>'+table(['类别','Precision','Recall','F1','参考support','FP / FN'],
                [[label,f"{m['precision']:.2%}",f"{m['recall']:.2%}",f"{m['f1']:.2%}",m['reference'],f"{audit['strictCounts'][label]['FP']} / {audit['strictCounts'][label]['FN']}"] for label,m in result['bestDev']['metrics']['perClass'].items()])
            body+='<p>DATASET15个提及只覆盖4篇文献，不是15个独立数据集；仍有11个数据集假阳性。TASK F1仅52.54%；最佳权重仍有55次非法BIO转移，非法I丢弃、无强制修复。16篇每篇都至少有一处严格跨度/类别不一致；AI标签也可能有遗漏，不改参考追分。</p>'
            body+='<h2>数据、训练与隔离验收</h2>'+table(['核验项','实际结果'],[['合同','独立abstract_v1，原整篇Unicode文本，512token拒绝截断；不拼题名'],['NER输入','train29/37（78.38%） / dev16/19（84.21%）；隔离8 / 3'],['训练','RTX4060 Laptop · 6轮/90步；train梯度，dev选epoch4；编码器+分类头变化、重载预测一致'],['RE准入','train17正例，无明确负例；dev完整关系输入0对。UNRESOLVED屏蔽，未训练RE'],['最终测试','保留19篇摘要test内容未标注/分词/推理；旧09/17/29测试未重跑'],['线上版本','31轮图和旧模型不变；无入库/重启/自动晋级'],['工程检查','363项通过；严格dev指标按已保存预测重新计数核对，不是语义gold']])
            body+='<h2>真实step loss与逐轮开发结果</h2>'+loss_curve(steps)+table(['epoch','累计步数','dev F1','选择'],[[e['epoch'],e['steps'],f"{e['dev']['metrics']['micro']['f1']:.2%}",'最佳' if e['epoch']==4 else '未采用'] for e in epochs])
            sample=rows['dev'][1];predictions=c.read_jsonl(RUN/'dev_predictions.jsonl')[1]['predictedEntities']
            body+='<h2>RL-Pruner摘要 · 真实预测错误示例</h2><p>GoogleNet/ResNet截短后被误标为DATASET，MobileNet类别也误判；不是已解决的成功案例。</p><div class="title">'+highlight(sample['text'],predictions)+'</div>'
            (EVIDENCE/'09_annotation_expansion.html').write_text(page('独立摘要NER开发与残留缺陷 · 第35轮',body,datetime.now(UTC).isoformat(),['audit_state.json','sources/kg_datasets/dblp/course_v4_runs/abstract_ner_development_20261008_35/development_result.json','sources/kg_datasets/dblp/course_v4_runs/abstract_ner_development_20261008_35/steps.jsonl']),encoding='utf-8')
            c.write_json(EVIDENCE/'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','filesSha256':{p.relative_to(EVIDENCE).as_posix():c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
            print(json.dumps({'prepared':True,'engineeringTests':363,'candidateDevF1':result['bestDev']['metrics']['micro']['f1']}))
        except Exception as error:
            c.write_json(EVIDENCE/'failure.json',{'status':'failed_no_synthetic_fallback','errorType':type(error).__name__,'error':str(error)});raise
    else:
        output=RUNS/'verification_20261008_round35.json'
        if output.exists():raise FileExistsError('Preserve seal')
        g.verified_files(EVIDENCE);assert read(EVIDENCE/'audit_state.json')==audit
        captures=json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'))
        assert captures['status']=='completed' and len(captures['captures'])==1 and captures['originalConsoleScreenshot'] is False
        for image in captures['captures']:
            assert c.file_sha256(EVIDENCE/image['image'])==image['sha256'] and c.file_sha256(EVIDENCE/image['sourcePage'])==image['sourcePageSha256']
        c.write_json(output,{'passed':True,'checkedAtUTC':datetime.now(UTC).isoformat(),'engineeringTests':363,'audit':audit,
            'immutableSourceSha256':previous['immutableSourceSha256'],'previousVerificationSha256':c.file_sha256(RUNS/'verification_20261008_round34.json'),
            'evidenceManifestSha256':c.file_sha256(EVIDENCE/'manifest.json'),'capturesSha256':c.file_sha256(EVIDENCE/'captures.json'),
            'modelRetrained':True,'relationTrained':False,'testEvaluated':False,'qualityPromotionPassed':False,'reportExpansionPaused':True})
        print(json.dumps({'passed':True,'engineeringTests':363,'candidateDevF1':result['bestDev']['metrics']['micro']['f1'],'modelPromoted':False}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','seal'));main(parser.parse_args().action)

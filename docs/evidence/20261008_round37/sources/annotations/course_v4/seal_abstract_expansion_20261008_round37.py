"""Recompute the data-only experiment, retain regression decision, and seal real artifact screenshots."""
import argparse
import copy
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
import train_course_relation as re_model
from course_abstract_v1 import read
from train_expanded_abstract_ner import load_inputs
from evaluate_course_relation import score_pipeline
from train_abstract_relation import diagnose
from export_course_evidence import page,table,loss_curve
import seal_abstract_relation_20261008_round36 as previous_round

RUNS=ROOT/'kg_datasets/dblp/course_v4_runs'
RUN=RUNS/'abstract_ner_expansion_development_20261008_37'
SOURCE=ROOT/'kg_datasets/dblp/course_abstract_train_sources_20261008_37'
REVIEWED=ROOT/'kg_datasets/dblp/course_abstract_expansion_reviewed_20261008_37'
SNAPSHOT=ROOT/'kg_datasets/dblp/course_abstract_expansion_inputs_20261008_37'
EVIDENCE=ROOT/'docs/evidence/20261008_round37'

def dev_metric(raw):
    # The shared historic scorer defaults to a held-out label; change display metadata, not saved numbers.
    result=copy.deepcopy(raw);target='exposed_dev_AI_reference_not_final_test';result['evaluationTarget']=target
    result['entityScope']='predicted_NER_entities_without_reference_features'
    result['positiveMicro']['evaluationTarget']=target
    for row in result['perClass'].values():row['evaluationTarget']=target
    return result

def checked():
    previous_round.checked();previous=read(RUNS/'verification_20261008_round36.json')
    g.verified_files(ROOT/'docs/evidence/20261008_round36',previous['evidenceManifestSha256'])
    assert c.file_sha256(ROOT/'docs/evidence/20261008_round36/captures.json')==previous['capturesSha256']
    config,parent,rows=load_inputs(SNAPSHOT,SOURCE,REVIEWED);manifest=g.verified_files(RUN)
    assert all(c.file_sha256(ROOT/path)==sha for path,sha in manifest['inputSha256'].items())
    suite=ElementTree.parse(RUNS/'tests_20261008_round37_all.xml').getroot().find('testsuite')
    assert suite.get('tests')=='365' and all(suite.get(k)=='0' for k in ('errors','failures','skipped'))
    result=read(RUN/'development_result.json');state=read(RUN/'status.json');pipeline=read(RUN/'pipeline_development_result.json');summary=read(SNAPSHOT/'summary.json')
    assert state['status']=='completed' and state['trainingStarted'] and state['settings']==parent['NERTraining']
    assert result['passed'] and result['classifierAndEncoderChanged'] and result['reloadPredictionsIdentical'] and result['devRowsUnchanged'] and not result['devUsedForGradient']
    assert all(result[k] is False for k in ('testEvaluated','testTokenized','modelPromoted','qualityPromotionPassed'))
    assert result['trainDocuments']==len(rows['train'])==48 and result['devDocuments']==len(rows['dev'])==16
    steps=c.read_jsonl(RUN/'steps.jsonl');epochs=read(RUN/'epochs.json');ids={r['sampleId'] for r in rows['train']}
    assert result['steps']==state['steps']==len(steps)==144 and result['epochs']==len(epochs)==6 and [s['step'] for s in steps]==list(range(1,145))
    for epoch in range(1,7):
        seen=[sid for step in steps if step['epoch']==epoch for sid in step['sampleIds']];assert len(seen)==48 and set(seen)==ids
    assert all(math.isfinite(s['loss']) and math.isfinite(s['gradientNorm']) for s in steps)
    best=max(epochs,key=lambda e:e['dev']['metrics']['micro']['f1'])
    assert result['bestDev']==best['dev'] and result['bestCheckpoint']==f'checkpoint_epoch_{best["epoch"]:02d}' and best['epoch']==6
    predictions=c.read_jsonl(RUN/'dev_predictions.jsonl')
    assert [p['sampleId'] for p in predictions]==[r['sampleId'] for r in rows['dev']]
    assert all(p['referenceEntities']==r['entities'] for p,r in zip(predictions,rows['dev']))
    assert ner.score_rows(rows['dev'],[p['predictedEntities'] for p in predictions],evaluation_target='dev_ai_reference_agreement_not_human_gold')==result['bestDev']['metrics']
    for entry in c.read_jsonl(SNAPSHOT/'additional_alignment.jsonl'):
        row=next(r for r in rows['train'] if r['sampleId']==entry['sampleId']);offsets=entry['offsets'];labels=entry['labels']
        assert labels==c.align_bio(offsets,row['entities'],row['text'])
        decoded=ner.decode_bio([0 if tuple(o)==(0,0) else label for o,label in zip(offsets,labels)],offsets,row['text'])
        assert not decoded['invalidTransitions'] and decoded['entities']==[{k:e[k] for k in ('start','end','text','label')} for e in row['entities']]
    docs=c.read_jsonl(RUN/'pipeline_dev_documents.jsonl');refs=c.read_jsonl(RUN/'pipeline_dev_reference_pairs.jsonl');predicted=c.read_jsonl(RUN/'expanded_NER_old_RE_predictions.jsonl')
    metric=score_pipeline(docs,refs,predicted);saved=pipeline['expandedNER_oldRE'];assert all(metric[k]==saved[k] for k in metric)
    entities={p['sampleId']:p['predictedEntities'] for p in predictions}
    missed=[e for d in docs for e in diagnose(d,entities[d['sampleId']],[r for r in refs if r['sampleId']==d['sampleId']],[p for p in predicted if p['sampleId']==d['sampleId']])]
    assert missed==c.read_jsonl(RUN/'expanded_NER_old_RE_missed_relations.jsonl') and dict(Counter(e['primaryCause'] for e in missed))==saved['missedReferencePrimaryCauses']
    false=previous_round.pipeline_errors(docs,refs,predicted);micro=metric['positiveMicro'];assert len(false)==micro['predicted']-micro['truePositive']==85 and len(missed)==micro['reference']-micro['truePositive']==26
    errors={'falsePositive':len(false),'falseNegative':len(missed),'FPPrimaryCauses':dict(Counter(e['primaryCause'] for e in false)),
        'FNPrimaryCauses':dict(Counter(e['primaryCause'] for e in missed)),'falsePositiveExamples':false,'missedReferenceExamples':missed}
    for name,baseline in pipeline['previous'].items():assert score_pipeline(docs,refs,c.read_jsonl(previous_round.RUN/(name+'_predictions.jsonl')))==baseline
    assert pipeline['labelFreeInferenceMatchesNERDev'] and pipeline['fixedOldRE'] and len(docs)==5 and len(refs)==58 and pipeline['referenceEVALUATED_ON']==0
    candidate=metric['positiveMicro'];old=pipeline['previous']['new_NER_old_RE']['positiveMicro'];title=pipeline['previous']['old_NER_old_RE']['positiveMicro'];gates=parent['promotionGates']
    decision={'candidateNER':'rejected_pipeline_precision_and_f1_regression','baseline':'round35_abstract_NER_with_frozen_old_RE',
        'previousPipeline':copy.deepcopy(old),'candidatePipeline':copy.deepcopy(candidate),'pipelinePrecisionChange':candidate['precision']-old['precision'],'pipelineF1Change':candidate['f1']-old['f1'],
        'pipelineRecallChange':candidate['recall']-old['recall'],'titleBaselineRecallRegression':title['recall']-candidate['recall'],'allowedAbsoluteRecallRegression':gates['maxAbsoluteRecallRegression'],
        'pipelineDocumentCoverage':len(docs)/19,'minimumDocumentCoverage':gates['minimumDocumentCoverage'],'pipelineReferenceEVALUATED_ON':0,
        'automaticPromotionAllowed':False,'qualityPromotionPassed':False,'testEvaluated':False,
        'notice':'Data-only exploratory dev experiment. Tiny NER micro change does not establish improvement; pipeline P/F1 regress. Original gates, source/dev labels and production stay unchanged.'}
    assert decision['pipelinePrecisionChange']<0 and decision['pipelineF1Change']<0 and decision['titleBaselineRecallRegression']>gates['maxAbsoluteRecallRegression']
    for item in (decision['previousPipeline'],decision['candidatePipeline']):item['evaluationTarget']='exposed_dev_AI_reference_not_final_test'
    audited={'evaluationTarget':'exposed_dev_AI_reference_not_final_test','pipelineDocumentCoverage':len(docs)/19,
        'previous':{name:dev_metric(m) for name,m in pipeline['previous'].items()},'expandedNER_oldRE':dev_metric(saved),
        'rawResultUnmodified':True,'metadataCorrectionOnly':True,'testEvaluated':False}
    audit={'passed':True,'engineeringTests':365,'additionalRequested':24,'additionalSourceMatched':21,'additionalNERTrain':19,'trainDocuments':48,'devDocuments':16,
        'NERTrainSteps':144,'RETrained':False,'trainDocumentsEveryEpochVerified':True,'savedMetricsRecomputed':True,'devRowsUnchanged':True,
        'newWeightsSha256':c.file_sha256(RUN/result['bestCheckpoint']/'model.safetensors'),'runManifestSha256':c.file_sha256(RUN/'manifest.json'),
        'snapshotManifestSha256':c.file_sha256(SNAPSHOT/'manifest.json'),'previousModelsAndArtifactsUnchanged':True,
        'testContentConsumed':False,'modelPromoted':False,'qualityPromotionPassed':False,'databaseWritten':False,'serviceRestarted':False,'reportExpansionPaused':True,
        'scope':'Offline train-data expansion and saved-dev audit; no new live application acceptance or independent gold evaluation.'}
    return previous,result,pipeline,summary,steps,epochs,audit,decision,errors,audited

def main(action):
    previous,result,pipeline,summary,steps,epochs,audit,decision,errors,audited=checked()
    if action=='prepare':
        if EVIDENCE.exists():raise FileExistsError('Preserve evidence')
        EVIDENCE.mkdir(parents=True);sources=EVIDENCE/'sources';sources.mkdir()
        paths=[Path(__file__),ROOT/'README.md',ROOT/'docs/system_status_round37.md',ROOT/'docs/model_optimization_abstract_v1.md',ROOT/'tests/test_expanded_abstract_ner.py',
            ROOT/'resources/course_abstract_expansion_v1.json',ROOT/'scripts/collect_train_abstracts.py',ROOT/'scripts/train_expanded_abstract_ner.py',
            ROOT/'annotations/course_v4/abstract_expansion_decisions_20261008_37.json',ROOT/'annotations/course_v4/abstract_expansion_reviews_20261008_37.json',RUNS/'tests_20261008_round37_all.xml']
        paths += [p for folder in (RUN,SOURCE,REVIEWED,SNAPSHOT) for p in folder.iterdir() if p.is_file() and p.suffix in ('.json','.jsonl','.txt')]
        paths += [previous_round.RUN/'pipeline_development_result.json',ROOT/'kg_datasets/dblp/course_v4_runs/abstract_ner_development_20261008_35/development_result.json']
        for source in paths:
            target=sources/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        for name,value in (('audit_state',audit),('candidate_decision',decision),('pipeline_error_audit',errors),('audited_development_metrics',audited)):c.write_json(EVIDENCE/(name+'.json'),value)
        body='<h2>24次限速官方采集 → 21篇匹配 → 19篇NER新增输入</h2>'+table(['范围','本轮结果','保留边界'],[['采集','24/24请求完成，3篇题名不一致','不补足失败/隔离样本；网页按robots至少15.1秒单连接'],['AI标注','21篇初标+同会话自复核；19篇严格BIO通过','2篇多义/嵌套隔离；非独立gold；724个未决关系不填负例'],['训练集','29→48篇；METHOD362 / TASK185 / DATASET44','新增DATASET9来自4篇；教程/综述只作训练语言样本'],['来源规模','75→96篇摘要，DBLP书目仍20,000','原dev16/19、test19、旧图和权重不变']])
        body+='<h2>固定旧RE · 同5/19完整dev文档</h2>'+table(['NER','Precision','Recall','F1','TP / 预测 / 参考'],[[name,f"{m['positiveMicro']['precision']:.2%}",f"{m['positiveMicro']['recall']:.2%}",f"{m['positiveMicro']['f1']:.2%}",f"{m['positiveMicro']['truePositive']} / {m['positiveMicro']['predicted']} / {m['positiveMicro']['reference']}"] for name,m in [('旧题名NER',audited['previous']['old_NER_old_RE']),('35轮NER',audited['previous']['new_NER_old_RE']),('37轮扩充NER',audited['expandedNER_oldRE'])]])
        body+='<h2>拒绝新候选 · 不能把数据量增加当性能提升</h2><p>相对35轮NER：召回提高4.35百分点，但Precision与F1退化；相对旧题名NER召回仍下降4.35百分点，超过2点护栏。完整文档覆盖26.32%，EVALUATED_ON参考0；不晋级，不更换线上模型，也不读取保留测试。</p>'
        body+='<h2>实际错误归因与下一步</h2>'+table(['项目','35轮摘要NER','37轮扩充NER'],[['漏关系主因','缺失19 / 边界7 / 类型2',json.dumps(errors['FNPrimaryCauses'],ensure_ascii=False)],['FP / FN','56 / 28',f"{errors['falsePositive']} / {errors['falseNegative']}"],['新FP主因','与FN分别计算',json.dumps(errors['FPPrimaryCauses'],ensure_ascii=False)],['下一步','不盲调RE/重跑test','训练侧逐次出现的上下文与任务跨度边界；补完整dev证据']])
        body+='<p>当前365项工程回归通过，逐条重算指标、每轮48篇覆盖和FP/FN原因；不是365项语义认证。所有数据为已暴露AI开发标签，不与旧60.07%题名test直接比较。原评分JSON保留历史默认目标字符串，审计文件仅修正为dev口径，数字与原记录不改。</p>'
        (EVIDENCE/'09_annotation_expansion.html').write_text(page('训练摘要扩充与未晋级决定 · 第37轮',body,datetime.now(UTC).isoformat(),['candidate_decision.json','pipeline_error_audit.json','audited_development_metrics.json']),encoding='utf-8')
        body='<h2>同超参数真实训练 · 6轮 / 144步 / epoch6</h2><p>RTX4060 Laptop；编码器和分类头变化，重载一致；训练和固定RE对照36.75秒。没有dev反传、RE重训、测试访问或部署。</p>'+loss_curve(steps)
        body+=table(['epoch','累计步数','NER严格dev F1','选择'],[[e['epoch'],e['steps'],f"{e['dev']['metrics']['micro']['f1']:.2%}",'最佳（未晋级）' if e['epoch']==6 else '未选择'] for e in epochs])
        body+='<h2>同184个AI参考实体 · 总分基本不变，类别有取舍</h2>'+table(['NER','Precision','Recall','micro F1','METHOD F1','TASK F1','DATASET F1'],[[name,*[f"{m['micro'][key]:.2%}" for key in ('precision','recall','f1')],*[f"{m['perClass'][label]['f1']:.2%}" for label in ('METHOD','TASK','DATASET')]] for name,m in [('旧题名迁移',result['baselineDev']['metrics']),('35轮摘要NER',result['previousAbstractNERDev']['metrics']),('37轮扩充NER',result['bestDev']['metrics'])]])
        body+='<p>总F1仅变化约0.04百分点，不能宣称显著改善。DATASET精确率54.17%→81.82%，召回86.67%→60.00%；TASK F1下降；非法BIO转移55→41。单看总F1或单个高分不能证明关系可靠性。</p><h2>数据与结论边界</h2><p>训练数据扩充在已有train论文组内，原dev标签、父合同、初始化、seed、6轮、batch2、lr2e-5和解码规则不改。已暴露dev不是独立gold。此次没有支持仅增数据量足以解决问题，下一步先处理训练侧任务边界/角色多义和参考覆盖，不继续盲目扩图。</p>'
        (EVIDENCE/'05_development.html').write_text(page('真实NER数据量单因素开发 · 第37轮',body,datetime.now(UTC).isoformat(),['sources/kg_datasets/dblp/course_v4_runs/abstract_ner_expansion_development_20261008_37/steps.jsonl','sources/kg_datasets/dblp/course_v4_runs/abstract_ner_expansion_development_20261008_37/epochs.json']),encoding='utf-8')
        c.write_json(EVIDENCE/'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','filesSha256':{p.relative_to(EVIDENCE).as_posix():c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
        print(json.dumps({'prepared':True,'engineeringTests':365,'candidateRejected':True}))
    else:
        target=RUNS/'verification_20261008_round37.json'
        if target.exists():raise FileExistsError('Preserve verification seal')
        g.verified_files(EVIDENCE)
        for name,expected in (('audit_state',audit),('candidate_decision',decision),('pipeline_error_audit',errors),('audited_development_metrics',audited)):assert read(EVIDENCE/(name+'.json'))==expected
        captures=json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'));assert captures['status']=='completed' and len(captures['captures'])==2 and not captures['originalConsoleScreenshot']
        for image in captures['captures']:assert c.file_sha256(EVIDENCE/image['image'])==image['sha256'] and c.file_sha256(EVIDENCE/image['sourcePage'])==image['sourcePageSha256']
        c.write_json(target,{'passed':True,'checkedAtUTC':datetime.now(UTC).isoformat(),'engineeringTests':365,'audit':audit,'candidateDecision':decision,
            'immutableSourceSha256':previous['immutableSourceSha256'],'previousVerificationSha256':c.file_sha256(RUNS/'verification_20261008_round36.json'),
            'evidenceManifestSha256':c.file_sha256(EVIDENCE/'manifest.json'),'capturesSha256':c.file_sha256(EVIDENCE/'captures.json'),'qualityPromotionPassed':False,'reportExpansionPaused':True})
        print(json.dumps({'passed':True,'engineeringTests':365,'candidateRejected':True,'modelPromoted':False}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','seal'));main(parser.parse_args().action)

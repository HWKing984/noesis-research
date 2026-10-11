"""Recount saved RE/pipeline development results and preserve a rejected candidate with real browser evidence."""
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
import train_course_relation as re_model
from course_abstract_v1 import read
from course_abstract_relation import CONTRACT,load_inputs
from evaluate_course_relation import score_pipeline
from train_abstract_relation import diagnose
from export_course_evidence import page,table,loss_curve
import seal_abstract_model_20261008_round35 as previous_round

RUNS=ROOT/'kg_datasets/dblp/course_v4_runs'
RUN=RUNS/'abstract_relation_development_20261008_36'
SNAPSHOT=ROOT/'kg_datasets/dblp/course_abstract_relation_inputs_20261008_36'
EVIDENCE=ROOT/'docs/evidence/20261008_round36'

def pipeline_errors(docs,refs,predictions):
    positives={re_model.pair_key(r)+(r['label'],) for r in refs if r['label']!='NO_RELATION'};lookup={d['sampleId']:d for d in docs};errors=[]
    for row in predictions:
        if row['label']=='NO_RELATION' or re_model.pair_key(row)+(row['label'],) in positives:continue
        entities=lookup[row['sampleId']]['entities'];key=lambda e:(e['start'],e['end'],e['label'])
        wrong=[role for role in ('head','tail') if key(row[role]) not in {key(e) for e in entities}]
        if not wrong and not any(re_model.pair_key(r)==re_model.pair_key(row) for r in refs):raise ValueError('A complete document lacks a legal reference pair')
        errors.append({'prediction':row,'primaryCause':'NER_endpoint_mismatch' if wrong else 'RE_decision','wrongEndpoints':wrong})
    return errors

def checked():
    previous_round.checked();previous=read(RUNS/'verification_20261008_round35.json')
    assert previous['passed'];g.verified_files(ROOT/'docs/evidence/20261008_round35',previous['evidenceManifestSha256'])
    assert c.file_sha256(ROOT/'docs/evidence/20261008_round35/captures.json')==previous['capturesSha256']
    suite=ElementTree.parse(RUNS/'tests_20261008_round36_all.xml').getroot().find('testsuite')
    assert suite.get('tests')=='364' and all(suite.get(k)=='0' for k in ('errors','failures','skipped'))
    config,data=load_inputs(SNAPSHOT);manifest=g.verified_files(RUN)
    assert all(c.file_sha256(ROOT/p)==sha for p,sha in manifest['inputSha256'].items())
    result=read(RUN/'development_result.json');pipeline=read(RUN/'pipeline_development_result.json');state=read(RUN/'status.json');summary=read(SNAPSHOT/'summary.json')
    assert result['passed'] and state['status']=='completed' and result['classifierAndEncoderChanged'] and result['reloadPredictionsIdentical'] and not result['devUsedForGradient']
    assert state['trainingStarted'] and result['steps']==state['steps']==294 and result['epochs']==6 and result['bestCheckpoint']=='checkpoint_epoch_01'
    assert all(result[k] is False for k in ('testEvaluated','testTokenized','modelPromoted','qualityPromotionPassed'))
    assert state['settings']==config['RETraining'] and c.file_sha256(RUN/result['bestCheckpoint']/'model.safetensors')!=config['RETraining']['initialWeightsSha256']
    steps=c.read_jsonl(RUN/'steps.jsonl');epochs=read(RUN/'epochs.json');train_ids={re_model.pair_id(p) for p in data['train']['relation']}
    assert [s['step'] for s in steps]==list(range(1,295)) and len(epochs)==6
    for epoch in range(1,7):
        ids=[p for step in steps if step['epoch']==epoch for p in step['pairIds']];assert len(ids)==195 and set(ids)==train_ids
    assert all(math.isfinite(s['loss']) and math.isfinite(s['gradientNorm']) for s in steps)
    scores=[re_model.selection_score(e['dev']['metrics'],'all_class_macro') for e in epochs];assert scores.index(max(scores))==0 and result['bestDev']==epochs[0]['dev']
    for name,field in (('old','baselineDev'),('new','bestDev')):
        predicted=c.read_jsonl(RUN/(name+'_module_dev_predictions.jsonl'));assert [re_model.pair_key(p) for p in predicted]==[re_model.pair_key(p) for p in data['dev']['relation']]
        metrics=re_model.score_relations(data['dev']['relation'],[p['label'] for p in predicted]);assert metrics==result[field]['metrics']==pipeline['moduleMetrics'][name]
    docs=c.read_jsonl(RUN/'pipeline_dev_documents.jsonl');refs=c.read_jsonl(RUN/'pipeline_dev_reference_pairs.jsonl')
    assert docs==data['dev']['full_relation'] and refs==[p for p in data['dev']['relation'] if p['sampleId'] in {d['sampleId'] for d in docs}]
    audit_errors={}
    for name,metrics in pipeline['pipelineMetrics'].items():
        predicted=c.read_jsonl(RUN/(name+'_predictions.jsonl'));scored=score_pipeline(docs,refs,predicted)
        assert all(scored[k]==metrics[k] for k in ('positiveMicro','perClass','positiveMacroF1','supportedPositiveClasses','negativeDecisions'))
        ner_name=name.split('_NER_')[0];entities={p['sampleId']:p['predictedEntities'] for p in c.read_jsonl(RUN/(ner_name+'_ner_dev_predictions.jsonl'))}
        missed=[e for d in docs for e in diagnose(d,entities[d['sampleId']],[r for r in refs if r['sampleId']==d['sampleId']],[p for p in predicted if p['sampleId']==d['sampleId']])]
        assert missed==c.read_jsonl(RUN/(name+'_missed_relations.jsonl'))
        false=pipeline_errors(docs,refs,predicted);m=metrics['positiveMicro']
        assert len(false)==m['predicted']-m['truePositive'] and len(missed)==m['reference']-m['truePositive']
        audit_errors[name]={'falsePositive':len(false),'falseNegative':len(missed),'FPPrimaryCauses':dict(Counter(e['primaryCause'] for e in false)),
            'FNPrimaryCauses':dict(Counter(e['primaryCause'] for e in missed)),'falsePositiveExamples':false,'missedReferenceExamples':missed}
    old_macro=re_model.selection_score(result['baselineDev']['metrics'],'all_class_macro');new_macro=re_model.selection_score(result['bestDev']['metrics'],'all_class_macro')
    a=pipeline['pipelineMetrics']['old_NER_old_RE']['positiveMicro'];b=pipeline['pipelineMetrics']['new_NER_old_RE']['positiveMicro']
    decision={'candidateRE':'rejected_dev_regression','oldConditionalModuleAllClassMacroF1':old_macro,'candidateConditionalModuleAllClassMacroF1':new_macro,
        'candidateNERPipeline':'not_promoted_recall_and_coverage_gates_failed','pipelineBaselineRecall':a['recall'],'candidateNERWithOldRERecall':b['recall'],
        'recallRegression':a['recall']-b['recall'],'allowedAbsoluteRecallRegression':read(ROOT/'resources/course_abstract_v1.json')['promotionGates']['maxAbsoluteRecallRegression'],
        'pipelineDocumentCoverage':len(docs)/19,'minimumDocumentCoverage':0.8,'pipelineReferenceEVALUATED_ON':sum(p['label']=='EVALUATED_ON' for p in refs),
        'automaticPromotionAllowed':False,'qualityPromotionPassed':False,'testEvaluated':False,
        'notice':'Rejecting a candidate is a real development result, not training failure. The new module cannot replace the better old checkpoint. Conditional module scores and five-document pipeline scores are not overall knowledge correctness.'}
    assert new_macro<old_macro and decision['recallRegression']>decision['allowedAbsoluteRecallRegression'] and len(docs)==5 and len(refs)==58
    audit={'passed':True,'engineeringTests':364,'modelRetrained':True,'NERRetrained':False,'RETrainSteps':294,'RETrainPairs':195,'moduleDevPairs':242,
        'pipelineDevDocuments':5,'pipelineQueueDocuments':19,'savedMetricsRecomputed':True,'trainPairCoverageEveryEpochVerified':True,
        'previousModelsAndArtifactsUnchanged':True,'testEvaluated':False,'testContentConsumed':False,'modelPromoted':False,'qualityPromotionPassed':False,
        'databaseWritten':False,'serviceRestarted':False,'REBestWeightsSha256':c.file_sha256(RUN/result['bestCheckpoint']/'model.safetensors'),
        'runManifestSha256':c.file_sha256(RUN/'manifest.json'),'snapshotManifestSha256':c.file_sha256(SNAPSHOT/'manifest.json'),
        'scope':'Offline saved-candidate/data/error audit only; no new live browser or graph integration acceptance.'}
    return previous,result,pipeline,summary,steps,epochs,audit,decision,audit_errors

def main(action):
    previous,result,pipeline,summary,steps,epochs,audit,decision,errors=checked()
    if action=='prepare':
        if EVIDENCE.exists():raise FileExistsError('Preserve evidence')
        sources=EVIDENCE/'sources';sources.mkdir(parents=True)
        try:
            paths=[Path(__file__),CONTRACT,ROOT/'README.md',ROOT/'docs/system_status_round36.md',ROOT/'docs/model_optimization_abstract_v1.md',ROOT/'tests/test_abstract_relation.py',
                ROOT/'scripts/course_abstract_relation.py',ROOT/'scripts/train_abstract_relation.py',ROOT/'annotations/course_v4/abstract_relation_decisions_20261008_36.json',
                ROOT/'annotations/course_v4/abstract_relation_reviews_20261008_36.json',RUNS/'tests_20261008_round36_all.xml']
            paths += [SNAPSHOT/name for name in ('summary.json','manifest.json','train_origins.jsonl','dev_origins.jsonl','train_reviewed_receipts.jsonl','dev_reviewed_receipts.jsonl')]
            paths += [p for p in RUN.iterdir() if p.is_file()]
            for path in paths:
                target=sources/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
            c.write_json(EVIDENCE/'audit_state.json',audit);c.write_json(EVIDENCE/'candidate_decision.json',decision);c.write_json(EVIDENCE/'pipeline_error_audit.json',errors)
            quad=[[name,f"{m['positiveMicro']['precision']:.2%}",f"{m['positiveMicro']['recall']:.2%}",f"{m['positiveMicro']['f1']:.2%}",f"{m['positiveMicro']['truePositive']} / {m['positiveMicro']['predicted']} / {m['positiveMicro']['reference']}"] for name,m in pipeline['pipelineMetrics'].items()]
            body='<h2>完整文档dev四种对照 · 同一5篇，非final-test</h2>'+table(['NER / RE','Precision','Recall','F1','TP / 预测 / 参考'],quad)
            body+='<p>原19篇锁定队列中只有5篇完整，覆盖26.32%；含1篇零参考实体对，必须保留。46条参考正关系全部为USED_FOR，EVALUATED_ON参考为0：本表不验证数据集关系。不同于旧题名测试，不可和60.07%排行。</p>'
            body+='<h2>明确拒绝升级</h2>'+table(['开发判据','实际结果'],[['RE候选','三类宏F1：旧88.16% → 新85.48%，负类F1：68.09% → 60.47%；不替换旧RE'],['NER候选组合','配旧RE时F1提高，但Recall47.83% → 39.13%，下降8.70百分点，超声明2百分点护栏'],['完整队列覆盖','5/19=26.32%，不足80%；没有EVALUATED_ON参考支持'],['旧版隔离','题名权重/旧测试/35轮NER/31轮图/历史证据SHA不变，保留19篇摘要test未消费'],['真实训练','RE6轮/294步，train195对，dev242个明确对；最早最佳epoch1；编码器+分类头变化、重载一致'],['工程验收','364项通过，另按已保存预测重算指标和错误；不是语义gold'],['当前部署','无数据库写入、服务重启、模型晋级；报告继续暂停']])
            body+='<h2>错误传播 · FN主因互斥，FP与FN不混加</h2>'+table(['对照','FP','FP端点错误 / 正确端点错关系','FN','FN主因'],
                [[name,e['falsePositive'],f"{e['FPPrimaryCauses'].get('NER_endpoint_mismatch',0)} / {e['FPPrimaryCauses'].get('RE_decision',0)}",e['falseNegative'],json.dumps(e['FNPrimaryCauses'],ensure_ascii=False)] for name,e in errors.items()])
            body+='<h2>新标注数据与仍未解决的问题</h2>'+table(['范围','明确标签','未决','说明'],[['train','195 = USED_FOR145 / EVALUATED_ON43 / NO_RELATION7',913,'明确对195/1,108=17.60%；负例仅3篇来源，不能证明稳定泛化'],['dev','242 = USED_FOR202 / EVALUATED_ON10 / NO_RELATION30',190,'明确对242/432=56.02%；条件性模块成绩，不能混同全体实体对'],['稀有dev正例','EVALUATED_ON10','不按类型填未知','10个提及对仅来自3篇/4个数据集名字，含同义称呼和重复提及'],['语义来源','AI判断+同会话自复核','非独立gold','源NER未修改；负例来自明确角色/数据使用对比，不由缺少评测语句推得']])
            body+='<p>下一步集中增加训练侧整篇摘要和任务跨度/角色多样性；补负例与新的完整dev关系证据。当前少量同会话AI标签、低覆盖与模型漏实体依然限制可靠性，不使用封存测试调分。</p>'
            (EVIDENCE/'09_annotation_expansion.html').write_text(page('摘要关系开发、误差传播与候选拒绝 · 第36轮',body,datetime.now(UTC).isoformat(),['candidate_decision.json','pipeline_error_audit.json','sources/kg_datasets/dblp/course_v4_runs/abstract_relation_development_20261008_36/pipeline_development_result.json']),encoding='utf-8')
            body='<h2>条件性关系模块 · 仅242个明确dev实体对</h2>'+table(['模型','正关系Precision','正关系Recall','正关系F1','三类宏F1','NO_RELATION F1'],
                [[name,f"{m['positiveMicro']['precision']:.2%}",f"{m['positiveMicro']['recall']:.2%}",f"{m['positiveMicro']['f1']:.2%}",f"{re_model.selection_score(m,'all_class_macro'):.2%}",f"{m['perClass']['NO_RELATION']['f1']:.2%}"] for name,m in [('旧RE迁移',result['baselineDev']['metrics']),('train类型多数',result['typeMajorityDev']),('新RE epoch1',result['bestDev']['metrics'])]])
            body+='<p>43/145/7的train类别数使用既有平衡损失：NO_RELATION权重9.2857。六轮之后仍未胜过旧模型；不继续根据同一dev追分，不冒称负例问题已解决。未决标签不进入损失，证据和理由不作为模型特征。</p>'
            body+='<h2>实际逐步loss与开发选择</h2>'+loss_curve(steps)+table(['epoch','累计步数','dev三类宏F1','选择'],[[e['epoch'],e['steps'],f"{re_model.selection_score(e['dev']['metrics'],'all_class_macro'):.2%}",'候选最佳（未晋级）' if e['epoch']==1 else '未选择'] for e in epochs])
            body+='<h2>数据来源与受控边界</h2><p>新独立partial_v1合同未覆盖35轮abstract_v1合同/输入/成绩。论文组、原整篇文本、NER实体和512token上限不变，max marked train333/dev306，无截断；15篇train和13篇dev有明确关系修订与实际同会话自复核，其余收据原样继承。负例包括被压缩模型与压缩算法的角色差异、隐式/显式模块的输出差异、UCF101评测与ImageNet初始化的差异；都只是AI原文范围判断，不保证独立语义正确。</p>'
            (EVIDENCE/'07_relation_development.html').write_text(page('真实摘要RE训练与未晋级原因 · 第36轮',body,datetime.now(UTC).isoformat(),['sources/kg_datasets/dblp/course_v4_runs/abstract_relation_development_20261008_36/steps.jsonl','sources/kg_datasets/dblp/course_v4_runs/abstract_relation_development_20261008_36/epochs.json']),encoding='utf-8')
            c.write_json(EVIDENCE/'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','filesSha256':{p.relative_to(EVIDENCE).as_posix():c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
            print(json.dumps({'prepared':True,'engineeringTests':364,'RECandidateDecision':decision['candidateRE']}))
        except Exception as error:
            c.write_json(EVIDENCE/'failure.json',{'status':'failed_no_synthetic_fallback','errorType':type(error).__name__,'error':str(error)});raise
    else:
        output=RUNS/'verification_20261008_round36.json'
        if output.exists():raise FileExistsError('Preserve seal')
        g.verified_files(EVIDENCE);assert read(EVIDENCE/'audit_state.json')==audit and read(EVIDENCE/'candidate_decision.json')==decision and read(EVIDENCE/'pipeline_error_audit.json')==errors
        captures=json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'));assert captures['status']=='completed' and len(captures['captures'])==2 and captures['originalConsoleScreenshot'] is False
        for image in captures['captures']:assert c.file_sha256(EVIDENCE/image['image'])==image['sha256'] and c.file_sha256(EVIDENCE/image['sourcePage'])==image['sourcePageSha256']
        c.write_json(output,{'passed':True,'checkedAtUTC':datetime.now(UTC).isoformat(),'engineeringTests':364,'audit':audit,'candidateDecision':decision,'immutableSourceSha256':previous['immutableSourceSha256'],
            'previousVerificationSha256':c.file_sha256(RUNS/'verification_20261008_round35.json'),'evidenceManifestSha256':c.file_sha256(EVIDENCE/'manifest.json'),
            'capturesSha256':c.file_sha256(EVIDENCE/'captures.json'),'qualityPromotionPassed':False,'reportExpansionPaused':True})
        print(json.dumps({'passed':True,'engineeringTests':364,'RECandidateRejected':True,'modelPromoted':False}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','seal'));main(parser.parse_args().action)

"""Recompute the two frozen decoder experiments and seal actual browser evidence."""
import argparse
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import UTC,datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import evaluate_abstract_abstention as evaluation
from course_abstract_v1 import read
from export_course_evidence import page,table

c,g,prior=evaluation.c,evaluation.g,evaluation.prior
RUNS=ROOT/'kg_datasets/dblp/course_v4_runs'; FINAL=RUNS/'abstract_abstention_development_20261008_48'
EVIDENCE=ROOT/'docs/evidence/20261008_round48'
REGRESSION=RUNS/'tests_20261008_round48_workspace_temp.xml'


def checked():
    config,source,parent,data=evaluation.load_inputs();manifest=g.verified_files(FINAL)
    if any(c.file_sha256(ROOT/p)!=sha for p,sha in manifest['inputSha256'].items()):raise ValueError('Abstention source changed')
    before=read(source/'development_result.json');after=read(FINAL/'development_result.json');rows=data['dev']['ner'];full=data['dev']['full_relation'];ids={d['sampleId'] for d in full};refs=[p for p in data['dev']['relation'] if p['sampleId'] in ids]
    if not all(read(p/'status.json')['status']=='completed' for p in (source,FINAL)) or not after['exactCacheReplay'] or after['trainingExecuted'] or after['testEvaluated'] or after['modelPromoted'] or after['gates']['developmentGatesPassed']:raise ValueError('Completion/abstention state drift')
    logits=c.read_jsonl(source/'dev_logits.jsonl');actual=[];raw_invalid=0
    for d,v in zip(rows,logits):
        modes=evaluation.decoder.decode_modes(v['logits'],v['offsets'],d['text'])
        decoded=evaluation.decode_with_abstention(modes['argmax']['tags'],v['offsets'],d['text']);actual.append(decoded['entities']);raw_invalid+=decoded['rawInvalidTransitions']
    saved=c.read_jsonl(FINAL/'ner_predictions.jsonl')
    if [p['sampleId'] for p in saved]!=[d['sampleId'] for d in rows] or [p['predictedEntities'] for p in saved]!=actual or raw_invalid!=65:raise ValueError('Replay subset/sequence drift')
    if evaluation.ner.score_rows(rows,actual,evaluation_target=prior.TARGET)!=after['metrics']:raise ValueError('NER replay metric drift')
    for mode in ('argmax','constrained'):
        scored=c.read_jsonl(source/(mode+'_pipeline_predictions.jsonl'));recomputed=prior.dev_scope(prior.score_pipeline(full,refs,scored),'complete_document_exposed_dev_AI_reference_not_final_test')
        if recomputed['positiveMicro']!=before['pipelineMetrics'][mode]['positiveMicro']:raise ValueError('Earlier comparison metric drift')
    scored=c.read_jsonl(FINAL/'pipeline_predictions.jsonl');cache={p['pairId']:p for p in c.read_jsonl(source/'argmax_pipeline_predictions.jsonl')};removed=c.read_jsonl(FINAL/'abstained_pairs.jsonl')
    if any(p!=cache[p['pairId']] for p in scored) or {p['pairId'] for p in scored}&{p['pairId'] for p in removed} or {p['pairId'] for p in scored}|{p['pairId'] for p in removed}!=set(cache):raise ValueError('Kept/abstained cache partition drift')
    recomputed=prior.dev_scope(prior.score_pipeline(full,refs,scored),'complete_document_exposed_dev_AI_reference_not_final_test')
    causes,false=evaluation.decoder.error_summary(full,refs,scored)
    if recomputed['positiveMicro']!=after['pipelineMetrics']['positiveMicro'] or causes!=after['pipelineMetrics']['endpointMismatch'] or false!=c.read_jsonl(FINAL/'false_relations.jsonl'):raise ValueError('Final pipeline/false-positive drift')
    ledger=c.read_jsonl(FINAL/'abstention_ledger.jsonl')
    if sum(len(v['abstainedEntities']) for v in ledger)!=after['abstainedEntities'] or len(removed)!=after['abstainedPairs'] or (after['trainReferencePreserved'],after['trainEntityPreserved'])!=(58,678):raise ValueError('Abstention/train reference count drift')
    junit=ET.parse(REGRESSION).getroot().find('testsuite').attrib;oldjunit=ET.parse(RUNS/'tests_20261008_round47_workspace_temp.xml').getroot().find('testsuite').attrib
    for attributes,expected in ((junit,'376'),(oldjunit,'375')):
        if (attributes['tests'],attributes['errors'],attributes['failures'],attributes['skipped'])!=(expected,'0','0','0'):raise ValueError('Regression failed/partial')
    audit={'run47ManifestSha256':c.file_sha256(source/'manifest.json'),'run48ManifestSha256':c.file_sha256(FINAL/'manifest.json'),'regression47Sha256':c.file_sha256(RUNS/'tests_20261008_round47_workspace_temp.xml'),'regression48Sha256':c.file_sha256(REGRESSION),'engineeringTests':376,'regressionSeconds':float(junit['time']),
        'illegalBefore':65,'illegalLegalDecoder':before['invalidTransitions']['constrained'],'rawIllegalAfterAbstention':raw_invalid,'abstainedEntities':after['abstainedEntities'],'abstainedPairs':after['abstainedPairs'],'trainSpansPreserved':678,'pipelineBefore':after['baseline46'],'pipelineLegal':before['pipelineMetrics']['constrained']['positiveMicro'],'pipelineAbstention':after['pipelineMetrics']['positiveMicro'],'gates':after['gates']['checks'],'testEvaluated':False,'labelsChanged':False,'modelPromoted':False}
    return audit,before,after,ledger


def main(action):
    audit,before,after,ledger=checked()
    if action=='prepare':
        if EVIDENCE.exists():raise FileExistsError('Preserve evidence')
        paths=[Path(__file__),evaluation.CONTRACT,evaluation.decoder.CONTRACT,ROOT/'scripts/course_bio_abstention.py',ROOT/'scripts/evaluate_abstract_abstention.py',ROOT/'scripts/evaluate_abstract_decoder.py',ROOT/'scripts/export_course_evidence.py',ROOT/'scripts/capture_course_evidence.ps1',ROOT/'tests/test_abstract_abstention.py',ROOT/'tests/test_abstract_decoder.py',REGRESSION,RUNS/'tests_20261008_round47_workspace_temp.xml',RUNS/'verification_20261008_round46.json']
        for folder in (RUNS/'abstract_decoder_development_20261008_47',FINAL):paths.extend(folder/name for name in ('manifest.json','status.json','selection_lock.json','development_result.json'))
        paths.extend(FINAL/name for name in ('abstention_ledger.jsonl','abstained_pairs.jsonl','false_relations.jsonl'))
        EVIDENCE.mkdir(parents=True)
        for p in paths:
            target=EVIDENCE/'sources'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
        c.write_json(EVIDENCE/'audit_state.json',audit);stamp=datetime.now(UTC).isoformat(); old=before['metrics']['argmax'];legal=before['metrics']['constrained'];new=after['metrics']
        body='<p>冻结46版SciBERT实体与关系权重，仅比较解码行为。47版legal BIO用同一原始分数推理；48版保守弃用回放封存分数与完全相同输入的RE缓存，没有新训练或新标签。</p>'
        body+=table(['方案','NER P/R/F1','完整关系 P/R/F1','错报正边'],[[name,f"{n['micro']['precision']:.2%} / {n['micro']['recall']:.2%} / {n['micro']['f1']:.2%}",f"{p['precision']:.2%} / {p['recall']:.2%} / {p['f1']:.2%}",p['predicted']-p['truePositive']] for name,n,p in [('原46严格解码',old,audit['pipelineBefore']),('47合法路径',legal,audit['pipelineLegal']),('48保守弃用',new,audit['pipelineAbstention'])]])
        body+='<h2>收益和边界</h2><p>保守弃用删去6个结构不确定的实体：NER命中仍130，预测183→177，F1 70.84%→72.02%。完整关系命中仍50，预测169→167，错报119→117，F1仅39.53%→39.84%。DATASET召回仍66.67%；与旧42完整F1 54.35%相比仍未达晋级条件。</p>'
        body+='<p>legal路径虽将非法BIO从65变为0，却新增错报，完整F1降至36.10%；该方案被拒绝。48版仍记录原65非法转移，不能宣称序列模型已修好。完整EVAL参考0、文档覆盖7/19、已暴露AI开发数据，最终测试未执行。</p>'
        body+='<h2>核验</h2>'+table(['检查','实际'],[
            ['训练标注','58篇/678跨度原样保留，无参考跨度被结构规则弃用'],
            ['缓存复用','每个保留候选的文献/原文SHA/方向/端点完全相同；删除候选另存，不填NO_RELATION'],
            ['回归',f'47轮375通过；48轮376通过，JUnit {audit["regressionSeconds"]:.2f}秒，D隔离tmp'],
            ['原始预测','65→0的合法解码与6实体/2候选的弃用均可由封存logits重算']])
        (EVIDENCE/'02_training.html').write_text(page('冻结模型解码对照与结构弃用 · 第47–48轮',body,stamp,['sources/kg_datasets/dblp/course_v4_runs/abstract_decoder_development_20261008_47/development_result.json','sources/kg_datasets/dblp/course_v4_runs/abstract_abstention_development_20261008_48/development_result.json']),encoding='utf-8')
        body='<p>结构规则仅暂缓可疑预测，不扩张实体、不补B标签、不改原文、不使用开发参考标签决定保留与否。所有动作有原文跨度、原因与模型来源。</p>'
        body+=table(['弃用原文预测','预测类型','原因'],[[e['text'],e['label'],'；'.join(e['abstentionReasons'])] for v in ledger for e in v['abstainedEntities']])
        body+='<h2>完整关系错报仍然集中在TASK端点</h2>'+table(['几何不匹配','原46','48弃用后'],[['仅TASK/DATASET尾端点',83,after['pipelineMetrics']['endpointMismatch']['tail']],['仅METHOD头端点',11,after['pipelineMetrics']['endpointMismatch']['head']],['两个端点',14,after['pipelineMetrics']['endpointMismatch']['head+tail']],['端点正确/关系不符',11,after['pipelineMetrics']['endpointMismatch']['relation_only']]])
        body+='<p>数字按AI参考的精确跨度/类型统计，不自动断言原文语义真伪。83条尾端点错报未改善，证明结构弃用只覆盖一部分问题；需要训练侧更丰富的任务对象、范围和角色证据，以及独立来源的完整关系AI参考覆盖。</p>'
        body+='<h2>后续决策</h2><p>新增保守弃用实现保存在候选流程，现用模型/图未替换；两轮均无写库、服务重启或新训练。完整报告继续暂停。下一步只对训练来源做固定范围的TASK对象/角色检查，不用已见开发错误表直接改参考标签追分。</p>'
        (EVIDENCE/'04_traceability.html').write_text(page('逐跨度弃用记录与剩余语义问题 · 第48轮',body,stamp,['sources/kg_datasets/dblp/course_v4_runs/abstract_abstention_development_20261008_48/abstention_ledger.jsonl','sources/kg_datasets/dblp/course_v4_runs/abstract_abstention_development_20261008_48/abstained_pairs.jsonl']),encoding='utf-8')
        c.write_json(EVIDENCE/'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','filesSha256':{p.relative_to(EVIDENCE).as_posix():c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}});print({'prepared':True,'engineeringTests':376})
    else:
        target=RUNS/'verification_20261008_round48.json'
        if target.exists():raise FileExistsError('Preserve verification')
        g.verified_files(EVIDENCE)
        if read(EVIDENCE/'audit_state.json')!=audit:raise ValueError('Evidence audit changed')
        captures=json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'))
        if captures['status']!='completed' or {(p['sourcePage'],p['image']) for p in captures['captures']}!={('02_training.html','02_training.png'),('04_traceability.html','04_traceability.png')}:raise ValueError('Capture incomplete')
        for item in captures['captures']:
            if c.file_sha256(EVIDENCE/item['image'])!=item['sha256'] or c.file_sha256(EVIDENCE/item['sourcePage'])!=item['sourcePageSha256']:raise ValueError('Screenshot drift')
        c.write_json(target,{'passed':True,'checkedAtUTC':datetime.now(UTC).isoformat(),'audit':audit,'previousVerificationSha256':c.file_sha256(RUNS/'verification_20261008_round46.json'),'evidenceManifestSha256':c.file_sha256(EVIDENCE/'manifest.json'),'capturesSha256':c.file_sha256(EVIDENCE/'captures.json'),'qualityPromotionPassed':False,'modelPromoted':False});print({'passed':True,'engineeringTests':376,'pipelineF1':audit['pipelineAbstention']['f1']})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','seal'));main(parser.parse_args().action)

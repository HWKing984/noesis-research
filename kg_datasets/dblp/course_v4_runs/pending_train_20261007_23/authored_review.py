"""Explicit candidate-aware same-session AI self-review, not independent gold."""
import copy
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / 'scripts'))
import course_weak as c
from compile_course_ai import compile_artifact
from expand_course_ai_review import expand_artifact
from import_course_ai import import_results, assemble

JUDGMENTS = """0|confirmed|Hardware-limit understanding overlaps sparse-network target; roofline is analysis framing.
1|confirmed|User-experience analysis is generic; software/visualization do not identify a concrete target.
2|confirmed|CarExpert approach and LLMs explicitly address in-car conversational QA.
3|confirmed|Neural network solves conditional transport; Bayesian application need not be transport executor.
4|confirmed|Jailbreak prompts target LLMs; fooling full target overlaps model, not an instruction.
5|confirmed|GLiNER and bidirectional Transformer explicitly implement named entity recognition.
6|confirmed|Classification association clear; full correlation-exploration target overlaps language models.
7|confirmed|Hallucination correction overlaps LLM target; verification component does not resolve full inventory.
8|revised|LLM may generate supervision rather than directly summarize dialogs; executor role is uncertain.
9|revised|Diffusion-based synthesis mixes a recognizable method with task boundary; retain negative association but isolate incomplete inventory.
10|confirmed|Improving transfer-learning adaptability overlaps method target; no downstream task named.
11|confirmed|Quantum/classical networks are benchmarked objects, not benchmark datasets.
12|confirmed|PySCIPOpt-ML is software; model-embedding task overlaps embedded ML target.
13|confirmed|Metric depth is output quantity; title lacks literal estimation operation, so no synthetic task.
14|confirmed|Transformer/RNN equivalence is a model claim, not task relation.
15|confirmed|Legal themes are non-computational context; no legal guidance inferred.
16|confirmed|NLP education survey states no particular extraction/generation task.
17|confirmed|Reset distribution versus pre-training technique ambiguous; exploration lacks target, preserve quarantine.
18|confirmed|RLHF improvement overlaps RLHF family; reward ensemble is method component.
19|confirmed|Bayesian DL estimates useful life; optimizer may only train estimator.
20|confirmed|Medical transcription ASR is explicit target with LLM instrument; no clinical efficacy asserted.
21|confirmed|GNN explicitly classifies nodes; disambiguated is qualifier.
22|confirmed|ML ensemble explicitly detects cyberbullying.
23|confirmed|CARLA-v2 candidate may be simulator, not dataset release; all dataset pairs unresolved and entire record isolated.
24|confirmed|Tokenization and Transformer are methods; sensor-failure robustness is property, not task.
25|confirmed|TPLLM and LLM family explicitly predict traffic.
26|confirmed|Explanation operation intertwines LLM qualifier; KG resource not dataset.
27|confirmed|LLM essay-proficiency scoring is investigated use; question does not prove accuracy.
28|confirmed|TextCNN implementation overlaps model; collaboration does not specify recommendation operation.
29|confirmed|Video-conferencing environment is software goal; no named generation operation.
30|confirmed|RakutenAI-7B is named model; extending LLM overlaps target and Japanese supplies no invented translation task.
31|confirmed|Quantum architecture optimization overlaps model target; no optimizer name.
32|confirmed|Educational assessment practice is human workflow context, not stated automated task.
33|confirmed|Radial networks and layer routing qualify LLM architecture; no operational target.
34|confirmed|Localization and spatial reasoning are explicit visual-LLM targets; improvement unverified here.
35|revised|Cross-lingual and character-level jointly qualify one neural CRF architecture, rather than two omitted-head members.
36|confirmed|Claude/NMT translate; generic From LLM framing does not resolve every executor role.
37|confirmed|Cache-aware RL is technique; recommender system alone does not identify recommendation target.
38|revised|Curriculum tuning may train reasoner rather than execute reasoning; withdraw certain executor relation.
39|confirmed|GPT4 tests BERT, not vice versa; full model-analysis task overlaps targets.
40|confirmed|Multimodal DL explicitly recognizes images.
41|confirmed|KG-EmpiRE is knowledge resource; sustainable literature review is research framing, no named benchmark release.
42|confirmed|Dual-segment clustering and FL are techniques; heterogeneous is setting.
43|confirmed|Private ML explicitly powers combinatorial auction design.
44|confirmed|ML/LLM explicitly predict Shanghai lane-house rents; location not dataset.
45|confirmed|Matryoshka query Transformer is method architecture, no separate task.
46|confirmed|LLM explicitly matches entities; no benchmark named.
47|confirmed|Conversational priors correction overlaps LLM chatbot target, corrector unnamed.
48|confirmed|Bayesian network and variational inference are model/training families; theorem is result.
49|confirmed|LLM efficacy comparison overlaps evaluated model; RAG context does not identify evaluator.
50|confirmed|RL diagnosis/understanding targets RL, no independent analyzer named.
51|confirmed|Path individualization association retained; adaptive-learning pedagogical versus method role uncertain.
52|confirmed|BrainMetDetect/ML predict primary tumor; radiomics and MRI are inputs, not dataset identities.
53|confirmed|GNN and spatial-information learning explicitly support weather-forecast postprocessing.
54|confirmed|LLM sarcasm-detection question supplies investigated association, not a reasoning-quality guarantee.
55|confirmed|KG-driven video-language learning is composite for action recognition.
56|confirmed|Unipa-GPT/LLMs explicitly perform university QA in Italian.
57|confirmed|Threat modeling/red-teaming targets LLMs; model target not automatically red-team method.
58|confirmed|Medical imaging is broad domain and bare classification lacks object; no task invented.
59|confirmed|LLMs extract scientific information from additive-manufacturing research; teaming is workflow.
60|confirmed|Specialized-model correction versus task boundary uncertain; target LLM overlaps full task.
61|confirmed|Hijacking attack is technique, FL target family, no distinct downstream task.
62|confirmed|IKUN/LLMs explicitly translate multilingual text; WMT24 shared task not automatically dataset.
63|confirmed|LLM autonomous-agent composite simulates organizational behavior.
64|confirmed|BERT/Transformer detect generic news frames; avoid duplicate opening paraphrase.
65|confirmed|Veridical data science is technique-family framing; medical models have no specific downstream task.
66|confirmed|Reward-qualified knowledge distillation is full composite, no nested LLM duplicate.
67|confirmed|LVCD/diffusion colorize lineart videos with reference conditioning.
68|confirmed|Good Idea evaluation lacks a concrete operation/object; do not infer unspecified classifier.
69|confirmed|Country classification clear; comparative analysis and dataset optimization leave full inventory uncertain.
70|confirmed|Fuzzy transfer model stated; SSVEP BCI system is application artifact, no decoding task inferred.
71|confirmed|Neuron-qualified personality induction versus task boundary uncertain; induced LLM overlaps target.
72|confirmed|Transformer translates signs; SignAttention may interpret translator, not execute translation.
73|confirmed|Diffusion Transformer Policy is complete method identity without control target.
74|confirmed|MedGo and full Chinese medical LLM name model; no diagnosis operation inferred.
75|confirmed|TEAFormers/tensor Transformer forecast multidimensional series; preserve capitalization.
76|confirmed|Predictor, Transformer and ESM2 explicitly support protein screening.
77|confirmed|SoftCTRL/full KL-control Transformer-RL composite explicitly supports driving.
78|confirmed|LLM exam-question/answer generation explicit; no educational efficacy claimed.
79|confirmed|Integration/enhancement modifies vision Transformer architecture; self-supervision is method, remote sensing broad context.
80|confirmed|LoRA-BERT/NLP model predict long noncoding RNAs; accuracy is claim only.
81|confirmed|PriorDiffusion/diffusion explicitly estimate monocular depth; language prior is input information.
82|confirmed|ZoomLDM/latent diffusion generate multiscale images.
83|confirmed|OSDFace/one-step diffusion restore faces; one-step is mechanism qualifier.
84|confirmed|Brand-building impact is business context, no concrete AI operation.
85|confirmed|DataLab is platform, business intelligence broad goal; LLM family only.
86|confirmed|Pinco/diffusion inpaint; adapter may condition rather than directly implement full target.
87|confirmed|ML explicitly detects Android intrusions.
88|confirmed|Sensing systems expansion lacks specific sensing operation; knowledge transfer role uncertain.
89|confirmed|AnyDressing/latent diffusion implement multi-garment virtual dressing.
90|confirmed|LLM uncertainty quantification overlaps measured model, estimator unspecified.
91|confirmed|RNN detects depression in Bangla social text; no clinical validity inferred.
92|confirmed|Olympus routing mechanism does not turn generic vision tasks into named operations.
93|confirmed|Self-attentive Transformer postprocesses temperature/wind forecasts.
94|confirmed|Full critique-tune adaptive-pressure RL composite controls multi-intersection signals.
95|revised|Weight-only transfer can train a speech predictor without being runtime predictor; relation stays uncertain.
96|revised|Integrating IDHEAS does not identify whether it is algorithm, framework or resource from title alone.
97|confirmed|Remote-sensing object detection literal; few-shot/generalization framing excluded.
98|confirmed|Generative AI/graph diffusion support sensor placement; no physical-system dataset inferred.
99|confirmed|Cache eviction is technique; full inference target overlaps LLM, no fabricated independent task.
100|confirmed|EndoChat/full multimodal LLM are model names; endoscopic surgery broad domain.
101|confirmed|Feature-learning/debiasing tasks overlap networks; target Transformer not automatically debiaser.
102|confirmed|Conceptual-combination association retained but full evaluation overlaps LLM target.
103|confirmed|Judge role lacks literal evaluation object/protocol; software-engineering domain alone insufficient.
104|confirmed|LLM unlearning overlaps target; activation redirection is intervention method.
105|confirmed|Transfer and Meta-Learning share Learning head; keep group and no reconstructed members.
106|confirmed|Janus/full collaborative vision Transformer are complete identities; network environment setting.
107|confirmed|Deep RL explicitly performs insect-scale vehicle hovering flight.
108|confirmed|Mantis/foundation model classify time series; quality adjectives excluded.
109|confirmed|ML detects fraudulent Chichewa SMSs; language retained.
110|confirmed|Healthcare trust/intention survey not a diagnosis or treatment task.
111|confirmed|Scientific computing is broad and comparison supplies no specified operations; quarantine.
112|revised|Domain Adaptive describes adaptation setting, not base object-detection task; trim task boundary.
113|confirmed|Tunnel-diode activation belongs to full quantum-neuromorphic architecture; no physical device Transformer inferred.
114|confirmed|Hierarchical neuro-symbolic decision Transformer is full model identity.
115|revised|Type-information/self-supervision describe inputs/training, not denoising task identity; keep base KG denoising.
116|confirmed|Full CNN reachability task overlaps verified model; hybrid zonotope is verification technique.
117|confirmed|LLM agents simulate/detect attacks; abbreviated operation omits exact target and remains quarantined.
118|confirmed|LLMs explicitly generate unit tests; quality/language adjectives excluded.
119|confirmed|Distillation may train filter and LLM may teach; neither definitely executes filtering.
120|confirmed|Architecture search overlaps language-model target; named search method does not resolve flat inventory.
121|confirmed|CoMP/pre-training technique and foundation models are methods; no separate downstream task.
122|confirmed|Output ownership is legal context; no concrete automatic attribution task or legal conclusion.
123|confirmed|Embeddings support semantic cache; LLM may merely benefit from cache.
124|confirmed|Academic report writing is workflow context, no specific automated generation operation stated.
125|confirmed|Model zoo is generic collection, not named benchmark suite.
126|confirmed|Medical imaging/label availability are domain/settings, not specific DL task.
127|confirmed|German lip-word recognition clear; development/evaluation overlap algorithm target.
128|confirmed|Climate prediction omits predicted quantity; do not infer precipitation or temperature.
129|confirmed|Bias verification overlaps evaluated LLM; no dataset identity supplied.
130|confirmed|Similarity detects paraphrases; ChatGPT produces target paraphrases, not the identifier; BBC article corpus unnamed.
131|confirmed|Self-classification correction is implementing technique explicitly for object detection.
132|confirmed|PersonaBOT slogan does not specify simulation/generation task; no invented persona operation.
133|confirmed|Foundation-model representation supports auscultation heart-rate estimation.
134|confirmed|Diffusion samples posterior; GP supplies prior distribution, not necessarily sampler; typo preserved.
135|confirmed|Self-preference measurement overlaps judging LLM target.
136|confirmed|Foundation-model tuning overlaps target; partial-label learning is learning regime.
137|confirmed|Agricultural image analysis generic; review does not specify segmentation/classification target.
138|confirmed|DivScore detects generated text; LLM inside provenance modifier is not duplicated nested method.
139|confirmed|Bare ranking lacks object; no recommendation target inferred from LlamaRec name.
140|confirmed|Adapter mitigates hallucination; LLM may be corrected target rather than corrector.
141|confirmed|VLM understands video quality; RL may train it rather than evaluate video itself.
142|confirmed|Unifying biomedical expertise lacks specific operation and overlaps foundation-model target.
143|confirmed|VMoBA/block attention/video diffusion are methods; no unstated video-generation task.
144|confirmed|DEREK software-engine name lacks full extraction target; acronym not enough for invented task.
145|confirmed|Subconcept probing studies harmfulness; full task overlaps LLM target.
146|confirmed|Wellbeing-concept explanation is investigated LLM use, not verified explanation quality.
147|confirmed|Corpus-aware training and neural translator are method families; no duplicated nested task.
148|confirmed|Cytotoxicity study does not literally name predicting; QSAR type/role uncertain without external enrichment.
149|confirmed|Cipher attack targets fine-tuning API, not defender; safeguarding full task overlaps LLM interface.
150|confirmed|Compositionality understanding overlaps LLM target; no independently named analyzer.
151|revised|Complete autoscaling target is the LLM-inference workload; short task omitted context and full task overlaps LLM.
152|confirmed|LLM generates programs to trigger compiler numerical inconsistency; keep complete objective.
153|confirmed|Credence-goods honesty/distrust are economics outcomes, not computational targets.
154|confirmed|Inverse-problem technique investigates scaling laws; full analyzed-model task overlaps LLM target.
155|confirmed|LLM ensemble explicitly emulates human preferences; compact is size framing.
156|confirmed|ML classifies landcover/detects changes; remote sensing may only acquire inputs.
157|confirmed|BEVUDA++ detects objects; adaptation may only train detector rather than execute detection.
158|confirmed|DeepMech/ML explicitly predict chemical reaction mechanisms.
159|confirmed|Spatial prompting is technique; no downstream task specified for multimodal LLM.
160|confirmed|MAIFormer/full inverted multi-agent Transformer predict flight trajectory.
161|confirmed|Adversarial RL simulates ESP cheater; acronym not expanded or executed.
162|confirmed|K-Prism is named segmentation model, task literal clear.
163|confirmed|Latent-predictive representations may be features rather than standalone method; keep uncertain.
164|confirmed|Psychometric evaluation overlaps target multi-agent LLM, no flat evaluation task inferred.
165|confirmed|Offline-to-online RL regimes are theory description, no downstream operation.
166|revised|Targeted drug discovery is broad goal without explicit search/generation/prediction operation; do not certify specific task.
167|revised|SD/SDXL share model-family head; preserve actual coordinated group rather than ordinary METHOD.
168|confirmed|NP-Engine/LLM explicitly reason about optimization; synthetic problems are unnamed inputs, not benchmark release.
169|confirmed|Count-based reward technique supports exploration in LLM reasoning, no nested duplicate model.
170|confirmed|Folktale automation does not specify operation; Cinderella is case content, not dataset.
171|confirmed|Proactive solving measurement overlaps agent target and problem object unspecified.
172|confirmed|Graph and recurrent share neural networks head; preserve group, no invented members.
173|confirmed|LLM-guided probabilistic fusion is full composite for document layout analysis.
174|confirmed|Bare recommendation lacks item/user object, so candidate stays unresolved.
175|confirmed|Prompting/LLM automate geospatial dashboards; self-validation may only check output.
176|confirmed|Syllogistic reasoning association clear but full understanding task overlaps LLM target.
177|confirmed|Diffusion designs controllers; Youla may parameterize space rather than generate controller.
178|confirmed|Chemically informed ML predicts copolymerization reactivity ratios.
179|confirmed|ML screens molecular compounds; fingerprint may be descriptor only.
180|confirmed|Temporal KG embedding explicitly supports future-event prediction.
181|confirmed|NLP survey associates symbolic music generation/retrieval, not a new experiment.
182|confirmed|RelFormer/Transformer explicitly perform dense captioning.
183|confirmed|Triple-stream commonsense circulation Transformer is full captioning architecture.
184|confirmed|i-Align explicitly aligns knowledge graphs; resource not benchmark.
185|revised|Transfer learning may train IDS-INT detector rather than execute intrusion detection; retain named detector association.
186|confirmed|LLM customizes SQL operator implementations; not generic SQL generation.
187|confirmed|Text-to-image generation may augment captioner data, not execute captioning itself.
188|confirmed|Ontology building task explicit, unnamed methodology supplies no method identity.
189|confirmed|ML indexes/clusters PubMed articles, but full platform-design target overlaps method; database not dataset release.
190|confirmed|Multi-agent RL shares spectrum and allocates power; secure is constraint/quality.
191|confirmed|ML/ResNet extract features; full classifier execution remains unresolved.
192|confirmed|ANN predicts particle characteristics; full modular-implementation task overlaps ANN.
193|confirmed|ML explicitly classifies research methodologies.
194|confirmed|Broad-learning system diagnoses bearing faults; CV may only be domain context.
195|confirmed|Classification lacks target object; keep unresolved.
196|confirmed|Device recognizer may feed separate emission estimator; no direct execution assumed.
197|confirmed|DL/target-related Transformer explicitly predict industrial quality.
198|confirmed|Power transformer is apparatus, not neural model; fault perception method/task unspecified.
199|revised|Facebook/Meta are platforms, not METHOD; remove erroneous platform candidate while preserving generic-analysis uncertainty."""


def review():
    run = ROOT / 'kg_datasets/dblp/course_v4_runs/pending_train_20261007_23'
    source = run / 'generation_decisions.json'
    digest = 'c5c15b7da2201740a8690b33149021dca72671e1a74926c315f0afd00533354f'
    assert c.file_sha256(source)==digest
    first = json.loads(source.read_text(encoding='utf-8'))['decisions']
    judgments = [(int(i),v,r) for i,v,r in (line.split('|',2) for line in JUDGMENTS.splitlines())]
    assert len(first)==200 and [i for i,_,_ in judgments]==list(range(200))
    revisions = {i:copy.deepcopy(first[i]) for i,v,_ in judgments if v=='revised'}
    for i in (8,38,95):
        revisions[i]['relations'][0].update(label='UNRESOLVED',reason='Training/supervision technique may train task executor rather than itself execute the complete target.')
        revisions[i].update(relationStatus='unresolved',relationReason='Training versus deployed task-execution role unspecified.')
    revisions[9].update(entityStatus='unresolved',entityReason='Diffusion-based synthesis mixes method qualifier and full task; flat inventory cannot independently represent both.',
        relationStatus='unresolved',relationReason='Retain observed opposing role but do not certify complete method/task inventory.')
    revisions[35].update(groupMentions=[],entities=[{'text':'Named Entity Recognition','label':'TASK'},
        {'text':'Cross-Lingual, Character-Level Neural Conditional Random Fields','label':'METHOD'}],
        relations=[{'head':'e2','tail':'e1','label':'USED_FOR','reason':'Full cross-lingual character-level neural CRF explicitly performs NER.'}])
    revisions[96].update(entityStatus='unresolved',entityReason='IDHEAS identity as algorithm/framework/resource cannot be established from unexpanded acronym alone.',
        relationStatus='unresolved',relationReason='Cannot certify full instrument inventory from title; IDHEAS is only a candidate.')
    revisions[96]['relations'][1].update(label='UNRESOLVED',reason='Integrating unexpanded IDHEAS does not establish its standalone task-executing role.')
    revisions[112]['entities'][1]['text'] = 'Object Detection for Microscopic Images'
    revisions[115]['entities'][0]['text'] = 'Knowledge Graph Denoising'
    revisions[151].update(entityStatus='unresolved',entityReason='Full autoscaling task must retain LLM-inference target and overlaps the identifiable model in flat schema.',
        relationStatus='unresolved',relationReason='Observed workload-versus-scaler role does not resolve full nonoverlapping task inventory.')
    revisions[166].update(entityStatus='unresolved',entityReason='Targeted drug discovery is a broad research goal without literal specific computational operation.',
        relationStatus='unresolved',relationReason='Do not certify an unspecified drug search/generation/prediction operation.')
    revisions[166]['relations'][0].update(label='UNRESOLVED',reason='Generative-model drug-discovery association does not specify actual technical operation.')
    revisions[167].update(entities=first[167]['entities'][:2],groupMentions=[{'text':'SD/SDXL Latent Diffusion Models','label':'METHOD'}],
        entityStatus='complete',entityReason='',relationStatus='complete',relationReason='',notes='CADE 2.5 is release/event framing; SD/SDXL share family head, no member names reconstructed.')
    revisions[185]['relations'][1].update(label='UNRESOLVED',reason='Transformer-based transfer learning may train the detector rather than directly detect intrusion.')
    revisions[185].update(relationStatus='unresolved',relationReason='Training procedure versus deployed detector role uncertain.')
    revisions[199].update(entities=[{'text':'deep learning-based dual-stage SEM-ANN','label':'METHOD'}],
        entityReason='Platform usage analysis does not specify concrete computational operation; platforms are not methods.')
    assert len(revisions)==13
    output = []
    for i,verdict,reason in judgments:
        item = {'sampleId':first[i]['sampleId'],'verdict':verdict,'reason':reason}
        if verdict=='revised': item['replacement']=revisions[i]
        output.append(item)
    path = run / 'review_judgments.json'
    if path.exists(): raise FileExistsError('Preserve existing review.')
    c.write_json(path,{'provider':'codex_session','model':'unknown_session_model','round':'candidate_aware_ai_review',
        'generationDecisionsSha256':digest,'judgments':output})
    shutil.copyfile(Path(__file__),run / 'authored_review.py')
    expand_artifact(source,path,run / 'review_expanded')
    dataset = ROOT / 'kg_datasets/dblp/course_v4_weak'
    previous = run / 'generation/receipts.jsonl'
    compile_artifact(dataset,run / 'jobs.jsonl',run / 'review_expanded/review_decisions.json',run / 'review_compiled',previous=previous)
    import_results(dataset,run / 'review_compiled/responses.jsonl',run / 'review',provider='codex_session',model='unknown_session_model',previous=previous)
    parent = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_15'
    target = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_16'
    summary = assemble(dataset,[parent / 'receipts.jsonl',run / 'review/receipts.jsonl'],target)
    original = c.read_jsonl(parent / 'receipts.jsonl')
    assert c.read_jsonl(target / 'receipts.jsonl')==original+c.read_jsonl(run / 'review/receipts.jsonl')
    assert all((parent / n).read_bytes()==(target / n).read_bytes() for n in
        ('ner_inputs_dev.jsonl','ner_inputs_test.jsonl','relation_inputs_dev.jsonl','relation_inputs_test.jsonl'))
    c.write_json(run / 'manifest.json',{'kind':'new_training_labels_same_session_candidate_aware_AI_self_review',
        'parentSnapshotManifestSha256':c.file_sha256(parent / 'manifest.json'),'newSnapshotManifestSha256':c.file_sha256(target / 'manifest.json'),
        'documents':200,'confirmed':187,'revised':13,'humanGold':False,'independentReviewer':False,'trainingStarted':False,
        'finalTestInferenceRepeated':False,'oldReceiptsUnchanged':True,'devTestInputsByteIdentical':True,
        'filesSha256':{p.relative_to(run).as_posix():c.file_sha256(p) for p in run.rglob('*') if p.is_file()}})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    review()

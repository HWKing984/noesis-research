"""Explicit same-session review of 200 titles; never independent or human gold."""
import copy
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_weak as c
from compile_course_ai import compile_artifact
from expand_course_ai_review import expand_artifact
from import_course_ai import import_results, assemble

# Each line is an authored judgment, not a default-confirm classifier.
JUDGMENTS = """0|confirmed|Bioinformatics KG/data review names no algorithm, computational operation or dataset release.
1|confirmed|Hardware acceleration overlaps the network target; optical infrastructure supplies no complete task boundary.
2|confirmed|Active contours, variational level sets and ML are explicitly combined segmentation techniques.
3|confirmed|Networks label topics using unnamed images; complete operation/object retained.
4|confirmed|Translation task retains memory constraint; no implementing algorithm is named.
5|confirmed|L-BFGS optimizer and ML are method families; no METHOD-to-METHOD relation is invented.
6|confirmed|Translation is an implementing technique for geoparsing in this sentence, rather than its target.
7|confirmed|DL removes heterogeneous blur; motion flow is output framing, not DATASET.
8|confirmed|Deep CNN extracts sensor-based gait parameters; no gait benchmark is named.
9|confirmed|Full CNN training task overlaps its target; FFT and overlap-and-add remain methods only.
10|confirmed|Neural translation explicitly supplies word-similarity embedding technique.
11|revised|Expected output change is an acquisition criterion; guiding exploration alone does not establish task execution.
12|confirmed|Permutation-invariant training of recurrent networks is one composite, not duplicated nested entities.
13|confirmed|Kernelized CNN explicitly describes images; no image corpus is named.
14|confirmed|Echocardiogram classification uses DL; fast/accurate is unverified quality framing.
15|confirmed|LSTM performs temporal extraction; full downstream QA implementation stays unresolved.
16|confirmed|Sequential recurrent architecture explicitly models language.
17|confirmed|Network classifies patients; expansion/compression may only prepare inputs.
18|confirmed|Batch hierarchical RL is a complete family; bare Algorithms names no second method.
19|confirmed|Topology-adaptive GCN architecture has no stated downstream task.
20|confirmed|Embedded deployment targets the DL model; it is not itself the deploying algorithm.
21|confirmed|Recurrent attention discovery explicitly implements multi-label recognition.
22|confirmed|Full RL-agent design operation overlaps the target; ethics shaping does not resolve flat inventory.
23|confirmed|DRL explicitly implements mobile data offloading; cost/energy are constraints.
24|confirmed|Computer vision is domain context, not a named robust-fitting solver; retain uncertainty.
25|confirmed|GONet and DL explicitly estimate traversability; semi-supervision is setting.
26|confirmed|Sensor pattern noise may be a feature rather than method; preserve incomplete inventory despite clear DL association.
27|confirmed|Dynamics-analysis operation overlaps networks; entropy/chaos are properties, not datasets.
28|confirmed|CNN segments brain images; localization may be incorporated inputs rather than an executed target.
29|confirmed|Velocity-porosity supermodel and DNN are model identities without a literal operation.
30|confirmed|Adversarially trained VAE is a full composite for image generation; fidelity is quality wording.
31|confirmed|SmoothOut smooths minima; large-batch DL is recipient process, not necessarily smoother.
32|confirmed|Generalization/simple-function bias states a property, not a named task or dataset.
33|confirmed|DNN explicitly synthesizes propositional proofs; retain logic object.
34|confirmed|Xcel-RAM/SRAM are hardware; full binary-network acceleration overlaps model target.
35|confirmed|Improving self-supervision overlaps named learning method; no nested task synthesis.
36|confirmed|Event-KG development is explicit; Twitter headlines are unnamed inputs, not DATASET.
37|confirmed|OWLAx/Protege are plugin/software artifacts; ontology axiomatization is the stated task.
38|confirmed|dyngraph2vec and dynamic graph representation technique capture network dynamics.
39|confirmed|Information diffusion concerns social propagation, not image-generative diffusion.
40|confirmed|Tree extraction uses graph refinement; network refinement versus end-to-end extraction remains uncertain.
41|confirmed|Cost prediction overlaps target DL models; no predictor name is given.
42|confirmed|Neural networks explicitly model identity rules.
43|confirmed|Off-grid model-based DL and O-MODL are literal identities; no task is stated.
44|confirmed|Translation is task; unsupervised is setting and unnamed approach supplies no method identity.
45|confirmed|Interaction-aware Kalman networks explicitly predict trajectories.
46|revised|Bare Curriculum does not identify a specific curriculum-learning algorithm; incomplete method inventory needs quarantine.
47|confirmed|Detection on surveillance UAV is a complete task; latency/accuracy are quality claims.
48|confirmed|Multimodal ML predicts osteoarthritis progression; radiographs/clinical data are unnamed inputs.
49|revised|Pre-training is a technical operation on GNNs; full task overlaps the target, unlike a complete model-only title.
50|confirmed|Evolutionary optimizer is explicit but full network-training target overlaps DNN.
51|confirmed|DNN detects communication symbols; millimeter wave specifies target context.
52|confirmed|BERT task role is not fully settled by robustness question; attack targets rather than executes classification.
53|confirmed|Neural machine translation is stated operation; noisy lexical constraints are inputs/settings.
54|confirmed|Seq2seq recurrent model translates; parallel training may only train that model.
55|confirmed|Relu network performs function approximation; preserve original spelling.
56|confirmed|Modeling data-structure influence overlaps networks and lacks a named modeling algorithm.
57|confirmed|Translation model is fine-tuned recipient, not the sentence selector; explicit negative role retained.
58|confirmed|Gradient boosting supports training; full network-training operation overlaps target model.
59|confirmed|Formula transformers and test generators are symbolic procedures, not neural Transformer inference.
60|confirmed|Optimizer comparison lacks named optimizer and complete literal task inventory.
61|confirmed|DL recognizes sites on mobile devices; crowdsourced imagery is unnamed input.
62|confirmed|Bidirectional entailment is a technique for translation evaluation, not EVALUATED_ON without DATASET.
63|confirmed|Failure modes are properties of ML systems; no technical task or benchmark identity.
64|confirmed|Word-class embedding technique explicitly supports multiclass classification.
65|confirmed|RNN explicitly performs predictive precompute; no benchmark is named.
66|confirmed|Make TCP Great is a slogan without a literal specified networking operation.
67|confirmed|Adversarial ML may protect or attack forecasting; title does not establish forecaster role.
68|confirmed|Transformer decoding overlaps Transformer target; n-gram attention stays method.
69|confirmed|Regularized GP models traffic; generic ML applications do not establish a second direct executor.
70|confirmed|Priors/regularization are modifiers within one CNN composite, not separately reconstructed shared-head methods.
71|confirmed|RL-enhanced quantum-inspired algorithm is one composite for combinatorial optimization.
72|confirmed|Networks explicitly implement mechanism design for public projects.
73|confirmed|Model-free RL explicitly addresses robotic table tennis; no robot dataset identity.
74|confirmed|DL and transfer-learning algorithms explicitly support pneumonia diagnosis; no clinical efficacy asserted.
75|confirmed|CNN estimates scale; full visual tracking execution is downstream and unresolved.
76|confirmed|Transformer translation association is explicit; depth/low-resource describe architecture/setting.
77|confirmed|PFNN and penalty-free network solve boundary-value problems; retain geometry object constraints.
78|confirmed|GIMP-ML and GIMP are software; CV is a model family without a stated processing task.
79|confirmed|Transportation systems are broad application context, not a specific survey task.
80|confirmed|Privacy and GNN are technique families; title states no operational target.
81|confirmed|FLAMBE and representation-learning/model families are explicit; structural complexity is a property.
82|confirmed|GCN, heat kernel and semi-supervised learning are methods; learning setting alone is not a task.
83|confirmed|Unnamed space-weather ontology is resource/context, not a named dataset or algorithm.
84|confirmed|Transfer learning explicitly mitigates classification bias; no invented underlying classification object.
85|confirmed|Unnamed model-free method lacks identity and MIMO systems do not specify target operation.
86|confirmed|Aggregation-and-distribution jointly qualifies one named CoADNet architecture; no member names are reconstructed.
87|confirmed|Dialog system operation is unspecified; preserve possible task candidate without certifying inventory.
88|confirmed|MicroNet explicitly recognizes images; low FLOPs is quality/computation constraint.
89|confirmed|Multimodal Transformer explicitly learns video representations; parameter efficiency is architecture framing.
90|confirmed|Drug discovery/development is broad goal without a specific ML prediction/search operation.
91|confirmed|DL completes matrices; manifold learning may only supply geometry/features.
92|confirmed|ANN explicitly imputes rounded zeros in compositional data.
93|confirmed|Performance/cluster-limit evaluation overlaps selection setting; evaluated ML is not necessarily evaluator.
94|confirmed|Text-image-layout Transformer implements document understanding; slogan is not another model identity.
95|confirmed|DL explicitly extracts lumen/media-adventitia in ultrasound; no dataset release named.
96|confirmed|Deep-and-wide network predicts Rajasthan rainfall; RSMR names target, not dataset.
97|confirmed|Statistical viewpoint supplies no operational target beyond DL family.
98|confirmed|Pose-GNN and GNN family estimate camera pose.
99|confirmed|Expert priors have unclear resource/method identity; preserve quarantine despite clear driving association.
100|confirmed|Group collaborative learning explicitly detects co-salient objects.
101|confirmed|Agent-robustness improvement overlaps RL target; environment attacks are not automatically defense execution.
102|confirmed|Stochastic second-order DL is one method; no task or named dataset.
103|confirmed|Two-layer ensemble is a full composite explicitly segmenting medical images.
104|confirmed|VIPriors challenge is not automatically a released DATASET; unspecified competitive method stays unresolved.
105|confirmed|Data transformation role is unclear; title gives ML classification association but incomplete inventory.
106|confirmed|Recomposition overlaps RL building blocks; hypernetworks do not resolve target span.
107|confirmed|Transferred spatiotemporal network composite models seizure videos; no named seizure benchmark.
108|confirmed|FL with dynamic Transformer explicitly targets text-to-speech; both complete methods retained.
109|confirmed|Local ensemble Kalman filters estimate state/parameters and explicitly apply to learning chaotic dynamics.
110|confirmed|Adam generalization analysis overlaps network target; proper regularization is not a dataset.
111|confirmed|DAE-GAN and dynamic aspect-aware GAN synthesize images from text.
112|confirmed|Infinity symbol is preserved literally in named model; expansion is complete Transformer identity.
113|confirmed|Explainability/safety are desired properties; no particular explanatory method or healthcare task is named.
114|confirmed|DL detects symptoms; weighting may only combine modes rather than itself detect.
115|confirmed|MFE-NER and feature-fusion embedding explicitly address Chinese NER.
116|confirmed|Gradient compression and FL are techniques; Layerd typo is preserved, not silently corrected.
117|confirmed|SPARQL silhouette generation is query-generation technique implementing KG question answering.
118|confirmed|Backdoor attack targets network training; flat full task overlaps target model.
119|confirmed|Exploration lacks technical object/domain; keep uncertain rather than invent a task.
120|confirmed|Residual-connection Transformer diarizes speakers; unnamed auxiliary loss is not a separate named algorithm.
121|confirmed|Interpreting DL models overlaps models; NLP names family/domain, not interpretation task object boundary.
122|confirmed|Overparameterization is architecture property; shallow networks are the named family.
123|confirmed|Attention/CV are methods; survey contains no specific target or benchmark.
124|confirmed|First- and second-order share Algorithms head; group remains isolated, with no reconstructed member span.
125|confirmed|FedSoft and its full clustered-FL expansion are complete methods, not a new task.
126|confirmed|ML detects ventricular tachycardia; ECG is modality, not a named dataset.
127|confirmed|Bibliometric title states ML diagnosis association but is not a new diagnostic evaluation.
128|confirmed|Medical imaging is broad context; security/defence does not specify an executed task.
129|confirmed|Interactron explicitly performs embodied adaptive object detection.
130|revised|Transfer learning may only train the recognizer; language-model decoding implements recognition but is not interchangeable with training.
131|confirmed|Multitasking/importance sampling qualify evolutionary RL; no downstream operation is specified.
132|confirmed|NLP and ensemble learning explicitly filter liver-injury literature; inputs are unnamed articles.
133|confirmed|Comparative evaluation task overlaps methods; clear prediction association alone cannot certify entire inventory.
134|confirmed|RL coordinates multiple EV charging points; computational efficiency is a claim.
135|confirmed|Adaptive multi-size-kernel CNN is a full fault-diagnosis architecture.
136|confirmed|Meta-learning, Bayesian binary networks and Born machines are methods, not a METHOD-to-TASK relation.
137|confirmed|Feature disentangling versus transfer-trained StyleGAN executor remains uncertain.
138|confirmed|RANG/node-generation technique serves physics-informed networks; no separate nested node-generation task.
139|confirmed|Genetic data analysis lacks a specific technical subproblem; preserve candidate uncertainty.
140|confirmed|Entry-flipped Transformer infers/predicts participant behavior; full coordinated task retained.
141|confirmed|Subtype-Former/DL discover cancer subtypes; multi-omics data is unnamed.
142|confirmed|Federated DRL allocates O-RAN slicing resources.
143|confirmed|ODformer/spatiotemporal Transformer forecast OD matrices; scenario qualifier is not DATASET.
144|confirmed|Transformer-based DL predicts stock prices; case location is not dataset identity or financial advice.
145|confirmed|Complex-valued GCN architecture is stated; electric-power AI applications lack specific task.
146|confirmed|MolGraph/TensorFlow/Keras are packages/frameworks; implementation task overlaps GNN target.
147|confirmed|Membership assessment overlaps inference/ML; Membership-Doctor identity cannot establish neural method from title.
148|confirmed|Learnable activation belongs to full Transformer architecture; no task stated.
149|confirmed|Pre-training/random initialization are training procedures, not necessarily translation executors.
150|confirmed|Deep networks and complex-network mathematical model are literal method/model families only.
151|confirmed|GNN predicts links; sketching may prepare subgraph features rather than execute prediction.
152|confirmed|Distributionally adaptive meta-RL is one full method; no downstream task.
153|confirmed|PTDE expansion includes training/execution composite; preserve Distillated typo.
154|confirmed|DiffuSeq and diffusion models explicitly perform seq2seq text generation.
155|confirmed|Ontology development is a literal operation; consensus/representation are conceptual characterizations.
156|confirmed|Training-performance comparison overlaps target network; Elixir/Python are languages.
157|confirmed|Diffusion performs speech super-resolution; conditioning/sampling role as a separate task remains uncertain.
158|confirmed|Offline RL with primitive discovery is composite; bare Control does not specify technical task.
159|confirmed|MAGVIT and masked generative video Transformer are named/full methods; no literal generation task added.
160|confirmed|Training-systems task overlaps large-model DL; unnamed Systems supplies no algorithm identity.
161|confirmed|Signed message is a feature/property question, not a named task or data release.
162|confirmed|RangeViT/vision Transformers segment 3D driving scenes; autonomous driving is task context.
163|confirmed|Generated curriculum goals guide RL; RL is not automatically the goal-generating algorithm.
164|confirmed|Open problems/solutions are generic discussion, not a specified technical operation.
165|revised|Edited is state/quality framing rather than a specific architecture identity; remove it from model span.
166|confirmed|DL authenticates RF fingerprints; chaotic antenna arrays are physical devices.
167|confirmed|Sparse-latent-point diffusion generates meshes; controllable modifies stated task.
168|confirmed|Online RL and periodic MDP are method/problem models without another task.
169|confirmed|NASA KG discovery may be resource name or operation; title cannot disambiguate, so quarantine.
170|confirmed|ProductAE/DL are methods; error-correction codes do not literally name encoding/decoding/construction operation.
171|confirmed|NN-Copula-CD and its copula-guided network detect remote-sensing changes.
172|confirmed|Q-DETR and quantized detection Transformer name model identities; Detector does not synthesize missing task.
173|confirmed|Tutor is software and Math Task lacks specified object/operation; no efficacy asserted.
174|confirmed|Game-theoretic framework is a mathematical technique for FL, not necessarily software; no task relation.
175|confirmed|Phoneme-informed network transcribes singing notes.
176|confirmed|Representation learning is explicit target of Proto-Value Networks here; unnamed auxiliary tasks not invented.
177|confirmed|Neural network scores essays; dynamic loss may only train it, so task-execution pair stays uncertain.
178|confirmed|DRL solves stabilize-avoid control; epigraph is formulation rather than necessarily solver.
179|confirmed|NavGPT/LLMs perform navigation reasoning; full reasoning target avoids duplicate nested navigation task.
180|revised|Evaluator denotes an evaluation role but object/protocol are unspecified; a complete method-only inventory is overconfident.
181|confirmed|Masked diffusion detects medical-image anomalies; unsupervised is training setting.
182|confirmed|YOLOv8 detects onboard AR objects; display hardware is not method or dataset.
183|confirmed|Healthcare KG resources/promises name no specific operation, algorithm or dataset.
184|confirmed|Adversarial prompting and LLM explicitly generate astronomy hypotheses; robustness is not demonstrated here.
185|confirmed|Low-rank POMDP is problem model, not a stated planner/representation-learning algorithm.
186|confirmed|FastBCSD and network detect binary-code similarity; no code benchmark named.
187|confirmed|Nano1D segmentation is specific but coordinated analysis unspecified; full task inventory stays unresolved.
188|confirmed|FL server is offloaded software, not offloading algorithm; Smart NIC is hardware.
189|confirmed|SLSSNN and spike-train/conversion architecture are complete identities; energy efficiency is property.
190|confirmed|Stack Overflow activity is unnamed evidence, not a named dataset release or technical task.
191|confirmed|Mathematical explanation overlaps encoder-decoder target; explained networks are not necessarily explainers.
192|confirmed|SecureBoost is tuned target, not tuner; multi-objective FL explicitly tunes hyperparameters.
193|confirmed|BarlowRL, Barlow Twins and RL are method families; data efficiency is property.
194|confirmed|Pseudo-label improvement and detection are explicit operations without named implementer; vocabulary is setting.
195|confirmed|Federated-assisted Q learning is composite implementing joint offloading/routing.
196|confirmed|Region proposal network explicitly supports detection; quality/few-shot qualifiers excluded.
197|confirmed|MFRL-BI/model-free RL controls process; Bayesian inference may only design scheme.
198|confirmed|GAME/DL integrate multimodal data; downstream adolescent screening role remains uncertain, not clinical validation.
199|confirmed|Physics-informed ML optimizes power-system parameters; no named power benchmark."""


def review():
    run = ROOT / 'kg_datasets/dblp/course_v4_runs/pending_train_20261007_22'
    source = run / 'generation_decisions.json'
    digest = '07a81b7f088cfe4b0d10a7160f98809affe862f939cd848fd5234f729595b986'
    assert c.file_sha256(source) == digest
    first = json.loads(source.read_text(encoding='utf-8'))['decisions']
    judgments = [(int(i),v,r) for i,v,r in (line.split('|',2) for line in JUDGMENTS.splitlines())]
    assert len(first) == 200 and [i for i,_,_ in judgments] == list(range(200))
    revisions = {i:copy.deepcopy(first[i]) for i,v,_ in judgments if v == 'revised'}
    revisions[11]['relations'][1].update(label='UNRESOLVED',reason='Acquisition criterion may select exploration inputs rather than execute the complete exploration task.')
    revisions[11].update(relationStatus='unresolved',relationReason='Criterion versus task-executing role not fully specified.')
    revisions[46].update(entities=[{'text':'Reinforcement Learning','label':'METHOD'}],
        entityStatus='unresolved',entityReason='Bare Curriculum may denote a schedule/resource or a curriculum-learning technique; no full identity stated.',
        relationStatus='unresolved',relationReason='Complete method/task inventory cannot be established from title.')
    revisions[49].update(entityStatus='unresolved',entityReason='Full pre-training task overlaps the GNN target in the flat schema.',
        relationStatus='unresolved',relationReason='Target networks are not an independently named pre-training algorithm.')
    revisions[130]['relations'][0].update(label='UNRESOLVED',reason='Transfer learning may only train a recognizer rather than itself perform speech recognition.')
    revisions[130].update(relationStatus='unresolved',relationReason='Transfer-training versus task-execution role unspecified.')
    revisions[165]['entities'][0]['text'] = 'neural networks'
    revisions[180].update(entityStatus='unresolved',entityReason='Evaluator role implies evaluation, but object/protocol and literal complete task are unspecified.',
        relationStatus='unresolved',relationReason='No complete evaluation-task inventory; do not invent a target or a negative pair.')
    output = []
    for i,verdict,reason in judgments:
        item = {'sampleId':first[i]['sampleId'],'verdict':verdict,'reason':reason}
        if verdict == 'revised': item['replacement'] = revisions[i]
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
    parent = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_14'
    target = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_15'
    summary = assemble(dataset,[parent / 'receipts.jsonl',run / 'review/receipts.jsonl'],target)
    original = c.read_jsonl(parent / 'receipts.jsonl')
    assert c.read_jsonl(target / 'receipts.jsonl') == original + c.read_jsonl(run / 'review/receipts.jsonl')
    assert all((parent / n).read_bytes()==(target / n).read_bytes() for n in
        ('ner_inputs_dev.jsonl','ner_inputs_test.jsonl','relation_inputs_dev.jsonl','relation_inputs_test.jsonl'))
    c.write_json(run / 'manifest.json',{'kind':'new_training_labels_same_session_candidate_aware_AI_self_review',
        'parentSnapshotManifestSha256':c.file_sha256(parent / 'manifest.json'),'newSnapshotManifestSha256':c.file_sha256(target / 'manifest.json'),
        'documents':200,'confirmed':194,'revised':6,'humanGold':False,'independentReviewer':False,'trainingStarted':False,
        'finalTestInferenceRepeated':False,'oldReceiptsUnchanged':True,'devTestInputsByteIdentical':True,
        'filesSha256':{p.relative_to(run).as_posix():c.file_sha256(p) for p in run.rglob('*') if p.is_file()}})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    review()

"""Explicit title-only candidate-aware AI self-review; not independent gold."""
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

JUDGMENTS = """0|confirmed|Agronomic graph explicitly maps rice sequences; phenology retained inside composite.
1|confirmed|Partitioned neural network is computing target, not independent partitioner.
2|confirmed|Supervised and unsupervised share learning head; preserve group and image-classification target.
3|confirmed|Decision support and ML forecasting are stated; drainage context retained.
4|confirmed|C-to-Rust translation and type migration are literal operation and languages.
5|confirmed|Transformer forecasts rail wind speed; hybrid unnamed.
6|confirmed|Tree algorithms assess coastal vulnerability; location not dataset.
7|confirmed|COIN is accelerator; full acceleration task overlaps GCN target.
8|confirmed|Tourism information model may be schema; retain extractor candidates without certifying inventory.
9|confirmed|Cooperative robot does not specify concrete operation.
10|confirmed|Augmentation trains GNN; no downstream task stated.
11|confirmed|Review concerns text summarization; generic datasets supply no release identity.
12|confirmed|Full funnel cascaded-fusion GNN predicts protein interactions.
13|confirmed|DeepSeeded and cascaded DNN segment dense cells; biofilm not dataset.
14|confirmed|DL estimation explicit; attention features and transfer training not certified executors.
15|confirmed|Concept-driven representation learning explicitly completes knowledge graph.
16|confirmed|PSO-SVM and ML identify damage; improvement unverified.
17|confirmed|Physics-informed neural network simulates multiple scattering.
18|confirmed|Industry 4.0 is domain, not concrete computation.
19|confirmed|PM2.5 is explicit prediction quantity, not dataset identity.
20|confirmed|Formal verification and RL techniques stated; independent complete task absent.
21|confirmed|Bioinformatics legal discussion names no computational operation.
22|confirmed|Multitask FL detects and classifies microservice anomalies.
23|confirmed|3D V-Net recognizes and segments ossicles; no clinical efficacy inferred.
24|confirmed|sEMG and prosthesis are modality/hardware, not vision task.
25|confirmed|SmartFPS and NN perform wireless-inertial positioning.
26|confirmed|DETR detects objects; driving contextual.
27|confirmed|Future directions states no specific task.
28|confirmed|Exploratory state representation learning is method without downstream task.
29|confirmed|Finite-time stability describes delayed fuzzy neural network property.
30|confirmed|Latent diffusion generates reservoir facies.
31|confirmed|Crop mapping explicit; Sentinel-2 and LiDAR acquisition not benchmark releases.
32|confirmed|Concrete forecasting quantity unspecified; do not infer strength.
33|confirmed|RL implements handover, beacon transmission is mechanism.
34|confirmed|Hybrid NN detects risky adult situations; no clinical validation.
35|confirmed|NLP predicts comic speakers; visual relations inputs.
36|confirmed|Vehicle security and bare classification do not define classification object.
37|confirmed|Filtering transformer is physical component, no neural model.
38|confirmed|DL estimates speech intelligibility; autoencoder may only provide features.
39|revised|Sparse transfer learning may train emotion recognizer rather than directly recognize speech emotion.
40|confirmed|Graph attention network and RL place virtual network function graphs.
41|confirmed|Gait privacy protection lacks concrete computation; dataset unnamed.
42|confirmed|Space-time aggregation/result reuse detects video objects.
43|confirmed|Investment strategy lacks specific prediction/allocation; earnings index technique identity uncertain.
44|confirmed|Position-weighted embedding translates text.
45|confirmed|Differential-private FL performs sleep staging; imbalanced EEG is data setting.
46|confirmed|DL predicts robot positioning errors and finds features; robot context retained.
47|confirmed|ML detects malware; future directions not extra task.
48|confirmed|Semantic service discovery aids routing; energy evaluation/optimization role uncertain.
49|confirmed|Vision Transformer and perceiver detect facial action units.
50|confirmed|Region-based Randers geodesic segments images.
51|confirmed|ANN classifies microarrays; Spark platform not model.
52|confirmed|Modified CNN/SA-MGO healthcare chatbot lacks specific QA task; insights broad goal.
53|confirmed|ML maps agricultural intensification; Landsat/Sentinel sensors not release identities.
54|confirmed|Image-recognition-based location intertwines task and technique; isolate boundary.
55|confirmed|Quantized inference characterization overlaps Transformer target; CPU hardware context.
56|confirmed|Ontology expansion literal; UWN resource-versus-algorithm identity uncertain.
57|confirmed|Camouflaged detection/tracking are survey targets; no method named.
58|confirmed|DL and joint-slope probabilistic filter fuse medical images.
59|revised|Unexpanded UTAUT model does not establish computational-method identity; adoption is human behavior context.
60|confirmed|Financial decision making lacks specific action; no invented trading target.
61|confirmed|PPCA denoises and ANN classifies CT; crossed instrument roles uncertain.
62|confirmed|ML estimates cardiometabolic risk; exposome input unnamed.
63|confirmed|NLP identifies problematic opioid use; no clinical efficacy asserted.
64|confirmed|DL extracts breast-cancer clinical information.
65|confirmed|Intrusion-system modeling overlaps embedded adversarial NN technique.
66|revised|Interpretable Network lacks a specified neural architecture; keep candidate uncertain and retain tree-FL detection.
67|confirmed|Sequential cipher, feedback Hopfield and chaotic sequence techniques; no separate task.
68|confirmed|Healthcare prediction lacks output quantity/object.
69|confirmed|CNN-ELM composite classifies age and gender.
70|confirmed|Projection steepest-descent NN solves nonsmooth optimization.
71|confirmed|Delayed generalized NN stability is theoretical property.
72|confirmed|Probabilistic NN detects islanding; phase-space may be representation.
73|confirmed|CNN recognizes facial expressions in the wild; three models not three named identities.
74|confirmed|Full sparse directed attention GCN recognizes EEG emotion.
75|confirmed|Stability/passivity analysis overlaps delayed NN target.
76|confirmed|Synchronization target overlaps Clifford NN; encryption alone does not certify inventory.
77|confirmed|Backpropagation training may train rather than execute vehicle stability control.
78|confirmed|Corrigendum retains DL/fMRI diagnosis association, not new validation.
79|confirmed|Programming-work assessment explicit; named ontology resource not algorithm.
80|confirmed|Acoustic evasion opposes emotion detection; ML detector role separate.
81|confirmed|Talk2Care communication assistant lacks literal QA/transcription operation.
82|confirmed|Joint transaction-language/graph-representation composite detects Ethereum fraud.
83|confirmed|Intrusion detection explicit; separated industrial context not reconstructed into nonliteral span.
84|confirmed|Financial health/performance diagnosis is concrete assessment, not generic business application.
85|confirmed|Security service-function chain lacks specific allocation/routing action.
86|confirmed|Feature selection and transfer may prepare/train intrusion detector.
87|confirmed|Visual VR security lacks explicit operation.
88|confirmed|Multiview variational DL localizes indoor positions.
89|confirmed|DEN depth-enhancement network supports detection; standalone executor uncertain.
90|confirmed|Internet augmentation broad goal; RL rate-adaptation task/method boundary uncertain.
91|revised|Charging scheme problem does not name scheduling operation; remove Problem/Scheme and isolate unspecified action.
92|confirmed|DL builds sentiment lexicon; later financial prediction may be separate.
93|confirmed|Temporally evolving GNN detects fake news.
94|confirmed|ML detects mobile malware; traffic imbalance setting excluded.
95|confirmed|Kronecker convolutions and DL detect kidney stones in coronal CT.
96|confirmed|GNN predicts enterprise bankruptcy, no financial performance promise.
97|confirmed|Anti-jamming communication lacks named control action; transfer and Q-learning retained.
98|confirmed|Gated contextual Transformer generates multimodal retinal descriptions.
99|confirmed|DL detects botnet attacks.
100|confirmed|DL and word embeddings classify Arabic healthcare questions.
101|confirmed|ML detects seizures; event-driven processing may be preprocessing.
102|confirmed|CBNA-RF and ML detect/defend MitM; SDN context retained.
103|confirmed|DL identifies missing is-a relations; SNOMED CT ontology not dataset.
104|confirmed|ML selects sequence-level MRI protocols.
105|confirmed|Corrigendum preserved; drug demystification operation unclear.
106|confirmed|Soccer outcome prediction literal; machine and deep share learning head, preserve group.
107|revised|Semantic similarity can assist screening as score, rather than execute whole screening workflow.
108|confirmed|ZiMM/DL model relapses without literal prediction operation.
109|confirmed|HeTOP terminology server and antibody organization resource not named learning methods.
110|confirmed|Full GNN-based prediction task overlaps embedded method; LLM may provide embeddings.
111|confirmed|Bootstrap ARDL and ML stated; economic nexus not computational task.
112|confirmed|Full salp-foraging ant optimizer segments multithreshold remote images.
113|confirmed|NER/linking tasks literal; MER shell server software not automatically model.
114|confirmed|ML performs virtual drug screening, not broad discovery alone.
115|confirmed|Innovative drug discovery lacks explicit search/generation/prediction.
116|confirmed|Mean-field spiking NN with inhibitory synapses full architecture; no task.
117|confirmed|Gradient-based DNN simulates porous multiphase flow.
118|confirmed|Institution viability understanding lacks concrete computation.
119|confirmed|Full encoder/CNN feature-concatenation technique identifies leaf disease.
120|confirmed|Markovian NN synchronization target overlaps model.
121|confirmed|NN maps roads with LiDAR evidence; sensor not benchmark.
122|confirmed|CNN full name and acronym diagnose medical-image breast cancer.
123|confirmed|Federated ML predicts coronary calcification scores.
124|confirmed|Dynamic-model/controller task boundary and generic-model identity uncertain.
125|confirmed|Hybrid DL recognizes patient activity; PAR task acronym retained.
126|confirmed|ANN forecasts apparel sales.
127|confirmed|DL detects intrusion; blockchain/encryption may provide security rather than detect.
128|confirmed|Synthetical reasoning/multitask-model identities uncertain; tabular-textual QA retained.
129|confirmed|Fourier NN inpaints large regions; structural analysis may only supply representation.
130|confirmed|Full response-enrichment task includes ChatGPT target; flat overlap prevents complete inventory.
131|confirmed|Static/contextual/character share Embeddings head, preserve group without invented members.
132|confirmed|RL plans visual inspection acquisitions in remanufacturing.
133|confirmed|Production-controller design versus actual production control boundary unclear.
134|confirmed|Label synchronization explicit; FL may be synchronized target rather than synchronizer.
135|confirmed|Falling Prediction literal; biped context separated by method cannot be reconstructed into span.
136|confirmed|Karyon summarizes ontologies; ontology not dataset.
137|confirmed|Multimodal ML prognoses Alzheimer disease; title not clinical efficacy.
138|confirmed|ATM/adaptive Transformer reconstructs irregular multitemporal remote images.
139|confirmed|BDNet/densely connected CNN recognize Bengali handwritten digits.
140|confirmed|1D-CapsNet-LSTM and DL forecast multistep stock index.
141|confirmed|Mining evidence sentences and document-level RE are task operations; method unnamed.
142|confirmed|Ultrasonic diagnostic operation boundary unclear; no clinical efficacy claim.
143|confirmed|Network automation lacks specific action; retain uncertainty.
144|confirmed|No in-scope entity found after title inspection; empty not unannotated.
145|confirmed|ML candidate retained; concrete task not certified.
146|confirmed|Yolo-tla and YOLOv5 detect small objects.
147|confirmed|NN family stated with no downstream task.
148|confirmed|Title checked, no in-scope entity.
149|confirmed|SVM classifies text; supervised term weights may only prepare representation.
150|revised|Restore low-dimensional qualifier to full gated hierarchical hyperbolic embedding boundary.
151|confirmed|Probabilistic ontology may be representation, MLN recognizes activity.
152|confirmed|DMAdam/dual averaging optimizer and DNN stated, no independent task.
153|confirmed|TEQA explicitly answers questions with temporal graph context.
154|confirmed|Hybrid DL recognizes speech emotion; selection/metaheuristic may only train or prepare input.
155|confirmed|Temporal inductive path NN detects attacks; separated cloud context not reconstructed.
156|confirmed|Monocular-GPS fusion operation versus named technique boundary uncertain.
157|confirmed|Semantic QA concrete; methodology unnamed.
158|confirmed|NN family stated without separate task.
159|revised|Semantic guidance may be detector component, so unresolved pair must agree with stated uncertainty.
160|revised|Spectrum-feature model may only supply detector representation, not execute tiny-object detection.
161|confirmed|Uzbek news corpus lacks release identity; do not certify DATASET.
162|confirmed|Quantum evolution role and full model boundary unresolved; preserve candidates.
163|confirmed|I2U-Net and full dual-path U-Net segment medical images.
164|confirmed|Transformer NLP predicts emergency severity; data integration role not certified.
165|confirmed|Ontology generation is task; no named method.
166|confirmed|Decision tree and ML family, no task inferred.
167|confirmed|DL family without specified downstream operation.
168|confirmed|Gait analysis lacks explicit computation; CV broad context.
169|confirmed|No in-scope entity after title inspection.
170|confirmed|CNN performs process tomography of structured optical gates.
171|confirmed|Vision Transformer classifies SEM nanomaterial images.
172|confirmed|Correlator Transformer is architecture; theoretical property not task.
173|confirmed|Half-quadratic splitting and CNN explicitly deblur images.
174|confirmed|Anomaly detection lacks object; retain GNN association but isolate inventory.
175|confirmed|CV monitors and detects warpage; no benchmark named.
176|confirmed|Retraction preserved as notice; unspecified task remains isolated.
177|confirmed|Evolutionary CNN diagnoses lung nodules, not proof of clinical accuracy.
178|confirmed|CV recognizes COVID X-rays; transfer may only train recognizer.
179|confirmed|EACT-Det and full criss-cross Transformer architecture detect similar diseases.
180|confirmed|Full iterative-transfer NN explicitly clusters/classifies single-cell types.
181|confirmed|One neuron and DL predict aftershocks; title claim not efficacy proof.
182|confirmed|Hybrid NN classifies breast-cancer data; TOPSIS may select rather than classify.
183|confirmed|LDA and ANN geographically classify mineral waters; Spain context not dataset.
184|confirmed|CNN detects radar targets.
185|confirmed|ML tracks patient vital signs; no clinical validation inferred.
186|confirmed|DRL deploys multi-domain services; ecosystem context retained.
187|confirmed|NN method candidate retained, operation unclear.
188|confirmed|ML detects cardiac arrhythmias, title not clinical evidence.
189|confirmed|Levenberg-Marquardt NN estimates specified PSS parameters.
190|confirmed|FCM-guided DL damps power-network oscillation.
191|confirmed|Cubic-logistic GCM network candidate; concrete operational target unspecified.
192|confirmed|Kullback-Leibler constraint integrates information; classifier execution uncertain.
193|confirmed|MSL-MNN and lightweight multi-scale memristive NN remove image rain.
194|confirmed|Generative-AI digital twin composite; concrete operation unspecified.
195|confirmed|Wind-farm cable routing explicit, algorithm unnamed.
196|confirmed|Shallow NN with rectified-power activation; property not task.
197|confirmed|Hierarchical NN architecture, no task supplied.
198|confirmed|Semi-dilated CNN predicts epileptic seizures.
199|confirmed|Front-door criterion role versus detector unclear.
200|confirmed|LLM detects perioperative complications; LoRA trains, full inventory remains uncertain.
201|confirmed|ML predicts post-emergency healthcare contacts.
202|confirmed|Full delayed reaction-diffusion Cohen-Grossberg architecture, theoretical property not task.
203|confirmed|Adaptive CNN recognizes faces.
204|confirmed|LLM and CNN-LSTM optimize portfolios; no financial performance promise.
205|confirmed|LLM candidate with uncertain concrete operational target.
206|confirmed|DRL selects network traffic features; not automatically intrusion detector.
207|confirmed|CNN detects intrusion.
208|confirmed|DL/EfficientNet classify brain tumors; quantum genetic role uncertain.
209|confirmed|Spanish emotion analysis operation insufficiently specified; transformers candidate retained.
210|confirmed|RL maximizes backscatter communication throughput.
211|confirmed|DL predicts heart disease, no clinical accuracy asserted.
212|confirmed|MVST and multi-view GCN identify spatial transcriptome domains.
213|confirmed|Blockchain and DL stated but full operation uncertain.
214|confirmed|CNN family candidate without certified task inventory.
215|confirmed|Fuzzy transfer explicitly supplies VM resource allocation strategy.
216|confirmed|Graph representation learning classifies road types.
217|confirmed|Full constrained-triplet kernel Transformer fuses features; intermediate target literal.
218|confirmed|Pattern recognition/CV broad techniques; specific task unclear.
219|confirmed|CMIGNet and full inverse-guidance network detect RGB-depth salient objects.
220|confirmed|Sparse skeleton may be representation rather than technique; retain uncertain inventory.
221|confirmed|DiffSLT and diffusion model translate signs.
222|confirmed|Capsule network with k-means routing classifies text.
223|confirmed|KG optimization allocates workshop resources.
224|confirmed|YOLOv7 detects crop weeds.
225|confirmed|Target-aware vision Transformer recognizes polarimetric HRRP targets.
226|confirmed|ML classifies endangered tropical-forest tree species.
227|confirmed|ML method retained, no concrete task certified.
228|confirmed|DRL resource allocation literal; application framing not extra task.
229|confirmed|Progressive DL and AdaBoost predict landslide displacement rates.
230|confirmed|Full multi-scale-fusion CNN classifies remote sensing images.
231|confirmed|Enhancement branch/context module may be intermediate detector components.
232|confirmed|P2FEViT and full CNN-embedded hybrid Transformer classify remote images.
233|confirmed|ANN reconstructs microwave satellite soil moisture over named plateau.
234|confirmed|DL segments plant point clouds at organ level.
235|confirmed|Corrected literal Mapping of retained; compiler correction is separately recorded failure, not self-review revision.
236|confirmed|Multi-scale multi-attention Siamese Transformer detects image changes.
237|confirmed|DSSM and spectrum-separable DNN segment multi-spectral images.
238|confirmed|3D direction-encoded Bayesian NN predicts urban blast loading.
239|confirmed|Access management lacks specific control operation; preserve uncertainty.
240|confirmed|BERT and GCN explicitly recommend citations.
241|confirmed|Waste-reduction optimization lacks particular computation; do not infer controller.
242|confirmed|DL candidate retained, inventory unresolved.
243|confirmed|DL recognizes pedestrians and animals.
244|confirmed|Imagined-speech EEG decoding literal, method boundary uncertain.
245|confirmed|Transfer may train skin-cancer recognizer rather than detect/classify.
246|confirmed|Detection/comparison techniques mix method and task roles; isolate inventory.
247|confirmed|CO2-based ML estimates occupancy; CO2 input not dataset.
248|confirmed|DL assesses upper-limb function; title not clinical validation.
249|confirmed|ML recognizes grasp postures; downstream hand control role uncertain.
250|confirmed|DL classifies underexposed blackberries; image fusion may be preprocessing.
251|confirmed|Vision Transformer detects plant disease.
252|confirmed|DL recognizes Arabic air writing; language/modality retained.
253|confirmed|3D DL diagnoses pulmonary nodules, no clinical efficacy inferred.
254|confirmed|ML classifies oil ripeness; chemical profiling may acquire inputs.
255|confirmed|GrAb and DL detect energy theft.
256|confirmed|RNN predicts hand gestures from sEMG.
257|confirmed|DL recognizes orchard apples.
258|confirmed|Multiscale nonlinear diffusion denoises images.
259|confirmed|Privacy-preserving graph ML composite, broad data/computation framing not task.
260|confirmed|DL assesses Wikipedia article quality; named people not in-scope entities.
261|confirmed|Quantization target overlaps neural networks; corrigendum not new validation.
262|confirmed|Steel Ms Temperature quantity given without literal prediction operation.
263|confirmed|Word embedding and CNN/Bi-GRU fusion classify text; Fusion joins one composite not shared-head group.
264|confirmed|CNN super-resolves hyperspectral images; decomposition may preprocess.
265|confirmed|Heuristic-optimized CNN classifies brain tumors, no clinical validation.
266|confirmed|Gogglesdet/clustering Transformer detect goggles; a new dataset is unnamed.
267|confirmed|Self-attention Transformer assesses image quality; no-reference setting excluded.
268|confirmed|Fusion of ML models predicts stroke risk, not clinical efficacy.
269|confirmed|Effective-data selection/correlation operation unspecified; heart-failure detection association alone incomplete.
270|confirmed|DL segments medical lesions; multiple sclerosis context not benchmark.
271|confirmed|ML survey covers COVID detection/diagnosis/prediction, not new clinical experiment.
272|confirmed|ANN models seed-oil extraction; central composite design may plan experiments.
273|confirmed|ML predicts stock trends; sentiment/politics input context.
274|confirmed|Secondary-path-decoupled noise-control algorithm composite; DL family, no separate nonoverlapping task.
275|revised|Entropy may select thresholds rather than execute whole SAR segmentation; pair must remain unresolved.
276|confirmed|DL recognizes radar human motion; radar context separated in title.
277|confirmed|SAR-guided conditional diffusion removes clouds; style adaptation may train model.
278|confirmed|Fuzzy similarity may select samples; full ML improvement task overlaps method.
279|confirmed|Small-ship detection explicit; satellite data generic.
280|confirmed|PSO-driven LLM designs prompts; later medical extraction executor uncertain.
281|revised|Remove dangling Driven connector while retaining symmetry-informed multimodal LLM method qualifiers.
282|confirmed|Symmetric multiscale convolutional Transformer classifies plant-disease images.
283|confirmed|DL detects object-based video forgery.
284|confirmed|Pruning task overlaps neural network target; FL does not establish pruner.
285|confirmed|TSTNet/semantic Transformer named; computing-power-network versus driving action inventory unclear.
286|confirmed|Data mining/ML engineering-education enhancement broad goal, no specific task.
287|confirmed|Inverse RL planning association retained; driving execution not certain.
288|confirmed|AgentGraph and structured DRL manage dialogue.
289|confirmed|sEMG processing lacks precise operation; FPGA is hardware.
290|confirmed|Subtraction/segmentation may preprocess for unusual-event detection.
291|confirmed|Training-improvement task overlaps memristive network; voltage smoothing candidate uncertain.
292|confirmed|Transformer feedback in CMOS LNA is physical circuitry, no neural model.
293|confirmed|Obfuscation and ML attacks techniques; no independent concrete attack task.
294|confirmed|Incentive mechanism versus learning role unclear; full incentive operation not certified.
295|confirmed|FL convergence-analysis target overlaps model, no independent analyzer named.
296|confirmed|Split FL technique; constrained edge network setting not task.
297|confirmed|DL side-channel analysis literal security task at title level.
298|confirmed|Model-driven DRL beamforms RIS multi-user transmission.
299|confirmed|DL detects duplicate rulemaking comments; unsupervised setting excluded.
300|confirmed|DL enhances perceptual video quality for synthesized 3D views.
301|confirmed|Generative and discriminative share fuzzy RBM learning head; preserve coordinated group.
302|confirmed|Dirichlet mixture of robust task models/lifelong RL are techniques; no downstream operation.
303|confirmed|DL maps road-safety features from street-view imagery.
304|confirmed|Generative-AI adoption is organizational behavior, not computational task.
305|confirmed|Embedded object detection explicit; unnamed hardware accelerator not METHOD.
306|confirmed|Second Order Newton-Type identifies optimization technique; generic Method excluded.
307|confirmed|Multiagent RL plans traffic signals; congestion resistance is goal.
308|confirmed|GNN predicts socioeconomic status; mobility/relationships inputs not datasets.
309|confirmed|EVKG is knowledge resource, not named model or evaluation dataset.
310|confirmed|Electromagnetic processing lacks specified action; expert-system identity ambiguous.
311|confirmed|Remote-image interpretation lacks concrete computation; full foundation-model composite retained.
312|confirmed|Multimodal representation learning and masked-image modeling techniques, no separate downstream task.
313|confirmed|CNN-Transformer estimates building heights; sample augmentation may only train estimator.
314|confirmed|Progressive interleaved-fusion network detects remote salient objects.
315|confirmed|BRSTD detects remote tiny objects.
316|confirmed|Trajectory representation may be data rather than method; isolate inventory.
317|confirmed|Alignment may train representation rather than detect objects.
318|confirmed|LSCF/full semantic-guidance ConvFormer performs referring segmentation.
319|confirmed|Distillation and foundation teacher may train detector; no direct execution inferred.
320|confirmed|DL retrieves air-sea heat flux; AMSR2 is instrument, not dataset.
321|confirmed|UnmixDiff/full unmixing diffusion synthesizes hyperspectral images.
322|confirmed|SwinSUNet and Transformer detect remote-image changes.
323|confirmed|SCENE-YOLO is named detector; scene supervision training context.
324|confirmed|Attention balancing method/task boundary unclear; preserve object detection candidate.
325|confirmed|HO2RL/full offline-online RL controls pantograph.
326|confirmed|ML generates secret keys for IRS multi-antenna systems.
327|confirmed|DL detects malware; sensitivity is quality constraint.
328|confirmed|Memrisitive typo preserved; Rulkov network dynamics not downstream task.
329|confirmed|Energy-efficient edge computing lacks specific allocation/offloading action.
330|confirmed|Cost-sensitive multitask ML detects IoT intrusion.
331|confirmed|Uncertainty-guided Transformer ensemble predicts crossing intentions.
332|confirmed|Foundation model estimates pose; template update may prepare references.
333|confirmed|NN identifies arc faults; sparse representation may only prepare features.
334|confirmed|DL detects turbine gearbox failure; SCADA data generic.
335|confirmed|CNN extracts sweat glands from OCT.
336|confirmed|E-TRGAN/full Transformer GAN reconstructs dense surface EMG.
337|confirmed|Confidence alignment refines labels, not necessarily detects objects.
338|confirmed|Knowledge inheritance mechanism/executor unclear; object detection retained.
339|confirmed|Multitask CNN recognizes faces across poses.
340|confirmed|Coordinated RL optimizes road network.
341|confirmed|WSI analysis and detached segmentation targets lack certified full inventory.
342|confirmed|WavFace/multimodal Transformer screen depression; no clinical validity claim.
343|confirmed|HepNet/DNN classify hepatic steatosis; microwave inputs not benchmark.
344|confirmed|Knowledge-aided CNN segments small organs.
345|confirmed|Full attention spatiotemporal hybrid NN predicts traffic flow.
346|revised|Deep qualifies method not target; retain multimodal detection/segmentation driving task boundary.
347|confirmed|DRL charging planning literal; effective is claim.
348|confirmed|Segmentation-enhanced asynchronous FL technique; transportation not specific task.
349|confirmed|SUSTechGAN generates images; augmentation does not automatically execute detection.
350|confirmed|Privacy-preserving data operation unspecified; candidate inventory unresolved.
351|revised|Delete dangling intelligent agent-based adjective; keep named IAFCO method and optimization task, remap edge IDs.
352|confirmed|chatHPC software and empowering users do not specify QA/programming operation.
353|confirmed|Full sequential hierarchical FL retained; non-IID datasets generic.
354|confirmed|DeepMesh and DL track cardiac motion.
355|confirmed|Active learning selects labels; uncertainty target and segmenter role unresolved.
356|confirmed|FPL+ association retained; cross-modality adaptation may only train segmenter.
357|confirmed|Hallucination similarity is behavior/property, no specific correction task.
358|confirmed|Over-generalization mitigation overlaps RL target; independent mitigation method unnamed.
359|confirmed|DL emulates numerical models; generic models are target not METHOD.
360|confirmed|Editorial inspection/maintenance lacks explicit computation.
361|confirmed|Memristor NN stability is theoretical property.
362|confirmed|CACNN/full capsule-attention CNN recognizes 3D objects.
363|confirmed|Foundation models segment medical images, retrieval/few-shot contextual.
364|confirmed|NN classifies nodules; information bottleneck may only regularize.
365|confirmed|AutoSilicon/LLM generate RTL; full capability scaling overlaps model target.
366|confirmed|RNN and residual learning enhance compressed vibrotactile signals.
367|confirmed|Ontology-aware prescription recommendation is literal task; algorithm unnamed, no treatment advice.
368|confirmed|Recurrent weights may be parameters; full pruning target overlaps network.
369|confirmed|CM-GAN/full cross-modal GAN learn common representation as explicit target.
370|revised|Contrastive representation learning may train re-identification features rather than execute full re-ID.
371|confirmed|Adversarial attack opposes modulation recognition; CNN performs it, retain explicit negative role.
372|confirmed|OpaqueAttack attacks DL target; full attack task overlaps target.
373|confirmed|AAD pooling accelerator is hardware; CNN target not hardware designer.
374|confirmed|SIMD-like utilization enhancement targets sparse CNN hardware, not independent learning task.
375|confirmed|RL jointly controls network traffic signals.
376|confirmed|GNN beamforms holographic millimeter-wave MIMO.
377|confirmed|RL tracks driving paths.
378|confirmed|FL may be offloaded workload; full FL design task overlaps target model.
379|confirmed|FL resource allocation explicit; delay sensitivity contextual.
380|confirmed|Kinecting cognition slogan lacks concrete behavior operation.
381|confirmed|DRL plans UAV paths retaining dynamics and acceleration control.
382|confirmed|Mamba-Transformer multi-agent RL coordination lacks application action/object.
383|confirmed|Residual GCN recognizes gait.
384|confirmed|StairNetV3 and DL model stairs; no depth benchmark named.
385|confirmed|FANN/frame-attention NN recognize facial-video student engagement.
386|confirmed|Unet segmentation/binarization may preprocess for water-level detector; mixed inventory isolated.
387|confirmed|DriveMLM driving association retained; aligned LLM full execution uncertain.
388|confirmed|Full beta-filter CNN recognizes Arabic letters.
389|confirmed|Service-wise wireless optimization lacks specific variable/action.
390|confirmed|NLP research names no specific task.
391|confirmed|Neighboring-relation target qualifier and meta-training role unresolved."""


def review():
    run = ROOT / 'kg_datasets/dblp/course_v4_runs/pending_train_20261007_24'
    source = run / 'generation_decisions.json'
    digest = 'e64386195ffb938a35f22a6096fda294c697a7adfbb24fedd6fcb69525d87471'
    assert c.file_sha256(source)==digest
    first = json.loads(source.read_text(encoding='utf-8'))['decisions']
    judgments = [(int(i),v,r) for i,v,r in (line.split('|',2) for line in JUDGMENTS.splitlines())]
    assert len(first)==392 and [i for i,_,_ in judgments]==list(range(392))
    revisions = {i:copy.deepcopy(first[i]) for i,v,_ in judgments if v=='revised'}
    for i in (39,107,159,160,275,370):
        revisions[i]['relations'][0].update(label='UNRESOLVED',reason='Training, scoring or intermediate representation may support rather than directly execute complete target.')
        revisions[i].update(relationStatus='unresolved',relationReason='Intermediate/training component versus complete executor role unspecified.')
    revisions[59].update(entityStatus='unresolved',entityReason='Unexpanded UTAUT model identity as computational algorithm versus conceptual adoption model uncertain.',
        relationStatus='unresolved',relationReason='Cannot certify computational instrument inventory from unexpanded model name.',
        notes='Teacher willingness is adoption context, not automated computation; UTAUT remains uncertain candidate.')
    revisions[66].update(entityStatus='unresolved',entityReason='Interpretable Network lacks a specified neural architecture or technique identity.',
        relationStatus='unresolved',relationReason='Unspecified network identity prevents complete instrument inventory.')
    revisions[66]['relations'][1].update(label='UNRESOLVED',reason='Generic interpretable network candidate does not identify full computational executor.')
    revisions[91]['entities'][0]['text'] = 'Dynamic Charging'
    revisions[91].update(entityStatus='unresolved',entityReason='Charging scheme problem does not specify allocation, scheduling or other computational operation.',
        relationStatus='unresolved',relationReason='Actor-critic charging association does not establish specific computation.',notes='Do not invent scheduling from Scheme Problem.')
    revisions[91]['relations'][0].update(label='UNRESOLVED',reason='Charging scheme problem leaves concrete computational action unspecified.')
    revisions[150]['entities'][1]['text'] = 'low-dimensional gated hierarchical hyperbolic embedding'
    revisions[150]['notes'] = 'Low-dimensional qualifier belongs in full method span, not notes alone.'
    revisions[281]['entities'][0]['text'] = 'Symmetry-Informed Multimodal LLM'
    revisions[281]['notes'] = 'Driven is linking modifier; full symmetry-informed multimodal LLM qualifiers retained.'
    revisions[346]['entities'][0]['text'] = 'Multi-Modal Object Detection and Semantic Segmentation for Autonomous Driving'
    revisions[351].update(entities=[first[351]['entities'][0],first[351]['entities'][2]],
        relations=[{'head':'e1','tail':'e2','label':'USED_FOR','reason':'Named IAFCO framework explicitly concerns combinatorial optimization in quoted correction title.'}],
        notes='Correction notice not new validation; dangling generic agent-based adjective removed, named method retained.')
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
    parent = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_16'
    target = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_17'
    summary = assemble(dataset,[parent / 'receipts.jsonl',run / 'review/receipts.jsonl'],target)
    assert c.read_jsonl(target / 'receipts.jsonl')==c.read_jsonl(parent / 'receipts.jsonl')+c.read_jsonl(run / 'review/receipts.jsonl')
    assert all((parent / n).read_bytes()==(target / n).read_bytes() for n in
        ('ner_inputs_dev.jsonl','ner_inputs_test.jsonl','relation_inputs_dev.jsonl','relation_inputs_test.jsonl'))
    c.write_json(run / 'manifest.json',{'kind':'new_training_labels_same_session_candidate_aware_AI_self_review',
        'parentSnapshotManifestSha256':c.file_sha256(parent / 'manifest.json'),'newSnapshotManifestSha256':c.file_sha256(target / 'manifest.json'),
        'documents':392,'confirmed':379,'revised':13,'humanGold':False,'independentReviewer':False,'trainingStarted':False,
        'finalTestInferenceRepeated':False,'oldReceiptsUnchanged':True,'devTestInputsByteIdentical':True,
        'filesSha256':{p.relative_to(run).as_posix():c.file_sha256(p) for p in run.rglob('*') if p.is_file()}})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    review()

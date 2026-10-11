# AI Literature KG v2：20篇盲标式边界复核

**性质**：这是AI评审者基于 `blind_50_reference.jsonl` 做的独立语义试标，用来压力测试边界规则；不是人类金标准，不得把 reviewer/source 改写成 `human_reviewed`。

试标20篇，共提出 **46** 个实体跨度：METHOD 24、TASK 21、DATASET 1。当前词典草稿在同20篇中有 21 个跨度；严格 start/end/label 完全一致的只有 10 个。这个差异不是模型F1，而是规则/词典覆盖诊断。

## 结论

当前 v2 **不建议冻结**。DOMAIN 从 NER 移出、gold 状态拆分、reference 锁定这些修订是正确的；但实体边界仍至少有三类会导致系统性标注者分歧：复合 METHOD、共享中心词并列结构、TASK 修饰语/技术操作范围。

## 20篇结果

|#|标题|独立试标|当前草稿|规则判断|
|---:|---|---|---|---|
|1|FuseLinker: Leveraging LLM's pre-trained text embeddings and domain knowledge to enhance GNN-based link prediction on biomedical knowledge graphs.|METHOD: `FuseLinker`<br>METHOD: `LLM`<br>METHOD: `GNN`<br>TASK: `link prediction`|METHOD: `LLM`<br>TASK: `link prediction`|命名模型+缩写方法+任务均可从标题确定。未标 text embeddings：当前规则尚未明确“表示/特征”是否一律算 METHOD。|
|2|Metric learning-based kernel transformer with triplets and label constraints for feature fusion.|METHOD: `Metric learning-based kernel transformer`<br>TASK: `feature fusion`|METHOD: `transformer`|复合方法应在平面BIO下取最大技术短语；feature fusion 是否属于 TASK 需在规范中明确“技术操作型任务”范围。|
|3|Multi-lingual Geoparsing based on Machine Translation.|TASK: `Multi-lingual Geoparsing`<br>TASK: `Machine Translation`|TASK: `Multi-lingual Geoparsing`<br>TASK: `Machine Translation`|Machine Translation 虽在句中充当 enabling technique，但概念类型仍是 TASK；应明确“实体类型≠句法角色”。|
|4|ACLNet: A Deep Learning Model for ACL Rupture Classification Combined with Bone Morphology.|METHOD: `ACLNet`<br>METHOD: `Deep Learning`<br>TASK: `ACL Rupture Classification`|METHOD: `Deep Learning`|ACLNet 由冒号后的 A Deep Learning Model 直接确认是命名模型；Deep Learning 保留为独立出现的方法族。|
|5|WearVQA: A Visual Question Answering Benchmark for Wearables in Egocentric Authentic Real-world scenarios.|DATASET: `WearVQA`<br>TASK: `Visual Question Answering`|TASK: `Visual Question Answering`|WearVQA 后接 Benchmark，足以在标题级判为 DATASET/benchmark；Visual Question Answering 为 TASK。|
|6|Automatic prompt design via particle swarm optimization driven LLM for efficient medical information extraction.|TASK: `prompt design`<br>METHOD: `particle swarm optimization`<br>METHOD: `LLM`<br>TASK: `medical information extraction`|METHOD: `LLM`|particle swarm optimization 和 LLM 明确；medical information extraction 明确。prompt design 是否纳入 TASK 是当前任务本体边界问题。|
|7|StyleDiffusion: Controllable Disentangled Style Transfer via Diffusion Models.|METHOD: `StyleDiffusion`<br>TASK: `Style Transfer`<br>METHOD: `Diffusion Models`|METHOD: `Diffusion Models`|StyleDiffusion 是命名方法，Diffusion Models 是独立方法族，Style Transfer 是基础任务；Controllable/Disentangled 作为目标/性质修饰暂不并入 TASK。|
|9|LXMERT: Learning Cross-Modality Encoder Representations from Transformers.|METHOD: `LXMERT`<br>METHOD: `Transformers`|METHOD: `Transformers`|LXMERT 是命名模型；Transformers 为独立出现的方法族。|
|13|Assessing the Impact of Static, Contextual and Character Embeddings for Arabic Machine Translation.|METHOD: `Static, Contextual and Character Embeddings`<br>TASK: `Arabic Machine Translation`|TASK: `Machine Translation`|共享中心词并列结构无法用平面BIO拆成 Static / Contextual / Character 三个独立 Embeddings；本次暂以整个协调短语作为一个 METHOD group mention。|
|15|Unified architecture and design methodology for integrated SDM-WSS employing PLC-based spatial beam transformer array for various types of SDM fibers.|NONE|METHOD: `transformer`|这里的 transformer 是光通信/空间光束变换器件，不是算法或AI模型；应明确排除物理器件同形词。|
|16|A Robust Green Grape Image Segmentation Algorithm Against Varying Illumination Conditions.|TASK: `Green Grape Image Segmentation`|TASK: `Image Segmentation`|Green Grape 是分割对象，改变任务语义，应纳入 TASK；Robust 是评价性修饰，Algorithm 是泛化载体词，均不纳入。|
|18|Multi-Agent Pattern Formation: a Distributed Model-Free Deep Reinforcement Learning Approach.|TASK: `Multi-Agent Pattern Formation`<br>METHOD: `Distributed Model-Free Deep Reinforcement Learning`|METHOD: `Deep Reinforcement Learning`|Distributed、Model-Free、Deep 都是区分方法的技术限定词，平面BIO应整体标；Approach 为泛化载体词不标。|
|20|Reducing the search space in ontology alignment using clustering techniques and topic identification.|TASK: `ontology alignment`<br>METHOD: `clustering`<br>TASK: `topic identification`|NONE|ontology alignment 是具体任务，不能因为含 ontology 一概排除；clustering 是方法；topic identification 是否作为 TASK 应明确技术子任务范围。|
|21|Image Denoising via Multiscale Nonlinear Diffusion Models.|TASK: `Image Denoising`<br>METHOD: `Multiscale Nonlinear Diffusion Models`|METHOD: `Diffusion Models`|Multiscale/Nonlinear 都区分具体 diffusion 方法，应整体保留；但后续实体链接必须区分 PDE diffusion 与生成式 diffusion。|
|22|Multivariate Time-Series Forecasting with Temporal Polynomial Graph Neural Networks.|TASK: `Multivariate Time-Series Forecasting`<br>METHOD: `Temporal Polynomial Graph Neural Networks`|METHOD: `Graph Neural Networks`|Temporal Polynomial 是架构/模型限定词，应随 Graph Neural Networks 一起标；任务应保留 Multivariate Time-Series。|
|24|Safe and Interpretable Human-Like Planning With Transformer-Based Deep Inverse Reinforcement Learning for Autonomous Driving.|TASK: `Planning`<br>METHOD: `Transformer-Based Deep Inverse Reinforcement Learning`|METHOD: `Transformer`<br>METHOD: `Reinforcement Learning`|复合方法存在嵌套：Transformer-Based + Deep Inverse Reinforcement Learning。为适配平面BIO，本次整体标一个 METHOD；Planning 的 Human-Like 修饰是否保留仍需规则裁决。|
|25|Pose-GNN : Camera Pose Estimation System Using Graph Neural Networks.|METHOD: `Pose-GNN`<br>TASK: `Camera Pose Estimation`<br>METHOD: `Graph Neural Networks`|METHOD: `Graph Neural Networks`|Pose-GNN 是命名系统/模型，Graph Neural Networks 是独立出现的方法族；Camera Pose Estimation 为任务。|
|29|Food Image Recognition by Using Bag of SURF: Color Features.|TASK: `Food Image Recognition`<br>METHOD: `Bag of SURF`|TASK: `Image Recognition`|Food 是任务对象，应纳入 TASK；Bag of SURF 是明确方法。Color Features 是否为 METHOD/representation 当前规则不清，暂不标。|
|31|Multimodal Learning for Web Information Extraction.|METHOD: `Multimodal Learning`<br>TASK: `Web Information Extraction`|NONE|Multimodal Learning 是方法范式；Web Information Extraction 是具体任务。词典零命中不能判无实体。|
|41|MFE-NER: Multi-feature Fusion Embedding for Chinese Named Entity Recognition.|METHOD: `MFE-NER`<br>METHOD: `Multi-feature Fusion Embedding`<br>TASK: `Chinese Named Entity Recognition`|TASK: `Named Entity Recognition`|MFE-NER 是命名方法；Multi-feature Fusion Embedding 是方法描述；Chinese 是任务语言范围，应纳入 TASK。|

## 建议在 v2-candidate 冻结前加入的边界规则

1. **METHOD 采用最大连续技术短语（maximal technical NP）**：保留能改变方法身份/结构/训练范式的技术限定词，如 `Temporal Polynomial Graph Neural Networks`、`Distributed Model-Free Deep Reinforcement Learning`；排除 `novel/efficient/robust` 等评价词，以及非词汇化的 `approach/method/technique/algorithm` 载体词。平面BIO下，不再同时标其内部嵌套方法；父方法族在实体链接/本体层补。
2. **命名模型/框架规则**：标题自身能通过 `X: A ... model/system/...`、`X ... via Y`、`X ... using Y` 等语法确认 X 是技术对象时，X 标 METHOD；`X: ... Benchmark/Dataset` 则标 DATASET。仅凭大写、连字符或缩写形式不能判断。
3. **TASK 保留语义对象/语言/模态/场景限定，去掉评价/训练设定限定**：如 `Green Grape Image Segmentation`、`Arabic Machine Translation`、`Chinese Named Entity Recognition`；`robust/efficient/high-fidelity/few-shot` 默认不并入基础TASK。对于 `Human-Like`、`Low-Resource` 这类设置性修饰需在规范列白/黑名单或统一归入辅助属性。
4. **技术操作型问题是否属于 TASK 必须明确**：本试标把 `feature fusion`、`prompt design`、`topic identification` 作为候选TASK。若项目只要下游 benchmark task，则应明确排除；若目标是“某问题用什么方法”，则应纳入。不能靠标注者直觉。
5. **协调省略结构**：`Static, Contextual and Character Embeddings` 在平面BIO中无法无损拆成3个实体。若坚持BIO，规定“共享中心词的并列短语整体标为一个 group mention，后续实体链接拆分”；否则必须升级到 discontinuous/nested span schema。
6. **同形词按语义类型，不按词形命中**：物理 `spatial beam transformer array` 不标；算法/数学模型 `Multiscale Nonlinear Diffusion Models` 可以标，但实体链接时不得与生成式 Diffusion Model 自动合并。
7. **Ontology/KG 不是整体禁区**：`ontology alignment`、`knowledge graph completion`、`link prediction` 是具体 TASK；单独 `ontology` / `knowledge graph` 是对象/资源概念，不能自动标TASK。
8. **表示与特征类术语需单独定界**：`embeddings`、`Color Features`、`text embeddings` 当前会造成分歧。建议只有“明确命名/标准化表示方法或论文核心技术对象”才标 METHOD；泛称 `features/embeddings/representations` 默认不标。

## 冻结建议

先把上述8条写回 guidelines，并用这20篇做回归样例；随后再让一名真实标注者在不看本答案的情况下盲标同20篇。若 strict span+label 分歧仍集中在 2/13/20/24/29/41 这类边界样本，就继续修规则；若大部分分歧只剩个别语义判断，再进入完整200篇。
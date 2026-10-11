# 第59轮：第49轮 supplementary-dev 逐对关系源文审阅建议

这是只读源文审阅的建议清单，不是已执行标签修改、模型结果或独立金标准。旧文件、成绩、NER与原始收据未改。没有读取任何模型预测、错误或保留test正文；本阶段只完整读两篇固定摘要。

## 固定源选择与绑定

规则在完整阅读这两篇正文前已发给root：按第49轮原始顺序，选择NER完整、groupMentions为空、METHOD/DATASET兼有且已有EVALUATED_ON参考的前两篇。只利用已封存人工智能参考标签元数据，不利用任何预测。此规则是来源标签驱动的定向补充DEV审阅，非随机样本、非新的盲测；不会因无法补全而替换源文。

- 来源：kg_datasets/dblp/course_abstract_supplement_reviewed_20261009_49。
- 来源manifest SHA256：2fc9aeaefa200100de611e5940ee5fa3cf6bbcfcea520f3700542be11f8c82f7。
- 2003.10555，split=dev，sample-9fd869fc8bed9bdd4727，63 allowed pairs。
  - 原文SHA256：911ea266bee1c81302e0e0e71c44f852701caaa3349bc915ff589d0d587d9b77。
  - 上游receipt SHA256：73f6268d9a0705dd8bf312a62d1663bae27be4d7fa2aa6cb808e0315654cbd32。
- 2006.03654，split=dev，sample-fa2a676d1b0eea9d662e，156 allowed pairs。
  - 原文SHA256：6e51be908ca93534b364ac20ace62314008e7b4062020faa0f94c542e346ca3b。
  - 上游receipt SHA256：fc773befd57587735f7b0b37aeae40359992127963165cb5364163b025e7300c。

以下每行是一个现有allowed pair，不新增实体、不增加候选库存。引用ID对应后面的原文literal quote，理由ID对应源文推理。“UNRESOLVED”的上下文引用只解释为何暂不能判断，不应被写成事实evidence；真实未决收据的evidence仍为null。多个引用可在实际新判断中取涵盖它们和端点的原文连续跨度，不能把不连续拼接文字伪装成原文。

## 2003.10555 · ELECTRA摘要（标题名称不加入NER）

METHOD：e3 BERT、e6 generator network、e8 discriminative model、e11 BERT、e12 GPT、e15 RoBERTa、e16 XLNet。
TASK：e1 Masked language modeling、e2 MLM、e4 reconstruct the original tokens、e5 replaced token detection、e7 predicts the original identities of the corrupted tokens、e9 predicts whether each token in the corrupted input was replaced by a generator sample or not、e10 MLM、e14 natural language understanding。
DATASET：e13 GLUE。

### Literal quotes

E1:

> Masked language modeling (MLM) pre-training methods such as BERT corrupt the input by replacing some tokens with [MASK] and then train a model to reconstruct the original tokens.

E2:

> As an alternative, we propose a more sample-efficient pre-training task called replaced token detection. Instead of masking the input, our approach corrupts it by replacing some tokens with plausible alternatives sampled from a small generator network.

E3:

> Then, instead of training a model that predicts the original identities of the corrupted tokens, we train a discriminative model that predicts whether each token in the corrupted input was replaced by a generator sample or not.

E4:

> Masked language modeling (MLM) pre-training methods such as BERT corrupt the input by replacing some tokens with [MASK] and then train a model to reconstruct the original tokens. While they produce good results when transferred to downstream NLP tasks, they generally require large amounts of compute to be effective. As an alternative, we propose a more sample-efficient pre-training task called replaced token detection. Instead of masking the input, our approach corrupts it by replacing some tokens with plausible alternatives sampled from a small generator network. Then, instead of training a model that predicts the original identities of the corrupted tokens, we train a discriminative model that predicts whether each token in the corrupted input was replaced by a generator sample or not.

E5:

> The gains are particularly strong for small models; for example, we train a model on one GPU for 4 days that outperforms GPT (trained using 30x more compute) on the GLUE natural language understanding benchmark.

E6:

> Our approach also works well at scale, where it performs comparably to RoBERTa and XLNet while using less than 1/4 of their compute and outperforms them when using the same amount of compute.

E7:

> Then, instead of training a model that predicts the original identities of the corrupted tokens, we train a discriminative model that predicts whether each token in the corrupted input was replaced by a generator sample or not. Thorough experiments demonstrate this new pre-training task is more efficient than MLM because the task is defined over all input tokens rather than just the small subset that was masked out. As a result, the contextual representations learned by our approach substantially outperform the ones learned by BERT given the same model size, data, and compute. The gains are particularly strong for small models; for example, we train a model on one GPU for 4 days that outperforms GPT (trained using 30x more compute) on the GLUE natural language understanding benchmark.

### Source reasoning

- ER1：原文明确BERT的MLM/原token重建目标；e7“预测原token身份”是后文与这一同一目标对照的表述，不是新方法实际目标。重复BERT/MLM是源文内相关提及。
- ER2：在本文局部目标分工中，BERT归属重建/MLM，替代方案的discriminative model归属replaced-token detection。明确“as an alternative / instead of”对照支持限定语境的NO_RELATION，不宣称BERT永远不能改造成检测器。
- ER3：generator提供plausible alternatives，替换判别由明确对照的discriminative model执行。e5与e9是该同一检测任务的名称/说明；此处负例限定为直接任务执行角色，不否认generator对整体方案的贡献。
- ER4：discriminative model直接预测token是否被替换，等价于声明的replaced-token detection。
- ER5：instead-of明确排除了原token身份/MLM重建目标在本文这一discriminative model上的任务归属；e1/e2/e4/e7/e10是原文内该重建目标的相关描述。不是从共现、缺测或类别填出负例。
- ER6：建议采用可复核的省略指代链：全文唯一明确新训练的模型是“we train a discriminative model”；随后“our approach”的contextual representations、“we train a model”小模型实例及GLUE NLU测量属于该新模型方案。保留完整链E7，不从标题补ELECTRA，不把generator继承为被测模型，不给这条边附加任何未出现的分数。此为AI来源判断，root仍需实际复核指代是否充分；若认为实例配置归属不唯一，应继续UNRESOLVED而非负例。
- ER7：GPT是GLUE natural language understanding比较句中明确的被测基线，同时该句明确其对应NLU任务；较低表现仍是正评测关系。
- EU1：原文只说明generator采样替代token，未说明其自身的MLM/原身份训练目标或GLUE/NLU独立角色。既不能把整体测量继承给generator，也不能由没测证明NO_RELATION。
- EU2：BERT的比较与downstream NLP泛述未明确绑定到此处GLUE/NLU实例；不能把GPT的具体GLUE句无条件赋给BERT。
- EU3：GPT的compute与GLUE比较未给其在本文的具体token级预训练任务；不从模型常识补目标。
- EU4：末句RoBERTa/XLNet的at-scale comparison没有明确限定到GLUE及哪项token/NLU任务，不沿前一小模型示例扩展整个比较范围。

### 全部63对

| head | tail | 建议label | literal quote | source reasoning | 相对旧标签 |
|---|---|---|---|---|---|
| e3 | e1 | USED_FOR | E1+E3 | ER1 | 保持 |
| e3 | e2 | USED_FOR | E1+E3 | ER1 | 保持 |
| e3 | e4 | USED_FOR | E1+E3 | ER1 | 保持 |
| e3 | e5 | NO_RELATION | E4 | ER2 | 新增候选（旧UNRESOLVED） |
| e3 | e7 | USED_FOR | E1+E3 | ER1 | 新增候选（旧UNRESOLVED） |
| e3 | e9 | NO_RELATION | E4 | ER2 | 新增候选（旧UNRESOLVED） |
| e3 | e10 | USED_FOR | E1+E3 | ER1 | 保持 |
| e3 | e13 | UNRESOLVED | E1+E5 | EU2 | 保持 |
| e3 | e14 | UNRESOLVED | E1+E5 | EU2 | 保持 |
| e6 | e1 | UNRESOLVED | E2+E3 | EU1 | 保持 |
| e6 | e2 | UNRESOLVED | E2+E3 | EU1 | 保持 |
| e6 | e4 | UNRESOLVED | E2+E3 | EU1 | 保持 |
| e6 | e5 | NO_RELATION | E2+E3 | ER3 | 新增候选（旧UNRESOLVED） |
| e6 | e7 | UNRESOLVED | E2+E3 | EU1 | 保持 |
| e6 | e9 | NO_RELATION | E2+E3 | ER3 | 保持 |
| e6 | e10 | UNRESOLVED | E2+E3 | EU1 | 保持 |
| e6 | e13 | UNRESOLVED | E2+E3 | EU1 | 保持 |
| e6 | e14 | UNRESOLVED | E2+E3 | EU1 | 保持 |
| e8 | e1 | NO_RELATION | E4 | ER5 | 新增候选（旧UNRESOLVED） |
| e8 | e2 | NO_RELATION | E4 | ER5 | 新增候选（旧UNRESOLVED） |
| e8 | e4 | NO_RELATION | E4 | ER5 | 新增候选（旧UNRESOLVED） |
| e8 | e5 | USED_FOR | E2+E3 | ER4 | 保持 |
| e8 | e7 | NO_RELATION | E4 | ER5 | 保持 |
| e8 | e9 | USED_FOR | E2+E3 | ER4 | 保持 |
| e8 | e10 | NO_RELATION | E4 | ER5 | 新增候选（旧UNRESOLVED） |
| e8 | e13 | EVALUATED_ON | E7 | ER6 | 新增候选（旧UNRESOLVED） |
| e8 | e14 | USED_FOR | E7 | ER6 | 新增候选（旧UNRESOLVED） |
| e11 | e1 | USED_FOR | E1+E3 | ER1 | 保持 |
| e11 | e2 | USED_FOR | E1+E3 | ER1 | 保持 |
| e11 | e4 | USED_FOR | E1+E3 | ER1 | 保持 |
| e11 | e5 | NO_RELATION | E4 | ER2 | 新增候选（旧UNRESOLVED） |
| e11 | e7 | USED_FOR | E1+E3 | ER1 | 新增候选（旧UNRESOLVED） |
| e11 | e9 | NO_RELATION | E4 | ER2 | 新增候选（旧UNRESOLVED） |
| e11 | e10 | USED_FOR | E1+E3 | ER1 | 保持 |
| e11 | e13 | UNRESOLVED | E1+E5 | EU2 | 保持 |
| e11 | e14 | UNRESOLVED | E1+E5 | EU2 | 保持 |
| e12 | e1 | UNRESOLVED | E5 | EU3 | 保持 |
| e12 | e2 | UNRESOLVED | E5 | EU3 | 保持 |
| e12 | e4 | UNRESOLVED | E5 | EU3 | 保持 |
| e12 | e5 | UNRESOLVED | E5 | EU3 | 保持 |
| e12 | e7 | UNRESOLVED | E5 | EU3 | 保持 |
| e12 | e9 | UNRESOLVED | E5 | EU3 | 保持 |
| e12 | e10 | UNRESOLVED | E5 | EU3 | 保持 |
| e12 | e13 | EVALUATED_ON | E5 | ER7 | 保持 |
| e12 | e14 | USED_FOR | E5 | ER7 | 新增候选（旧UNRESOLVED） |
| e15 | e1 | UNRESOLVED | E6 | EU4 | 保持 |
| e15 | e2 | UNRESOLVED | E6 | EU4 | 保持 |
| e15 | e4 | UNRESOLVED | E6 | EU4 | 保持 |
| e15 | e5 | UNRESOLVED | E6 | EU4 | 保持 |
| e15 | e7 | UNRESOLVED | E6 | EU4 | 保持 |
| e15 | e9 | UNRESOLVED | E6 | EU4 | 保持 |
| e15 | e10 | UNRESOLVED | E6 | EU4 | 保持 |
| e15 | e13 | UNRESOLVED | E6 | EU4 | 保持 |
| e15 | e14 | UNRESOLVED | E6 | EU4 | 保持 |
| e16 | e1 | UNRESOLVED | E6 | EU4 | 保持 |
| e16 | e2 | UNRESOLVED | E6 | EU4 | 保持 |
| e16 | e4 | UNRESOLVED | E6 | EU4 | 保持 |
| e16 | e5 | UNRESOLVED | E6 | EU4 | 保持 |
| e16 | e7 | UNRESOLVED | E6 | EU4 | 保持 |
| e16 | e9 | UNRESOLVED | E6 | EU4 | 保持 |
| e16 | e10 | UNRESOLVED | E6 | EU4 | 保持 |
| e16 | e13 | UNRESOLVED | E6 | EU4 | 保持 |
| e16 | e14 | UNRESOLVED | E6 | EU4 | 保持 |

## 2006.03654 · DeBERTa摘要

METHOD：e1 pre-trained neural language models；e2 DeBERTa、e3完整架构名；e4 BERT、e5 RoBERTa；e6 disentangled attention mechanism；e7 enhanced mask decoder；e10 virtual adversarial training；e16 RoBERTa-Large；e17 half-data上下文DeBERTa；e21 scaled上下文DeBERTa、e22 single上下文DeBERTa、e24 ensemble上下文DeBERTa。
TASK：e8 predict the masked tokens；e9/e11 model pre-training；e12 natural language understanding、e13 NLU；e14 natural langauge generation、e15 NLG（保留原文typo）。
DATASET：e18 MNLI、e19 SQuAD v2.0、e20 RACE、e23/e25 SuperGLUE。

### Literal quotes

D1:

> In this paper we propose a new model architecture DeBERTa (Decoding-enhanced BERT with disentangled attention) that improves the BERT and RoBERTa models using two novel techniques.

D2:

> Second, an enhanced mask decoder is used to incorporate absolute positions in the decoding layer to predict the masked tokens in model pre-training.

D3:

> In addition, a new virtual adversarial training method is used for fine-tuning to improve models' generalization.

D4:

> We show that these techniques significantly improve the efficiency of model pre-training and the performance of both natural language understanding (NLU) and natural langauge generation (NLG) downstream tasks.

D5:

> Compared to RoBERTa-Large, a DeBERTa model trained on half of the training data performs consistently better on a wide range of NLP tasks, achieving improvements on MNLI by +0.9% (90.2% vs. 91.1%), on SQuAD v2.0 by +2.3% (88.4% vs. 90.7%) and RACE by +3.6% (83.2% vs. 86.8%).

D6:

> Notably, we scale up DeBERTa by training a larger version that consists of 48 Transform layers with 1.5 billion parameters. The significant performance boost makes the single DeBERTa model surpass the human performance on the SuperGLUE benchmark (Wang et al., 2019a) for the first time in terms of macro-average score (89.9 versus 89.8), and the ensemble DeBERTa model sits atop the SuperGLUE leaderboard as of January 6, 2021, out performing the human baseline by a decent margin (90.3 versus 89.8).

D7:

> Recent progress in pre-trained neural language models has significantly improved the performance of many natural language processing (NLP) tasks.

D8:

> The first is the disentangled attention mechanism, where each word is represented using two vectors that encode its content and position, respectively, and the attention weights among words are computed using disentangled matrices on their contents and relative positions, respectively.

### Source reasoning

- DR1：提出的完整DeBERTa架构明确包含mask decoder执行的masked-token prediction/model pre-training用途；给完整方法这一用途，不把原本一般家族或不同配置的测量泛化。
- DR2：保持原已判whole architecture→NLU/NLG用途，完整架构名称/缩写相关提及，不修改旧证据/理由。
- DR3：decoder的明确目标是predict masked tokens in model pre-training；两个pre-training提及是全文同一预训练阶段，不是fine-tuning。
- DR4：保持half-data DeBERTa与RoBERTa-Large在MNLI/SQuAD/RACE的直接比较。不要把这些分数移到scaled-single或ensemble，也不要把RoBERTa-Large缩为无配置的RoBERTa。
- DR5：两处SuperGLUE字面提及在连续同句中都是同一benchmark；新增仅是DATASET提及共指的二元边，分别保持scaled/single模型自身89.9的归属与ensemble自身90.3的归属。没有把单模型/ensemble合并、没有将一个配置的成绩赋给另一配置。旧3对保持原标签与原证据；新增e21→e25、e22→e25及e24→e23须取含正确配置测量和两个benchmark提及的完整D6。相关跨度对不是新增独立实验。
- DU1：首句是泛指预训练模型与泛指NLP进展；不能把后面特定架构、具体目标或benchmark测量赋给所有pre-trained neural language models。
- DU2：e4/e5是被改进的BERT/RoBERTa名称，没有在本文给它们明确token/NLU/NLG目标与具体benchmark测量归属；RoBERTa-Large和普通RoBERTa也不应由字面相近混为同配置。
- DU3：attention的局部目标是编码内容/位置并计算weights，decoder的局部目标是masked-token prediction；整体架构的下游效果不能自动转成每个组件执行所有任务或被所有benchmarks测量。未明确归属不等于NO_RELATION；不要凭未做独立消融判负。
- DU4：VAT明确用于fine-tuning/generalization，但现有TASK库存中没有这个确切目标；不能隐式加实体，不能把“for fine-tuning”直接扩为每个pre-training/NLU/NLG任务或benchmark，也不能从不同阶段/缺测自动判负。
- DU5：e2/e3是一般完整架构名称；后面half-data、scaled-single和ensemble的具体结果需保留配置归属，不能给此处所有早期架构提及无条件继承benchmark测量。
- DU6：half-data DeBERTa/RoBERTa-Large段只明确三个benchmarks与泛指NLP tasks；不根据benchmark常识补NLU/NLG任务或masked-token阶段，也不继承后段SuperGLUE配置结果。
- DU7：后段只明确scaled single/ensemble的SuperGLUE测量；没有明确该配置的其余任务或前三个benchmarks。不能因缺少测量标成负例。

### 全部156对

| head | tail | 建议label | literal quote | source reasoning | 相对旧标签 |
|---|---|---|---|---|---|
| e1 | e8 | UNRESOLVED | D7 | DU1 | 保持 |
| e1 | e9 | UNRESOLVED | D7 | DU1 | 保持 |
| e1 | e11 | UNRESOLVED | D7 | DU1 | 保持 |
| e1 | e12 | UNRESOLVED | D7 | DU1 | 保持 |
| e1 | e13 | UNRESOLVED | D7 | DU1 | 保持 |
| e1 | e14 | UNRESOLVED | D7 | DU1 | 保持 |
| e1 | e15 | UNRESOLVED | D7 | DU1 | 保持 |
| e1 | e18 | UNRESOLVED | D7 | DU1 | 保持 |
| e1 | e19 | UNRESOLVED | D7 | DU1 | 保持 |
| e1 | e20 | UNRESOLVED | D7 | DU1 | 保持 |
| e1 | e23 | UNRESOLVED | D7 | DU1 | 保持 |
| e1 | e25 | UNRESOLVED | D7 | DU1 | 保持 |
| e2 | e8 | USED_FOR | D1+D2 | DR1 | 新增候选（旧UNRESOLVED） |
| e2 | e9 | USED_FOR | D1+D2 | DR1 | 新增候选（旧UNRESOLVED） |
| e2 | e11 | USED_FOR | D1+D2 | DR1 | 新增候选（旧UNRESOLVED） |
| e2 | e12 | USED_FOR | D1+D4 | DR2 | 保持 |
| e2 | e13 | USED_FOR | D1+D4 | DR2 | 保持 |
| e2 | e14 | USED_FOR | D1+D4 | DR2 | 保持 |
| e2 | e15 | USED_FOR | D1+D4 | DR2 | 保持 |
| e2 | e18 | UNRESOLVED | D1+D5+D6 | DU5 | 保持 |
| e2 | e19 | UNRESOLVED | D1+D5+D6 | DU5 | 保持 |
| e2 | e20 | UNRESOLVED | D1+D5+D6 | DU5 | 保持 |
| e2 | e23 | UNRESOLVED | D1+D5+D6 | DU5 | 保持 |
| e2 | e25 | UNRESOLVED | D1+D5+D6 | DU5 | 保持 |
| e3 | e8 | USED_FOR | D1+D2 | DR1 | 新增候选（旧UNRESOLVED） |
| e3 | e9 | USED_FOR | D1+D2 | DR1 | 新增候选（旧UNRESOLVED） |
| e3 | e11 | USED_FOR | D1+D2 | DR1 | 新增候选（旧UNRESOLVED） |
| e3 | e12 | USED_FOR | D1+D4 | DR2 | 保持 |
| e3 | e13 | USED_FOR | D1+D4 | DR2 | 保持 |
| e3 | e14 | USED_FOR | D1+D4 | DR2 | 保持 |
| e3 | e15 | USED_FOR | D1+D4 | DR2 | 保持 |
| e3 | e18 | UNRESOLVED | D1+D5+D6 | DU5 | 保持 |
| e3 | e19 | UNRESOLVED | D1+D5+D6 | DU5 | 保持 |
| e3 | e20 | UNRESOLVED | D1+D5+D6 | DU5 | 保持 |
| e3 | e23 | UNRESOLVED | D1+D5+D6 | DU5 | 保持 |
| e3 | e25 | UNRESOLVED | D1+D5+D6 | DU5 | 保持 |
| e4 | e8 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e4 | e9 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e4 | e11 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e4 | e12 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e4 | e13 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e4 | e14 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e4 | e15 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e4 | e18 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e4 | e19 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e4 | e20 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e4 | e23 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e4 | e25 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e5 | e8 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e5 | e9 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e5 | e11 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e5 | e12 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e5 | e13 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e5 | e14 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e5 | e15 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e5 | e18 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e5 | e19 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e5 | e20 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e5 | e23 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e5 | e25 | UNRESOLVED | D1+D5 | DU2 | 保持 |
| e6 | e8 | UNRESOLVED | D8+D4 | DU3 | 保持 |
| e6 | e9 | UNRESOLVED | D8+D4 | DU3 | 保持 |
| e6 | e11 | UNRESOLVED | D8+D4 | DU3 | 保持 |
| e6 | e12 | UNRESOLVED | D8+D4 | DU3 | 保持 |
| e6 | e13 | UNRESOLVED | D8+D4 | DU3 | 保持 |
| e6 | e14 | UNRESOLVED | D8+D4 | DU3 | 保持 |
| e6 | e15 | UNRESOLVED | D8+D4 | DU3 | 保持 |
| e6 | e18 | UNRESOLVED | D8+D4 | DU3 | 保持 |
| e6 | e19 | UNRESOLVED | D8+D4 | DU3 | 保持 |
| e6 | e20 | UNRESOLVED | D8+D4 | DU3 | 保持 |
| e6 | e23 | UNRESOLVED | D8+D4 | DU3 | 保持 |
| e6 | e25 | UNRESOLVED | D8+D4 | DU3 | 保持 |
| e7 | e8 | USED_FOR | D2 | DR3 | 保持 |
| e7 | e9 | USED_FOR | D2 | DR3 | 新增候选（旧UNRESOLVED） |
| e7 | e11 | USED_FOR | D2 | DR3 | 新增候选（旧UNRESOLVED） |
| e7 | e12 | UNRESOLVED | D2+D4 | DU3 | 保持 |
| e7 | e13 | UNRESOLVED | D2+D4 | DU3 | 保持 |
| e7 | e14 | UNRESOLVED | D2+D4 | DU3 | 保持 |
| e7 | e15 | UNRESOLVED | D2+D4 | DU3 | 保持 |
| e7 | e18 | UNRESOLVED | D2+D4 | DU3 | 保持 |
| e7 | e19 | UNRESOLVED | D2+D4 | DU3 | 保持 |
| e7 | e20 | UNRESOLVED | D2+D4 | DU3 | 保持 |
| e7 | e23 | UNRESOLVED | D2+D4 | DU3 | 保持 |
| e7 | e25 | UNRESOLVED | D2+D4 | DU3 | 保持 |
| e10 | e8 | UNRESOLVED | D3+D4 | DU4 | 保持 |
| e10 | e9 | UNRESOLVED | D3+D4 | DU4 | 保持 |
| e10 | e11 | UNRESOLVED | D3+D4 | DU4 | 保持 |
| e10 | e12 | UNRESOLVED | D3+D4 | DU4 | 保持 |
| e10 | e13 | UNRESOLVED | D3+D4 | DU4 | 保持 |
| e10 | e14 | UNRESOLVED | D3+D4 | DU4 | 保持 |
| e10 | e15 | UNRESOLVED | D3+D4 | DU4 | 保持 |
| e10 | e18 | UNRESOLVED | D3+D4 | DU4 | 保持 |
| e10 | e19 | UNRESOLVED | D3+D4 | DU4 | 保持 |
| e10 | e20 | UNRESOLVED | D3+D4 | DU4 | 保持 |
| e10 | e23 | UNRESOLVED | D3+D4 | DU4 | 保持 |
| e10 | e25 | UNRESOLVED | D3+D4 | DU4 | 保持 |
| e16 | e8 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e16 | e9 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e16 | e11 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e16 | e12 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e16 | e13 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e16 | e14 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e16 | e15 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e16 | e18 | EVALUATED_ON | D5 | DR4 | 保持 |
| e16 | e19 | EVALUATED_ON | D5 | DR4 | 保持 |
| e16 | e20 | EVALUATED_ON | D5 | DR4 | 保持 |
| e16 | e23 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e16 | e25 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e17 | e8 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e17 | e9 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e17 | e11 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e17 | e12 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e17 | e13 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e17 | e14 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e17 | e15 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e17 | e18 | EVALUATED_ON | D5 | DR4 | 保持 |
| e17 | e19 | EVALUATED_ON | D5 | DR4 | 保持 |
| e17 | e20 | EVALUATED_ON | D5 | DR4 | 保持 |
| e17 | e23 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e17 | e25 | UNRESOLVED | D5+D6 | DU6 | 保持 |
| e21 | e8 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e21 | e9 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e21 | e11 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e21 | e12 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e21 | e13 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e21 | e14 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e21 | e15 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e21 | e18 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e21 | e19 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e21 | e20 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e21 | e23 | EVALUATED_ON | D6 | DR5 | 保持 |
| e21 | e25 | EVALUATED_ON | D6 | DR5 | 新增候选（旧UNRESOLVED） |
| e22 | e8 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e22 | e9 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e22 | e11 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e22 | e12 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e22 | e13 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e22 | e14 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e22 | e15 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e22 | e18 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e22 | e19 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e22 | e20 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e22 | e23 | EVALUATED_ON | D6 | DR5 | 保持 |
| e22 | e25 | EVALUATED_ON | D6 | DR5 | 新增候选（旧UNRESOLVED） |
| e24 | e8 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e24 | e9 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e24 | e11 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e24 | e12 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e24 | e13 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e24 | e14 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e24 | e15 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e24 | e18 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e24 | e19 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e24 | e20 | UNRESOLVED | D5+D6 | DU7 | 保持 |
| e24 | e23 | EVALUATED_ON | D6 | DR5 | 新增候选（旧UNRESOLVED） |
| e24 | e25 | EVALUATED_ON | D6 | DR5 | 保持 |

## 守恒与准入结论

- 全部219个现有allowed pairs均列出，不新增实体或候选键，不撤销原31个已判标签。
- 若root复核接受上述所有新增候选：两篇已判31→56，其中USED_FOR19→31、EVALUATED_ON10→14、NO_RELATION2→11；UNRESOLVED188→163。新增25=12 USED_FOR +4 EVALUATED_ON +9 NO_RELATION。
- ELECTRA建议63对中27已判/36未决（14 USED_FOR、2 EVALUATED_ON、11 NO_RELATION）。DeBERTa建议156对中29已判/127未决（17 USED_FOR、12 EVALUATED_ON）。
- **完整关系文档仍为0；完整EVALUATED_ON文档支持不能诚实提升。** 不通过空缺补负、泛指家族继承或跨配置成绩搬移强行完成。generator/泛指METHOD与benchmark的缺证据仍须未决；这正是单摘要二元监督的边界。
- root需实际逐对自复核，尤其ER6省略模型指代与DR5两个SuperGLUE提及共指；若不能明确接受，保留未决。这不是独立人工核验，也不是最终/盲测数据。
- 本建议只供**新版本DEV参考**，不可训练、不可回填49或51–58旧成绩。今后若用新参考评价，必须声明新分母/覆盖和既有暴露，不和旧F1直接拼排行榜。


# 第36轮：摘要关系开发与NER→RE误差传播

2026-10-08。本轮完成新的明确关系标签、真实关系训练、同dev四种对照和错误归因。结果支持**拒绝模型升级**，不支持“可靠性问题已经解决”。按MLE流程先冻结独立合同，复用现有标记分类、严格评分与BIO解码；无新依赖、联合抽取/Agent架构，报告仍暂停。

## 数据合同与真实标注

35轮完整文档规则只有1篇dev可用（ITO），且0个关系对。本轮另存 [course_abstract_relation_v1.json](../resources/course_abstract_relation_v1.json)：模块开发仅评分明确已判定的实体对；pipeline仍要求整篇NER/RE完整、保留零参考对文档。原abstract_v1合同、标签、输入和成绩不改；部分模块成绩不是完整队列的准确率。

15篇train、13篇dev有逐组明确AI关系判断与实际同会话自复核，其余原收据原样继承；不是又完成全部56篇关系标注。源NER实体/边界/类别/隔离状态逐字段不变，摘要原文和论文组也不变，未凭NER预测修参考。关系判断时未查看RE预测；35轮NER dev结果已见，故不冒充独立盲审或human gold。

| NER合格文档内统计 | train | dev |
|---|---:|---:|
| 整篇队列 / NER合格 | 37 / 29 | 19 / 16 |
| 有明确实体对的文档 | 16 | 13 |
| 明确标签对 | 195 | 242 |
| USED_FOR | 145 | 202 |
| EVALUATED_ON | 43 | 10 |
| NO_RELATION | 7 | 30 |
| 未决对（屏蔽） | 913 | 190 |
| 明确对覆盖（NER合格文档内） | 195/1,108=17.60% | 242/432=56.02% |
| 整篇关系完整文档 | 4 | 5 |

负例不是缺少评测语句或差性能推得：原文明确区分被压缩CNN/GoogleNet等对象与RL-Pruner操作方、隐式/显式模块的不同输出、传播模型与放置生成算法、UCF101评测与比较方ImageNet初始化。仍只是AI在文档范围内的角色判断，不是独立语义认证或世界层面的“从不使用”。PASCAL VOC背景提及继续UNRESOLVED，不制造数据集负例；GPT-3在HumanEval成功率0%仍是EVALUATED_ON，不因失败改负。

训练负例仅7对、来自3篇；验证负例30对只来自2篇。dev EVALUATED_ON10对来自3篇文献/4个数据集名称，含重复提及，不是10个独立实验。标签依赖、样本选择与排除偏差仍明显。新增原文证据必须覆盖两端点和支持摘录；模型不把理由/证据标签当特征。最大标记后train333/dev306token，小于512，没有截断或丢失败对。

## 真实RE训练，候选退化

RTX4060 Laptop，从15轮冻结实体标记RE epoch3 warm-start，seed20261008、batch4、lr2e-5、6轮、既有平衡损失（NO_RELATION权重9.2857）。195个train对每轮恰好覆盖一次，共294步；只在train反传梯度，dev按三类宏F1最早最佳选择epoch1。全过程及随后四种对照约97.99秒。编码器/分类头均变化，重载预测相同，源码/输入/权重按SHA绑定。

| 同242个明确dev对 | 正关系Precision | 正关系Recall | 正关系F1 | 三类宏F1 | NO_RELATION F1 |
|---|---:|---:|---:|---:|---:|
| 旧RE迁移 | 93.78% | 99.53% | 96.57% | 88.16% | 68.09% |
| train类型多数基线 | 87.60% | 100.00% | 93.39% | 64.36% | 0.00% |
| 新RE候选epoch1 | 92.58% | 100.00% | 96.15% | 85.48% | 60.47% |

新RE仅识别13/30个负例，旧RE识别16/30；新三类宏F1与正关系Precision/F1都不及旧权重。训练确实完成，不能把失败升级包装为“效果提升”：明确决定 `candidateRE=rejected_dev_regression`，权重保留用于复核，**不替换旧RE**。没有反复看到dev后改超参数追分。

以上是条件性模块一致性，未决对不作为FP/TN。高模块正关系F1不能掩盖低端到端表现；也不和17轮题名模块99.25%作直接排行。

## 同一完整文档dev的四种对照

5/19篇完整（26.32%），包含1篇零参考对ITO；另有14篇不可进行完整pipeline评分，保持原原因而非空负例。58个完整参考实体对中，46个USED_FOR正例、12个NO_RELATION，EVALUATED_ON正例0。实体预测不使用参考labels，NER35冻结权重重放全16篇并核对与35轮原预测/指标一致；旧NER同摘要分母核对旧迁移基线。不重新训练NER或读取保留test。

| 同一5篇组合 | Precision | Recall | F1 | TP / 预测正例 / 参考正例 |
|---|---:|---:|---:|---:|
| 旧NER / 旧RE | 8.59% | 47.83% | 14.57% | 22 / 256 / 46 |
| 新NER / 旧RE | 24.32% | 39.13% | 30.00% | 18 / 74 / 46 |
| 旧NER / 新RE | 8.30% | 47.83% | 14.15% | 22 / 265 / 46 |
| 新NER / 新RE | 22.50% | 39.13% | 28.57% | 18 / 80 / 46 |

这不是14.57%/30%对旧60.07%题名test的升降对照；文本单位、标签、队列和分母不同。完整dev没有EVALUATED_ON支持，不能证明数据集关系被改进。非完整文档的未知预测既不冒称正确，也不算此表FP/TN。

## 可复核的错误归因和决定

| 组合 | FP | 端点不匹配 / 正确端点错关系 | FN | FN主要来源 |
|---|---:|---:|---:|---|
| 旧NER / 旧RE | 234 | 228 / 6 | 24 | 边界24 |
| 新NER / 旧RE | 56 | 54 / 2 | 28 | 漏实体19、边界7、类型2 |
| 旧NER / 新RE | 243 | 235 / 8 | 24 | 边界24 |
| 新NER / 新RE | 62 | 59 / 3 | 28 | 漏实体19、边界7、类型2 |

按每个参考正例检查头尾实体、跨度/类型、候选生成与RE决策；保留可能重叠的所有标记，再按缺失→类别→边界→候选→RE给互斥主因。FP单独检查预测两端是否匹配AI参考实体，不和FN相加成“总错误率”。原文、预测、分数、证据和每条原因已保存，错误也可能包括AI参考遗漏，不保证全是模型语义错误。

新NER配旧RE减少FP、提高F1，但Recall从47.83%降至39.13%，下降8.70百分点，超过训练前声明的2百分点护栏；完整覆盖26.32%不足80%，EVALUATED_ON参考不足。故 `candidateNERPipeline=not_promoted_recall_and_coverage_gates_failed`。新RE更换不能补回缺失端点，重心应转向NER的训练样本和跨度/类别定义，不继续盲调关系网络。

当前 `qualityPromotionPassed=false`。旧生产模型、35轮NER候选、09/17/29测试、31轮图及历史证据均校验未变；19篇摘要test内容未被标注、分词、推理或训练（只有源包完整性哈希检查）。无数据库写入、服务重启、概念模糊合并或作者身份升级；本轮不宣称新的线上验收。

下一步优先新增**训练侧**整篇摘要与任务/角色多样性，扩大独立来源的负例；补充新的完整dev关系证据并保持固定队列/覆盖透明。以NER端点错误为实验目标，冻结新版本后才能重训；旧测试不能拿来选样本/词典/提示。当前不要求用户人工标注，也不能承诺仅靠同会话AI标签达到独立金标准可靠性。

## 实际入口与证据

复现必须使用新输出目录。当前新增训练入口无final-test参数或自动晋级：

```powershell
& '.\.venv-validation\Scripts\python.exe' -B -m pytest tests -q
& '.\.venv-training\Scripts\python.exe' -B scripts/train_abstract_relation.py --snapshot kg_datasets/dblp/course_abstract_relation_inputs_20261008_36 --output kg_datasets/dblp/course_v4_runs/NEW_ABSTRACT_RE_DEV
```

[关系修订入口](../scripts/course_abstract_relation.py)、[真实训练/四种对照](../scripts/train_abstract_relation.py)、[可运行契约与错误检查](../tests/test_abstract_relation.py)。364项工程回归通过，另按保存的预测重新计算模块/完整pipeline指标、每轮train覆盖和FP/FN主因，不是364项语义认证。

数据包 `kg_datasets/dblp/course_abstract_relation_inputs_20261008_36`；运行 `course_v4_runs/abstract_relation_development_20261008_36`；[机器核验](../kg_datasets/dblp/course_v4_runs/verification_20261008_round36.json)。

[候选拒绝与四种对照截图](evidence/20261008_round36/09_annotation_expansion.png)、[真实训练产物截图](evidence/20261008_round36/07_relation_development.png)。截图是浏览器渲染真实JSON/JSONL/XML的离线证据页，不是训练现场或Neo4j应用界面。原页、源码/结果快照、逐对错误审计、`candidate_decision.json`、manifest和captures哈希同目录保留。

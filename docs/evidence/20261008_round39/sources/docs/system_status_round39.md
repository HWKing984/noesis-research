# 第39轮：评测归属与角色反例的训练监督补强

2026-10-08。继续使用MLE工作流：先固定38轮源清单、36轮关系语义和四篇选择范围，再读整篇原文、逐组判断、自复核及预检。**本轮补的是训练标签，不是新模型成绩或可靠性验收；未训练、推理、写库或重启。**完整课程报告仍暂停。

## 已实际完成

选择范围是37轮锁定训练扩充中，全部四篇NER完整且含命名DATASET的摘要，未按dev/test错误或模型分数挑选；无新采集或替换失败论文。新增入口 `scripts/enrich_abstract_relations.py` 复用现有 `revise`、`rows_for`、收据和严格编码，不改历史源码/合同/数据包。

四篇完整原文、实体和候选对已阅读。初判经展开校验后重新核对全部组和角色，由同一会话AI实际自复核；只给四篇生成新的初标/一次复核收据，另外54篇收据原样继承。实体跨度、类别、状态、理由、groupMentions、源文与论文组均不改，已有201个明确对的标签/证据/理由全部保留。

| 训练源文 | 新增USED_FOR | 新增EVALUATED_ON | 新增NO_RELATION | 仍未决 / 原候选 |
|---|---:|---:|---:|---:|
| 2503.01309：3D segmentation | 2 | 0 | 6 | 46 / 54 |
| 2107.10847：RLQP | 16 | 9 | 4 | 34 / 63 |
| 2402.14245：CriticGPT | 7 | 1 | 0 | 57 / 65 |
| 2510.26830：SmoothGuard | 7 | 6 | 9 | 26 / 48 |
| 合计 | **32** | **16** | **19** | 163 / 230 |

每个明确对有原文证据覆盖头尾、角色解释和源文哈希。负例只用已有合同的明确角色对照：产生输入mask的VFM与执行后续3D查询/合并的步骤、接受元策略调优的solver与调优操作者、防御/扰动/过滤/接收者之间的分工。**NO_RELATION是固定文档语义范围内的AI判断，不是说某类方法永远无法用于该任务**；仍可能有标签噪声，不能冒充独立gold。没有把共现、效果不好、未报告评测或UNRESOLVED自动判负。

## 一个重要修正：整体方法评测不等于组件单独评测

2503.01309明确说“our approach”在ScanNet/SceneNN评测，但保留NER清单只有若干组件，没有可唯一归属的命名整体方法。因此**所有组件—benchmark候选保持UNRESOLVED**，没有为了增加EVALUATED_ON而把VFMs、voxel hashing或filtering自动绑到两个数据集。这是本轮选择了四篇却只有三篇新增明确评测标签的原因。

CriticGPT论文的Meta-World表现明确归属其reward model，只给该源文的reward-model提及建立标签，不把CriticGPT所有提及、reward modeling和reward model当成同一对象。SmoothGuard三个benchmark只明确归属防御框架，不推出每个noise/clustering子组件被单独评测；RLQP泛化评测也不自动推广到所有RL/QP solver提及。

新增16个评测**跨度对**只来自3篇论文，按源文ID＋方法名称＋benchmark名称去重为7个组合。重复的RLQP、SmoothGuard名称具有相关性，不能解释成16次独立实验，也不能据此保证模型已掌握三种以外的场景。

## 当前数据与准入

| 新修订训练资产（未训练） | 数量/状态 |
|---|---|
| 固定训练摘要 / NER可用 / 隔离 | 58 / 50 / 8篇，全部原NER字段不变 |
| 已明确关系对 | **268**，原201；新增67 |
| 标签分布 | USED_FOR183 / EVALUATED_ON59 / NO_RELATION26 |
| 已判 / 可用NER文档候选 | 268 / 1845 = **14.53%**，原10.89% |
| 未决对 | **1577**，不输出到明确关系训练行，不当NO_RELATION |
| 完整关系训练文档 | 仍6/58，包含零候选文档，没有按新增已判对假装文档完整 |
| 原dev与摘要test | dev19篇、完整pipeline仍5/19且EVALUATED_ON参考0；test19篇内容未消费 |

50篇NER全部严格token/BIO往返；268个明确关系对的实体标记编码全部通过，最大333 tokens，不截断。输出NER行的收据/合同元数据随关系版本变化，**只是NER内容/状态不变，不声称新行字节或来源SHA与38轮完全相同**；本轮输入是新关系快照，尚未自动接入任何模型训练或应用。

另外逐篇检查了八篇原NER隔离，将共享中心词、任务/领域歧义、源文黏连/复合词、未命名任务/数据和弱研究内容原因写入独立排查文件。它是**排查记录，不是新标签、独立审核或解隔离收据**，八篇保持原状态；不为提高覆盖凑成all-O。

## 回归与不可夸大的结论

新增一个运行检查，覆盖全NER字段不变、原明确关系保留、组件评测仍未决、reward-model归属、缺负例依据/假证据拒绝和初标未复核不准入。正式完整回归**367项通过，130.58秒，零失败/错误/跳过**；不是367项语义正确性证明。

机器审计重算候选分母、67个新增对、来源重复名称、收据/原文/字符偏移/旧标签与排除集合，复用38轮核验检查旧权重、35/36/37运行包、封存成绩、源包、旧证据与31轮固定图包。dev/test只核验既有资料完整性，没有本轮语义阅读、标注、分词或推理，不拿旧test追分。

**本轮没有新F1**；37轮NER71.28%与pipeline26.49%仍是旧的已暴露AI dev诊断，不能加上67条标签就宣称变好。`qualityPromotionPassed=false`、`modelPromoted=false`。线上模型与图不替换；没有新数据库/HTTP/应用验收。2万篇书目、194,639节点/263,059关系的31轮包不改。

## 复现和证据

新输出必须不存在，不覆盖封存快照：

```powershell
& '.\.venv-training\Scripts\python.exe' scripts/enrich_abstract_relations.py --decisions annotations/course_v4/abstract_relation_enrichment_decisions_20261008_39.json --reviews annotations/course_v4/abstract_relation_enrichment_reviews_20261008_39.json --output kg_datasets/dblp/NEW_RELATION_ENRICHMENT
& '.\.venv-validation\Scripts\python.exe' -m pytest tests/test_relation_enrichment.py -q
```

当前产物：`kg_datasets/dblp/course_abstract_relation_enriched_20261008_39`，含58篇原文/新旧收据、上游绑定、50篇NER行、268明确关系、67新增对、未决仍在原收据中、完整文档、8篇隔离和BIO对齐。锁定合同 `resources/course_abstract_relation_enrichment_v1.json`；四篇初判/复核及八篇排查文件在 `annotations/course_v4`，带39轮后缀。

[机器核验](../kg_datasets/dblp/course_v4_runs/verification_20261008_round39.json)、[关系补强结果截图](evidence/20261008_round39/09_annotation_expansion.png)、[原文与评测归属截图](evidence/20261008_round39/04_traceability.png)。真实浏览器渲染保存产物，**不是模型预测、终端、训练现场或Neo4j画面**；源码/JSON/JSONL/XML快照、PNG与截图时间/哈希均保留。

## 下一步仍需完成

补完整开发文档的关系证据与稀有关系覆盖，继续核对训练侧任务跨度/家族与研究对象；八篇隔离需要真正解决定义或表达问题，不能只改状态。旧开发标签、成绩和合同保持各自历史版本，任何新任务定义另锁队列/比较范围，不把旧dev已见错误变成提示或准入规则。达到预声明的训练/比较条件后做一次新版本模型对照，整条pipeline和选择规则锁定后才使用保留test。独立验证、长尾概念与无PID作者身份缺口未全部解决。

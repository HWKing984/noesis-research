# 第38轮：逐次上下文标注修复与训练数据准入

2026-10-08。按MLE工作流先锁两个已知训练隔离案例、父合同、来源清单和修订边界，再逐篇重读原文、AI初标/同会话复核，最后严格BIO预检。**本轮修复的是标注表达与上下文角色，不是模型可靠性验收；没有重新训练、推理或上线。**课程完整报告仍暂停。

## 已完成

新增 `resources/course_abstract_occurrence_v1.json` 与版本化入口 `scripts/revise_contextual_abstracts.py`，旧编译器、源文、收据、权重与成绩不改。每个声明词的所有独立出现必须逐处判断并写原因，支持METHOD/TASK/DATASET、OUT_OF_SCOPE和WITHIN_ENTITY；后者必须绑定一个真正覆盖该词的已选实体。遗漏出现、布尔/越界序号、URL实体、跨度重叠和错误原文哈希均拒绝，不靠最长跨类别覆盖强行放行。真正嵌套实体或并列共用中心词仍不自动解决。

| 原训练隔离 | 本轮实际判断 | 原因与边界 |
|---|---|---|
| arXiv 2409.13884 | `multi-LLM debiasing framework`全名为METHOD；后文`for debiasing LLMs`中的`debiasing`为TASK | 前一个是方法名称的词法修饰，后一个独立陈述目标；不是在同一位置断言重叠的两个实体 |
| arXiv 2110.02932 | 明确`using machine learning (ML) methods`和`deploying ML`为技术家族METHOD | `ML Practitioners/community/development`是人群、领域或工作流，不随缩写传播类别；访谈不是命名DATASET |

两个源文及字符偏移、所有发生位置的理由、初标/复核哈希和上游收据绑定均保存。后一案例包含版本化范围澄清，不能声称彻底消除了所有ML多义性；二者是AI参考，不是独立人工gold。未按dev/test模型错误或分数选这两篇，也没有把访谈文献算成新增原创AI模型论文。

## 数据结果与分母

训练摘要固定58篇：**50篇严格BIO准入、8篇继续隔离**，原来为48/10。参考提及METHOD378 / TASK189 / DATASET44。50篇使用本地SciBERT tokenizer、不截断、原始Unicode偏移，全部严格往返一致。

只给两篇生成新的初标和一次实际同会话复核，其余56篇收据原样继承。继承源为36轮37篇训练侧关系修订收据和37轮21篇新增训练收据，保留36轮195条已判关系，不退回更早的17条候选版本。旧48篇可用NER文档的原文、实体、类别、论文组不变；其中关系修订后的收据来源/SHA以及行元数据不同，**不声称新输入逐字节等同旧48篇文件**。

对变更实体的两篇先废弃旧端点编号、重建全部候选，再凭原文逐对判断。2409.13884原`e13`是LLMs，新`e13`是debiasing，直接继承旧编号会造成错误边。新增6条明确USED_FOR（偏差缓解的三种策略、multi-LLM方法改善推理、框架的偏差降低/去偏目标），每条证据覆盖头尾跨度。其余46对仍UNRESOLVED，不把被改进的LLMs自动判成执行者。

| 新修订训练资产（未训练） | 数量/状态 |
|---|---|
| 固定训练队列 / 新判断 / 原样继承 | 58 / 2 / 56篇 |
| NER可用 / 隔离 | 50 / 8篇 |
| 已明确关系对 | 201：USED_FOR151 / EVALUATED_ON43 / NO_RELATION7 |
| 可用NER文档的候选关系分母 | 1845对，1644未决；已明确覆盖201/1845，约10.89% |
| 完整关系训练文档 | 6/58篇，包含零关系候选的文档，不等于全体RE可用 |
| 原dev | 19篇；NER16篇，完整pipeline仍5/19，EVALUATED_ON参考仍0 |
| 原保留摘要test | 19篇内容未消费，仅源包哈希检查 |

37轮“新增724个未决”是整个21篇收据里的候选计数，包含当时被NER隔离文档的部分标签；本表只数**NER完整可用文档**里的对，不能直接混用两个分母。DATASET/EVALUATED_ON支持没有增加，罕见类和完整开发覆盖缺口仍在。2万篇书目、31轮图谱节点/关系规模没有改变。

## 回归、失败与留痕

新增一个可运行检查，覆盖逐次角色、中文Unicode偏移、覆盖实体的原始发生序号、遗漏/重叠/URL/哈希拒绝、新旧收据、变更端点和未决保护。完整正式回归**366项通过，95.72秒，无失败/错误/跳过**；这是工程检查，不是366项语义正确性认证。

首次从根目录运行pytest误收集证据/交接目录里的历史测试副本，出现20个模块重名收集错误。失败XML保留为 `tests_20261008_round38_all.xml`。检查发现没有现有pytest配置，新增最小 `pytest.ini`，使默认收集范围只包含正式 `tests`，重新运行通过记录为 `tests_20261008_round38_scoped.xml`。没有删除或改写历史副本，也没有把失败记录覆盖成成功。

机器审计重算源文/收据一致性、50篇BIO、旧48篇NER字段、候选/未决关系分母，核验旧题名权重、35/36/37摘要候选运行包、封存成绩、旧证据包、dev与保留源包及固定31图的哈希。**未连接数据库、重启应用或做新线上验收**；不能把旧在线状态当本轮刷新后的证明。

本轮没有新F1。37轮NER71.28%、固定旧RE的pipeline26.49%仍是原先已暴露AI dev诊断，候选被拒。`qualityPromotionPassed=false`、`modelPromoted=false`，数据准入不等于性能改进。

## 复现与产物

新输出必须不存在，避免覆盖已封存记录：

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/revise_contextual_abstracts.py generate --decisions annotations/course_v4/abstract_occurrence_decisions_20261008_38.json --output kg_datasets/dblp/NEW_OCCURRENCE_GENERATION
& '.\.venv-training\Scripts\python.exe' scripts/revise_contextual_abstracts.py review --generation kg_datasets/dblp/NEW_OCCURRENCE_GENERATION --reviews annotations/course_v4/abstract_occurrence_reviews_20261008_38.json --output kg_datasets/dblp/NEW_OCCURRENCE_REVIEW
& '.\.venv-validation\Scripts\python.exe' -m pytest tests/test_contextual_abstracts.py -q
```

当前初标 `course_abstract_occurrence_generated_20261008_38`；修订输入 `course_abstract_occurrence_reviewed_20261008_38`（均在 `kg_datasets/dblp`）。包含原文、收据、上游绑定、50篇NER行、201条明确关系、1644条未决保留在收据中、8篇排除及token/BIO对齐。尚未自动接入任何训练或线上应用入口。

[机器核验](../kg_datasets/dblp/course_v4_runs/verification_20261008_round38.json)、[上下文修复与边界截图](evidence/20261008_round38/09_annotation_expansion.png)、[真实来源跨度截图](evidence/20261008_round38/03_predictions.png)。截图是浏览器对真实产物的渲染，**不是模型预测、终端、训练现场或Neo4j画面**；原XML、源码/决策快照和截图时间/哈希同目录保存。

## 下一步

逐处表达问题已有可用入口，但旧标签的任务跨度一致性、方法家族与研究对象区分没有整体完成重审；其余8篇隔离不能只靠发生位置修复。继续补有证据的完整关系开发文档及稀有类别，保持旧参考版本不变，新的标注规则若改变任务定义须另锁开发契约/队列。数据质量与评价覆盖达到准入条件后，再做一次预声明配置的模型对照，不因为两篇解隔离立即循环训练追dev分。整个pipeline锁定后才使用保留test。长尾概念归一、无可靠PID作者身份和独立验证缺口仍未全部解决。

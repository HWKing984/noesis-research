# V2优先语义裁决、共指证据与离线重放

本批按深度审核的限定清单完成统计修正、TASK口径说明、5条新候选复核及两组已有评测关系的共指补证。所有数据仍为AI伪标签；没有训练、模型推理、新F1、生产替换或独立人工金标准。

正式目录为`kg_datasets/dblp/course_v2_priority_revision_20261010_final`。状态：`priority_review_and_evidence_chain_completed_negative_scope_pending_not_training_ready`。

## 数据与修订范围

| 项目 | 上一版 | 本版 |
|---|---:|---:|
| 摘要/实体提及/候选宇宙 | 12 / 177 / 684 | 不变 |
| USED_FOR | 63 | 68 |
| EVALUATED_ON | 17 | 17 |
| NO_RELATION（继续隔离） | 5 | 5 |
| UNRESOLVED | 599 | 594 |
| 正关系候选导出 | 80 | 85 |
| 有候选正例的不同论文 | 11 | 11 |
| 支持组 | 25 | 29 |
| 字面去重：区分大小写 | 50 | 55 |
| 字面去重：忽略大小写 | 49 | 54 |

旧“80条来自10篇”是说明错误，已在[旧技术说明](course_v2_entity_completion_20261010.md)修正；旧数据和ZIP保持。旧用途来源10篇、评测5篇、交集4篇，联合11篇；本版因MNIST论文新添增广用途，用途来源为11篇，评测仍5篇。新summary增加`totalSourcePapersWithEligibleRE`及旧版同口径字段，测试防止再次把类别篇数当联合篇数。

50/49的差异来自`Autoencoders`与`autoencoders`，不是某一条关系漏导出。计数口径显式保存，不能把提及对、字面组合、支持组或论文数称为独立事实数。

## 五条裁决

| 原文实体对 | 本批判断 | 明确范围 |
|---|---|---|
| Rotation → augment training data | USED_FOR | 与translation共用同一句支持；训练操作，不是MNIST评测 |
| translation → augment training data | USED_FOR | `training_proxy`，子类型`training_augmentation`只作审计 |
| deep learning → remote sensing object detection | USED_FOR | 原文明确背景用途，不是GE-FSOD组件/评测 |
| PVA → identity preservation | USED_FOR | 身份保持作为研究目标；不认证实际效果优秀 |
| diffusion process → generate optimal sensor placement strategies | USED_FOR | `utilizes X to generate Y`明确组件操作；不继承整个EFGD的其他目标或分数 |

[一页TASK/角色准则](course_v2_task_scope_v1.md)先明确训练操作、研究目标、指标和输出名词的边界，再作AI判定。没有改变METHOD/TASK/DATASET或关系模型Schema，也不直接导入CSV的新角色名。

五条都使用完整原文句子与精确Unicode偏移；CSV的`evidenceHint`中有截短提示，未作为字面证据直接使用。2条增广关系共用一个支持组；总计增加4组，不能说新增5项独立实验。

[固定原文决策与同会话自查](../annotations/course_v4/v2_priority_decisions_20261010.json)保留受绑定的原文/旧收据SHA、实际裁决和归属限制。其他679个候选的标签均未修改；5条旧角色反例仍保留标签、支持与隔离原因，普通负例导出为0。

## 两组共指证据

1. SQuAD：保存首句数据集全称/别名、`We analyze the dataset`语境，以及模型`which achieves`先行关系。全称和缩写两条既有评测提及共用同一证据链，标签/理由/原证据/支持组均不改。
2. HumanEval：为`repeated sampling → HumanEval`分别保存`this method`的策略先行句和`our problems`的HumanEval语境先行句，不把分数分派给独立生产Codex。

本批共补3个提及级关系、两组链，在`coreferenceEvidence`内保存`anaphorSpan`、`antecedentSpan`、`kind`与解释。仅补这两组，不宣称所有跨句/别名关系都补完。源内语境归属仍是AI解释，不是新增明确`on SQuAD`原文，更不是独立正确率证明。

原有80条正例的标签、理由和连续证据全部保留；只有上述3条支持元数据增加辅助链。V2导出明确保留新辅助字段与子类型，原V1编码器输入不变。真实tokenizer编码测试确认元数据有无不改变模型features。

## 校验与外部重放

[98项最终相关检查](../outputs/v2_priority_revision_final_20261010.xml)通过：本批27、上一完整性32、语义修订23、首批准备16；不累加重跑次数。新增检查包含五条裁决守恒、负例隔离、伪先行句/重复裁决/非法角色拒绝、来源篇数回归、重新签名的错误summary拒绝、元数据不入模型输入，以及测试结果缺失时不创建半成品。

包内`source_snapshot`保存受控生成器、编码器、依赖源码及测试副本；`source_bindings.json`绑定字节。`check_history`保存上一版69通过/1失败的原XML、71项通过XML与本批98项通过XML。源码供审核，完整历史生成器/原训练套件仍依赖未打包的上游数据和本地ML环境，**不是拿到ZIP就能复跑整个仓库**。

另提供实际可独立运行的标准库校验脚本。解压后在本版数据目录运行：

```powershell
python -I source_snapshot/scripts/verify_v2_priority_bundle.py .
```

已分别在训练环境的隔离子进程和基础Python环境运行通过，返回61类数据断言：文件/SHA、来源绑定、收据链、实体偏移、候选守恒、五条裁决范围、共指字面跨度、未决掩码、导出一致性、统计与源码副本等。它只读保存数据，不联网、不读模型、不连接Neo4j。61类是数据约束分类，不是61次语义认证，也不能与98个pytest测试相加宣传。

外部因此可重放保存数据的工程约束；不能凭保护SHA记录验证本机生产资产，也不能证明未知关系是否语义成立。本机另复核6个V1保护文件仍与旧版一致；未修改旧模型、图、应用或原训练器，未读取保留test正文。

[本批真实结果页面截图](../kg_datasets/dblp/course_v2_priority_revision_20261010_final/09_annotation_expansion.png)与[captures.json](../kg_datasets/dblp/course_v2_priority_revision_20261010_final/captures.json)已保存并目视核对，是数据结果页渲染，不是训练现场截图。

## 本轮失败留痕

首次预检97项通过。第二次测试尚未结束时误提前生成，最终JUnit未写出，生成器报FileNotFoundError，留下未封存的`course_v2_priority_revision_20261010`目录；该目录没有manifest，**不是交付版本**。没有删除或冒充成功。

修复为先验证JUnit再创建目录，增加“结果文件缺失不留半成品”检查，最终98项通过后才生成 `_final`。详细记录见[失败与修复账本](../outputs/v2_priority_revision_failure_20261010.json)。旧缺陷和失败文件保留，不能把旧97项记录当新代码的最终验收。

## 当前停止点

本批四项已完成。可审核[8条变更/补证清单](../kg_datasets/dblp/course_v2_priority_revision_20261010_final/priority_review.csv)和[全684条关系账本](../kg_datasets/dblp/course_v2_priority_revision_20261010_final/relation_ledger.jsonl)。原177实体未动，185新增对中仍有180未决；总未决594。

V2仍不具备普通RE三分类训练准备：接受负例0，5争议负例待单独裁决；新独立验证/最终测试分组、去重与选型门槛未锁定。下一批先解决有明确证据的负例协议，不为凑数量把未知转负例，不拿已暴露12篇充最终测试。不扩论文、不换架构、不启动训练；本技术记录不是课程最终报告。

# 第35轮：独立摘要合同、验证标注与真实NER开发

2026-10-08。本轮按MLE流程先冻结规则和标签，再进行开发训练；沿用既有严格BIO/评分工具，不改题名合同、已暴露测试集、线上图或旧生产权重。完整课程报告仍暂停。

## 已完成

独立合同为 [course_abstract_v1.json](../resources/course_abstract_v1.json)，文本单位为整篇摘要，不拼题名、不改原文；512token超长拒绝，原论文组划分不变，外部基准只在train，先锁超参数与操作性晋级门槛。输入通过来源manifest、文本/收据/合同哈希绑定，不把历史摘录重复计为样本。

19篇dev已逐篇AI判断及同会话自复核，16篇NER可用、3篇隔离；3篇原因分别是任务跨度嵌套方法、另一处任务/方法嵌套、评估指标是否属于METHOD的类别歧义。自复核补充3篇的遗漏，标注时未查看模型预测，不冒称独立gold。

原37篇train仍保留29篇NER可用、8篇隔离。训练实体METHOD211 / TASK109 / DATASET35；dev METHOD116 / TASK53 / DATASET15。BIO逐条严格对齐并原跨度往返一致；实测最大train350/dev302token，没有静默截断。NER覆盖：train29/37=78.38%、dev16/19=84.21%。未判定/被隔离记录不成为空负例。

新候选从08轮生产NER epoch4权重warm-start，配置在本轮标注/训练前声明：seed20261008、batch2、lr2e-5、FP32/eager/确定性、6轮。RTX4060 Laptop实际运行90步，约22.15秒，峰值CUDA占用2,278,442,496字节；完整step与epoch日志均保存。只用train计算梯度，以同一dev严格实体micro F1选最早最佳checkpoint：epoch4。分类头与编码器权重都变化；最佳checkpoint重载后预测逐条相同。

## 实际开发结果

相同16篇摘要、相同AI标签与严格跨度/类别评分。旧权重是**迁移到摘要上的对照**，49.89%不能解释为线上题名效果。候选71.24%也不能与旧74.37%的题名test直接排行。

| 摘要dev模型 | Precision | Recall | F1 | TP / 预测 / 参考 |
|---|---:|---:|---:|---:|
| 旧题名权重迁移基线 | 43.08% | 59.24% | 49.89% | 109 / 253 / 184 |
| train词典基线 | 58.14% | 13.59% | 22.03% | 25 / 43 / 184 |
| 新摘要NER epoch4 | 69.23% | 73.37% | 71.24% | 135 / 195 / 184 |

| 候选类别 | Precision | Recall | F1 | 参考support | FP / FN |
|---|---:|---:|---:|---:|---:|
| METHOD | 85.85% | 78.45% | 81.98% | 116 | 15 / 25 |
| TASK | 47.69% | 58.49% | 52.54% | 53 | 34 / 22 |
| DATASET | 54.17% | 86.67% | 66.67% | 15 | 11 / 2 |

所有分数是AI参考一致性，不是事实正确率。15个DATASET提及只覆盖4篇摘要、7种原文写法（ITO全称与缩写等重复出现），不等于15个独立数据集。数量与独立性仍不足；操作性support下限不构成统计证明。

第5/6轮F1降为70.40%/68.46%，未采用；没有看到dev结果后追加调参。epoch4仍有55次非法BIO转移，沿用丢弃非法I的解码，未启用此前退化的强制修复。实际dev错误包括CNNs截短为CNN、GoogleNet/ResNet被截短标为DATASET、MobileNet类别误判、任务漏识别。AI标签本身也可能遗漏或边界不一致；当前标签/分数冻结保存，不根据预测反向修参考以抬分。

## 关系与整体系统仍未完成

新合同允许实体完整train中逐对使用已复核正/负例，UNRESOLVED屏蔽。本次形成17条train正关系（EVALUATED_ON11 / USED_FOR6），**没有明确NO_RELATION负例**。合格NER文档内未决train1,091 / dev421；这是入选NER文档的分母，不混同33轮全部37篇的1,119与本轮全部19篇的656。

dev19篇的全部候选包含USED_FOR9 / EVALUATED_ON2 / UNRESOLVED656，但有正例的文档仍未完成所有关系判定，按完整文档评估合同不得直接采用。train完整RE文档只有Fashion-MNIST，dev只有ITO；两者均没有合法方法—任务/数据集实体对，**0对不是模型高分证据**。实际relation_dev为空，`relationTrainingReady=false`；本轮没有训练RE、没有四种NER×RE对照，也没有新的pipeline成绩。

保留19篇摘要test内容未用于标注、分词、推理或训练，只有源包完整性哈希检查；旧09/17/29测试结果没有重跑。候选没有通过完整晋级验收：`qualityPromotionPassed=false`、`modelPromoted=false`。线上仍31轮graphId `ai-literature-ed16399925fac2a599ed`、旧题名模型；无数据库写入、服务重启或推理覆盖。作者身份和概念继续采用31轮保守归一，不新增模糊合并。

下一步：在train/dev源文中明确关系证据与范围内负例，保留不能判定的对；关系准入满足后执行同dev交叉对照与端到端误差归因，再锁整个pipeline和最终测试入口。目前不需要用户手工标注，也不以伪负例凑样本。

## 复现与证据

所有输出目录必须是新目录。复用现有已冻结dev标注与输入可训练另一个开发运行，但不能覆盖本轮结果：

```powershell
& '.\.venv-validation\Scripts\python.exe' -B -m pytest tests -q
& '.\.venv-training\Scripts\python.exe' -B scripts/train_abstract_ner.py --snapshot kg_datasets/dblp/course_abstract_v1_inputs_20261008_35 --dev kg_datasets/dblp/course_abstract_dev_reviewed_20261008_35 --output kg_datasets/dblp/course_v4_runs/NEW_ABSTRACT_NER_DEV
```

代码入口：[course_abstract_v1.py](../scripts/course_abstract_v1.py)、[train_abstract_ner.py](../scripts/train_abstract_ner.py)、[契约回归](../tests/test_abstract_v1.py)。全量363工程检查通过，不是363项语义验证。

产物为 `kg_datasets/dblp/course_abstract_dev_reviewed_20261008_35`、`course_abstract_v1_inputs_20261008_35`，训练在 `course_v4_runs/abstract_ner_development_20261008_35`，含逐步日志、逐轮结果、最佳权重、重载校验、dev逐文预测/错误和源码绑定。机器核验：[verification_20261008_round35.json](../kg_datasets/dblp/course_v4_runs/verification_20261008_round35.json)。

截图：[真实产物可视化](evidence/20261008_round35/09_annotation_expansion.png)，原页与来源快照/哈希同目录保留。它是浏览器渲染实际结果文件的截图，不是训练现场或Neo4j应用界面，不能用它宣称新图已经入库或独立人工核验通过。

# 课程交付冻结与唯一一次题名扩充实验

2026-10-10。本文件为交付状态和实验收尾记录，不是最终课程报告。按用户确定的边界：不新增标注、不更换架构、不继续摘要研究，仅训练一次扩充题名NER与RE，再在原验证范围比较并停止。使用MLE工作流提前锁定输入、规则及生产保护文件；没有新增服务或部署候选模型。

## 冻结的在用系统

- 应用入口保持 `scripts/course_quality_app.py --port 8765`；沿用原本已配置的连接方式，不在本记录保存密码。
- 在用配置 `resources/course_graph_quality_v3_runtime.json`；58版图 `ai-literature-63686318d85cccb07afb`，20,000文献、194,597节点、263,059关系、21,497候选断言。
- 生产NER仍为08开发运行 `checkpoint_epoch_04`，RE仍为15开发运行 `checkpoint_epoch_03`。新实验没有修改生产指向、重启服务或写数据库。
- 实验末尾只读HTTP检查返回 `ready`、上述graphId及 `liveImportCompleted=true`。这不是再次完整应用终验；原综合验收记录继续保留。
- 旧题名测试NER F1 **74.37%**、端到端关系F1 **60.07%**保持封存历史成绩。下面的新旧对照均为开发集，不得把新开发分数与旧测试分数直接比较。

## 实验边界与真实训练

隔离目录：[outputs/title_expansion_once_20261010](../outputs/title_expansion_once_20261010)。本工作区没有Git仓库，使用独立产物目录隔离，不声称创建了Git实验分支。

训练前的[选择与停止锁](../outputs/title_expansion_once_20261010/experiment_lock.json)绑定17版快照、原验证字节、生产文件、旧模型、脚本和配置。训练/留出样本ID、论文组ID、文献ID、文本哈希及规范化题名交集均为0。复用原收据和原Schema，不把未决关系改为NO_RELATION，不将摘要样本混入题名实验。

| 项目 | 本次实际执行 |
|---|---|
| 基础权重 | 原固定SciBERT `allenai/scibert_scivocab_uncased`、revision `24f92d32b1bfb0bcaf9ab193ff3ad01e87732fc1` |
| NER | 1,219题名、2,596实体，6轮/918步；学习率5e-5、batch8、max128、seed20261006；原严格实体micro F1选第5轮 |
| RE | 975对，6轮/732步；学习率2e-5、batch8、max128、seed20261006；原全类别macro F1选第1轮 |
| RE损失 | 沿用原逆频率加权方法，权重由扩充训练分布重新计算；不是新增加权规则 |
| 检查点与推理 | 两个最佳检查点均真实保存并重载一致；关系无标签推理重现所选开发预测 |
| 计算设备 | 原Torch2.8/CUDA、RTX4060 Laptop；NER运行158.25秒、RE116.42秒，不含外部审计与截图 |

原训练/架构/优化器/解码/评分公式保持；当前入口相对历史版本有共享评估函数和验证加固，不声称源码字节与2026-10-06训练脚本完全相同。主实验固定相同轮数，因此扩充数据同时增加了梯度步数，不是相同步数预算对照。

DATASET训练仍12个实体/12篇来源；EVALUATED_ON仍3对/2篇；明确负例35对/34篇。新增主要为METHOD、TASK及USED_FOR，不能称长尾覆盖改善。

## 同口径开发结果

NER固定167/200篇、359参考实体；完整关系固定158/200篇、157参考正关系。包含45篇没有参考候选对的文献，保留额外预测关系的误报机会；未决文献排除但保留队列分母。

| 项目 | Precision | Recall | F1 | TP / FP / FN |
|---|---:|---:|---:|---:|
| 旧NER | 73.73% | 76.60% | 75.14% | 275 / 98 / 84 |
| 扩充NER | 79.60% | 77.16% | 78.36% | 277 / 71 / 82 |
| 旧NER＋旧RE | 62.22% | 71.34% | 66.47% | 112 / 68 / 45 |
| 扩充NER＋扩充RE | 70.78% | 69.43% | 70.10% | 109 / 45 / 48 |

NER METHOD F1 78.97%→83.09%，TASK69.80%→72.47%，DATASET66.67%→33.33%（正确实体2/3→1/3）。Pipeline USED_FOR F1 66.47%→70.78%，但Recall71.61%→70.32%；EVALUATED_ON正确关系1/2→0/2。主收益是降低误报，不是找到了更多正确关系。

参考实体RE正关系F1 99.05%→99.37%，NO_RELATION召回均3/5；不能把模块高分解释为真实关系准确率。实体标注和同会话AI复核仍非独立人工金标准。

混合组合仅为诊断：扩充NER＋旧RE F1 70.78%；旧NER＋扩充RE65.88%。它们没有被用来重选训练检查点或上线混合模型，不依据这些数字追加实验。

## 停止决定

预先锁定的门槛包括NER及常见类不退化、Pipeline F1至少提升2个百分点、误报不增加、明确负例召回不下降，以及稀有类正确匹配数不丢失。

整体收益通过，但 `NERDATASETTruePositivesNotLost` 与 `PipelineEVALUATED_ONTruePositivesNotLost` 两项失败。因此 **candidateAccepted=false，productionReplacementAllowed=false，optimizationStopped=true**。权重保留为实验产物，课程交付继续使用原Pipeline，不继续重训、追加新标注、调阈值或更换架构。第6轮NER虽然DATASET识别数更高，也不允许事后改用它绕过已经锁定的选型规则。

仅一个随机种子，未建立统计显著性、重复实验稳定性或新留出测试成绩；极小稀有类分母不支持泛化结论。这次实验回答的是“扩充题名数据在固定AI参考开发集上有无收益”，答案是常见链路有收益，但存在稀有类代价，不满足完整候选资格。

## 保存的证据

- [完整比较与门槛](../outputs/title_expansion_once_20261010/comparison.json)、[全部错误账本](../outputs/title_expansion_once_20261010/pipeline_errors.jsonl)。
- 两套训练的 `steps.jsonl`、`epochs.json`、`status.json`、`development_result.json`、最佳权重与来源清单全部保留；主目录封存manifest绑定文件。
- [53项相关检查](../outputs/title_expansion_regression_20261010.xml)：0失败/错误/跳过；训练前9项检查包含在这53项中，不累加成62项，也不是53项模型语义正确性核验。
- [独立集合重算记录](../outputs/title_expansion_handoff_20261010/verification.json)：重建NER、模块和四种Pipeline集合指标，核对918/732连续步日志、梯度样本只来自train、原选型规则、保护文件及旧最终测试所有封存文件哈希。没有运行旧测试模型推理；预留摘要test仅检查二进制SHA。
- [真实浏览器结果截图](../outputs/title_expansion_once_20261010/07_relation_development.png)、[拍摄元数据](../outputs/title_expansion_once_20261010/captures.json)。截图已目视检查至来源页脚，是保存结果页面，不是原终端或Neo4j画面。

课程系统冻结的是“可使用、可溯源的候选文献检索版本”，不是“高可靠科研知识图谱”。作者未决身份、受控概念归一范围和模型局限继续如实保留；它们不再触发本次课程模型优化的循环。

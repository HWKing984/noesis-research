# V2 定向对照：实际结果

完成冻结 NER 权重的解码对照、一次 RE 加权训练，以及预先指定的 2×2 Pipeline 对照。test20 正文未读取，生产未替换。

本轮未重训 NER、未改实验用标签、未新增困难负例。另导出两项训练侧补标候选供审核，未用于本次结果。

## NER

| 指标 | 原 argmax | 合法 BIO |
|---|---:|---:|
| micro F1 | 62.07% | 62.87% |
| METHOD F1 | 73.83% | 74.80% |
| TASK F1 | 43.48% | 44.80% |
| DATASET F1 | 62.22% | 65.31% |
| 非法 BIO 转移 | 177 | 0 |

使用项目已有的最大得分合法 BIO 路径解码，没有根据 dev 实体答案编写修正规则。它只保证序列合法，不保证完整词边界或语义正确。
训练集原解码 F1=98.52%，这是训练内拟合结果。训练 65 篇和 dev 20 篇参考标签的 BIO 编码/还原均通过。
训练与 dev 的差距支持当前泛化不足的判断；不能仅凭这一实验将原因全部归于标签噪声或样本数。

## RE

| 指标 | 原损失 | 加权损失 |
|---|---:|---:|
| 三类别 macro F1 | 61.90% | 62.81% |
| USED_FOR precision | 89.08% | 89.24% |
| USED_FOR recall | 100.00% | 98.47% |
| USED_FOR f1 | 94.22% | 93.62% |
| EVALUATED_ON precision | 77.61% | 77.61% |
| EVALUATED_ON recall | 100.00% | 100.00% |
| EVALUATED_ON f1 | 87.39% | 87.39% |
| NO_RELATION precision | 100.00% | 33.33% |
| NO_RELATION recall | 2.08% | 4.17% |
| NO_RELATION f1 | 4.08% | 7.41% |

加权组固定训练 6 轮/378 步，按相同三类别 macro F1 规则选择第 5 轮，重载预测一致。
相同 seed=20261011、SciBERT 基座、学习率、批大小和采样顺序。权重来自训练组频次：USED_FOR 0.42687、EVALUATED_ON 2.88506、NO_RELATION 3.21795。
每个样本交叉熵乘固定类别权重后取批均值。没有同时改变采样、补负例或调整置信度阈值。

## Pipeline：同一 dev 的条件范围

| 组合 | P | R | 条件 F1 | 候选对 | 输出正边 | 拒绝对 | 未决匹配掩码 |
|---|---:|---:|---:|---:|---:|---:|---:|
| argmax_NER_original_RE | 12.46% | 42.17% | 19.24% | 1320 | 1239 | 81 | 180 |
| legal_NER_original_RE | 11.61% | 45.69% | 18.51% | 1539 | 1443 | 96 | 211 |
| argmax_NER_weighted_RE | 12.88% | 41.53% | 19.67% | 1320 | 1184 | 136 | 175 |
| legal_NER_weighted_RE | 11.97% | 45.05% | 18.91% | 1539 | 1381 | 158 | 203 |

关系参考覆盖率仍为 361/974=37.06%；613 对未决，完整端到端 F1 保持 null。精确匹配未决对的预测被掩码；非参考实体端点按严格 AI 参考跨度计错。
所有分数都是已暴露 dev 的 AI 参考匹配，不能当作独立测试或与 V1 旧题名成绩直接比较。四个组合全部报告，未选最高数冒充正式成绩。

## 训练侧定向复核

原训练解码共有 28 条 FP/FN 跨度记录；大多是模型未学好的边界，不能反过来把标签改成模型预测。
- 保留 `offline knowledge base construction` 的 offline 修饰语。
- 保留 `fine-tune the model's responses` 整体跨度，拒绝拆成 fine- 与 tune…。
- 保留 `identifies predictive features`，不把后面的 that 包入实体。
- `cognitive` 出自 cognitive science 的片段，不能据此补成 METHOD。
- SQuAD 的 `answer the questions` 与 PET 的 `imaging` 导出为 TASK 补标候选。
候选副本包含 65 篇、943 个实体；重建新增 10 个合法实体对，全部先标 UNRESOLVED。原 674 对已裁决标签保留。本轮训练没有使用该候选副本。
- `entity and relation encoders` 涉及并列方法粒度，留待定向裁决，未强行补标。

## 下一步边界

合法 BIO 消除非法转移，但无法单独解决泛化与误配对；类别加权的实际作用见上表，不能假定它已经解决负例问题。
后续数据工作应集中于训练侧有原文依据的困难负例和 TASK 表述覆盖。不能将 dev 错误答案直接回流训练，也不能批量把 UNRESOLVED 改成 NO_RELATION。
本轮结果和权重封存。V1 同口径比较、NER 迁移初始化和 LLM 证据核验未在此轮执行。
原始 ner_decoder_result 的 train 指标内部沿用通用 evaluationTarget 字符串；其外层 evaluationScope 明确为 in_sample_training_label_diagnostic，本报告按训练内诊断解释。

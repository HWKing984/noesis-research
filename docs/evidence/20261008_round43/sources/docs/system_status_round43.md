# 第43轮：训练侧泛化诊断与一处任务边界修订

2026-10-08。完成50篇训练摘要的两版冻结NER实际推理、16篇含DATASET原文的AI检查/同会话自复核，以及1篇训练标签的独立版本修订。**没有新训练、开发/最终测试成绩、模型晋级或线上更新。**完整课程报告继续暂停。

## 已确认的诊断结果

诊断合同先锁定41版train58篇队列、50篇合格NER、8隔离；只按语义读取训练数据，开发文件及19篇保留test仅核对二进制哈希。模型输入特征不带参考实体或标签；推理后再评分。运行22.73秒，保存逐篇预测、逐条FP/FN、聚类及环境/输入/权重/源码SHA。

| 同50篇训练数据，仅为样本内诊断 | 冻结35摘要NER | 冻结42摘要NER |
|---|---:|---:|
| Precision / Recall / F1 | 86.00% / 83.47% / 84.72% | 99.84% / 99.67% / 99.75% |
| TP / 预测 / AI参考 | 510 / 593 / 611 | 609 / 610 / 611 |
| DATASET TP / 参考 | 41 / 44 | 44 / 44 |
| TASK TP / 参考 | 149 / 189 | 187 / 189 |
| FP / FN | 83 / 101 | 1 / 2 |
| 非法BIO转移 | 70 | 0 |

**这不是新模型效果排行榜。**旧35仅训练过其中29篇，新42训练过全部50篇；不能把新42的99.75%当未见文献准确率，也不能以两个训练范围不同的样本内分数证明泛化改善。所有分数相对于AI参考，不是独立人工gold。

新42已学会训练集全部44个DATASET；对照第42轮封存dev记录的DATASET召回40%（本轮未重评），更符合泛化、分布或标签规则问题，不支持“增加训练轮数即可修复”。**这不是已经证明的唯一因果解释**，标签噪声和小样本波动仍可能参与。

训练数据共378 METHOD、189 TASK、44 DATASET；DATASET来自16篇/27个字面名称，别名尚未归一，不能称27个独立数据集。其中14/44=31.82%提及集中在同一MMLU-Pro摘要。BIO可评分token共11,220，DATASET标注142个（1.27%）；重复提及不能冒充独立论文支持。字面同名跨类冲突未发现，不意味着上下文类别和边界全部正确。

## 实际修订的一处训练错误

在看到本轮训练预测前，已读完16篇含DATASET的整篇原文并记录训练论文`2501.02474`的任务边界不一致：

- 首次`Remote sensing object detection`，原标签保留完整`0:31`。
- 后一次同样的任务短语，原标签只保留`object detection`的`377:393`；新版本改为`remote sensing object detection`的`362:393`。

本轮新42训练预测剩余FP1/FN2也全部来自这篇：首处边界截短、后处漏掉参考实体。修订依据是原文及此前记录的不一致，**不是按模型预测迁就标签，更没有改dev/test标签**。

单独合同`course_abstract_task_boundary_v1.json`限定这一个连续任务短语，不推广成所有TASK都强制取最大修饰范围。完成新的初标收据＋实际同会话复核，记录原/新收据SHA和前后跨度；源文本、样本ID、实体ID、类型与其余20个实体均不改。其他57篇收据逐行字节不变。

涉及e3的10个候选对原本全部UNRESOLVED，修订后继续未知，没有填负例或新增正边；若存在已判关系触及改动端点，入口会拒绝自动继承。其余明确关系/证据保留，再从新收据重建行和端点。当前train仍是NER50/隔离8、明确267（USED_FOR183/EVALUATED_ON58/NO_RELATION26）、未决1578/1845、完整关系6篇。

新训练快照：`kg_datasets/dblp/course_abstract_task_boundary_reviewed_20261008_43`。50篇BIO编码及保存offsets/labels的严格往返通过；开发侧文件只按原始字节复制，SHA相同。行`contractSha256`仍指父36序列化规则，训练修订合同另行绑定，不冒充已用新版模型训练。42版训练入口仍锁41版，下一次使用修订数据须另锁实验，不能直接修改历史入口。

其余源文审查中的泛化活动/一般能力/并列任务范围提醒没有强行改标签，也不直接算作已证明的错误。DATASET命名在这16篇中有原文支持，不能由此宣称全部50篇所有实体或全部2万篇数据干净。

## 验证与留痕

最终完整回归：**371通过，162.27秒，零失败/错误/跳过**，仅在D盘工作区的隔离pytest临时目录下验证。162.27秒为pytest终端总时长，JUnit套件记录162.153秒；截图/机器核验使用后者。此前43轮首次新增测试因漏设scripts导入路径而收集失败，原XML保留；已修复测试入口，单项检查通过。第一遍371项通过152.51秒先于新增跨度修订检查；最终162.27秒覆盖当前代码。C盘默认临时目录历史rename/WinError5问题未解决，不以D盘通过声称根因已修复。

封存核验重新计算两模型训练指标和全部误差行/聚类，检查57份原收据字节、50份新BIO、源参考/开发文件原样与旧模型/保留test/生产配置SHA。不是371项人工语义认证，也不是重新训练或重评dev。实际浏览器截图展示保存产物，不冒充原始终端、训练现场或Neo4j界面。

入口：[机器核验](../kg_datasets/dblp/course_v4_runs/verification_20261008_round43.json)、[诊断截图](evidence/20261008_round43/02_training.png)、[修订证据截图](evidence/20261008_round43/04_traceability.png)、[诊断结果](../kg_datasets/dblp/course_v4_runs/abstract_train_diagnostic_20261008_43/audit.json)、[修订记录](../kg_datasets/dblp/course_abstract_task_boundary_reviewed_20261008_43/revision.json)。截图实际检查并封存后机器核验才产生。

```powershell
# 只读校验与另存的训练侧诊断；现有输出不可覆盖。
& './.venv-validation/Scripts/python.exe' scripts/audit_abstract_ner_training.py preflight
& './.venv-training/Scripts/python.exe' scripts/audit_abstract_ner_training.py diagnose --output kg_datasets/dblp/course_v4_runs/NEW_TRAIN_DIAGNOSTIC
& './.venv-training/Scripts/python.exe' scripts/revise_train_task_boundary.py --output kg_datasets/dblp/NEW_TRAIN_TASK_REVISION
```

## 下一步与未完成项

优先按明确训练侧规则补独立论文、名称和上下文多样性，并解决广义TASK活动/能力边界；不要从已见dev/test选训练短语，也不凭44个重复提及盲加epoch或直接加权追分。后续训练须预先锁定修订输入、资源预算、同范围比较与稀有类召回护栏，保留当前开发记录；新修订尚无模型收益成绩。

完整EVALUATED_ON评估支持、独立参考、8篇训练隔离、模型泛化与作者/概念长尾质量仍未解决。既有完整dev EVAL0/覆盖7/19仍阻断晋级；本轮`qualityPromotionPassed=false`、`modelPromoted=false`。没有写库、服务重启或新线上验收；2万篇书目、31轮图和线上旧模型保持原样。

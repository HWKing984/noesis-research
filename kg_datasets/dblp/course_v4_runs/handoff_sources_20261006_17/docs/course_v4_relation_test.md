# 冻结RE模块与NER→RE严格测试（轮次17）

本轮完成固定RE候选的只读测试和冻结NER预测下的pipeline评估，没有训练、调阈值或再执行NER最终test。工程链路通过，但不能因固定参考实体下RE高分就称端到端可靠。下一步是可追溯候选事实入库与Neo4j应用，当前尚未完成应用验收。

## 1. 测试前约定与数据准备

RE候选在15轮已冻结：[选择锁](../annotations/course_v4/re_test_selection_20261006.json)绑定10数据、实体对表示、epoch3、258步训练和权重082e9b3b280fe2bb9f4449205c801bcccaffbf1e661572406e5cb570e4ef6da1。本轮不因测试结果替换候选。

[显式AI关系判断及逐篇自复核源码](../annotations/course_v4/test_relation_20261006.py)包含144篇固定NER可用题名的逐条关系判断及复核理由；程序只展开已写出的语义决定，不调用模型或根据类别推断正负标签。标注者为当前Codex会话，模型身份记录unknown_session_model；两轮为候选可见、同会话AI判断，不是独立模型、人员盲审或人工gold。原56篇NER未决原样继承隔离，不伪造新实体复核或负例。

标注严格沿用原实体跨度、类别、完整/未决状态和groupMentions；只做METHOD→TASK的USED_FOR、METHOD→DATASET的EVALUATED_ON及明确负例NO_RELATION。原10数据及NER封存数据不改写；新11中train/dev逐条、逐字节不变，test实体逻辑不变，但关系更新导致annotationSha256及NER test导出文件字节不同，不能误称test文件完全相同。父凭据与新任务来源分别保留。

144篇逐篇首轮及自复核完成，138篇关系完整，6篇因角色方向/证据不足仍未决；加上56篇原NER未决，62篇排除。关系判断完整的138篇包含38篇没有范围内实体对，这些不是自动生成的NO_RELATION样本。其余100篇形成137个参考实体对：USED_FOR132、EVALUATED_ON1、NO_RELATION4。例：InsectSet459只是新数据集“for bioacoustic ML”，不能据此强标实际评估；Deep Learning Meets/并列操作等不靠共现造关系。

最新[11数据清单](../kg_datasets/dblp/course_v4_training_inputs_11/manifest.json)哈希1bd4930f706a666ea681fae2a99924cfd36b9acb20b16c8c870d4e5b529d2815；累计仍908篇AI判断，NER728篇（417/167/144），RE642条（343/162/137）。没有新增论文，1092篇train仍待首轮。summary中的trainingStarted=false是封存数据导出状态，真实评估状态另存run，不回填改写。

在推理前生成[测试数据封存](../annotations/course_v4/re_test_data_20261006.json)，绑定11数据、RE选择锁、关系判断来源及原NER测试预测清单；采用138篇完整子集、严格端点匹配、不调参政策。该文件哈希3e94546f85cc0837ffc3b794966175659b641927a99db715a27eab892afcef82。之后一次实际RE CUDA运行，不反过来按成绩修订标签。

## 2. 神经网络与执行流程

RE仍使用15的SciBERT有方向头尾开始标记向量拼接，1536维→三类线性头，沿用原标记、max_length=128、batch_size=8及类型约束，无结构或权重变更。加载器严格校验完整权重、类别映射和表示配置。所有推理实体对去掉关系label，forward返回targets=None，证据理由、参考关系与标签不进入模型特征。

运行前重算保存artifact/hash、选择轮次和来源时间，核对固定train/dev、全部200篇队列、实体继承、RE判断在候选锁定之后；真实162条dev预测/指标回放一致才允许test推理。模块输入137个参考实体对；pipeline只使用原NER09冻结预测，并枚举138篇所有范围内候选对，共148条，不按参考实体对筛选预测。所有编码无截断/静默拒绝，Torch eval/inference_mode、参数requires_grad=false，无优化器/反向传播。

pipeline复用的是原144篇NER test实际预测，其中138篇满足本轮完整关系条件。**没有再次执行NER test推理或选择NER checkpoint。**它评估真实保存的NER输出经RE分类后的端到端关系，不能写成重新训练/测试了实体模型。

[最终运行](../kg_datasets/dblp/course_v4_runs/re_final_test_20261006_17/manifest.json)哈希ce9697e286c4532d9e6b18b114b7d96eae65432e5b4f3cadfbc4629b0d4191af，保留源码/配置/输入归档、设备与依赖、preflight、dev回放、所有预测、基线及错误。NR权重仍968a594de551a1ab77a263a725fcdf487b8c559539f7452e2edeb8cf62c8d996，RE权重亦与选择锁一致。

## 3. 评分与真实结果

模块以固定参考实体对的关系类别完全匹配评分，正micro排除NO_RELATION、同时报告三类混淆矩阵和负例召回。pipeline将NO_RELATION视为无边；正边必须同时匹配论文、方向、头尾字符跨度、头尾实体类型和关系类别。原文跨度错一处就不能算TP；138篇含零参考实体对论文全部计入，额外预测边计FP。不报告不明确候选全集下的pipeline TN准确率。

| 范围/方法 | Precision | Recall | 正micro F1 | 其他关键信息 |
|---|---:|---:|---:|---|
| 同137对的train类型多数基线 | 97.08% | 100% | 98.52% | 4个负例全误报 |
| 冻结RE，固定参考实体 | 99.25% | 99.25% | 99.25% | 正边TP132/预测133/参考133；137对中2个类别错误 |
| 冻结NER→RE严格pipeline | 58.57% | 61.65% | 60.07% | TP82/预测140/参考133；FP58、FN51；51篇至少一条边差异 |

| 类别 | 模块参考数 | 模块P/R/F1 | pipeline参考数 | pipelineP/R/F1 |
|---|---:|---|---:|---|
| USED_FOR | 132 | 99.24% / 99.24% / 99.24% | 132 | 58.99% / 62.12% / 60.52% |
| EVALUATED_ON | 1 | 100% / 100% / 100% | 1 | 0% / 0% / 0% |
| NO_RELATION | 4 | 75% / 75% / 75% | 不作为正边 | 8次无边决定，不报告TN准确率 |

整体覆盖138/200=69%；这是完整AI参考子集的一致性成绩，不是全部200篇、人工gold、引用推荐有效性或稳定稀有类泛化。正类占133/137，类型基线已很高；RE模块micro仅比基线高约0.73个百分点，不能包装为突破。EVALUATED_ON仅1条、负例4条，百分比分母极小；pipeline漏掉唯一评估关系，正macro仅30.26%。先前NER已暴露这些test题名与实体，本轮关系标签在RE选型后产生，但不是全新文本盲测。

## 4. 全部错误及代表性原因

模块[2条完整错误](../kg_datasets/dblp/course_v4_runs/re_final_test_20261006_17/module_errors.jsonl)不删：

- “Reasoning in Conversation …”：AI参考将Large Language Models→Solving Subjective Tasks判为USED_FOR，模型判NO_RELATION。该题名有机制/受益对象方向的解释空间，AI参考不是无争议真值；保留原判断与模型输出，不依据test成绩改标。
- “To Control Diabetes …”：ML→Calorie Measurement的AI参考为NO_RELATION（并列测量手段，非ML执行的操作），模型误报USED_FOR；ML→Control Diabetes另一个实体对不混淆。

pipeline[51篇完整差异](../kg_datasets/dblp/course_v4_runs/re_final_test_20261006_17/pipeline_errors.jsonl)保留所有参考及预测边。首个题名中的Feature Augmentation Strategies被原NER截为Feature Augmentation：关系类别即便对也因端点不一致产生FP/FN。唯一的Wisconsin diagnostic dataset被NER漏掉，故评估关系FN；原NER又把NeurIPS赛事认作DATASET，在原本零参考实体对论文上生成LLM→NeurIPS的EVALUATED_ON假边。本轮没有为了消除这些错误修改NER解码、实体边界或测试标签。

预测文件中的继承labelSource/annotationSha256标识参考实体数据来源，不是新关系的真值认证；关系label来自冻结RE分类器，pipeline端点来自冻结NER。后续入库应额外标注model_prediction、具体权重版本/原题名/字符证据，不能把这些输出直接当ai_pseudo参考标签或DBLP原始事实。

## 5. 留痕、回归与复现

[测试图12](evidence/20261006_round17/08_relation_test.png)由真实结果在Edge中渲染并检查，非原始终端或Neo4j截图。重算模块/pipeline指标、候选全集、概率、覆盖、错误清单和基线才导出；来源/页面/PNG哈希分别见[图源清单](evidence/20261006_round17/manifest.json)与[拍摄记录](evidence/20261006_round17/captures.json)。旧15图不覆盖。

[338项全项目回归](../kg_datasets/dblp/course_v4_runs/tests_20261006_round17_handoff.xml)和[全链路核验](../kg_datasets/dblp/course_v4_runs/verification_20261006_round17.json)保留。新增检查包含端点跨度错误、空参考论文的误报、非法/重复候选、伪造数据封存、禁止覆盖已有失败运行，以及重封伪造覆盖率的证据拒绝；合成单元测试不是语义准确率。

仅合并同一源码的本轮单元与实际RE只读运行：[覆盖记录](../kg_datasets/dblp/course_v4_runs/coverage_relation_combined_20261006_17.json)中评估入口语句覆盖96.28%，完整历史证据导出器59.24%。未拿旧源码训练覆盖填充新代码，也不重训/重测NER提高覆盖；这些是语句覆盖，不是全部分支或语义准确率保证。

```powershell
& '.\.venv-validation\Scripts\python.exe' -B -m pytest tests -q
# 仅供固定配置的独立复现，不用test调参；新目录，不覆盖封存17。
& '.\.venv-training\Scripts\python.exe' -B scripts/evaluate_course_relation.py --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_11 --selection annotations/course_v4/re_test_selection_20261006.json --data-lock annotations/course_v4/re_test_data_20261006.json --output kg_datasets/dblp/course_v4_runs/NEW_FIXED_RE_TEST --device cuda
```

本轮遵循MLE冻结数据与模型、PyTorch无梯度/保存加载一致性，以及Python边界回归技能；不引入新模型、服务框架或依赖。实验三训练/选型/测试流程已有真实证据，但题名弱监督与60.07%pipeline表现不能称可靠应用验收。下一阶段按[计划](course_v4_plan.md)实现候选事实的可追溯Neo4j入库和检索应用，展示来源与不确定性；不按本次test错误继续微调这组封存模型。

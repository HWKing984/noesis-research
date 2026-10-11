# 显式实体对表示单项开发对照（15）

## 训练前约定

本轮目标：减少把受保护、被调度、受益的模型错误认作任务执行者，服务于可追溯的候选文献关联查询。决策者为课程项目使用者；不将模型预测直接提升为确定事实。

假设：同一句中存在多个实体角色时，只用SciBERT pooled CLS可能不足以区分指定实体对。只改分类表示为两个开始标记的上下文向量按METHOD头、TASK/DATASET尾顺序拼接，768+768→1536，经原dropout与三类线性头。文本前后顺序不改变语义头尾。原CLS为768维；编码器、原有五个unused标记词表、类型约束和输入信息不变。不加网络层、不引入新依赖。

该表示选择参考[Soares等，ACL 2019，Matching the Blanks](https://aclanthology.org/P19-1279.pdf)中的ENTITY MARKERS / ENTITY START比较；这里只借鉴标记表示，不复现其matching-the-blanks预训练或宣称论文中的性能适用于本课程数据。

锁定数据`course_v4_training_inputs_10`（manifest SHA-256 `fc70d7865c59791dc48bc5947e54bd5e07c20cc1a08eb755fe6fdb0f009f3e09`；运行前以实际清单核对）。508/200/200篇AI判断，累计908篇；train/dev关系343/162条，来自264/113篇题名，支持316/3/24与155/2/5。没有新增标签；人工gold为false。同会话候选感知AI复核的相关误差仍存在。测试关系尚无标签，不读取关系test、不调整已冻结NER。

与14比较：相同基础SciBERT版本、seed20261006、batch8、lr2e-5、max128、6轮258步、FP32 eager、train逆频率损失、三类macro F1选epoch，平分取较早。每轮每条train实体对恰好一次。初始化头形状不同，不能宣称相同随机数流、同样逐步梯度或多seed稳定性。新表示独立从基础权重训练，不从14继续微调。

主要开发指标：三类macro F1；同时报告正关系micro/macro、各类P/R/F1及支持、混淆矩阵、全部错误。仅当三类macro严格优于14（75.6580%）、正micro不低于14（98.4227%），且NO_RELATION精度不低于50%时，才将其作为下一阶段冻结候选；不满足就保留14，不根据本轮结果反复改门槛。该条件只是有限dev的选择门槛，不是泛化/图谱事实验收。EVALUATED_ON仅2条、NO仅5条，任何提升都须披露小支持和开发选择偏差。

错误预算：不能为负类高分隐藏新增正例漏报；不允许dev/test回灌、截断静默丢样本、把未决视为负例、理由或参考标签进入模型forward、架构/词表不一致仍加载成功。成功工程检查不等于关系正确性。

MLE技能用于先声明单项假设与门槛，Python测试技能用于先失败再实现，PyTorch技能用于实际梯度、形状和安全重载一致性。复用现有训练、评估、证据生成器；不增加框架或无限堆模型。

## 实际结果

真实GPU训练完成6轮/258步，耗时89.10秒（含加载、保存和coverage，不作速度对比）。343条训练实体对每轮恰好一次，dev不参与梯度；编码器和1536维分类头均更新，保存后的模型/tokenizer重新加载，162条dev预测和编码完全一致。采用训练前约定的三类macro选择epoch3；epoch4/6指标相同，取最早3，不挑最后轮。

| 开发比较 | 正micro F1 | 正macro F1 | 三类macro F1 | NO P / R / F1 | EVALUATED_ON Recall | 错误对 |
|---|---:|---:|---:|---|---:|---:|
| 类型多数基线 | 98.4326% | 99.2063% | 66.1376% | N/A / 0% / 0% | 2/2 | 5 |
| 14 pooled CLS / epoch2 | 98.4227% | 99.2013% | 75.6580% | 50% / 20% / 28.57% | 2/2 | 5 |
| 15 头尾标记拼接 / epoch3 | 99.0476% | 83.0128% | 77.5641% | 75% / 60% / 66.67% | **1/2** | 3 |

相对14，三类macro提高1.9061个百分点，正micro提高0.6249个百分点，负例由1/5正确变为3/5；但正macro下降16.1885个百分点，EVALUATED_ON由2/2变为1/2。这不是各类均改善：多数USED_FOR掩盖了稀有评估关系的损失，必须同时报告micro、macro和逐类支持。未经校准的softmax概率不能等同正确率。

正关系TP156/预测158/参考157，P98.7342%、R99.3631%；USED_FOR参考155、预测157、TP155；EVALUATED_ON参考2、预测1、TP1；NO_RELATION参考5、预测4、TP3。Accuracy159/162=98.1481%。以下为AI参考下的混淆矩阵，不是人工gold：

| AI参考\模型预测 | USED_FOR | EVALUATED_ON | NO_RELATION |
|---|---:|---:|---:|
| USED_FOR | 155 | 0 | 0 |
| EVALUATED_ON | 0 | 1 | 1 |
| NO_RELATION | 2 | 0 | 3 |

### 六轮完整开发记录

| epoch / step | dev未加权loss | 正micro F1 | 三类macro F1 | NO TP / 参考 |
|---|---:|---:|---:|---|
| 1 / 43 | 0.090798 | 98.4326% | 66.1376% | 0/5 |
| 2 / 86 | 0.066301 | 98.4026% | 73.3073% | 3/5 |
| 3 / 129 | 0.047384 | 99.0476% | 77.5641% | 3/5 |
| 4 / 172 | 0.081431 | 99.0476% | 77.5641% | 3/5 |
| 5 / 215 | 0.114192 | 98.7342% | 71.9027% | 2/5 |
| 6 / 258 | 0.059094 | 99.0476% | 77.5641% | 3/5 |

### 全部剩余错误与角色变化

新增正确负例：Adversarial Training→Robustness Evaluation（下游应用不是直接评估工具）、Deep Learning-Based Wind Speed Prediction→Cross-Dataset Data Augmentation（受益模型不是增强工具）。原LLM→Scheduling仍正确；14的Secflh防御正例漏报也被纠正。这些题名始终只在固定dev，不加入train。

| 题名 / 实体对 | AI参考→模型 | 解释 |
|---|---|---|
| Neural Network Security…：Neural Network→Hiding CNN Parameters | NO_RELATION→USED_FOR | 原被保护对象误报仍存在，正类概率0.911893；高置信也会错误。 |
| MIHBench…：Multimodal Large Language Models→MIHBench | EVALUATED_ON→NO_RELATION | 新增稀有评估关系漏报，NO概率0.979800；对象参与评估不等于对象执行缓解任务，模型仍混淆。 |
| MIHBench…：Multimodal Large Language Models→Mitigating Multi-Image Hallucinations | NO_RELATION→USED_FOR | 原被缓解对象误报仍存在，正类概率0.657938。 |

3条错误来自2篇题名，同一MIHBench的两条错误并非两个独立文献证据。完整实体跨度、pairId、标签及概率均保留在[全部错误](../kg_datasets/dblp/course_v4_runs/re_entity_development_20261006_15/dev_errors.jsonl)。不修改dev标签来美化结果。

## 候选冻结与下一阶段

15满足训练前明确的三个开发门槛（macro3严格超过14、正micro不低于14、NO精度≥50%），因此冻结epoch3作为本版RE**测试候选**；不是确认图谱事实或可靠性证明。接受的代价是稀有评估关系损失1条，只有2条dev支持，不能声称该类稳健。选择在RE test标签产生/评估之前完成，不继续堆模型追求dev分数。

[RE选择锁](../annotations/course_v4/re_test_selection_20261006.json)保存冻结时间、配置、10数据哈希、训练前约定哈希、模型/源码清单、权重哈希及固定200篇test队列哈希。选择权重SHA-256：`082e9b3b280fe2bb9f4449205c801bcccaffbf1e661572406e5cb570e4ef6da1`；运行manifest SHA-256：`b857e74d2e66712892d45d32ccf92ae471a0878a28b0fc6174deb5ef90e156a5`。完整[实际训练清单](../kg_datasets/dblp/course_v4_runs/re_entity_development_20261006_15/manifest.json)、[指标](../kg_datasets/dblp/course_v4_runs/re_entity_development_20261006_15/development_result.json)、[逐轮](../kg_datasets/dblp/course_v4_runs/re_entity_development_20261006_15/epochs.json)、[控制台日志](../kg_datasets/dblp/course_v4_runs/re_entity_development_20261006_15_console.log)保留。

test题名及NER标签已在之前NER实验中由同一会话处理过，不能声称全新文本盲测；**RE test标签当前尚未产生，RE test指标未用于选型**。下一阶段不改这些已冻NER标签/边界、不把其未决文献变成关系空负例；根据冻结政策完成200篇RE判定和未决原因，分别计算参考实体模块、冻结NER→RE端到端的覆盖/逐类支持/严格指标。若某类为零支持则N/A，不补造测试关系。看到RE test后若改模型，需要新未暴露的测试集。

## 检查与真实截图

328项全项目回归通过，失败/错误/跳过均0，XML57.639秒，见[回归记录](../kg_datasets/dblp/course_v4_runs/tests_20261006_round15_final.xml)。额外[CPU微型模型契约检查](../kg_datasets/dblp/course_v4_runs/re_entity_contract_20261006_15_final.json)使用合成张量，验证文本双顺序仍头→尾、目标不传forward、类型mask、编码器/头梯度、安全保存重载、6种畸形/遮蔽标记和架构/词表错配拒绝；不把合成张量当课程训练标签。[当前加载器重载旧14模型](../kg_datasets/dblp/course_v4_runs/re_entity_cls_compat_20261006_15.json)的dev预测与原封存逐条相同。

TDD先发现未实现配置/模型，再实现；微型重载检查还发现默认SDPA与eager计算路径会破坏逐值一致性，统一为课程已锁定eager后通过，没有放宽成“近似相等”。截图生成器新增表示与封存checkpoint配置绑定检查，防止用CLS结果冒称实体对模型。[同源码覆盖](../kg_datasets/dblp/course_v4_runs/coverage_re_entity_combined_20261006_15_final.json)结合10项单元、微型契约检查与15真实GPU训练：关系入口308/325条语句94.77%，新模型28/28条100%；未宣称完整分支覆盖或语义准确率。旧coverage不合入新行号。

![图9：CLS与显式实体对表示开发对照](evidence/20261006_round15/07_relation_development.png)

图注：同一10数据、逆频率损失及三类macro选型，14为历史CLS运行、15为本轮新GPU训练；不是本轮重训两组。15选epoch3，负例正确3/5，整体错误3条，但EVALUATED_ON召回仅1/2。真实保存结果由Edge截图并视觉检查，非原始终端或Neo4j界面；仍为参考实体dev和AI标签，非RE最终test或端到端。旧12张图保留，累计13张。来源见[源包清单](evidence/20261006_round15/manifest.json)、[拍摄记录](evidence/20261006_round15/captures.json)、[图注](evidence/20261006_round15/report_figures.md)。封存源包pending不改写，captures.completed才证明实际截图完成。

[全链路核验记录](../kg_datasets/dblp/course_v4_runs/verification_20261006_round15.json)：166个运行目录1120个封存输出、96份归档输入源码、10个数据导出版本88个文件、21个原始输入及13张PNG来源/图像哈希通过。原883份凭据前缀、dev/test与09逐字节、冻结NER权重/最终测试清单未变；训练前约定→训练→冻结的时间顺序和选择锁所有绑定均核对。核验时259个本地报告链接有效；此后追加本核验链接，数量另行检查。未将关系最终测试或应用记作已完成。

### 复现（必须指定新目录）

```powershell
& '.\.venv-training\Scripts\python.exe' -B tests/check_course_relation_entity_model.py
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_relation.py --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_10 --model kg_datasets/models/scibert_24f92d32 --output kg_datasets/dblp/course_v4_runs/NEW_ENTITY_RE_DEV --device cuda --balanced-loss --selection-metric all_class_macro --representation entity_markers
& '.\.venv-validation\Scripts\python.exe' -B -m pytest tests -q
```

当前入口默认`--representation cls`保持历史行为。实体对checkpoint必须使用共享`load_relation_model`读封存配置，不能用原生CLS或AutoModel忽略自定义表示后继续推理；源码已随15清单归档。冻结后新训练只能是另一个开发版本，不替换本版测试选择锁。最终RE/端到端和Neo4j仍未完成，未预写成功。
> 轮次16审计补充：严格权重/标签映射加载及无标签推理路径已修复，实际162条dev回放与本文封存预测完全一致，未重训或重测test。当前334项回归；本文原训练源码/权重/成绩仍保留历史身份。详见[复核记录](course_v4_audit.md)。


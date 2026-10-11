# 实验二：SciBERT train/dev 候选训练与结果（2026-10-06）

本文保留08开发训练当时的范围和状态。后续09已冻结该epoch4完成最终NER测试，最新标签、成绩和截图见 [最终测试报告](course_v4_ner_test.md)；下文“test未标注/未评估”均指08运行时，不改写历史输出。

已实际完成基于 `course_v4_training_inputs_08` 的 397 篇训练题名、167 篇验证题名、6 个 epoch / 300 个更新步。最佳 checkpoint 为第 4 轮，验证集严格实体 P/R/F1 为 **73.73% / 76.60% / 75.14%**。同一划分的训练跨度词典 F1 为 27.83%。这些是相对于 AI 参考标签的验证一致性，不是最终测试或人工 gold 成绩。

## 1 任务和方法选择

DBLP 的作者、论文、场馆、年份来自结构化字段；自然语言题名中的方法、任务和命名数据集没有现成的同等字段。本实验学习它们的连续原文位置与 METHOD / TASK / DATASET 类别，之后由关系模型判断“方法用于任务”“方法在数据集上评估”，用于术语检索和候选参考文献发现。识别出一个术语不证明论文实际使用它，关系仍须证据；是否适合引用需阅读原文。

沿用固定 SciBERT 英文科学语料编码器，12 层、hidden size 768，末端为 token 分类头，输出 7 类 BIO：O、B/I-METHOD、B/I-TASK、B/I-DATASET。整个编码器与分类头均更新。损失为 token 交叉熵，特殊 token 和 padding 的 label 为 -100，不计入损失；优化器 AdamW，weight decay 0.01，梯度范数裁剪上限 1.0。未加入 CRF 或 joint 关系头：当前明确采用 pipeline，先完成 NER 再训练关系模块。本次没有 BERT/CRF 对比，不能宣称 SciBERT 是全局最优架构。

模型固定为 `allenai/scibert_scivocab_uncased`，revision 为 `24f92d32b1bfb0bcaf9ab193ff3ad01e87732fc1`。基础权重 SHA-256 为 `e492944d88ac97dee6baa547671d3c526a3d067676883efb058311f4e5882e1a`。不执行远程模型代码；参数来自本地已验证文件，而非浮动 latest。

## 2 数据与标注过程

原始 DBLP AI 候选集为 20000 篇，先按论文组固定划分，再选定首批 1600/200/200 标注队列。历史已暴露候选和近重复不跨 split。2000 是预算目标，不是课程强制标注量，也不是已经全部标完。

本轮匿名批次 019 新增 25 篇 train，初次判断与候选可见 AI 自复核分别保存：24 确认、1 修订。修订把 Joint Relational Co-evolution 的方法身份保留未决，不把“没标方法”当完整答案；Graph and Recurrent Neural Network 共享中心词进入并列挑战集，不补造原文不存在的 Graph Neural Network。IWSLT'16 的事件/数据角色不明，不为增加 DATASET 数量强制定类。

累计 683 篇完成两轮 AI 判断，483 train / 200 dev / 0 test；其中 564 篇 NER 可用，515 篇满足关系导出条件，有合法实体对的文本实际导出 477 条关系输入。实体未决 118 篇、关系未决 167 篇、并列挑战 4 篇；按任务分别隔离。还有 1317 篇待首轮，其中 train 1117 / test 200，dev 队列已处理完但未决仍不用于训练。

| split | NER 题名 | METHOD 跨度 | TASK 跨度 | DATASET 跨度 | 关系样本 |
|---|---:|---:|---:|---:|---:|
| train | 397 | 460 | 346 | 12 | 315 |
| dev | 167 | 208 | 148 | 3 | 162 |
| test | 0 | 0 | 0 | 0 | 0 |

每条完整实体标注包含原文、Unicode [start,end)、类别及版本绑定凭据。来源保持 `codex_session / unknown_session_model`、`ai_pseudo`；第二轮看到了候选，不是独立盲审、独立模型核验或人工 gold。确认比例不代表语义准确率。

来源：[019 首轮判断](../annotations/course_v4/batch019_generation_decisions.json)、[019 自复核](../annotations/course_v4/batch019_review_judgments.json)、[08 导出统计](../kg_datasets/dblp/course_v4_training_inputs_08/summary.json)、[初次快照及复核凭据](../kg_datasets/dblp/course_v4_training_inputs_08/receipts.jsonl)。旧 01–07 原样保留。

## 3 实际执行步骤

1. 检查来源清单哈希，重新验证所有凭据，将 train/dev 输入逐条与可用凭据绑定；未标注/未决不转换为空负例。
2. 固定 WordPiece tokenizer，保留原始 Unicode offset，无截断；检查每个实体边界是否恰好与 token 边界对齐。564 篇全部通过，最长 train/dev 为 33/32 token，拒绝 0。
3. 仅由 397 篇 train 的跨度创建词典，642 个无类别冲突词组；最长非重叠匹配，在同一 167 篇 dev 上计分。dev/test 标签不用于补词典。
4. 从固定基础 SciBERT 初始化新 token 分类头；新头权重未在预训练权重中初始化的提示是预期现象，不是已有 NER 模型成绩。
5. 固定 seed 20261006、batch 8、learning rate 5e-5、max length 128、6 epochs。RTX 4060 Laptop GPU / CUDA 12.6，确定性 eager FP32，关闭 TF32，记录实际依赖版本。没有早停、学习率搜索或调度器，6 轮候选按预先设置全部跑完，不保证已找到最优超参数。
6. 每轮只遍历 train 一次，末批 5 篇；50 步/轮。逐步记录 loss、gradient norm、sample IDs；每轮 dev 在 eval/no_grad 下评估，dev 不回传梯度。
7. 用严格实体 micro F1 选最佳 checkpoint，相同分数取较早 epoch。保存改善轮 1/2/4 的 safetensors 与 tokenizer，不覆盖历史权重。
8. 重载第 4 轮 checkpoint，167 篇 dev 的实体预测与保存前完全一致；编码器/分类头在训练末与选中权重中都确实变化。保存完整 dev 预测和 76 篇错误案例。没有 tokenization、训练或评估 test。
9. 运行结束再次检查数据、源码、契约和基础权重哈希，封存输出清单及小型来源文件副本。未实现断点续训；重跑必须新目录。

状态中 `trainingStarted=true`、`developmentTrainingStarted=true`，而 `formalTrainingStarted=false`、`testEvaluated=false`。这里 formal 指完整课程实验的最终评估流程，不能据该 false 误解为没有实际梯度更新。数据导出 summary 的 `trainingStarted=false` 是生成时的封存快照，不修改它来写实时状态。

## 4 验证结果及基线比较

严格实体匹配要求同一文档、起止位置、类别均完全一致，不是 token accuracy。空类 precision 可为 N/A，不把零预测伪造成 100%。非法 orphan I 不自动修成 B；记录并丢弃该非法延续。

| epoch | step | dev token loss | dev P | dev R | dev F1 | 保存改善权重 |
|---|---:|---:|---:|---:|---:|---|
| 1 | 50 | 0.51841 | 61.82% | 66.30% | 63.98% | 是 |
| 2 | 100 | 0.49186 | 71.07% | 70.47% | 70.77% | 是 |
| 3 | 150 | 0.81777 | 63.59% | 63.23% | 63.41% | 否 |
| 4 | 200 | 0.64004 | 73.73% | 76.60% | 75.14% | 是，最终选中 |
| 5 | 250 | 0.76430 | 77.22% | 72.70% | 74.89% | 否 |
| 6 | 300 | 0.76845 | 71.80% | 76.60% | 74.12% | 否 |

选择依据是实体 F1，不是 loss，所以第 2 轮 loss 较低也没有选中。保留后续成绩下降，不能说训练越久越好。验证 loss 的回升提示过拟合或优化波动的可能，但仅凭这一轮不能判定唯一原因。训练曲线展示 300 个实际未平滑 batch loss，并不是 dev loss 曲线。

| 模型/类别 | AI参考跨度 | TP / 预测数 | P | R | F1 |
|---|---:|---|---:|---:|---:|
| train 词典，micro | 359 | 75 / 180 | 41.67% | 20.89% | 27.83% |
| SciBERT epoch 4，micro | 359 | 275 / 373 | 73.73% | 76.60% | 75.14% |
| METHOD | 208 | 169 / 220 | 76.82% | 81.25% | 78.97% |
| TASK | 148 | 104 / 150 | 69.33% | 70.27% | 69.80% |
| DATASET | 3 | 2 / 3 | 66.67% | 66.67% | 66.67% |

本次神经模型与词典可以比较，因为使用相同 train/dev 及严格实体指标；dev micro F1 相差约 47.31 个百分点。但这是单次 seed、dev 选型结果，不是显著性检验，不是最终 test 泛化证据，更不是 AI 伪标签的真实语义正确率。DATASET 的 dev 只有 3 个跨度，训练仅 12 个，数值不能用于声称稳定泛化。

## 5 错误分析与局限

完整保存顺序中的首个错误题名为：`Molecular Dynamics Simulations on Cloud Computing and Machine Learning Platforms.`。AI 参考含 TASK `Molecular Dynamics Simulations` 与 METHOD `Machine Learning`；模型只预测 TASK `Molecular`，表现为目标边界截短及方法漏检。第二个例子的 `CMDPs` 被截为 METHOD `CM`，是子词边界和类别错误。它们是真实保存结果，不是编写的演示数据。

最佳 epoch 有 82 次非法 BIO 延续，76/167 篇至少存在一个跨度/类别差异。严格匹配会把边界差异计为 FP 和 FN；不能仅展示容易的正确例子。错误也可能包含 AI 参考本身的概念/类别问题，未经独立语义审核不能都断言是模型错。未知参考不在评估中，排除未决题名导致评估子集选择偏差。

目前未标注 200 篇 test，NER/关系最终 readiness 仍为 false；DATASET/EVALUATED_ON 15/5 仍偏少。下一步按既定规范补充剩余训练与封存测试参考，不用 test 结果修改提示、边界或超参数；完成一次性最终评估后再训练关系模型、测 NER→RE 端到端 pipeline、导入候选图谱并实现检索应用。关系样本的 477 条不是已训练的 RE 模型成绩。

## 6 真实证据与可直接使用的图

![6轮训练与验证选型](evidence/20261006_round08/05_development.png)

图注：固定论文组划分下，SciBERT 在 RTX 4060 上对 397 篇 train 进行 6 轮微调，用 167 篇 dev 的严格实体 F1 选择第 4 轮权重。表中保留所有 epoch、分类支持及首个真实错误案例；75.14% 为 AI 参考标签下的 dev 选型成绩，不是最终测试准确率。图片是保存结果的实际浏览器可视化截图，不是训练现场终端或 Neo4j 界面。

- [实际训练状态与时间](../kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/status.json)：2026-10-06 01:17:24–01:21:53 UTC（北京时间 09:17:24–09:21:53），总流程 269.45 秒，包含预检、词典、训练、评估、保存及哈希；不是纯 GPU kernel 耗时。
- [全部 epoch 指标](../kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/epochs.json)、[300 步原日志](../kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/steps.jsonl)、[最终选型结果](../kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/development_result.json)。
- [167 篇 dev 真实预测](../kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/dev_predictions.jsonl)、[76 篇错误](../kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/dev_errors.jsonl)、[同划分词典基线](../kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/dictionary_dev_metrics.json)。
- [最佳 safetensors](../kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/checkpoint_epoch_04/model.safetensors)，437356364 bytes，SHA-256 `968a594de551a1ab77a263a725fcdf487b8c559539f7452e2edeb8cf62c8d996`；[运行封存清单](../kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/manifest.json) SHA-256 `be3e49a72ac661f1ab118d83b96655198c6170c422ddfac45e53dc509bdb5054`，来源副本在运行目录 inputs/。
- [5 张报告图与图注](evidence/20261006_round08/report_figures.md)、[页面及来源清单](evidence/20261006_round08/manifest.json)、[真实拍摄时间和 PNG 哈希](evidence/20261006_round08/captures.json)。图2/3/4保留历史06冒烟结果；只有图5是本轮08候选模型，不能混用权重输入版本。
- [304 项全项目回归](../kg_datasets/dblp/course_v4_runs/tests_20261006_round08_final.xml)，失败/错误/跳过均为0。NER 入口单元检查与本轮真实训练路径合并覆盖率为 [90.43%](../kg_datasets/dblp/course_v4_runs/coverage_ner_combined_20261006_round08.json)，截图导出器单元与本轮真实导出路径合并为 [84.39%](../kg_datasets/dblp/course_v4_runs/coverage_evidence_combined_20261006_round08.json)，不等于模型准确率，也不宣称全部异常分支已验证。

本次按 MLE 工作流区分来源版本、dev 选型与 test 范围；PyTorch 模式确保 train/eval 与 no_grad 隔离，Python 测试技能用新增测试先复现缺失能力再验证实现。没有新增训练框架、标注 API 或图形依赖。

交付前最终源码再次回归：[304项通过、14.15秒](../kg_datasets/dblp/course_v4_runs/tests_20261006_round08_handoff.xml)，失败/错误/跳过为0。核对147个运行目录的851个封存输出、8个导出版本70个文件、21个原有输入及5张图/源页哈希；错误的开发模型快照组合在写出任何证据前被拒绝。详见 [全链路核对记录](../kg_datasets/dblp/course_v4_runs/verification_20261006_round08.json)。

## 7 重现命令

```powershell
# 必须使用不存在的新输出路径；不覆盖任何旧模型、输入或截图。
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_ner.py fit-dev --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_08 --model kg_datasets/models/scibert_24f92d32 --output kg_datasets/dblp/course_v4_runs/NEW_DEV_RUN --device cuda --epochs 6
& '.\.venv-validation\Scripts\python.exe' -B -m pytest tests -q
& '.\.venv-validation\Scripts\python.exe' -B scripts/export_course_evidence.py --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_08 --preflight kg_datasets/dblp/course_v4_runs/ner_development_20261006_08 --smoke kg_datasets/dblp/course_v4_runs/ner_smoke_20261006_02 --smoke-snapshot kg_datasets/dblp/course_v4_training_inputs_06 --tests kg_datasets/dblp/course_v4_runs/tests_20261006_round08_final.xml --development kg_datasets/dblp/course_v4_runs/ner_development_20261006_08 --output docs/evidence/NEW_EVIDENCE
& './scripts/capture_course_evidence.ps1' -EvidenceDirectory docs/evidence/NEW_EVIDENCE
```

`--samples` / `--steps` 仅控制 smoke，fit-dev 的步数由实际 train 篇数、batch、epochs 决定。本轮为 300 步，不是 status.config 中 smoke 默认 steps=120。固定 seeds 和确定性配置不保证更换硬件/库版本后逐字相同；本轮尚未重复完整 6 轮候选训练，不能冒称已验证该模型的重复训练一致性。历史两次一致只属于06小样本冒烟。

截图脚本为 PowerShell 原生过程，完成状态以 captures.json 为准；不要把它当 native exe 后用残留的 `$LASTEXITCODE` 判断。本轮五图实际完成后，外层误用该变量报告失败，但拍摄记录为 completed，逐图 SHA 及视觉检查均通过，未覆盖或重新伪造截图。

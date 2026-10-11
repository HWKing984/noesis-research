# 实验二：NER 模型与训练链路验证（2026-10-06）

本文记录基于06版本的历史冒烟链路，以下608篇/505篇数字与“尚未dev选型”状态仅对应当时。最新08累计683篇判断、564篇NER输入，已完成397/167篇train/dev、6轮/300步候选训练及dev选型；见 [08候选训练报告](course_v4_ner_development.md)和[报告证据索引](course_v4_report_evidence.md)。本文06冒烟权重与08候选权重分开，不混用版本。

本轮完成真实 SciBERT 微调冒烟，而不是用词典或 AI 响应假装训练。正式全量训练、验证集选型和测试集评估尚未完成。标注累计仍为 608 篇，本轮没有新增标注。

## 1. 实体抽取的作用与模型选择

DBLP 作者、论文、年份、会议/期刊字段已有结构，可以直接解析；论文题名中的方法、任务和命名数据集仍是自然语言。本实验训练模型定位这些术语的原文跨度并分类为 METHOD、TASK、DATASET，为后续关系分类提供实体对，而不是把结构化 XML 字段解析冒称深度学习抽取。

选用 [SciBERT 官方模型](https://huggingface.co/allenai/scibert_scivocab_uncased)，考虑到输入为英文科学文献题名，它的科学语料预训练与本领域较匹配；这只是模型选择理由，不是优于其他模型的实验证明。本轮未做 BERT 对比实验。版本锁定为 `24f92d32b1bfb0bcaf9ab193ff3ad01e87732fc1`，不使用浮动 latest，不执行远程模型代码。

具体网络为 12 层 BERT 编码器，隐藏维度 768、12 个注意力头；末端使用 dropout 与 `768→7` 的线性 token 分类头。七类为 O、B/I-METHOD、B/I-TASK、B/I-DATASET。对非特殊 token 使用交叉熵，编码器和分类头一起更新；没有使用 CRF，也没有 joint 实体关系网络。采用 pipeline：先 NER，再将预测的实体及原文输入后续关系分类模型。[BERT 模型接口](https://huggingface.co/docs/transformers/v4.57.1/en/model_doc/bert)支持此 token 分类结构。

## 2. 数据来源与固定划分

输入版本为 `course_v4_training_inputs_06`，队列版本为 `course_v4_weak`。原 2000 篇按论文组锁定 train/dev/test=1600/200/200；目前 608 篇完成当前会话 AI 首轮与候选可见自复核，其中训练 408、验证 200，测试尚未标注。标签不是人工 gold，复核不是独立盲审。

NER 导出按实体完成状态独立筛选，未决实体与共享中心词并列挑战样本不作为全 O 负例。当前可用 train 338、dev 167、test 0 篇。训练 METHOD/TASK/DATASET 跨度为 391/286/12；验证为 208/148/3。训练集覆盖不足、验证未决样本被排除造成的选择偏差均保留披露；DATASET 尤其稀少。

训练入口先核对封存文件哈希、来源数据集清单、规范和 schema，再重新验证每份凭据；每条 NER 输入的文本、跨度、referenceSha256、annotationSha256 必须与可训练凭据完全相同。只保证文件自身哈希正确却换了答案，也会被拒绝。没有对测试题名进行 tokenization、训练或预测打分；校验读取的是固定划分/来源元数据，不用于设计新规则或补词典。

数据导出 summary 的 `trainingStarted=false` 是当时的封存数据状态，未改写。实际运行是否训练以单独实验 `status.json` 为准；本轮冒烟 `trainingStarted=true`，`formalTrainingStarted=false`，`testEvaluated=false`。

## 3. Token 对齐与词典基线

使用本地固定 SciBERT fast tokenizer，保留 WordPiece 的原文 Unicode 字符 offset。一个实体首个子词赋 B，后续子词赋 I；特殊 token 与 batch padding 标签为 -100，不参与损失。实体连续且不重叠，不能切开 tokenizer 的子词边界；超过 token 上限直接失败，不能截断后悄悄删除实体。

真实检查 train/dev 全部 505 篇：通过 505、拒绝 0，最长分别 33/32 token，上限 128。这里的通过率是对齐检查结果，不是实体语义准确率。

基线只从 338 篇 train 的已确认跨度收集词组，类型冲突词组不强行定类；在 dev 用完整词边界、大小写不敏感、最长不重叠匹配，未使用 dev/test 补充词典。词典包含 539 个词组。

| dev 严格实体指标 | P | R | F1 | 参考实体数 |
|---|---:|---:|---:|---:|
| micro | 42.20% | 20.33% | 27.44% | 359 |
| METHOD | 46.15% | 31.73% | 37.61% | 208 |
| TASK | 23.33% | 4.73% | 7.87% | 148 |
| DATASET | 无预测，未定义 | 0% | 0% | 3 |

指标要求同一文档中起止位置和类别全部相同。全空分母不虚构 100%。这些是相对留出 AI 参考标签的一致性，尚不能作为人工核验的准确率。证据：[预检](../kg_datasets/dblp/course_v4_runs/ner_preflight_20261006_01/preflight.json)、[词典指标](../kg_datasets/dblp/course_v4_runs/ner_preflight_20261006_01/dictionary_dev_metrics.json)、同目录逐篇预测和清单。

## 4. 真实 GPU 冒烟

独立 `.venv-training` 使用 Python 3.12.4、PyTorch 2.8.0+cu126、Transformers 4.57.1；本机 RTX 4060 Laptop GPU，CUDA 12.6。系统 Python 和 `.venv-validation` 未替换。具体依赖见项目根目录 `requirements-training.txt` 与实装快照 `requirements-training.lock.txt`。PyTorch CUDA 安装组合来自[官方版本说明](https://pytorch.org/get-started/previous-versions/)。

只从 train 选 24 篇，优先确保三类至少出现，再使用固定随机种子补齐，因此不是随机代表性评测集。原文实体共 46 个：METHOD 27、TASK 18、DATASET 1。学习率 5e-5，AdamW、weight decay 0.01、batch 8、梯度裁剪 1.0、120 个更新步（24 篇分三批，约 40 轮），FP32 eager attention。seed=20261006，固定 Python/NumPy/PyTorch 随机种子，启用确定性算法并关闭 TF32 和 cudnn benchmark。[官方随机性说明](https://docs.pytorch.org/docs/2.8/notes/randomness.html)仍不保证跨硬件或依赖版本的逐位一致。

每步保留样本 ID、loss、梯度范数。解码不把孤立 I 自动修成 B：记录非法转移并丢弃该孤立 I；只有类型一致、间隙为空白的合法 I 才续接跨度。模型保存为 safetensors，随后重新加载，比较同一批训练文本的实体预测。

首次真实运行耗时约 110.10 秒：评估态 token loss 从 2.143906 降至 0.000197605，严格训练内实体 P/R/F1 均为 1.0，非法 I 从 254 降至 0；编码器和分类头均变化，保存重载后实体预测逐条相同。预设门槛为 loss 不高于初始一半、训练内严格实体 F1≥0.90、编码器/头确实更新、重载预测相同，全部通过。

这是小样本过拟合验证：只证明训练、梯度、解码、保存重载链路正常，**不能写成“测试准确率 100%”或“正式模型已完成”**。它与上面 dev 词典基线用的是不同数据，不能以 100% 对 27.44% 宣称模型效果胜出；DATASET 仅 1 个训练内跨度尤其不能说明泛化。

首次运行保留于 `ner_smoke_20261006_01`。发现内部指标沿用了公共 helper 的 held_out 名称，虽然外层已明确 in_sample，但仍改正命名并另建复跑版本，不改写旧实验。旧训练入口源码另存为 `ner_smoke_20261006_01.trainer.py`，哈希与旧清单一致。首次 coverage 命令的 source 参数错误，没有采集有效覆盖率，不能计入覆盖率证据；GPU 训练日志本身有效。

规范复跑版本为 [ner_smoke_20261006_02](../kg_datasets/dblp/course_v4_runs/ner_smoke_20261006_02/manifest.json)，耗时约 100.30 秒。其样本、每步日志、最终实体预测与 safetensors 权重的 SHA-256 均与首次运行相同，最终 loss/F1 和重载检查也相同。所有指标内外均明确标为 in_sample；9 个小型源码/规范/清单输入已归档并通过哈希核对。本机两次一致不构成跨环境保证。

全项目 299 项测试通过，失败/错误/跳过均为 0。单元检查与实际 GPU 复跑合并的六模块语句/分支覆盖率为 95.17%，训练入口为 91.55%；训练入口仅单元检查约 51%，未将 GPU 路径冒称单元测试已经覆盖。证据：[smoke 结果](../kg_datasets/dblp/course_v4_runs/ner_smoke_20261006_02/smoke_result.json)、[逐篇实体预测](../kg_datasets/dblp/course_v4_runs/ner_smoke_20261006_02/smoke_predictions.jsonl)、[pytest XML](../kg_datasets/dblp/course_v4_runs/tests_20261006_round06_verified.xml)、[合并覆盖率](../kg_datasets/dblp/course_v4_runs/coverage_ner_combined_20261006.json)、[完整核对记录](../kg_datasets/dblp/course_v4_runs/verification_20261006_ner.json)。130 个运行目录的 720 个清单内输出、6 个累计导出版本及 21 个原有输入均未漂移；覆盖率不是标签或模型语义准确率。

## 5. 复现命令

固定模型目录 `kg_datasets/models/scibert_24f92d32` 含原始 config/vocab/权重/模型卡及清单；权重大小 442221694 字节，SHA-256 为 `e492944d88ac97dee6baa547671d3c526a3d067676883efb058311f4e5882e1a`，与上游 LFS 哈希相同。尚未验证其他操作系统的新安装，不将本机成功泛化为跨平台验收。

```powershell
uv venv .venv-training --python 'D:\Program Files\Python312\python.exe'
uv pip install --python .venv-training/Scripts/python.exe -r requirements-training.lock.txt

# 已有环境无需重建；NEW 目录必须尚不存在。
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_ner.py preflight --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_06 --model kg_datasets/models/scibert_24f92d32 --output kg_datasets/dblp/course_v4_runs/ner_preflight_NEW
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_ner.py smoke --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_06 --model kg_datasets/models/scibert_24f92d32 --output kg_datasets/dblp/course_v4_runs/ner_smoke_NEW --device cuda
```

输出目录存在则拒绝覆盖，CUDA 指定但不可用则失败，不伪装 CPU 成功；异常保留 failed 状态与原因。运行前后复核输入哈希；新版本归档小型源码、规范与清单，权重、预测及日志各有哈希。当前只支持新目录重跑，不支持断点续训；课程正式训练再按实际需要增加该功能。

## 6. 当前能写入报告的结论

“本实验采用 SciBERT token classification 及七类 BIO 标签，对固定论文组划分的 AI 参考标注进行严格字符跨度对齐，建立训练词典基线，并在 RTX 4060 上完成 24 篇训练题名的真实过拟合冒烟，验证了参数更新、实体解码及保存重载的一致性。该验证不替代留出集评估；正式深度学习效果须在训练补标、dev 选型和一次性 test 评估后报告。”

按 MLE/PyTorch 工作流将数据预检、train-only 冒烟和正式留出实验分开；按 Python 测试技能验证内容绑定与边界。后续顺序：继续补训练队列，按既定规范生成封存测试参考标签；正式 NER 仅由 dev 调参；关系模型分别测参考实体与预测实体 pipeline；最后将模型候选及证据接入 Neo4j 和查询应用。本轮未训练关系模型、未写数据库、未完成实验二正式成绩。

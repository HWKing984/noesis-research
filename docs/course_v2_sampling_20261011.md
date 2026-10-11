# V2 实际选样清单与训练负例筛查

本批完成真实元数据清单与可重放选样，不是模型实验，也不是课程最终报告。按ML数据准入规范，不把元数据锁定当作标注完成，不把AI候选裁决当作人工金标准；不修改V1或已有六个核心JSONL。

## 实际完成的两项数据工作

### 1. 训练侧12篇负例筛查

逐篇读取已有原始整篇摘要，按既定宽口径检查否定、不适用和排他约束，保存12条筛查理由。没有恢复此前撤回的RL/DDCSR分工负例，也没有把599条未决转成负例。原文低分、一般局限、没有谓词以及训练数据用途均不能自动作负例。

发现一个需进一步裁决的候选：`2008.10400`中`pooling → MNIST`，原文`pooling is not used`明确否定其在所述CNN结构中的使用，第一句则明确CNN在MNIST上的结果。候选单独保存原文Unicode偏移、METHOD/DATASET端点、否定句及评测句。

关键反方意见：否定语法针对CNN结构，尚不是独立的pooling–MNIST评测否定。是否足以排除整个摘要范围的评测归属，需要作用域裁决。本批只建议`NO_RELATION`，仍`pending_scope_adjudication / candidateEligible=false / trainingAuthorized=false`；不修改原`UNRESOLVED`，不宣称已获得可靠训练负例。

实际新增：1条待裁决候选，接受负例仍0。复核入口为最终包的`negative_review_queue.csv`，完整档案为`negative_candidates.jsonl`；12篇筛查理由为`negative_screening.jsonl`。

### 2. 新评测元数据总体与选样

来源只使用[arXiv官方cs.AI 2025年2月列表](https://arxiv.org/list/cs.AI/2025-02)，固定有限时间/类别总体，不代表全部AI、arXiv或DBLP。实际GET两个元数据列表页面，2000+1654条；只解析题名与规范arXiv身份。没有请求任何新论文的`/abs/`、`/pdf/`、`/html/`正文或含摘要的API。

| 元数据步骤 | 数量 |
|---|---:|
| 原始来源记录 | 3,654 |
| 排除已知规范身份曝光 | 57 |
| 额外隔离历史题名匹配 | 18 |
| 最终有限候选总体 | 3,579 |
| 固定新验证身份 | 20 |
| 固定新测试身份 | 20 |
| 挑战集 | 0，本批没有构建 |

题名只做保守隔离，不把同题名直接认定为同一作者/论文。历史未映射的14,575条仍未完成权威身份消歧，元数据检查不证明近重复或语义独立；原文绑定和近重复复核尚未完成。

固定种子`20261011`，规范身份升序后按`random.Random(seed).sample`均匀无放回选取40篇，前20dev、后20test。实际选样Python3.14.7；协议、方法、种子、原始页面、排除清单、总体与成员哈希随包保存。各单独拆分的设计纳入概率为`20/3579`，只针对这一个有限总体。40篇小规模候选不保证稀有类支持或统计检验能力。

总体规范JSON SHA：`2cc1211ed512b609d1c9417e10d1d39c85d906e2f836223bbda454aa5aa30489`。

选样规范JSON SHA：`f5259768a07be236755f4d5c778309bb69558eb59ddbc4daa51846705ba47a2c`。

## 协议修订与初次清单保留

先按v1规范身份规则得到3,597候选、20dev/20test。追加元数据题名比对发现18条仍与历史书目同题名；初次40篇均未命中。没有看新摘要、标签或模型输出。为保守排除已知风险，明确制定v2题名隔离协议并重新抽取，不静默删样本或改种子。

初次包`course_v2_sampling_20261011`原样保留；当前唯一准入包是`course_v2_sampling_20261011_final`。v2复用初次真实GET页面并保留原抓取时间/页面SHA，不把缓存重放记作一次新网络采集。协议修订发生在元数据采集后、任何新原文访问前；两次清单及差异随审核包交付。

官方旧短月份路由`/2502`实际返回404，改用同一月份的官方`/2025-02`路由成功；没有通过GitHub代理请求arXiv，没有因此换月份或总体。

## 当前准入入口与验证

元数据入口是`course_v2_sampling.prelock`，最终内容入口是`course_v2_sampling.finalize`。新入口必须复算实际来源页面、总体、历史隔离、固定种子抽样与成员集合，单独传一个`samplingFrameLocked=true`不够。旧生成器与旧布尔接口只重放历史，不作为当前新成员准入。

最终清单是`train12 / dev20 / test20`，仍`pending_content_binding / evaluationAuthorized=false`。后续真实内容须经同一抽样清单入口绑定准确SHA、来源及近重复复核；最终评价仍需要完整参考与单独执行授权。新20篇测试摘要继续封存，本批未读取。

本批24项选样/筛查定向检查加34项既有准入检查，58项实际通过，0失败/错误/跳过；没有重跑旧整套239项。旧239项运行证据仍封存在父包。实际来源页面、3,579条总体、40个抽样身份已通过基础Python只读重放。测试数量不表示语义正确率。

最终受控58项运行ID为`03f68466-044c-4dbc-a013-e3a6897fa1fe`，Python3.12.4/pytest9.0.3，实际退出码0，收据计时3.549376秒；固定58个唯一测试标识及55份源码SHA，保存命令、起止时间、JUnit与实际日志于`outputs/v2_sampling_20261011_checks/`。这是实际执行记录，不以调用者提供的通过XML作为准入依据。最终清单另经Python3.12.4与基础Python3.14.7只读重放，结果相同。

父包130类约束也实际重放通过。已安装Edge真实结果截图已生成并目视核对，130,815字节，SHA-256为`ca80b1d252bcb114bbaf258ddd88da545428d8b0b37a40706e203e5998190394`，截图收据另存，不重签已封存的数据manifest。

## 可以直接复核的文件

- `sampling_protocol.json`：v2有限总体和选样规则。
- `sampling_frame.json`：实际页面、总体/上下文/选样哈希、数量与概率。
- `population.jsonl / excluded_population.jsonl`：纳入总体与75条排除/隔离记录。
- `selected_members.json / evaluation_lock.json`：40个新身份及12个旧train身份。
- `negative_review_queue.csv / negative_candidates.jsonl`：唯一候选及正反论据。
- `sources/`：两页真实列表及冻结历史书目CSV。
- `audit_parent/`：此前准入审核包原字节拷贝，含130类重放和239项历史运行证据。

查看：[可复核选样包](../outputs/v2_sampling_audit_20261011.zip)、[元数据审核清单](../outputs/v2_sampling_evidence_20261011/selected_metadata_review.csv)、[负例复核清单](../kg_datasets/dblp/course_v2_sampling_20261011_final/negative_review_queue.csv)、[实际结果页](../outputs/v2_sampling_evidence_20261011/09_annotation_expansion.html)。结果页是数据生成的浏览器留痕，不是Neo4j或训练现场截图。

解压后在包根目录执行：

```powershell
python -I -B kg_datasets/dblp/course_v2_sampling_20261011_final/source_snapshot/scripts/prepare_v2_sampling.py --verify kg_datasets/dblp/course_v2_sampling_20261011_final
```

预期`status=passed / eligiblePopulationCount=3579 / metadataMembers=40 / train12/dev20/test20`；`contentBindingCompleted / evaluationAuthorized / trainingAuthorized / semanticIndependenceProven`均false。初次包可用其自身的旧源码快照重放，不能使用当前生成器混验历史版本。

## 剩余实质工作

先裁决该候选，必要时只在训练侧定向寻找明确否定/排他证据；再采集并完整标注固定dev摘要，测试摘要留待独立封存标注流程，不进入模型选择。仍需足够的负例、稀有类别来源与完整评测参考，才能授权一次受控SciBERT训练。

本批没有训练、推理、测试内容解析、模型晋级、图谱入库或在线Neo4j验收，没有新Precision/Recall/F1。AI筛查是AI参考证据，不是独立人工金标准。

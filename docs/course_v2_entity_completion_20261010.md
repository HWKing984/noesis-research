# V2首批：实体完整性、关系作用域与证据保留导出

本批完成4篇摘要遗漏补标、全12篇候选对重建和V2独立候选导出。所有判断仍为AI伪标签；8篇继承上一版完整性判断，4篇在本批按明确范围作全文复核。没有新训练、推理、准确率或生产替换。

当前状态：`entity_completion_and_role_export_done_negative_scope_pending_not_training_ready`。

## 本批范围与接口

依据用户提供的独立审核，修复原版实体不完整、ID迁移风险、负例作用域过窄、旧导出丢失角色与证据等问题。只新增V2生成器、契约、4篇明确补标决策和对应测试；旧生成器、训练器、模型、图与应用不改。采用MLE workflow的数据契约与泄漏检查要求：角色/证据分组用于审核与分层统计，不作为推理时无法获得的输入特征。

- [锁定契约](../resources/course_v2_entity_completion_v1.json)
- [4篇原文补标与排除理由](../annotations/course_v4/v2_entity_completion_decisions_20261010.json)
- [生成与导出脚本](../scripts/complete_v2_evidence_pilot.py)
- [本批测试](../tests/test_v2_entity_completion.py)
- [完整输出目录](../kg_datasets/dblp/course_v2_entity_completion_20261010/summary.json)

## 1. 实体完整性修订

| 论文 | 旧提及 | 新提及 | 旧候选对 | 重建候选对 | 核心补标 |
|---|---:|---:|---:|---:|---|
| 2008.10400 | 8 | 18 | 12 | 45 | 卷积/全连接层、pooling、旋转/平移、增广目标和集成描述 |
| 2501.02474 | 21 | 22 | 110 | 121 | 背景方法deep learning；组件输出名词/性能指标明确排除 |
| 2501.06756 | 14 | 19 | 40 | 78 | 通信韧性/图韧性测量目标、扩散与反馈机制 |
| 2312.03556 | 18 | 28 | 77 | 180 | 生成模型family、微调、cross-attention/denoising/encoder组件、任务短称 |

总提及151→177，新增26：METHOD新增20、TASK新增6、DATASET未增加。当前METHOD99、TASK58、DATASET20。不能把补组件实体描述成“补充了长尾数据集”。

保留所有旧边界与类别，通过`(start,end,text,label)`锚点迁移旧关系，而非沿用旧ID。新ID仍按原文顺序连续编号。全文、排除理由、原有/新增提及和Unicode偏移见[实体复核文件](../kg_datasets/dblp/course_v2_entity_completion_20261010/entity_review.md)；[ID迁移账本](../kg_datasets/dblp/course_v2_entity_completion_20261010/entity_id_migrations.jsonl)可独立比对。

完整性是当前标注范围下的AI判断，不是外部人工认证。特别是输出对象与操作任务、背景定义与任务名称的粒度仍需要审核；排除理由公开，不能靠程序偏移通过宣称语义没有遗漏。pooling被否定不影响实体提及，但不能推导使用关系；Fiedler value是指标，不当方法；CelebAHQ-IDI作为训练数据仍不能推导评测。

## 2. 作用域与关系重建

`USED_FOR`统一为**原文明确归属于该方法主体的用途或目标**。背景用途、代理训练、组件操作、下游应用都可以表达该关系，但必须保留角色；不能从整体方法、上位类别或组件共现自动继承。

原有5条`NO_RELATION`依赖“直接执行者”的窄义对比，而不是否定统一用途范围，故保留原标签、单独标记`pending_direct_indirect_negative_scope`，**不导出为普通RE训练目标**。这是隔离，不是把它们认证为负例，也不是偷偷改为未决。

全部499个旧候选判断和支持内容原样迁移。增加实体后重新枚举合法方向，候选总数499→684；185个新增对全部为`UNRESOLVED`，没有通过实体共现自动补边。

| 标签 | 本批审核账本 | 候选RE导出 |
|---|---:|---:|
| USED_FOR | 63 | 63 |
| EVALUATED_ON | 17 | 17 |
| NO_RELATION | 5 | 0（争议隔离） |
| UNRESOLVED | 599 | 0（掩码，不当负例） |

关系导出80对来自11篇有正例论文；USED_FOR来自10篇、EVALUATED_ON来自5篇，交集4篇，合并11篇。这里按二次审核修正原文误写的10篇，旧数据和已发ZIP未覆盖。80不是新增80条事实，也不是80个独立实验；来自旧4篇隔离文献的28个已判正例此次才获得实体完整性候选资格。与上版57候选相比，是去掉5争议负例、纳入28既有正例。

任务角色统计：下游54、组件4、训练代理3、背景2；17评测标为`not_applicable`。用途17个支持组、评测8个支持组，**分组不等于独立事实**，重复提及仍存在。

## 3. V2独立候选导出

- [NER候选](../kg_datasets/dblp/course_v2_entity_completion_20261010/ner_candidates.jsonl)：12篇、177提及。
- [RE候选](../kg_datasets/dblp/course_v2_entity_completion_20261010/re_candidates.jsonl)：80有证据正例，保留taskRole、supportGroup、predicateSpans、attribution、negativeBasis及来源收据SHA。
- [全量关系审核CSV](../kg_datasets/dblp/course_v2_entity_completion_20261010/relation_review.csv)：684对，包含新增标记、候选资格和隔离原因。
- [关系完整账本](../kg_datasets/dblp/course_v2_entity_completion_20261010/relation_ledger.jsonl)：保留实体锚点、旧ID、原证据、上下游收据绑定。

每条候选均为`trainingAuthorized=false`。导出只证明字段、来源和资格规则完整，**没有锁新的训练/验证/测试选型协议，也没有准入训练**。全篇RE均为部分监督；不能因为有80条已判，就在完整评测里忽略599未决对。

## 4. 检查、截图与独立复核材料

[71项相关检查](../outputs/v2_entity_completion_verified_20261010.xml)通过：32项本批＋23项上一版＋16项首批准备，不累加重跑次数。覆盖12篇旧判断守恒、4篇ID迁移、候选宇宙重建、新对未决、错误来源/偏移/角色/证据拒绝、争议负例与静默漏导出拒绝、文件保护及读取范围。

使用本机既有SciBERT tokenizer真实检查全部12篇BIO编码/解码往返与80条关系标记编码，无截断；原分词与V1编码器复用。移除审计元数据前后模型features一致，未把角色或谓词标签泄漏给模型。这里只运行tokenizer，未加载模型作预测、未训练。

最终输出另作重新读取与导出逐项比对，重新解析两份打包的原始HTML，核对摘要与身份，并验证完整requests文件SHA。审核子目录`audit_sources`包含上一版refs/收据/账本/契约/manifest、两份原始页面/采集manifest/采集契约/请求记录、39项旧JUnit、本批71项JUnit和用户审核文件。缺失的历史字段仍为缺失/显式null，不伪造。

[一键审核压缩包](../outputs/v2_entity_completion_audit_20261010.zip)包含当前目录全部数据与来源副本、截图及收据；zip内清单文件和截图SHA均已重新校验。外部可复核数据/来源证据，不包括模型权重、整个历史工程或运行中的Neo4j实例。

[真实浏览器结果截图](../kg_datasets/dblp/course_v2_entity_completion_20261010/09_annotation_expansion.png)已保存并目视核对；[截图收据](../kg_datasets/dblp/course_v2_entity_completion_20261010/captures.json)标明这是实际数据页面渲染，不是原训练终端或Neo4j界面。

6个V1保护文件的当前SHA与上一版一致；V1训练/导出代码没有编辑。身份元数据隔离冲突0，仍未解析保留test正文，不宣称所有语义近重复已经排除。保护SHA是项目侧本机核对记录，打包并不让外部审核者凭空复现数据库或模型运行状态。

初轮预检69通过/1失败已留在[preflight JUnit](../outputs/v2_entity_completion_preflight_20261010.xml)：测试误把忽略标签-100当预测BIO类；只修测试，将特殊token映射O后完成真实往返。第二次70通过，补静默漏导出检查后最终71通过；未覆盖失败记录。环境初探错误路径/基础Python缺jsonschema，切回既有`.venv-training`/`.venv-validation`，没有安装新依赖。

## 5. 尚未结束的事项

1. 5个角色对比负例必须在统一作用域下再裁决：找到真正否定用途的证据才可准入，否则明确撤回/继续隔离。**当前接受负例为0**，不能说负例不足已解决。
2. 对新增185对按原文继续判断，不用UNRESOLVED填充NO_RELATION；优先能提供新独立语义证据的候选，不靠重复提及增样本。
3. 之后才能锁V2独立验证与最终留出协议、数据分组/去重策略和预定选型门槛。首批是已暴露TRAIN定向样本，不能转作独立最终测试。

本批按数据修复计划完成；V2仍`not_training_ready`。不扩论文、不改生产、不新增模型实验；最终课程报告仍由用户单独撰写。

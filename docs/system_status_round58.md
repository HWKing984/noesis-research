# 第58轮：现成模型同口径对照与概念图上线

2026-10-10。本轮继续已有课程系统，不写完整实验报告，不要求人工标注。AI参考标签仍披露为AI辅助判断和同会话复核，不改称独立人工金标准。

## 已落地的系统变化

概念v3在v2基础上只增加三组有本地证据的METHOD别名：LoRA/Low-Rank Adaptation、RAG/Retrieval-Augmented Generation、Random Forest/Random Forests。38组受控规则累计减少42个概念节点，本轮新增减少3个。GRU/CRF仍是提案；QLoRA、AdaLoRA、DoRA、RankRAG、RAG-Token/Sequence及具体模型版本不合并，不跨METHOD/TASK/DATASET合并。

所有原文字面提及、Unicode偏移、候选断言、模型来源及作者署名均保持。新图经过离线全节点/边映射核对，再以独立graphId真实导入，918批、无数据库重置，旧图保留：

- 在用graphId：`ai-literature-63686318d85cccb07afb`。
- 20,000文献，194,597节点，263,059关系，21,497候选断言。
- 节点：Publication20,000 / Person75,155 / Venue3,205 / Concept29,836 / Mention44,904 / Assertion21,497。
- 图包manifest SHA256：`393069faa8091c9def9d57e935ba433a95db407386697d3ecd17fb05afd45574`。
- 实际导入收据：`kg_datasets/dblp/course_v4_runs/concept_import_20261010_58.json`。

`resources/course_graph_quality_v3_runtime.json`已显式绑定新图。历史`course_graph_quality_runtime.json`保持第51轮原字节，用于已有训练来源绑定。只读应用保留v2兼容入口，服务器启动时校验并固定词表，健康接口、中文术语和检索aliasVersion使用同一v3快照，请求不再重复hash整包。当前页面：<http://127.0.0.1:8765/>；本轮没有启动8766。

33次真实HTTP检查及22组独立离线graph oracle查询对照通过：新别名分别命中LoRA1、RAG8、random forest7篇候选文献；旧CNN367，模型版本、同论文同方法联合检索、14条撤稿/通知题名信号及9条更正题名信号、详情与局部图提示、400参数拒绝和注入边界通过。数量是当前候选索引覆盖，不是领域总文献数或正确率。

新图manifest和resolution中的`liveDatabaseImported=false`是离线生成时的来源记录，保持原样；当前实际入库以独立导入收据和HTTP健康接口`liveImportCompleted=true`为准，不回填历史manifest。

## 现成GLiNER并未优于项目SciBERT

固定GLiNER medium-v2.1权重revision `40ec419335d09393f298636f471328b722c6da9e`、三种标签描述、默认0.5阈值、flat NER，未搜索提示/阈值。在与52版完全相同的16篇摘要开发文本上做零样本抽取，再接同一冻结57版RE，在相同7篇完整关系开发文档上比较：

| 配置 | Precision | Recall | F1 | TP/预测/参考 |
|---|---:|---:|---:|---:|
| SciBERT52 NER | 70.41% | 75.00% | 72.63% | 138/196/184 |
| GLiNER NER | 66.29% | 32.07% | 43.22% | 59/89/184 |
| SciBERT52 + 冻结57RE | 33.52% | 70.24% | 45.38% | 59/176/84 |
| GLiNER + 同一57RE | 0.00% | 0.00% | 0.00% | 0/50/84 |

独立重算确认0分不是缓存、分母或参数错误：GLiNER严格命中TASK为0/53；84条正参考关系中，45条只覆盖正确方法头、39条两端都不匹配，两端均正确为0，忽略类别仍无双端跨度匹配。比如额外包含“task”、把全名和括号缩写并成一个跨度，或将ResNet识别成DATASET。关系分类不能补回NER漏掉的端点。它并不是把所有候选都预测为NO_RELATION。

相同配置显式重放的raw NER、映射NER、两组RE预测、token长度五项输出与首次成功运行逐字节相同。本队列最长265词、含标签310子词，无本队列截断；参考实体无超过12词的跨度，仍须披露模型通用max_width=12限制及fast tokenizer字节回退警告。

只有这一个固定配置比较，不能推论所有预训练模型都差。SciBERT本身已是预训练模型上的领域微调；本轮GLiNER零样本不能替代课程已有真实训练实验。其外部预训练与项目文本是否重叠未知。NER覆盖16/19，完整Pipeline覆盖7/19，完整EVALUATED_ON正例仍0；没有消费预留最终测试、重新训练或更新生产题名权重，`qualityPromotionPassed=false`保持。

本轮运行直接绑定实际权重与输入哈希，并独立追加官方Hugging Face revision/LFS哈希和本地下载收据核对，检查通过。后补Python/protobuf/CUDA/GPU及helper清单明确标为post-run provenance，不能冒充推理时完整环境封存。旧评分helper嵌套的held_out字符串原样留存，展示明确使用exposed-dev，而非最终测试。

## 作者长尾：补了来源，未强行认人

复核57轮修正过的4条候选，实际对一条姓名连字符变体采集8份HTTP/robots记录及两条Crossref出版商元数据。Thanh Trung Huynh / Thanh-Trung Huynh与EPFL信息一致，但两条记录没有ORCID或人员唯一标识，不能据此证明同一身份；DBLP/ORCID的robots限制未绕过，EPFL人员页404保留。

本轮身份新增0，主页匹配66,093，未决署名9,062，全部保持隔离。9,062是未决署名节点，不是已确认的不同作者人数。

## 工程、失败记录与截图

概念迁移/应用相关65项、现成模型16项固定夹具测试通过。模型入口单元+实际固定重放行覆盖116/121=95.87%，不是分支覆盖或模型正确率。

首次GLiNER缺protobuf的失败目录保留；依赖单独安装在`.runtime-gliner`，未修改旧训练环境。最初coverage source参数错误导致无数据，不能算成功采集；正确重放另存。D盘runs内临时目录使一项“外路径”单测的夹具实际上合法，失败时执行了同一固定配置；失败XML/产物保留，仅在限定conftest夹具中使用独立虚拟ROOT，原封存测试和生产guard不改。没有拿失败重跑搜索参数。

首次HTTP验收指向未启动8766，连接拒绝收据保留；后续8765成功另存。初次全套485项为468通过/12失败/5错误，根因只有旧runtime配置被52/53/56训练快照锁定，而新切图修改了它。未变动训练数据/旧代码/封存manifest/哈希guard；恢复51配置精确SHA，新应用独立v3配置，新增配置隔离回归与旧boundary4项通过，再进行全套复验。最终33/22在线复验绑定新入口SHA并确认未漂移。

Chrome连接工具拒绝写当前工作区，没有成功截图；改用已验证的本机Edge CDP脚本，未改历史helper或任何PNG。实际1440/768/375截图通过无横向溢出、结果和表单标签检查，并已逐张目视核对。切换独立配置后的三张截图与切换前逐字节相同，另存最终capture记录，绑定新appSHA；前版捕获入口源码留在旧截图目录。模型证据页初次1300px截图截断页脚，保留原图，另存2100px完整图并目视核对；它是保存产物的真实浏览器渲染，不是GPU终端或Neo4j现场截图。

证据索引：

- 最终实际应用截图：`docs/evidence/20261010_round58_live_cdp_v3config/search_1440.png`、`search_768.png`、`search_375.png`及`captures.json`。
- 模型完整截图：`docs/evidence/20261010_round58_model/capture_full/03_predictions.png`。
- 模型原始结果：`kg_datasets/dblp/course_v4_runs/pretrained_ner_comparison_20261010_58_ready`和`...58_replay`。
- 保存预测自检：`annotations/course_v4/check_pretrained_ner_20261010_58.py`；下载来源核对：`check_pretrained_download_20261010_58.py`。
- 作者来源：`kg_datasets/dblp/course_v4_identity_evidence_20261010_58`。
- 最终在线验收：`kg_datasets/dblp/course_v4_runs/concept_app_acceptance_20261010_58_v3config.json`，包含runtime配置SHA与末尾未漂移检查。

最终完整Python回归487项全部通过，499.48秒，0失败/错误/跳过，见`kg_datasets/dblp/course_v4_runs/tests_all58_v3config.xml`。Native Node界面检查1项通过，覆盖清单快照导出、字面文本、移除/清空、过期搜索、permalink及有向路径说明；浏览器I/O在该Node测试中是stub，不能冒充真实下载终验。第一次485项失败记录原样保留；没有删测试或skip来获得绿测。最终机器复核和当前源码快照入口为`annotations/course_v4/check_system_20261010_58.py`，产物在`kg_datasets/dblp/course_v4_runs/system_verification_20261010_58`。

本轮不是高可靠摘要模型升级完成。下一优先仍是独立于已暴露开发预测的TASK边界标注一致性、明确正/负关系证据与完整稀有评测支持，然后锁定新的训练/选择/最终测试流程。概念继续只接受有证据的分类型同义合并，作者等待唯一身份佐证；不靠姓名近似、增加epoch或扩大书目规模声称解决质量问题。完整报告保持暂停。

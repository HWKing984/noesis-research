# AI 弱监督数据流程运行说明

当前54轮（2026-10-09）：[关系训练结果](system_status_round54.md)已封存，一次582步、第6轮、单最终检查点；训练侧学会反例但开发退化，不采用新模型。只读预检`.venv-validation/Scripts/python.exe scripts/train_role_abstract_relation.py preflight`核验386RE/65冻结NER/333dev；不要覆盖原训练输出、回改标签或增加epoch追分。没有新的最终测试或线上验收，不重新导入，不改8765/8766和运行配置，报告仍暂停。以下53及更早为历史记录。

当前53轮（2026-10-09）：[冻结RE训练侧诊断](system_status_round53.md)已完成，数据/115对预测/12错例已经封存。只读预检`.venv-validation/Scripts/python.exe scripts/enrich_train_roles.py preflight`核验锁定70来源/11复核；不要在原53输出重跑build或诊断，也不要改标签以追分。此次没有新训练、Pipeline或线上验收，生产/质量服务配置不变；下一拟合另锁固定52 NER的新旧RE对照，不重新入库，不使用保留test或将未知变负。以下52及更早为历史记录。

当前52轮（2026-10-09）：[NER训练数据单因素实验](system_status_round52.md)已完成，运行只读预检`.venv-training/Scripts/python.exe scripts/train_boundary_abstract_ner.py preflight`可核验65NER/271旧RE；模型与输入均封存，不重复拟合或覆盖。新NER尚未晋级；生产仍原题名模型，51质量页面8766/31旧页面8765及数据库不变。本轮结果、失败采集和真实可视化截图单独保留；没有最终test或新增线上验收。

当前51轮（2026-10-09）：[质量补强版本](system_status_round51.md)单独配置在`resources/course_graph_quality_runtime.json`、应用`http://127.0.0.1:8766/`；运行`.venv-validation/Scripts/python.exe scripts/course_quality_app.py`，交互输入密码。已真实导入，不必重复入库；旧默认配置/31图/8765不变。35组类型词表用于缩写/中文检索，来源绑定；新增作者证据通过详情API及节点属性查看。没有新模型升级、最终测试、数据库重置或许可/JDK变更。以下50及更早为历史说明。

当前50轮（2026-10-09）：[现有候选系统在线工程终验](system_status_round50.md)已通过，当前7474/7687/8765运行，使用31图/原题名模型，不重新导入。用户Desktop启动的数据库进程实际使用自带JRE21；全局JAVA_HOME仍是原值，本项目未代接受许可。先关闭页面前导出候选清单，清单不跨刷新保存。下面49及更早叙述是历史状态，不表示当前仍离线。

### 正常使用和重启

1. 从Neo4j Desktop启动`AI-Literature-KG`实例，业务数据库是`neo4j`；许可确认由用户自己完成。不要再用全局Java23直接启动本实例。
2. 若8765已经运行，直接打开[应用](http://127.0.0.1:8765/)，不要重复启动。关闭服务或重启电脑后，在项目目录运行下列命令，并在隐藏提示中输入已有密码；不把密码写进文件/命令参数。
3. “题名关键词”可搜索全书目；“方法候选”支持“扩散模型”等固定中文别名。打开详情后可查看原文跨度/候选断言/DBLP、DOI入口；多跳仅局部有界路径，同方法不是引用关系。
4. 加入候选文献清单并下载JSON/TXT；JSON包含书目和模型证据，TXT是非正式草稿，引用前仍须阅读原文、核验书目信息并按课程格式整理。

```powershell
# 仅在8765尚未启动时执行；默认配置固定31图，无重导入/新训练
& '.\.venv-validation\Scripts\python.exe' scripts/course_graph.py serve
# 允许再次执行的只读图包校验；不读取最终测试内容或写库
& '.\.venv-validation\Scripts\python.exe' scripts/course_graph.py verify
# 以下是本轮已执行并封存的验收命令，原输出路径不得覆盖重跑
& '.\.venv-validation\Scripts\python.exe' annotations/course_v4/check_application_20261009_round50.py
& '.\.venv-validation\Scripts\python.exe' annotations/course_v4/check_graph_explorer_20261007_round29.py --port 8765 --output kg_datasets/dblp/course_v4_runs/graph_explorer_acceptance_20261009_50.json
& annotations/course_v4/capture_system_20261007_round29.ps1 -EvidencePath D:\a-open_source\neo4j\docs\evidence\20261009_round50 -Suffix round50 -Workflow
& '.\.venv-validation\Scripts\python.exe' annotations/course_v4/seal_application_20261009_round50.py
```

服务只监听本机，不提供账户认证、后台常驻或跨设备公网服务。终验通过的是当前候选检索工程范围，不代表模型语义可靠性或全面无障碍通过。完整报告继续暂停。

当前49轮（2026-10-09）：[固定补充开发参考与运行环境诊断](system_status_round49.md)已完成，378项D隔离回归通过。当前7474/7687/8765均未运行；本轮console启动的CLI许可检查返回未接受许可，且Java23不受支持，已正常停止。本项目不代用户接受协议或改全局JDK。先从Neo4j Desktop正常启动AI-Literature-KG；如界面要求许可，由用户确认，若仍失败保留实际错误再诊断。恢复后才用既有serve入口和隐藏密码输入做一次在线终验，不重新导入、替换权重或重跑旧test。

```powershell
# 允许重复的只读身份/哈希预检；没有摘要请求、训练或test内容读取
& '.\.venv-validation\Scripts\python.exe' scripts/prepare_supplementary_dev.py preflight
# 以下是已执行的历史命令；输出和核验已经存在，禁止在原目录重跑覆盖
# collect/review需要已有训练环境的分词器；compile只用验证环境
& '.\.venv-training\Scripts\python.exe' scripts/prepare_supplementary_dev.py collect --output kg_datasets/dblp/course_abstract_supplement_sources_20261008_49_runtime
& '.\.venv-validation\Scripts\python.exe' annotations/course_v4/annotate_supplement_20261009_round49.py --source kg_datasets/dblp/course_abstract_supplement_sources_20261008_49_runtime --decisions annotations/course_v4/abstract_supplement_decisions_20261009_49.json --output kg_datasets/dblp/course_abstract_supplement_generated_20261009_49
& '.\.venv-training\Scripts\python.exe' annotations/course_v4/annotate_supplement_20261009_round49.py --source kg_datasets/dblp/course_abstract_supplement_generated_20261009_49 --decisions annotations/course_v4/abstract_supplement_decisions_20261009_49.json --reviews annotations/course_v4/abstract_supplement_reviews_20261009_49.json --output kg_datasets/dblp/course_abstract_supplement_reviewed_20261009_49
& '.\.venv-validation\Scripts\python.exe' annotations/course_v4/seal_supplement_20261009_round49.py prepare
& scripts/capture_course_evidence.ps1 -EvidenceDirectory docs/evidence/20261009_round49
& '.\.venv-validation\Scripts\python.exe' annotations/course_v4/seal_supplement_20261009_round49.py seal
& '.\.venv-validation\Scripts\python.exe' annotations/course_v4/check_runtime_environment_20261009_round49.py
```

新dev只有部分明确关系，完整文档0/8，不接入训练/最终test/生产图。来源、标签、unknown、隔离和原始失败均已封存；机器核验通过不是质量晋级。下面48及更早命令为历史版本记录，状态以49为准。

当前48轮（2026-10-08）：[结构性弃权及47/48共同核验](system_status_round48.md)完成，376项D隔离回归通过。以下是已执行入口，输出已封存，禁止原目录覆盖重跑：

```powershell
# 只读预检可再次执行；不训练、不访问保留test内容
& '.\.venv-validation\Scripts\python.exe' scripts/evaluate_abstract_abstention.py preflight
# 下列evaluate仅供复现记录；必须另指定不存在的输出目录
& '.\.venv-training\Scripts\python.exe' scripts/evaluate_abstract_decoder.py evaluate --output kg_datasets/dblp/course_v4_runs/abstract_decoder_development_20261008_47
& '.\.venv-validation\Scripts\python.exe' scripts/evaluate_abstract_abstention.py evaluate --output kg_datasets/dblp/course_v4_runs/abstract_abstention_development_20261008_48
# 下列证据步骤已完成，原目录/核验不得覆盖
& '.\.venv-validation\Scripts\python.exe' annotations/course_v4/seal_decoder_abstention_20261008_round48.py prepare
& './scripts/capture_course_evidence.ps1' -EvidenceDirectory 'D:\a-open_source\neo4j\docs\evidence\20261008_round48'
& '.\.venv-validation\Scripts\python.exe' annotations/course_v4/seal_decoder_abstention_20261008_round48.py seal
```

47合法BIO拒绝；48只重放封存logits和完全相同候选输入的RE缓存，6实体/2对弃权不转负例，pipeline39.84%仍不晋级。无新训练/写库/服务重启/最终测试，当前生产配置不变。以下46及更早为历史运行记录。

当前46轮（2026-10-08）：[新模型固定实验和核验](system_status_round46.md)按`resources/course_abstract_benchmark_training_v1.json`执行。`& '.\.venv-training\Scripts\python.exe' scripts/train_benchmark_abstract_models.py preflight`检查封存45输入；仅新输出目录执行`train --output kg_datasets/dblp/course_v4_runs/abstract_benchmark_development_20261008_46`，已完成一次，不得覆盖重跑。`& '.\.venv-validation\Scripts\python.exe' scripts/audit_benchmark_abstract_training.py prepare`、`& './scripts/capture_course_evidence.ps1' -EvidenceDirectory 'D:\a-open_source\neo4j\docs\evidence\20261008_round46'`、`... seal`已产生真实结果截图和机器核验；374项D隔离tmp最终回归通过。新46完整F1 39.53%低于旧42同范围54.35%，不晋级/写库/消费保留test；首次入口训练前缺文件失败已留痕。以下45及更早为历史记录。

当前45轮（2026-10-08）：`expand_train_benchmarks.py preflight/collect/snapshot`复用旧下载/解析与`compile_abstract_annotations.py`、`review_abstract_annotations.py`完成四个新训练基准；[顺序、结果和失败留痕](system_status_round45.md)。先等复核manifest完成再snapshot，提前入口缺manifest失败未写输出并留存；不覆盖原复核。最终`course_abstract_benchmark_inputs_20261008_45`为NER58/4隔离、271明确/1659未决，58旧收据/267旧关系/9dev文件不改。58BIO/271标记对与373项D隔离tmp回归通过234.89秒，C历史rename未修。尚未训练/推理或产生新F1；42训练入口仍不接受新数据，后续另锁实验/预算，不改旧入口/权重/31图或消费保留test，报告暂停。以下44及更早为历史记录。

当前44轮（2026-10-08）：新增`review_train_entity_scope.py preflight/generate/review`与`patch_train_method_inventory.py --output`，原输入不覆盖；[实际顺序、结果与边界](system_status_round44.md)。初标→基础复核→独立库存补漏三个产物封存，最终`course_abstract_scope_inventory_reviewed_20261008_44`为54NER/4隔离、267明确/1647未决；6新收据/52行不变，54BIO/9dev文件原字节通过。372项D隔离tmp回归通过144.86秒，C历史rename未修。42训练入口仍锁41，不得直接用44替换旧输入；新标签未训练，没有新dev/test或线上验收，后续另锁实验和预算。旧权重/31图/保留test与报告暂停约定不变。以下43及更早为历史记录。

当前43轮（2026-10-08）：新增`audit_abstract_ner_training.py preflight/diagnose`只读train50两冻结模型、`revise_train_task_boundary.py --output`修订一处源文任务边界；新目录禁止覆盖，旧入口/模型未修改。[命令、结果与边界](system_status_round43.md)。新42样本内DATASET44/44不是泛化分数；新标签尚未训练，dev仅按字节复制、关系未知保留、50篇严格BIO通过。最终371回归在D隔离pytest tmp通过162.27秒，C默认tmp旧rename问题未修；首次新测试导入路径收集错误XML保留。下一轮须新锁合同和训练资源预算，不改历史入口追dev分，不消费test/写库/重启，报告暂停。以下42及更早为历史记录。

当前42轮（2026-10-08）：`train_revised_abstract_models.py preflight/train`已通过独立合同接入41版行（行SHA仍父36），完成NER6轮150步与RE6轮402步，均epoch6；原始日志/checkpoint和同7篇dev四种新推理对照已封存。[实际命令、指标与D隔离tmp回归](system_status_round42.md)。新组合F1 54.35%但DATASET退化、完整EVAL0/覆盖不足而不晋级；不复用旧5篇评分或消费test，无写库/重启。370回归仅在D盘隔离pytest tmp下通过（136.57秒）；C默认tmp两次rename仍失败，源码未改/无skip/原XML保留，权限根因未解决。新输出须不存在，固定运行不自动重试/改参，报告暂停。以下41及更早为历史记录。

当前41轮（2026-10-08）：`review_eval_attribution.py` 已审计锁定train/dev全部69旧EVAL，3对明确撤回至未决、1处摘录扩张，只有2篇生成新初标/实际复核收据，其余75份继承。当前train267/dev333明确，NER50/16和隔离8/3不改；369回归、66BIO/600对标记编码通过，新输出禁止覆盖。[实际重放命令、数据与留痕](system_status_round41.md)。EVAL不强制独立消融，缺必要组合/版本不填负例；没有训练/推理、新成绩、test语义或上线。旧训练入口拒绝新合同，下一步锁定新输入与对照后薄适配，不改封存入口；报告暂停。以下40及更早为历史记录。

当前40轮（2026-10-08）：`complete_dev_relations.py` 已按固定dev原文和不变实体完成11篇初判/实际复核；6篇新增93对，明确dev335/未决97，完整7/19但无完整EVALUATED_ON支持。368正式回归与严格编码通过，新输出须不存在；[实际命令、分母与截图](system_status_round40.md)。源NER/隔离/242明确对、旧包和成绩保留，组合评测/组件归属风险另记待显式撤回；无训练/推理/新分数、保留test读取或上线，报告暂停。以下为历史记录。

当前39轮（2026-10-08）：关系入口 `enrich_abstract_relations.py` 已完成四篇train逐对证据补强与实际AI自复核；明确train268对/未决1577，NER50/8隔离及原标签不改，367正式回归通过。新输出须不存在，尚未接入训练或应用；[实际命令、分母与截图](system_status_round39.md)。未运行模型、改旧dev/test、写库或重启，没有新成绩/晋级；报告暂停。以下为历史记录。

当前38轮（2026-10-08）：逐次上下文修订、两篇新的AI初标/实际复核和50篇严格BIO已完成；58篇训练队列50可用/8隔离、明确关系201对，未决1644不填负例，未重训或运行模型。本轮新入口 `revise_contextual_abstracts.py`，新输出必须不存在，尚未接入训练/应用；[实际命令、失败记录与截图](system_status_round38.md)。正式回归366通过；根目录pytest现由pytest.ini限定tests，不收集历史证据副本。旧dev/test/权重/31图与已有成绩不改，报告暂停。以下为历史记录。

当前37轮（2026-10-08）：train摘要新增19篇NER合格输入、累计48篇，真实6轮144步；固定dev NER F1基本不变，固定旧RE pipeline Precision/F1退化，候选拒绝替换；365回归通过。采集使用新 `collect_train_abstracts.py` 并按网页robots至少15.1秒限速，不运行旧32网页采集命令。旧dev、19篇摘要test、权重/图不变，未上线或写库；[复现与证据](system_status_round37.md)。以下为历史记录。

当前36轮（2026-10-08）：部分标签RE合同、明确正/负对、真实RE6轮/294步及四种dev对照已完成，364工程回归通过；新RE退化被拒绝，完整dev5/19覆盖和Recall护栏未通过。NER35冻结复用，不重新训练；test内容仍保留，无数据库写入或上线。[实际命令/错误/截图](system_status_round36.md)。以下为历史记录。

当前35轮（2026-10-08）：独立摘要合同、19篇dev AI自复核和NER开发训练已完成，363工程回归通过。train29/dev16，6轮/90步，选epoch4；同摘要dev F1=71.24%，非最终测试。RE输入仍不具备训练准入，19篇test保留；未写库或升级线上模型。[状态与命令](system_status_round35.md)。以下34及更早为历史记录。

当前34轮（2026-10-08）：默认 `course_graph.py verify/check/import/serve` 使用 `resources/course_graph_runtime.json` 锁定31轮复检图，不再默认18包；配置路径、graphId或manifest/产物哈希错误时停止。历史包显式传 `--bundle`，`export`必须指定新的 `--bundle` 目标。8765已运行时不要重复启动，当前图与模型未更新。[当前状态](system_status_round34.md)、[摘要进度](system_status_round33.md)、[下一步实验路线](model_optimization_abstract_v1.md)。29轮新留出已完成评测，以下28及更早命令/状态是历史记录，不用于重跑测试调参；报告继续暂停。

最新28完成[四实验统一报告](course_complete_report_20261007.md)、[可打印HTML](course_complete_report_20261007.html)及扩充NER/RE候选开发训练；新留出200篇标签与最终测试尚未完成，候选不晋级。当前仍使用25图谱和8765服务，4条真实只读查询及353工程回归通过。[交付与限制](course_v4_delivery_round28.md)包含截图和交付包；以下轮次为历史记录。

最新27加入22项中文术语别名及双语显示，仍使用同一25图谱包和8765端口；“方法候选”可输入“扩散模型”。使用、复现、截图与18项实际验收见[中文检索报告](course_v4_chinese_search_round27.md)，重启密码仅隐藏输入。以下为历史记录。

最新26已真实入库并完成18项HTTP验收、350回归：20,000书目/19,999模型输出/1拒绝/21,497候选断言。运行于http://127.0.0.1:8765/，密码仅隐藏输入，不写项目文件；入口须显式选择25包。新入库/重复导入回执、操作与截图见[本轮报告](course_v4_live_application_round26.md)，下文为历史操作记录，不是当前认证失败状态。

最新25冻结模型生产处理20,000篇（19,999成功/1超长隔离），44,904提及/22,574关系对；新25包192,185节点/263,059边/21,497候选断言，350回归和内容核验通过。运行命令、实际执行代码与当前契约加固的版本区别、缓存、误判及截图见[生产报告](course_v4_corpus_inference_round25.md)。未重训/改标签/改最终成绩，未真实入库，旧材料保留。下一步须显式`--bundle kg_datasets/dblp/course_v4_graph_production_20261007_25`；默认仍是历史18，认证待有效凭据。

历史24首批2,000篇两轮AI判断全部完成，待首轮0；17标签扩展快照1,530篇NER/1,357篇RE完整/1,274个对。最后392篇379确认/13修订，步骤、实际失败归档、源码和截图见[完整报告](course_v4_data_expansion_round24.md)。新17不覆盖16/11，旧dev/test与16逐字节相同、冻结权重不变；345回归和全内容核验通过，本次未训练/模型推理/写库。539篇train RE隔离另存，稀有类别未增加。11仍是RE封存评估输入，17是未来新模型可用的标签扩展，不把新输入量当旧模型训练量。下一步冻结模型生产抽取，认证不阻止推理；下文为历史运行记录。

历史17已完成[冻结RE/pipeline测试](course_v4_relation_test.md)，评估固定数据11、当时累计908篇；固定实体RE99.25%、严格pipeline60.07%、69%覆盖。入口为`evaluate_course_relation.py`，仅接受数据/选择/封存/输出路径及设备，不提供调参选项；pipeline复用09保存的NER预测，无新NER test推理。历史fit-dev训练入口仍只训练开发版本，不覆盖当前选择锁或以test调参。

轮次16[审计修复](course_v4_audit.md)已完成，334项回归与真实dev回放通过；不新增训练或最终测试。训练checkpoint默认严格检查完整权重和标签映射；基础模型初始化须显式`initialize_from_base=True`且固定来源通过验证。真实RE推理使用无label的encode_pair与forward_batch，不伪造NO_RELATION；监督evaluate_model仍需真实标签。NER最终测试禁止调参参数及其等号写法，禁用缩写。来源日期仅显式声明，不能把任意XML称为固定快照。历史复现使用归档源码，新修复使用当前源码。

本流程准备可追溯AI标签并训练课程模型，不要求用户手工标注。来源/旧包不覆盖。已完成GPU NER冒烟、08 train/dev训练、09冻结NER最终测试、10–15六组累计RE开发训练及17固定RE/pipeline测试；Neo4j应用尚待完成。不能把合成单元测试称为语义标注或模型成绩。

15仅将分类表示从CLS改为头尾标记上下文向量拼接，固定10数据和其他配置，6轮/258步选epoch3；dev负例3/5正确、正micro99.05%、三类macro77.56%，但EVALUATED_ON召回1/2。328项回归及额外模型契约检查通过。见[最新报告](course_v4_relation_entity.md)与[冻结选择锁](../annotations/course_v4/re_test_selection_20261006.json)。复现须新目录，不替换锁；无新增标签，NER不重训。

```powershell
& '.\.venv-training\Scripts\python.exe' -B tests/check_course_relation_entity_model.py
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_relation.py --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_10 --model kg_datasets/models/scibert_24f92d32 --output kg_datasets/dblp/course_v4_runs/NEW_ENTITY_RE_DEV --device cuda --balanced-loss --selection-metric all_class_macro --representation entity_markers
```

加载实体对checkpoint须使用`train_course_relation.load_relation_model`，由封存表示与marker IDs选择匹配模型；不能用原生CLS/AutoModel忽略自定义表示。训练入口仅fit-dev；17独立只读入口`evaluate_course_relation.py`及固定复现命令见[测试报告](course_v4_relation_test.md)，不虚构应用成功。

历史11数据累计908篇AI标注/自复核，进度保留于 `course_v4_training_inputs_11/summary.json`，建队列及01–10不改写。历史10补25篇train角色题名；17只补固定实体上的test关系，NER输入417/167/144、关系343/162/137，当时1092篇train待首轮。新数据不重训NER；新test annotation哈希随关系改变，实体边界不变。08的397/167篇真实NER训练及09的144篇最终NER测试仍原样封存，NER F1=74.37%，AI参考、72%覆盖、DATASET仅2。详见[NER报告](course_v4_ner_test.md)及[RE测试报告](course_v4_relation_test.md)。

## 1 生成与验证

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/prepare_course_weak.py
& '.\.venv-validation\Scripts\python.exe' scripts/prepare_course_weak.py --verify-only kg_datasets/dblp/course_v4_weak
```

已有目录不可覆盖。后续重建请指定新 `--output` 并保留旧版本。

目录中的 references.jsonl 是独立的完整参考元数据，corpus_split_manifest.jsonl 记录全 20000 篇的组与划分。jobs/generation 下每批 25 篇，只有 sampleId、text、textSha256。将实际批次内容与 ai_prompt.md、response_schema.json 一同提供给标注 AI，返回完整 JSONL。题名不作为指令，不给 AI 主题、历史候选或划分。可由当前 Codex 会话生成真实 AI 结果；批量 API 执行器另行实现，不要求用户代替 AI 标注。

legacy 保存旧 20 篇候选的原始文件、转换结果与首轮来源记录。原模型未知就写 unknown，原提示未知就写 null；导入时间不是声称已执行新模型的时间。45 个旧跨度中 1 个并列提及移入 groupMentions，其余 44 个仍是候选。两项状态 unresolved、review=null，不进入训练。

## 2 导入首轮实际 AI 结果

以下 responses 文件必须实际存在并来自本轮 AI 标注；provider/model 填真实来源，当前会话模型标识不可见时明确填 unknown_session_model。

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/import_course_ai.py import --dataset kg_datasets/dblp/course_v4_weak --responses '实际首轮响应.jsonl' --output 'kg_datasets/dblp/course_v4_runs/batch01_generation' --provider 'codex_session' --model 'unknown_session_model'
```

输出保存 raw_responses.jsonl、receipts.jsonl、review_inputs.jsonl、summary.json 和 manifest.json。脚本只导入，不声称自己调用了模型。首轮完成也未通过第二轮复核，不进入训练。

复核 AI 读取 review_inputs.jsonl；它会看到初次标注，因此报告称 candidate-aware AI review，不能称独立盲审。重新检查所有术语、跨度、未标候选与关系证据，返回完整当前标注，并原样带 reviewOfSha256。若改变答案，初次快照和来源保留，不抹掉 AI 来源。

## 3 导入复核并组装训练输入

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/import_course_ai.py import --dataset kg_datasets/dblp/course_v4_weak --responses '实际复核响应.jsonl' --previous 'kg_datasets/dblp/course_v4_runs/batch01_generation/receipts.jsonl' --output 'kg_datasets/dblp/course_v4_runs/batch01_review' --provider 'codex_session' --model 'unknown_session_model'
& '.\.venv-validation\Scripts\python.exe' scripts/import_course_ai.py assemble --dataset kg_datasets/dblp/course_v4_weak --receipts 'kg_datasets/dblp/course_v4_runs/batch01_review/receipts.jsonl' --output 'kg_datasets/dblp/course_v4_training_inputs_01'
```

多批次在 --receipts 后逐个列出复核文件；同一样本重复出现会报错，不静默选新版。历史来源、未决结果和并列挑战样本仍保留。每次输出新目录，一次版本支持首轮与一次复核，后续重标另存修订，不覆盖历史。

历史08累计来源为batch001_review至batch019_review、batch065_review至batch072_review及dataset_priority001_review，共28份批次凭据。08复用07的658篇再加入019的25篇，07复用06的608篇再加入017/018。逐层输入哈希保留，不重复列入旧样本。原2000篇内的数据集优先批次15篇没有新增论文/移动split；优先顺序不是实体标签或无偏评测证明。

原 0066/0067 各有一篇已在优先批次处理，因此此前使用 `annotations/course_v4/batch066_pending_jobs.jsonl` 和 `batch067_pending_jobs.jsonl` 的 24 篇匿名子批次。本轮原 0007/0009/0014 分别剔除已处理的 1/2/2 篇，用 `batch007_pending_jobs.jsonl`、`batch009_pending_jobs.jsonl`、`batch014_pending_jobs.jsonl` 的 24/23/23 篇子批次；其余十批使用原始 25 篇。合计新增训练 245、验证 75 篇。重放必须使用对应原始任务或子批次，不能覆盖既有记录。

历史09的pending_generation.jsonl为1117条匿名输入，全部train，字段仅sampleId/text/textSha256。09复用08全部683篇，再加入测试073–080的200篇NER凭据；关系明确未处理。最新10将09的883条累计凭据与`relation_priority002_review/receipts.jsonl`的25条新ID组装为908条，旧凭据前缀原样一致，dev/test输入逐字节不变、待首轮1092篇。已首轮但unresolved不返回pending、不当空负例；不要向同一assemble重复放入新旧同ID凭据。

NER 输入要求实体 complete、内容绑定有效、有真实来源记录、完成 AI 第二轮且无 groupMentions。关系输入还要求 relationStatus complete、全部合法候选恰好判断一次、无 UNRESOLVED。实体训练不被关系未决阻塞。整条并列挑战文本第一阶段不训练，避免只排关系却让 BIO 学习未定义的整组实体。

summary 的训练准备状态要求三个 split 都有可用样本、相关类别 support 非零。非零仅是基本覆盖门槛，不保证样本充足或效果优秀。没有标签的 job 不会转成空负例；两轮确认无实体的文本才可以成为范围内负例。

## 4 后续真实模型实验

计划阶段 3 已建立 `.venv-training`（Python 3.12.4），固定 SciBERT 权重位于 `kg_datasets/models/scibert_24f92d32`，训练入口为 `scripts/train_course_ner.py`。使用 `course_v4_training_inputs_06` 实际验证 train 338/dev 167 篇全部 token 对齐，并完成 train-only GPU 过拟合冒烟两次。规范结果为 `course_v4_runs/ner_smoke_20261006_02`；来源、网络、权重、日志、复现命令及范围限制见 [实验二训练链路报告素材](course_v4_ner_smoke.md)。不要覆盖已有输出目录，重跑须选择新的名称。

08的397/167篇对齐通过、642词组的dev词典F1=27.83%，本轮实际训练6轮/300步，dev选第4轮权重，严格F1=75.14%。保存重载一致，76篇dev错误保留。输出preflight/dictionary/epochs/steps/dev_predictions/dev_errors/development_result/manifest等，实时状态见status.json。此成绩不是test。本轮五图为docs/evidence/20261006_round08，历史四图不覆盖，复现与图注见 [报告证据索引](course_v4_report_evidence.md)。

course_weak.align_bio校验Unicode跨度、特殊token、边界截断、重叠及BIO类别，过长即失败，不静默删实体。入口支持preflight/smoke/fit-dev/evaluate-test：前三种不读取test题名用于推理；--samples/--steps仅供smoke，fit-dev步数由batch/epochs决定。evaluate-test必须提供固定选择锁，--model表示已封存development运行，继承其配置、禁止测试调参；整个test队列完成复核后，先检查train/dev未改及原dev预测重载一致，再只读推理test。词典仅用固定train跨度。summary封存状态不改，实际运行状态另存。

```powershell
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_ner.py fit-dev --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_08 --model kg_datasets/models/scibert_24f92d32 --output kg_datasets/dblp/course_v4_runs/NEW_DEV_RUN --device cuda --epochs 6
```

--output须不存在；锁定依赖见requirements-training.lock.txt。fit-dev无断点续训，重跑须fresh新目录。checkpoint按严格dev micro F1最大、平分取较早epoch；不能用test选择。09已评估但稀有类仍不足，不称全部课程实验完成。

```powershell
# 已完成本轮最终测试。下面仅原样复现，不用测试结果再选模型；输出必须是新的目录。
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_ner.py evaluate-test --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_09 --model kg_datasets/dblp/course_v4_runs/ner_development_20261006_08 --selection annotations/course_v4/ner_test_selection_20261006.json --output kg_datasets/dblp/course_v4_runs/NEW_UNCHANGED_REPRO --device cuda
```

200篇test判断原文、200条自复核、初次快照与复核均保存。相关生成/编译/导入脚本仅重放明确判断，不自行调用AI或制造语义标签。NER本版本封存；新增关系标注必须另存任务修订并保留现有未处理关系快照，组装时显式替换选定ID而非重复合并。模型改进须另建版本和未暴露新测试集，不从已见test反复获取“最终成绩”。新图包09只含最终test图，旧08五图/07四图保留。

P/R/F1 采用实体级严格跨度与类别匹配，报告名为 AI 参考标签一致性；全空样本不会虚构 100% F1。关系同时报告参考实体下的模块成绩和预测实体下的端到端成绩。不可把两轮 AI 相互同意称为人工金标准的准确率。

### 关系开发10/11（已实跑，未通过语义质量门槛）

入口`train_course_relation.py`，同一09快照315train/162dev实体对，分别来自247/113篇题名。SciBERT头尾标记分类头，仅train训练、dev选型，未读取test题名做关系推理。两组各6轮/240步，10未加权、11按train逆频率加权；均选择epoch1、dev正micro F1=98.43%，与类型基线相同且5负例全错。编码器/分类头更新与保存重载通过不等于语义验收。报告与全部错误见 [关系开发报告](course_v4_relation_development.md)。

```powershell
# 输出必须是新目录；加权对照在同一命令末尾加 --balanced-loss。
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_relation.py --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_09 --model kg_datasets/models/scibert_24f92d32 --output kg_datasets/dblp/course_v4_runs/NEW_RE_DEV --device cuda
& '.\.venv-validation\Scripts\python.exe' -B -m pytest tests/test_course_relation_training.py tests/test_course_evidence.py -q
```

该入口目前仅开发训练，**没有RE evaluate-test或端到端模式**，不能套用NER evaluate-test命令制造关系测试成绩。下一步先补train角色区分和稀有类，另建任务修订保留旧凭据；完整RE test标签在候选冻结之后独立封存。NER权重不修改。320项回归通过，图7及源文件副本保存于`docs/evidence/20261006_round11`，旧10图保留。

### 角色补样与12–14开发（已实跑）

定向训练批次文件为`annotations/course_v4/relation_priority002_generation_decisions.json`和`relation_priority002_review_judgments.json`，匿名输入在`course_v4_runs/relation_priority002_jobs/jobs.jsonl`。编译/展开/导入只重放明确AI决定，不调用模型或生成语义。复核25篇中2修订，未决不强行裁决；QuixBugs部分明确EVALUATED_ON未进入完整训练覆盖。

```powershell
# 组装新版本；不覆盖10，不重复放入已含这些ID的凭据。
& '.\.venv-validation\Scripts\python.exe' -B scripts/import_course_ai.py assemble --dataset kg_datasets/dblp/course_v4_weak --receipts kg_datasets/dblp/course_v4_training_inputs_09/receipts.jsonl kg_datasets/dblp/course_v4_runs/relation_priority002_review/receipts.jsonl --output kg_datasets/dblp/NEW_ROLE_INPUTS
# 14复现：同数据新目录，默认positive_macro保持历史行为，all_class_macro须显式指定。
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_relation.py --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_10 --model kg_datasets/models/scibert_24f92d32 --output kg_datasets/dblp/course_v4_runs/NEW_ALLCLASS_RE_DEV --device cuda --balanced-loss --selection-metric all_class_macro
```

三组各6轮/258步。14按三类macro选epoch2，负例1/5正确，同时1条正关系漏报；正F1=98.42%、三类macro75.66%，仍不称可靠关系模型。13/14实际梯度日志和各轮指标完全相同，变化仅选型/保存，不把选择改变称为训练算法改善。325项回归、同源码关系入口94.46%语句覆盖、图8留痕；细节见 [角色对照报告](course_v4_relation_roles.md)。RE evaluate-test/端到端入口仍未实现，不能把这些dev数值当最终test。

## 首批实际 AI 结果的重放

`annotations/course_v4/batch001_generation_decisions.json` 保存当前会话 AI 对原文、实体类别及关系的逐条判断；`batch001_review_judgments.json` 保存阅读候选后的 23 条确认和 2 条修订。脚本只定位明确选定的原文、展开明确写下的复核决定、校验与导入，不自动决定语义或补造复核。

重放请使用新的输出目录，不能覆盖现有批次：

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/compile_course_ai.py --dataset kg_datasets/dblp/course_v4_weak --jobs kg_datasets/dblp/course_v4_weak/jobs/generation/batch-0001.jsonl --decisions annotations/course_v4/batch001_generation_decisions.json --output kg_datasets/dblp/course_v4_runs/batch001_generation_replay_new
& '.\.venv-validation\Scripts\python.exe' scripts/expand_course_ai_review.py --generation kg_datasets/dblp/course_v4_runs/batch001_generation_compiled/ai_decisions.json --judgments annotations/course_v4/batch001_review_judgments.json --output kg_datasets/dblp/course_v4_runs/batch001_review_expanded_new
& '.\.venv-validation\Scripts\python.exe' scripts/compile_course_ai.py --dataset kg_datasets/dblp/course_v4_weak --jobs kg_datasets/dblp/course_v4_weak/jobs/generation/batch-0001.jsonl --decisions kg_datasets/dblp/course_v4_runs/batch001_review_expanded_new/review_decisions.json --previous kg_datasets/dblp/course_v4_runs/batch001_generation/receipts.jsonl --output kg_datasets/dblp/course_v4_runs/batch001_review_replay_new
```

以上重放不重新调用 AI。原始初次快照和复核修改分别保存，不能把重放次数当作独立标注次数。现有 `batch001_generation_replay` 与 `batch001_review_replay` 已验证响应文件与原编译结果 SHA-256 一致。

## 5 回归验证

```powershell
& '.\.venv-validation\Scripts\python.exe' -m pytest tests -q
& '.\.venv-validation\Scripts\python.exe' -m pytest tests -q --cov=course_weak --cov=prepare_course_weak --cov=import_course_ai --cov=compile_course_ai --cov=expand_course_ai_review --cov-branch --cov-report=term-missing
& '.\.venv-validation\Scripts\python.exe' -m pytest tests/test_course_ner_training.py -q
```

测试中的 synthetic_test、not_a_real_model、示例标注只用于校验契约，不是课程实验结果。所有历史测试也要保持通过。
# 最新18应用入口（2026-10-07）

`scripts/course_graph.py`支持export/verify/check/import/serve。当前有效包为course_v4_graph_20261007_18_final；密码隐藏交互输入，默认业务库neo4j，不是实例名AI-Literature-KG。真实认证401/0导入批次，成功检索仍待验收；不执行密码重置或数据删除。命令、图结构、失败凭据、截图及后续顺序见[应用报告](course_v4_graph_application.md)。历史训练入口不得用于再次调已封存最终test。


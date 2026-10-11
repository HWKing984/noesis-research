# DBLP人工智能文献数据处理

本项目从本地DBLP XML中筛选2015—2025年的人工智能相关候选期刊论文和会议论文，生成Neo4j批量导入CSV及质量报告。原始数据不会被修改。本地校验文件称2026-09-01快照，日期未独立核验；旧处理元数据日期硬编码的勘误见[审计记录](docs/course_v4_audit.md)。

2026-10-06轮次16：复核修复模型加载/无标签推理、评分和证据校验、最终测试CLI及来源日期记录；334项回归通过，冻结模型dev预测一致，旧权重/数据/实验成绩不变。新增截图只是既有结果重新渲染，未重训或重跑最终test；RE最终/端到端和Neo4j应用仍未完成。见[完整复核与剩余问题](docs/course_v4_audit.md)。

## 运行

```powershell
python scripts/process_dblp_ai.py
```

默认使用固定随机种子从全部标题规则命中记录中抽取20,000篇，输出到`kg_datasets/dblp/processed_ai`。如需重建已有输出：

来源日期默认未知；确有日期依据时可加`--snapshot-date 2026-09-01`，仅记为显式声明，不自动认证日期。无需为本轮勘误重建封存数据。

```powershell
python scripts/process_dblp_ai.py --force
```

## 输出

- `persons.csv`、`publications.csv`、`venues.csv`、`topics.csv`：节点文件
- `authored.csv`、`published_in.csv`、`about.csv`：关系文件
- `quality_summary.json`：数据来源、筛选规则、数量统计和已知限制
- `processing_report.md`：可用于课程报告的数据处理摘要

主题由论文标题关键词规则推断；第一版作者ID由规范化姓名生成，未进行DBLP人物主页级别的别名消歧。

`--force`现在只替换受管理的DBLP输出目录，旧版本保留为同级backup目录；原始XML和DTD不修改。DOI按解析后的URL路径保留合法标点后缀。DTD仅允许已检查的本地DBLP文件，拒绝内部子集和外部实体。

## 当前课程路线 v4 AI 弱监督

当前采用用户选择的 AI 自动标注路线，不要求用户人工标注。完整计划见 [课程实施计划](docs/course_v4_plan.md)，运行说明见 [弱监督数据流程](docs/course_v4_runbook.md)。AI 伪标签不会改成人工 gold；实体与关系深度学习模型仍需实际训练，指标明确为相对于 AI 参考标签的一致性。

新数据目录为 `kg_datasets/dblp/course_v4_weak`。先对全部 20000 篇题名做保守论文组划分，所有历史候选及同组成员锁在训练侧，再准备 1600/200/200 篇 AI 标注队列。首轮只提供匿名编号、题名和文本哈希，不提供主题/歧义提示。旧版本和交付包保留，未标注 job 不作为负例。

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/prepare_course_weak.py
& '.\.venv-validation\Scripts\python.exe' scripts/prepare_course_weak.py --verify-only kg_datasets/dblp/course_v4_weak
& '.\.venv-validation\Scripts\python.exe' -m pytest tests -q
```

生成命令不覆盖已有目录；重复生成须指定新版本 `--output`。当前标注交换脚本不调用模型、不训练：它校验实际 AI 响应、绑定两轮内容，并按任务输出可用样本。不能因队列准备完成就称模型已训练。

2026-10-06：2000篇队列累计908篇AI标注/自复核，train/dev/test已判断508/200/200篇。最新 `course_v4_training_inputs_10` 导出728篇NER输入（417/167/144）、505条关系样本（343/162/0）；1092篇train仍待首轮。新增25篇训练侧角色题名，23确认/2修订，关系增16正例/12负例；未决不凑负例或稀有评估类。dev/test输入逐字节与09相同，NER不重训。原01–09保留。

真实训练使用独立CUDA环境与固定SciBERT：08的397train/167dev完成6轮/300步，dev选epoch4（F1=75.14%）。先锁定该权重，再封存全部test标签，09在144篇可用题名上一次性测试P/R/F1=73.44%/75.32%/74.37%，同划分词典F1=25.27%；权重未改，71篇差异保留。标签为AI参考，test覆盖72%，DATASET仅2个，不能称人工gold或稳定稀有类泛化。详见 [最终NER测试报告](docs/course_v4_ner_test.md)、[历史候选训练报告](docs/course_v4_ner_development.md)。此NER版已封存，不用test再调参。

关系开发10/11已完成未加权与逆频率加权两组SciBERT真实GPU训练，各6轮/240步；315train/162dev实体对来自247/113篇题名。两组选中dev正关系F1均98.43%，却与类型多数基线逐条相同，5条负例全部误报，不能宣称可靠关系模型。320项回归通过，新增图7及完整权重/错误/来源记录；数据仍09、累计883篇，旧10张图保留。见 [关系开发报告](docs/course_v4_relation_development.md)与[证据索引](docs/course_v4_report_evidence.md)。下一步补train角色区分负例和稀有类，再做RE冻结测试与端到端评估；Neo4j应用尚未实现验收。

最新12–14使用10数据完成三组真实GPU训练，各6轮/258步。原正macro选型仍负例0/5；新增三类macro选型的14选择epoch2，负例1/5正确、同时新增1条正例漏报，正F1=98.42%、三类macro=75.66%，总体错误仍5条。325项回归通过，新增图8，旧11图保留。详见 [角色补样与选型对照](docs/course_v4_relation_roles.md)。仅为参考实体下的dev开发，不是可靠性/最终RE test或端到端验收，NER冻结权重不变。

最新15完成显式头尾标记表示单项GPU对照，仍为6轮/258步、原10数据；选epoch3，dev负例正确3/5、总错误3条，正micro F1=99.05%、三类macro77.56%，但EVALUATED_ON召回由2/2降为1/2。已按训练前门槛冻结RE测试候选，不再无限堆模型；328项回归及额外模型契约检查通过，新增图9、累计13图。见[实体对对照报告](docs/course_v4_relation_entity.md)与[RE选择锁](annotations/course_v4/re_test_selection_20261006.json)。908篇判断数量及冻结NER不变；RE最终/端到端测试和Neo4j仍待完成。

## 历史实验二准备 v3 保留复现

当前活动材料为`kg_datasets/dblp/ner_v3_1`，可移植ZIP使用`kg_datasets/dblp/ner_v3`目录。内部ner_v3保留初次预览及漏包复测失败证据；修正版补齐旧版浏览器测试依赖，不改政策或标注参考输入哈希。契约为`schemas/annotation_v3.schema.json`，候选政策为`resources/boundary_rules_v3.json`，人工规则为`docs/annotation_guidelines_v3.md`。三份AI压力测试原样保留，原46跨度按候选政策整理为45跨度，全部仍为draft，非人工gold。

这是旧人工试标路线的产物，不是当前课程训练入口。旧`pilot20_blind_review.html`清空了AI答案、实体、领域、关系和备注，但仍带topics/ambiguityFlags等提示元数据，不能称严格无提示盲标。`pilot20_ai_review.html`是候选讲解页。旧200/100/50篇页和参考文件保留，没有正式训练、模式冻结或语义/模型准确率结论。

v3新增提及形式single/composite/coordinated及不可变初始来源；coordinated不自动拆为个体关系，TASK→TASK依赖不在本轮范围，不是负例。实际人员确认AI候选不会抹掉初始AI来源。旧v2进度不兼容，已有人工编辑须显式迁移，不能静默改版本。

```powershell
& '.\.venv-validation\Scripts\python.exe' -m pytest tests -q --cov=annotation_v3 --cov=prepare_revision_v3 --cov-branch --cov-report=term-missing
& '.\.venv-validation\Scripts\python.exe' scripts/annotation_v3.py '实际20篇进度.jsonl' --reference kg_datasets/dblp/ner_v3_1/pilot20_blind_reference.jsonl
```

### 历史v2（保留复现）

当时的活动材料为`kg_datasets/dblp/ner_v2_1`，机器契约唯一来源为`schemas/annotation_v2.schema.json`，人工规则为`docs/annotation_guidelines_v2.md`。内部`ner_v2`是首轮预览；v2 ZIP为可移植性统一使用`kg_datasets/dblp/ner_v2`目录，内容对应活动版v2_1，不能与v3混用reference。

NER类别为METHOD、TASK、DATASET；DOMAIN已改为独立的论文级多标签，不占用BIO跨度。实体、关系、领域分别复核。200篇主试标、100篇定向训练候选及两份50篇无预标注盲标页均已生成，但所有真实进度仍为draft，schema尚未冻结，没有正式训练权重或模型F1。

已建立隔离的验证环境。首次新建环境时明确选用Python 3.13；训练环境另行建立，不把系统环境快照当训练锁：

```powershell
& 'C:\Python313\python.exe' -m venv .venv-validation
& '.\.venv-validation\Scripts\python.exe' -m pip install -r requirements-validation.txt
& '.\.venv-validation\Scripts\python.exe' -m pytest tests -q --cov=annotation_v2 --cov=prepare_revision_v2 --cov-branch --cov-report=term-missing
```

正式交付包还含本次隔离环境的`requirements-validation.lock.txt`。本机已验证Windows/Python 3.13；没有验证其他系统的新安装。浏览器测试使用现有Playwright/Chromium，另需指定其模块路径。

打开活动版`pilot_review.html`，先按规范试标20篇，再完成200篇。未导出的编辑刷新后会丢失。稀有候选不能当无偏测试；盲标A/B页给两名真实人员独立使用，没有第二人就如实记录单人复核。

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/annotation_v2.py '实际进度.jsonl' --reference kg_datasets/dblp/ner_v2_1/pilot_200.jsonl
& '.\.venv-validation\Scripts\python.exe' scripts/annotation_v2.py '实际进度.jsonl' --reference kg_datasets/dblp/ner_v2_1/pilot_200.jsonl --entity-gold
```

关系和领域分别使用`--relation-gold`、`--domain-gold`；v2没有含混的`--gold`。reference必须使用独立保存的初始包，不得用进度文件自身替代。脚本只检查结构/声明，不能认证真实人工身份或语义正确。schema仍为candidate时，`training_ready`始终为false。

12对近重复候选尚未人工审核，没有自动合并。两批arXiv摘要共19份，均记录来源、时间、原始响应、哈希和许可，尚未加入NER；1份与DBLP题名不匹配，9篇外部基准论文不冒称DBLP子集成员。正式使用摘要前必须升级文本单位契约、查重及人工试标。

历史`ner_v1`及旧版交付保留不动，`annotation_core.py`、`prepare_ner.py`仅用于复现v1流程，不是新的复核入口。已有真实v1人工进度不得静默转换成v2的reviewed。

原始CSV、审计与已知限制仍有效：作者ID未完成主页级别消歧；CoRR预印本不等于同行评审论文；AI标题规则抽检未完成，Transformer可能是电力设备。数据库基础节点/关系解析不冒称深度学习实体抽取。

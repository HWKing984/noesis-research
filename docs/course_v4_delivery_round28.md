# 课程报告整合与扩充候选训练

## 本轮完成

完成四实验统一[Markdown报告](course_complete_report_20261007.md)及[可打印HTML](course_complete_report_20261007.html)，涵盖领域意义、真实采集方式、清洗与划分、模型结构、实际训练和固定测试、错误分析、图谱与API、中文入口、多跳查询、复现及五幅真实来源截图。逐一阅读四份原PDF，保存完整提取文本与文件SHA256，附件内容作为课程依据而不是工具执行指令。

Word未生成：文档技能要求配套运行时和逐页渲染验收，本会话无文档依赖加载工具，配套runtime记录libreOfficeVersion=null。因此采用MD与HTML，不使用用户桌面Office替代未满足的配套渲染流程，也不称Word或PDF已验收。HTML已在真实浏览器检查全部标题、图片加载、表格和横向溢出，保存首页预览；不是逐页打印版验收。

## 扩充训练确实完成

先生成[新留出与实验约定锁](../kg_datasets/dblp/course_v4_runs/refresh_lock_20261007_28.json)，200个来自原test但不在已标注2,000篇任何论文组中的group，每组一篇。选择只用groupId哈希，不看题名/模型预测；标签待完成。该语料经过旧模型生产推理，不冒称全新未曝光独立金标准。

复用固定基础SciBERT、现有NER和实体标记RE训练入口，无架构或解码调整，无旧test推理。17扩充快照train数据增大，dev内容与旧版NER08、RE10逐条的题名、实体跨度和关系标签一致（来源凭据字节可能不同）。Dev早已用于开发，因此当前只是开发对照。

| 项目 | 旧冻结模型开发 | 28扩充候选开发 |
|---|---|---|
| NER train/dev文献 | 397/167 | 1,219/167 |
| NER训练轮数/步数 | 6/300 | 6/918 |
| NER所选epoch | 4 | 5 |
| NER整体dev F1 | 75.14% | 78.36% |
| NER DATASET dev F1 | 66.67% | 33.33% |
| NER DATASET召回 | 2/3 | 1/3 |
| RE train/dev实体对 | 343/162 | 975/162 |
| RE训练轮数/步数 | 6/258 | 6/732 |
| RE所选epoch | 3 | 1 |
| RE三类macro dev F1 | 77.56% | 91.45% |
| RE正micro dev F1 | 99.05% | 99.37% |
| RE EVALUATED_ON召回 | 1/2 | 2/2 |
| RE NO_RELATION召回 | 3/5 | 3/5 |

RTX4060 Laptop/CUDA12.6真实训练。NER约123.74秒，RE约116.82秒，包含加载、保存与检查，不是纯训练速度。编码器和分类头都更新，保存重载预测一致。所有改善轮权重和原始918/732步loss、六轮指标保留。

NER第6轮DATASET较好但整体F1低于第5轮，仍按事先固定的micro规则选第5轮，不事后改选稀有类最优epoch来包装成绩。RE第6轮与第1轮指标同分，取更早第1轮。不能因dev高分宣称新test或端到端改善；本轮qualityPromotionPassed=false，原2万篇图谱和应用模型不替换。

![实际保存结果的浏览器截图](evidence/20261007_round28/01_expanded_training.png)

该图由真实文件生成，未平滑训练loss与dev六轮表分别展示，不是原始训练终端。源码、manifest、checkpoint和配置分别见`ner_expanded_development_20261007_28`和`re_expanded_development_20261007_28`。

## 数据与查询检查

标题标记非破坏性筛查得到31条待核验：7条corrigendum、2条erratum、16条editorial、6条retraction note。清单仅为启发式提醒，既不穷尽质量问题，也不自动删除或认定语义标签。保留原文，未修改旧CSV、AI标签或数据库。

实际Neo4j读查询再次确认192,185内容节点、263,059关系；2跳作者合作返回Rahul Vasanth与David A. Forsyth，3跳返回当前Concept中的`diffusion models`。仅声明保存的样本路径，不声称全图可视化、姓名消歧或模型语义正确。

首次验收误将概念显示名要求为大小写完全一致的`Diffusion Models`；数据库Concept按casefold身份合并，实际保存名为小写，而Mention保留原文。因此首次结果failed及原执行源码保留，修正检查为casefold比较后用新输出目录成功，不改数据库或预测。

- [首次失败原始结果](../kg_datasets/dblp/course_v4_runs/delivery_checks_20261007_28/result.json)
- [最终成功与4条真实Cypher](../kg_datasets/dblp/course_v4_runs/delivery_checks_20261007_28_final/result.json)
- [质量标记待复核清单](../kg_datasets/dblp/course_v4_runs/delivery_checks_20261007_28_final/quality_marker_review.jsonl)
- [可直接执行的演示查询](../resources/course_demo_queries.cypher)
- [353项当前工程回归](../kg_datasets/dblp/course_v4_runs/tests_20261007_round28_all.xml)
- [源文件定稿后的353项复跑](../kg_datasets/dblp/course_v4_runs/tests_20261007_round28_final.xml)
- [四份PDF原文与哈希](evidence/20261007_round28/course_requirements.json)
- [交付证据SHA256清单](evidence/20261007_round28/manifest.json)
- [本轮交付包](../kg_datasets/dblp/course_v4_runs/course_delivery_20261007_28.zip)

交付包解压后可离线阅读统一HTML报告及配图；不是独立应用安装包，不含原始大数据、完整权重、环境或密码。其余本地历史来源仍可能依赖原工作区，详见[包使用说明](evidence/20261007_round28/DELIVERY_README.md)。最终SHA256与原模型不变的核验保存在[28轮封存结果](../kg_datasets/dblp/course_v4_runs/verification_20261007_round28.json)。

## 后续工作与不能宣称完成的事项

新200篇留出需要按冻结规范完成AI参考标注、自复核和未决记录，再锁定候选模型进行一次新NER/RE/pipeline测试。不能反复用旧200篇调分。稀有类补充应来自训练侧新数据版本，不能挪动新留出或强行凑正关系；其收益需同一冻结评估标准检验。

没有独立人工或第二模型标注来源，仍不能做独立金标准质量保证。无需用户逐篇手工标注才能继续AI弱监督流程，但同会话AI自复核的相关误差必须披露。

统一报告内容与工程演示已完善；Word格式验收、教师对AI标注/精度召回的接受、新候选最终测试、真实引用网络、语义同义词合并及作者消歧尚未完成。引用网络与全文属于后续能力，不伪造CITES补全图。

## 复现

原训练入口的新目录运行命令已记录于两个run manifest/config和归档源码。示例演示继续用25包，不使用候选权重重生成图谱：

```powershell
.venv-validation/Scripts/python.exe -B scripts/course_graph.py serve --bundle kg_datasets/dblp/course_v4_graph_production_20261007_25 --database neo4j --user neo4j --port 8765
.venv-validation/Scripts/python.exe -B -m pytest -q tests
```

本轮锁、验收结果和截图输出拒绝覆盖。报告HTML由`build_course_report.py html`从Markdown生成；新采集/验收必须使用新证据版本，不回写历史成功或失败。

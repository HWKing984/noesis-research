# AI-Literature-KG · 人工智能文献知识图谱

第40轮开发关系复核（2026-10-08）：固定dev中全部11篇关系未完整的合格NER摘要逐篇检查/同会话复核，6篇新增93对（57用途/36局部角色反例）；明确dev242→335，97/432对未决，完整文档5→7/19但EVALUATED_ON参考仍0。原NER/隔离/242明确标签及旧分数不改，发现组合评测向组件归属的历史风险，单独留待复核撤回。368正式回归与严格编码通过；没有训练/推理或新F1。39轮train268对、31图、旧权重和保留test不变，可靠性仍未通过，报告暂停。

> 从本地 DBLP XML 中筛选 2015–2025 年人工智能相关论文，用 **AI 伪标签（弱监督）** 训练 SciBERT 做实体抽取与关系抽取，将抽取结果作为**带证据链的候选断言**写入 Neo4j，并提供一个本地只读的文献检索应用。

- **领域**：人工智能文献检索与候选参考文献发现
- **标注路线**：AI 伪标签（`ai_pseudo`），**不要求人工标注**；AI 是标注工具，不代替深度学习模型训练
- **当前线上**：第 31 轮图谱（194,639 节点 / 263,059 关系 / 21,497 候选断言），本地应用 `http://127.0.0.1:8765/`
- **最新文档轮次**：第 40 轮（开发侧关系证据/覆盖与历史归属风险复核，未重训）
- **最新状态**：见 [docs/system_status_round40.md](docs/system_status_round40.md)；历史滚动记录见 [docs/status_log.md](docs/status_log.md)

> ⚠️ **先读这一条**：模型指标衡量**相对于 AI 参考标签的一致性**，不是人工金标准上的真实正确率。Precision、Recall、F1、support、coverage分别披露，不能互换；未校准softmax分数不是事实概率。方法—任务 / 方法—数据集关系是 `status: candidate` 的候选断言，**不是已核实事实**。

---

## 目录

1. [这是什么](#1-这是什么)
2. [当前规模](#2-当前规模)
3. [端到端数据流](#3-端到端数据流)
4. [目录结构](#4-目录结构)
5. [数据与标注契约](#5-数据与标注契约)
6. [模型与评测口径](#6-模型与评测口径)
7. [环境与依赖](#7-环境与依赖)
8. [快速开始](#8-快速开始)
9. [图谱导入与只读应用](#9-图谱导入与只读应用)
10. [测试与回归](#10-测试与回归)
11. [已知限制与边界](#11-已知限制与边界)
12. [文档与证据索引](#12-文档与证据索引)
13. [后续路线](#13-后续路线)

---

## 1. 这是什么

本项目对应课程四个实验，产物是**一条从原始 XML 到可检索图谱的完整、可复现、可追溯的数据流水线**：

| 实验 | 要求 | 本项目对应 |
|---|---|---|
| 实验一 | 采集不少于 1000 条数据 | 从 DBLP XML 按标题规则筛出 **20,000 篇** AI 相关论文 + 书目 CSV |
| 实验二 | 训练 / 验证 / 测试实体抽取模型 | SciBERT token classification，7 个 BIO 标签（METHOD / TASK / DATASET） |
| 实验三 | 关系抽取模型 | SciBERT + 头尾实体标记的分类头（USED_FOR / EVALUATED_ON） |
| 实验四 | 抽取结果入库 Neo4j + 可用的应用 | 幂等导入 Neo4j + 本地只读检索应用（`127.0.0.1:8765`） |

**它不是什么**：不是全量 AI 领域文献库，不是引用网络，也不能替你判断"某篇论文是否必须引用"（DBLP 本版无 CITES 数据）。

---

## 2. 当前规模

截至 2026-10-08（第 40 轮数据修订；最近训练为第 37 轮，线上图谱仍为第 31 轮）：

| 层级 | 数量 | 说明 |
|---|---:|---|
| 原始语料 | 20,000 篇 | DBLP 结构化 XML 解析的**书目**，标题规则筛选，不是神经 NER 输出 |
| AI 标注队列 | 2,000 篇 | 训练 1,600 / 验证 200 / 测试 200，按论文组隔离划分 |
| 训练输入（累计） | NER 1,530 篇可用 · RE 1,357 篇完整 | 两轮 AI 判断 + 同会话自复核后的可用样本；含未决与隔离集 |
| 摘要资产 | 96 篇整篇摘要 | 87 篇对应已有DBLP文献 + 9 篇 arXiv 外部基准（**仅训练侧**）；不是新增图谱论文 |
| 整篇摘要训练标注 | 固定58篇；50篇NER准入、隔离8篇，39轮实体字段不改、尚未重训 | METHOD378 / TASK189 / DATASET44；关系新复核4篇、其余54篇收据继承，非独立gold |
| 摘要明确关系对 | 39轮train268（USED_FOR183 / EVALUATED_ON59 / NO_RELATION26）；40轮dev335（259 / 10 / 66） | 仅在NER完整文档中逐对使用；train1577/1845、dev97/432对未决，不填负例；原dev242对不改 |
| 摘要验证/测试 | dev19篇已自复核，NER16篇可用、3篇隔离 / test19篇保留 | dev METHOD116 / TASK53 / DATASET15提及；测试内容未消费或推理 |
| 摘要NER候选 | 最近训练为37轮train48 / dev16，6轮/144步，选epoch6 | dev P69.79% / R72.83% / F1 71.28%；38/39轮50篇修订未训练，无新成绩或final-test |
| 摘要RE候选（36轮历史训练） | train195 / dev242对，6轮/294步，选epoch1 | 条件性dev三类宏F1 85.48%低于旧88.16%，拒绝替换；未在新335对上重训/计分 |
| 摘要pipeline对照（旧范围） | 历史完整dev5/19，含1篇零参考对；46条正例均USED_FOR | 35轮NER/旧RE F1 30.00%；37轮扩充NER/旧RE26.49%，拒绝晋级；不套用新7/19范围 |
| 最新完整关系开发数据 | 40轮dev7/19完整（36.84%）；107参考对为84用途/23负例 | 仍没有EVALUATED_ON正例；未运行新pipeline评分，不称已验证可靠性 |
| 图谱（第 31 轮） | 194,639 节点 / 263,059 关系 / 21,497 候选断言 | 与旧图按 `graphId` 隔离共存，应用只查当前版本 |
| 当前工程回归 | 第40轮368项通过 | `tests_20261008_round40.xml`；含源文/NER/原标签/背景数据未决保护，不是语义正确率 |

第 31 轮图谱节点明细：`Publication` 20,000 · `Person` 75,155 · `Venue` 3,205 · `Concept` 29,878 · `Mention` 44,904 · `Assertion` 21,497。

> 第 31 轮引入**独立作者身份 + 受控概念版本**：79,698 个署名匹配到 DBLP 主页（66,091 个身份节点），9,064 个未决署名**单独保留、绝不模糊合并**；7 个重复概念按类型与明确词表归一，不泛化合并相似术语。

---

## 3. 端到端数据流

```text
                    ┌──────────────────────────────────────────┐
  kg_datasets/dblp/dblp.xml.gz  （需自备，含同目录 dblp.dtd）    │
                    └───────────────────┬──────────────────────┘
                                        │ scripts/process_dblp_ai.py
                                        ▼
        kg_datasets/dblp/processed_ai/  ← 实验一：书目 CSV + quality_summary.json
        persons / publications / venues / topics .csv
        authored / published_in / about .csv
                                        │
                                        │ scripts/prepare_course_weak.py
                                        ▼
        kg_datasets/dblp/course_v4_weak/  ← 契约、全语料分组划分、2000 篇匿名队列
        （首轮输入只有 sampleId + 题名 + textSha256，不给主题/历史候选/划分）
                                        │
                     ┌──────────────────┼──────────────────┐
                     │ 第一轮 AI 标注    │ 第二轮 candidate-aware AI 复核
                     │ (会话内驱动)      │ (看到初标，报告如实称「非独立盲审」)
                     ▼                  ▼
        annotations/course_v4/batch*_generation_decisions.json
        annotations/course_v4/batch*_review_judgments.json
                                        │ scripts/compile_course_ai.py / import_course_ai.py
                                        ▼
        kg_datasets/dblp/course_v4_training_inputs_01..17/  ← 组装后的弱监督训练输入
                                        │
              ┌─────────────────────────┴─────────────────────────┐
              │ scripts/train_course_ner.py                       │
              │ scripts/train_course_relation.py                  │
              ▼                                                   ▼
        NER 权重（封存）                                    RE 权重（封存）
        kg_datasets/dblp/course_v4_runs/...                 annotations/course_v4/*_selection_*.json 选择锁
              │                                                   │
              └─────────────────────────┬─────────────────────────┘
                                        │ scripts/infer_course_corpus.py（冻结模型，仅题名）
                                        ▼
        kg_datasets/dblp/course_v4_graph_production_20261007_25/   ← 192,185 节点包（全 20,000 篇）
                                        │ scripts/course_identity.py + course_resolution.py
                                        ▼
        kg_datasets/dblp/course_v4_graph_resolved_20261007_31_ready/ ← 作者身份/受控概念复检版
                                        │ scripts/course_graph.py  export / verify / import
                                        ▼
                              Neo4j（按 graphId 隔离，仅建立 Course* 标签与约束）
                                        │ scripts/course_graph.py  serve
                                        ▼
                        资源页 resources/course_literature.html  @ 127.0.0.1:8765
```

关键原则贯穿全程：**每一步都产出新目录，绝不覆盖历史产物**；每一步都记录输入/输出 SHA-256；脚本只重放**明确写下**的 AI 判断，**不自行调用模型、不生成语义标签**。

---

## 4. 目录结构

```text
neo4j/
├── README.md                        # 本文件：项目总览
├── requirements-validation.txt      # 校验/标注/图谱应用环境依赖
├── requirements-training.txt        # 训练环境依赖（torch cu126 + transformers）
├── requirements-training.lock.txt   # 训练环境锁定快照
│
├── schemas/                         # 机器可读契约（唯一来源）
│   ├── annotation_course_v4.schema.json   # 当前课程 v4 AI 响应契约
│   ├── annotation_v3.schema.json          # 历史 v3（保留复现）
│   └── annotation_v2.schema.json          # 历史 v2（保留复现）
│
├── resources/
│   ├── course_v4_config.json        # 课程 v4 配置：种子、划分、标签、关系对
│   ├── course_graph_runtime.json    # 当前默认图谱的路径/graphId/manifest哈希锁
│   ├── course_abstract_v1.json      # 独立摘要训练/选择/晋级合同，不改题名配置
│   ├── course_abstract_relation_v1.json # 独立部分标注RE诊断合同，保留完整文档pipeline验收
│   ├── course_literature.html       # 只读检索前端（单文件应用）
│   ├── course_demo_queries.cypher   # 图谱演示查询
│   ├── boundary_rules_v3.json       # v3 候选边界政策（历史）
│   ├── ner_draft_lexicon_v2.json    # v2 草案词典（历史）
│   └── benchmark_source_seeds.json  # 外部基准来源种子
│
├── scripts/                         # 全部流水线入口（无 Web 框架依赖，标准库 HTTP）
│   ├── process_dblp_ai.py           # 实验一：DBLP XML → 书目 CSV + 质量报告
│   ├── prepare_course_weak.py       # 课程 v4：契约 + 分组划分 + 匿名标注队列
│   ├── course_weak.py               # 弱监督核心契约（BIO 对齐、哈希、来源绑定）
│   ├── compile_course_ai.py         # 把明确 AI 判断编译成响应（不调用模型）
│   ├── import_course_ai.py          # 导入实际 AI 响应 / 绑定复核 / 组装训练输入
│   ├── expand_course_ai_review.py   # 展开明确写下的复核确认与修订
│   ├── train_course_ner.py          # NER：preflight / smoke / fit-dev / evaluate-test
│   ├── train_course_relation.py     # RE：train/dev（仅开发，无 evaluate-test）
│   ├── evaluate_course_relation.py  # 冻结 RE 模块 + 冻结 NER pipeline 只读测试
│   ├── infer_course_corpus.py       # 冻结模型全语料批量推理（不评分、不写库）
│   ├── course_identity.py           # 从本地 XML 精确恢复 DBLP 作者身份（不模糊合并）
│   ├── course_resolution.py         # 保守图增强：主页身份 + 类型化精确词表别名
│   ├── course_graph.py              # 图谱 export / verify / check / import / serve
│   ├── course_bio_constraints.py    # 最大发射合法 BIO 解码
│   ├── collect_course_abstract_pages.py  # 合规摘要通道（arXiv 官方 citation 元数据）
│   ├── review_abstract_annotations.py    # 摘要侧 AI 标注复核（不访问留出文本）
│   ├── course_abstract_v1.py         # 摘要dev收据与train/dev输入快照
│   ├── train_abstract_ner.py         # 独立摘要NER warm-start开发训练，无test入口
│   ├── collect_train_abstracts.py    # 预锁train扩充；网页robots限速与失败留痕
│   ├── train_expanded_abstract_ner.py # 数据量单因素实验，冻结dev与旧RE，无test入口
│   ├── course_abstract_relation.py    # 源NER不变的明确关系修订，未决屏蔽
│   ├── train_abstract_relation.py     # RE warm-start与同dev四种对照，无test/自动晋级
│   ├── build_course_report.py       # 报告渲染（Markdown 子集，不冒充 DOCX）
│   ├── export_course_evidence.py    # 真实实验产物 → 离线报告页（不造假 UI 截图）
│   ├── annotation_v2.py / annotation_v3.py / prepare_ner.py  # 历史 v1–v3 复现入口
│   └── capture_*.ps1                # 证据截图脚本（真实浏览器）
│
├── tests/                           # pytest 工程检查 + Playwright(.cjs) 浏览器检查
│   ├── test_course_*.py             # 课程 v4 契约/训练/推理/图谱/应用
│   ├── test_*_v2.py / test_*_v3.py  # 历史 v2 / v3 回归
│   └── test_course_ui.cjs           # 前端真实浏览器检查
│
├── annotations/course_v4/           # 会话内写下的逐条 AI 判断（ai_pseudo，不是人工标注）
│   ├── batch*_generation_decisions.json   # 首轮判断
│   ├── batch*_review_judgments.json       # 第二轮复核（确认/修订）
│   ├── abstract_*_20261008_32/33.json     # 摘要侧判断
│   └── ner_test_selection_*.json / re_test_selection_*.json  # 冻结选择锁
│
├── kg_datasets/
│   ├── dblp/
│   │   ├── processed_ai/                  # 实验一输出（节点/关系 CSV + 报告）
│   │   ├── course_v4_weak/                # 课程 v4 契约与 2000 篇匿名队列
│   │   ├── course_v4_training_inputs_01..17/  # 逐轮组装的训练输入（不可变）
│   │   ├── course_v4_runs/                # 各轮运行产物、测试 XML、覆盖率、核验 JSON
│   │   ├── course_v4_graph_*/             # 图谱包（18 / 25 / 31 等，按 graphId 隔离）
│   │   ├── course_abstract_*_20261008_32/33/35/  # 摘要采集、队列、标注与独立输入
│   │   ├── ner_v1 / ner_v2 / ner_v2_1 / ner_v3 / ner_v3_1/   # 历史人工试标（保留）
│   │   └── dblp.xml.gz + dblp.dtd         # ⚠️ 原始输入，需自备（见 §7）
│   ├── models/scibert_24f92d32/           # 固定 SciBERT 权重（本地，训练/推理共用）
│   └── imdb/                              # IMDb TSV 数据集（与 course_v4 流水线无关）
│
└── docs/                            # 报告、证据与状态（见 §12）
    ├── course_v4_plan.md            # 课程实施计划
    ├── course_v4_runbook.md         # 逐步运行说明（上游权威）
    ├── course_complete_report_20261007.md / .html   # 四实验统一报告
    ├── system_status_round31.md .. round40.md       # 逐轮状态，40为当前标签修订，37为最近训练
    ├── model_optimization_abstract_v1.md            # NER/RE开发及四种对照已执行，未达晋级门槛
    ├── status_log.md                # 历史滚动状态日志
    └── evidence/<日期>_roundNN/sources/             # 每轮真实截图、日志与源码快照
```

> `.venv-validation/` 与 `.venv-training/` 为本地虚拟环境（不入库），见 §7。

---

## 5. 数据与标注契约

**在用题名模型契约**：`resources/course_v4_config.json` + `schemas/annotation_course_v4.schema.json`。摘要标注有独立的 `course_abstract_queue_20261008_32/contract.json`；第35轮摘要模型合同为 `resources/course_abstract_v1.json`，训练/验证输入保持整篇原文、512token超长拒绝、不拼题名。来源manifest与收据哈希在输入快照中绑定；题名配置和最终测试入口原样保留。

### 实体与关系

| 项 | 取值 |
|---|---|
| 文本单位 | **题名**（`textKind: title`）；摘要另立契约，不静默混入 |
| 实体类别 | `METHOD` · `TASK` · `DATASET`（连续、不重叠的 Unicode 字符跨度） |
| BIO 标签 | `O` + `B-/I-{METHOD,TASK,DATASET}`，共 7 个 |
| 关系类型 | `USED_FOR`（METHOD→TASK）· `EVALUATED_ON`（METHOD→DATASET） |
| 关系判定 | `NO_RELATION`（范围内明确负例）· `UNRESOLVED`（证据不足，**不作为负例**） |
| 并列处理 | `separate_group_mentions_quarantine_entire_document`：共享中心词的并列提及存入 `groupMentions`，整条文本隔离出训练/评估，不拆造原文缺失词 |
| 划分 | 训练 1,600 / 验证 200 / 测试 200，比例 0.8/0.1/0.1，种子 `20261005` |
| 泄漏控制 | `legacyCandidatesPolicy`：所有历史候选及其同组成员**强制训练侧**；近重复候选只用于"放同一 split"，**绝不合并论文身份** |
| 评估目标 | `held_out_ai_reference_agreement_not_human_gold` |

### 不可变与可追溯原则

1. **每次输出新目录**，已有目录不可覆盖；重建须显式指定 `--output` 并保留旧版本。
2. **输入/输出全程 SHA-256**：题名哈希、响应哈希、`reviewOfSha256`、权重哈希、运行清单哈希、导出代码哈希。
3. **来源不可抹除**：AI 初标即使被复核修订，原始快照与来源仍保留；`--force` 只替换受管理的输出目录，旧版留作同级 backup。
4. **未产生真实 AI 响应的 job 维持 `pending`**，不填空数组冒充已完成；无标签的 job 绝不转成空负例。
5. **哈希只检测内容漂移**，不认证人的身份，也不认证语义正确性。

---

## 6. 模型与评测口径

**基础模型**：固定本地 SciBERT（`kg_datasets/models/scibert_24f92d32`）。NER与RE从同一预训练基础初始化，生产推理分别使用各自冻结的微调权重，不是两任务共用一个微调checkpoint。

| 指标 | 数值 | 含义与边界 |
|---|---|---|
| NER 严格 test F1（第 09 轮，封存） | **74.37%** | 实体级严格跨度+类别匹配；AI 参考；**72% 覆盖**（144/200 可判定） |
| 同子集词典基线 F1 | 25.27% | 词典只是基线，不是标准答案 |
| RE 模块正关系 F1（给AI参考实体） | **99.25%** | 条件模块一致性；实体不保证真实正确；类型多数基线已达98.52% |
| **完整 pipeline 正关系 F1** | **60.07%** | 更接近应用的抽取链路，但仅AI可判定子集、69%覆盖，不是2万篇总体正确率 |
| 第28轮候选 DATASET 类 dev F1 | 33.33% | 参考仅3个；不是当前生产模型稀有类表现，候选未晋级 |
| 第 29 轮新留出对照 | NER 66.83% / pipeline 44.63% | 同样本旧版 63.89% / 44.28%；**未达 MLE 门槛，未晋级，线上仍用旧模型** |

已封存测试的独立指标（只读既有结果文件，本轮没有重新推理）：

| 队列与任务 | Precision | Recall | F1 | 参考support | 文档coverage |
|---|---:|---:|---:|---:|---:|
| 第09轮NER严格匹配 | 73.44% | 75.32% | 74.37% | 312实体（DATASET2） | 144/200=72% |
| 第17轮RE模块，参考实体 | 99.25% | 99.25% | 99.25% | 133正关系（EVALUATED_ON1） | 138/200=69% |
| 第17轮完整pipeline | 58.57% | 61.65% | 60.07% | 133正关系（EVALUATED_ON1） | 138/200=69% |
| 第29轮候选NER | 69.71% | 64.18% | 66.83% | 416实体（DATASET4） | 187/200=93.5% |
| 第29轮候选pipeline | 49.69% | 40.50% | 44.63% | 200正关系（EVALUATED_ON0） | 175/200=87.5% |

来源：`ner_final_test_20261006_09/test_result.json`、`re_final_test_20261006_17/test_result.json`、`refresh_final_test_20261007_29/test_result.json`，均在 `kg_datasets/dblp/course_v4_runs`。不同队列/实体范围不能直接排行；第29轮没有EVALUATED_ON参考支持，不能据此宣称该关系已被验证。

**F1不等于正确率或错误比例**。第17轮pipeline仅在138篇可判定题名上有82/140条预测严格匹配AI参考，因此该子集不匹配比例为58/140=41.43%（由Precision计算），不是由F1推得，也不能外推21,497条全量候选断言的错误率。`confidence`为未校准softmax分数，未做可靠性校准时不叫“正确概率”。

第35轮独立摘要**dev**对照（非final-test）：在相同16/19篇可用摘要、184个AI参考实体上，旧题名权重迁移基线P43.08% / R59.24% / F1 49.89%；train词典F1 22.03%；新摘要NER epoch4为P69.23% / R73.37% / F1 71.24%。候选逐类F1：METHOD81.98%、TASK52.54%、DATASET66.67%；DATASET精确率仅54.17%，15个参考提及只来自4篇文档。不能据此宣称整体pipeline、稀有类或真实事实可靠性已解决。详见[本轮开发记录](docs/system_status_round35.md)。

第36轮关系诊断采用**另一个部分标注合同**，不改35轮输入或标签：关系模块只评分NER完整文档中已明确的242/432对（56.02%），三类宏F1旧88.16% / 新85.48%，类型多数基线64.36%；新RE负类F1 60.47%低于旧68.09%。完整pipeline只评分5/19篇全判定文档（26.32%），含零参考对文档：

| 同摘要dev组合 | Precision | Recall | F1 | TP / 预测 / 参考 |
|---|---:|---:|---:|---:|
| 旧NER / 旧RE | 8.59% | 47.83% | 14.57% | 22 / 256 / 46 |
| 新NER / 旧RE | 24.32% | 39.13% | 30.00% | 18 / 74 / 46 |
| 旧NER / 新RE | 8.30% | 47.83% | 14.15% | 22 / 265 / 46 |
| 新NER / 新RE | 22.50% | 39.13% | 28.57% | 18 / 80 / 46 |

这是同队列dev误差传播实验，**没有EVALUATED_ON参考正例**，不是旧题名60.07%的重复评测或可比成绩。新NER/旧RE的28条漏关系主因为漏实体19、边界7、类型2；56条假阳性中54条端点不匹配、2条正确端点错关系（均相对于AI参考）。新RE退化，且NER组合召回下降8.70百分点超2百分点护栏、覆盖不足，均不晋级。[完整记录与拒绝决定](docs/system_status_round36.md)。

第37轮只扩充锁定train：NER48篇/同dev16篇、6轮144步、epoch6。NER F1 71.28%（35轮71.24%），TASK F1 49.15%（旧52.54%）；DATASET P81.82%但R60.00%，不能仅按F1宣称稀有类已修复。同5篇完整dev/固定旧RE，pipeline P19.05% / R43.48% / F1 26.49%，不及35轮P24.32% / F1 30.00%；漏关系主因缺失5/边界21，FP85/FN26。明确拒绝新候选，当前重点转向训练侧逐次出现的上下文和任务跨度边界，不靠扩量或改dev追分。[实际结果与截图](docs/system_status_round37.md)。原评分JSON保留历史默认目标字符串，审计单独更正为dev口径，数字和原记录未重写。

第40轮仅补开发标签：固定19篇内明确对335/432（77.55%），完整文档7/19（36.84%），完整范围EVALUATED_ON仍0；没有新模型分数。旧242标签、NER和旧成绩保存原版本，不把新分母套到上述旧表。组合方法/组件归属风险单独记录，未认证历史标签；[新数据、未决原因与边界](docs/system_status_round40.md)。

**方法与纪律**：

- 超参数**只由 dev 决定**；测试结果先在 dev 阶段锁定权重与选择锁（`annotations/course_v4/ner_test_selection_*.json`、`re_test_selection_*.json`），**不得用 test 调参**。
- 冻结本版后**不再重复在已见 test 上宣称"最终成绩"**；模型改进须另建版本 + 未暴露的新测试集。
- 评测同时报告**参考实体下模块成绩**与**预测实体下端到端成绩**，并逐类披露 support 与未决覆盖；零 support 的类别不宣称已评估。
- 全部测试中的 `synthetic_test` / `not_a_real_model` / 示例标注**仅用于校验契约**，不是课程实验结果。

---

## 7. 环境与依赖

项目使用**两个隔离虚拟环境**（均不入库）：

| 环境 | Python | 用途 | 依赖文件 |
|---|---|---|---|
| `.venv-validation` | **3.13** | 标注契约、数据准备、导入校验、图谱导入/服务、全部回归测试 | `requirements-validation.txt` |
| `.venv-training` | **3.12.4** | NER / RE 真实 GPU 训练与冻结推理 | `requirements-training.txt`（锁定见 `.lock.txt`） |

**已实测环境**：Windows + Python 3.13（validation）/ 3.12.4（training）+ CUDA 12.6。**其他系统的新安装未经验证**。

### 首次创建

```powershell
# 校验环境（Python 3.13）
& 'C:\Python313\python.exe' -m venv .venv-validation
& '.\.venv-validation\Scripts\python.exe' -m pip install -r requirements-validation.txt

# 训练环境（Python 3.12.4，需与本机 CUDA 匹配）
& '<Python3.12>\python.exe' -m venv .venv-training
& '.\.venv-training\Scripts\python.exe' -m pip install -r requirements-training.txt
```

### 外部输入（需自备）

- **DBLP 原始数据**：`kg_datasets/dblp/dblp.xml.gz` + 同目录 `dblp.dtd`。仓库不附带原始 XML。
  - 脚本严格校验 DOCTYPE 为 `SYSTEM "dblp*.dtd"` 且无内部子集；**拒绝外部实体**，只允许已检查的本地 DTD。
- **SciBERT 权重**：`kg_datasets/models/scibert_24f92d32/`（本地固定版本，训练与推理必须一致）。
- **Neo4j**：本地实例，默认 `http://127.0.0.1:7474`、业务库 `neo4j`（Query API `/db/{database}/query/v2`）。
- **浏览器测试**：Playwright / Chromium（供 `tests/*.cjs` 使用）。

---

## 8. 快速开始

> 以下命令均以仓库根目录为工作目录。所有 `--output` 目标目录**必须不存在**（防止覆盖历史产物）。

### 8.1 实验一：DBLP → 书目 CSV

```powershell
# 默认从全部标题规则命中记录中按固定种子抽 20,000 篇 → kg_datasets/dblp/processed_ai
& '.\.venv-validation\Scripts\python.exe' scripts/process_dblp_ai.py

# 重建已有输出（旧版本保留为同级 backup 目录）
& '.\.venv-validation\Scripts\python.exe' scripts/process_dblp_ai.py --force
```

产出：`persons/publications/venues/topics.csv`、`authored/published_in/about.csv`、`quality_summary.json`、`processing_report.md`。
（来源日期默认未知；确有依据时才加 `--snapshot-date 2026-09-01`，且仅记为显式声明，不自动认证日期。）

### 8.2 课程 v4：准备队列并校验

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/prepare_course_weak.py
& '.\.venv-validation\Scripts\python.exe' scripts/prepare_course_weak.py --verify-only kg_datasets/dblp/course_v4_weak
```

### 8.3 导入 AI 结果并组装训练输入

```powershell
# 首轮
& '.\.venv-validation\Scripts\python.exe' scripts/import_course_ai.py import --dataset kg_datasets/dblp/course_v4_weak --responses '实际首轮响应.jsonl' --output kg_datasets/dblp/course_v4_runs/batch01_generation --provider 'codex_session' --model 'unknown_session_model'

# 复核（带 --previous 指向首轮 receipts）
& '.\.venv-validation\Scripts\python.exe' scripts/import_course_ai.py import --dataset kg_datasets/dblp/course_v4_weak --responses '实际复核响应.jsonl' --previous 'kg_datasets/dblp/course_v4_runs/batch01_generation/receipts.jsonl' --output kg_datasets/dblp/course_v4_runs/batch01_review --provider 'codex_session' --model 'unknown_session_model'

# 组装
& '.\.venv-validation\Scripts\python.exe' scripts/import_course_ai.py assemble --dataset kg_datasets/dblp/course_v4_weak --receipts 'kg_datasets/dblp/course_v4_runs/batch01_review/receipts.jsonl' --output kg_datasets/dblp/course_v4_training_inputs_01
```

> 导入脚本**不调用模型**，只校验收到的真实响应、绑定两轮内容并按任务输出可用样本。批量 API 执行器需另行实现。

### 8.4 训练 NER（GPU）

```powershell
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_ner.py fit-dev --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_08 --model kg_datasets/models/scibert_24f92d32 --output kg_datasets/dblp/course_v4_runs/NEW_DEV_RUN --device cuda --epochs 6
```

子命令：`preflight` / `smoke` / `fit-dev` / `evaluate-test`。前三种不读取 test 题名做推理；`evaluate-test` 必须提供固定选择锁，且只能**原样复现**封存的 development 运行。**RE 训练入口暂无 evaluate-test**，不能套用 NER 命令制造关系测试成绩。

### 8.5 冻结模型全语料推理

```powershell
& '.\.venv-training\Scripts\python.exe' -B scripts/infer_course_corpus.py --output kg_datasets/dblp/course_v4_graph_production_20261007_25 --device cuda
```

输入是**固定路径**（`course_v4_weak` + `processed_ai/publications.csv` + 第 09/17 轮冻结缓存，均按哈希校验），因此该入口只接受 `--output` / `--limit` / `--device` 三个参数。
产出：题名 NER→RE 批量推理结果 + `manifest.json`（`weightsUnchanged` / `trainingExecuted: false` / `evaluationExecuted: false` / `databaseWriteExecuted: false`）。**无标签、不评分、不写数据库。**

---

## 9. 图谱导入与只读应用

### 图谱包

| 包 | 规模 | 说明 |
|---|---|---|
| `course_v4_graph_20261007_18_final` | 96,616 节点 | 历史包，复现须显式传 `--bundle`，不再作为默认运行版本 |
| `course_v4_graph_production_20261007_25` | 192,185 节点 | 全 20,000 篇冻结模型生产包 |
| `course_v4_graph_resolved_20261007_31_ready` | **194,639 节点 / 263,059 关系 / 21,497 候选断言** | 当前默认复检包；无 `_ready` 后缀者为同轮历史构建，不混用 |

默认入口读取 `resources/course_graph_runtime.json`，在连接或写入数据库之前验证配置路径、graphId及manifest/产物哈希；缺失或漂移即停止，不回退18包。历史版本可显式传 `--bundle`。`export`必须显式指定新的输出目录，不能默认写向在用包：

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/course_graph.py verify
& '.\.venv-validation\Scripts\python.exe' scripts/course_graph.py check --database neo4j --user neo4j
# 仅需要再次导入时执行；保留已有导入收据，不覆盖：
& '.\.venv-validation\Scripts\python.exe' scripts/course_graph.py import --database neo4j --user neo4j --output kg_datasets/dblp/course_v4_runs/graph_import_new.json
# 已有8765服务时不重复启动：
& '.\.venv-validation\Scripts\python.exe' scripts/course_graph.py serve --port 8765
# 显式历史/其他包核验仍可使用 verify --bundle <path>
```

密码为**隐藏交互输入**（或进程级环境变量），不写入脚本、包或报告，也不作为 CLI 参数。

默认入口修复不改旧图谱的来源清单。包内 `inputSha256` 保存当时的执行源码哈希，不应为匹配新源码而重写；31轮原执行源码保存在 `docs/evidence/20261007_round31/sources`。本轮核验产物内容与原manifest，不声称当前源码与旧导出源码逐字一致。

### 图结构

```text
Publication ─MENTIONS→ Mention ─DENOTES→ Concept
Assertion ─SUPPORTED_BY→ Publication          # 题名作为证据来源，非已证实结论
Assertion ─HAS_HEAD→ 方法 Mention
Assertion ─HAS_TAIL→ 任务/数据集 Mention
Person ─AUTHORED→ Publication                 # 保留署名顺序，未做现实身份核验
Publication ─PUBLISHED_IN→ Venue
```

`Assertion` 属性保存 `predicate`、`status: candidate`、`model_prediction` 来源、原始题名、Unicode 偏移、标题哈希、NER/RE 权重哈希、运行清单哈希与三类分数。`confidence` 是**未校准的 softmax 分数，不是事实正确率**，高分不会自动升级为确定事实。

### 只读 API

| 接口 | 作用与约束 |
|---|---|
| `GET /api/health` | 检查真实 Neo4j 与当前图谱 `completed` 状态；未就绪 **503** |
| `GET /api/publications` | `q`/`author`/`venue`/`method`/`task`/`dataset`/`year` 筛选；`limit` 1–100、`offset` 0–20000；稳定排序、`hasNext` |
| `GET /api/publication?id=...` | 书目、署名顺序、场馆、模型提及、候选断言、原始证据与哈希；生成非正式参考文献草稿 |
| `GET /api/graph` | 局部节点图（逐跳方向、共享作者 2 跳、同方法 4 跳），支持缩放与节点证据查看 |

**错误语义**：无效/重复/未知参数 `400`，文献不存在 `404`，连接/认证/导入未就绪 `503`，内部异常 `500`。

**安全边界**：仅监听 `127.0.0.1`，校验 `Host`，无 CORS，**无任意 Cypher 入口**，页面数据经 `textContent` 渲染，链接只允许 HTTP(S)。**数据库不可用即 503，绝不回退到本地 JSON 假装有结果。**

**中文检索**：`zh_alias_v1` 提供 22 条**固定术语别名**（精确匹配，非翻译），例如输入"扩散模型"可命中 `diffusion model(s)`。未知中文原样检索。

**前端**：`resources/course_literature.html` 单文件应用，支持论文详情、候选清单（去重、上限 50 篇）、导出完整书目 / 原始模型证据 JSON / 引用草稿 TXT、局部节点图。

---

## 10. 测试与回归

```powershell
# 正式工程回归（第40轮368项通过；pytest.ini限定tests，避免收集历史证据副本）
& '.\.venv-validation\Scripts\python.exe' -m pytest tests -q

# 覆盖率（弱监督数据链路）
& '.\.venv-validation\Scripts\python.exe' -m pytest tests -q --cov=course_weak --cov=prepare_course_weak --cov=import_course_ai --cov=compile_course_ai --cov-branch --cov-report=term-missing

# 单模块
& '.\.venv-validation\Scripts\python.exe' -m pytest tests/test_course_graph.py -q --cov=course_graph --cov-report=term-missing
& '.\.venv-validation\Scripts\python.exe' -m pytest tests/test_course_ner_training.py -q
```

- 每轮运行都把 JUnit XML（如 `kg_datasets/dblp/course_v4_runs/tests_*_final.xml`）与覆盖率 JSON 存档。
- **所有历史测试也必须保持通过**；回归后须逐项区分 `pre-existing` 失败与本次引入的失败。
- 浏览器侧另有 4 个 `.cjs` 测试（Playwright/Chromium），覆盖前端真实渲染与交互。
- 合成成功场景**不算**真实 Neo4j 成功验收；真实数据库连通性必须单独核对。

---

## 11. 已知限制与边界

**模型可靠性**

- 完整pipeline正关系F1为60.07%、Precision58.57%、Recall61.65%，仅138篇AI可判定题名；F1不能推导全量候选边的错误比例。所有候选断言保留证据与不确定性，不能自动升级为事实。
- 稀有类支持不足（DATASET / EVALUATED_ON），数据集相关结论最不可靠。第 18 轮唯一一条 `EVALUATED_ON` 预测把 NeurIPS 误识为 DATASET。
- NER test 仅 72% 覆盖，DATASET 类参考仅 2 个，不能称全局最优或稳定泛化。

**数据与来源**

- 第31轮已恢复 **DBLP主页身份及别名**：66,091个Person为 `identityStatus: dblp_homepage_resolved`，9,064个未决署名为签名局部身份，不跨论文模糊合并。旧 `normalized_name_not_disambiguated` 描述只适用于历史图；主页匹配仍不是独立现实身份核验，DBLP之外的作者消歧未解决。
- 标题关键词筛选的 20,000 篇**不等于全部人工智能领域文献**，也不等于 20,000 篇都完成了神经抽取。
- CoRR 预印本**不等于**同行评审论文；AI 标题规则抽检未完成（例如 "Transformer" 可能指电力设备）。
- 摘要仅 96 篇；**全文 PDF 不托管**（版权/付费墙），只给 DBLP / DOI / arXiv 外链。外部基准 9 篇**仅训练侧**，不冒称 DBLP 子集成员。
- 旧32轮网页采集曾误用API的3.1秒间隔；37轮新入口按实际robots至少15.1秒采集并核验时间，历史来源原样保留。旧网页采集命令不再执行，当前入口见[状态与来源规则](docs/system_status_round37.md)。

**能力边界（明确不做）**

- 不做"某论文是否必须引用"判定；不做被引次数、引用链、影响力排序（**无 CITES 数据**）。
- 不从 `MENTIONS` 自动推断论文实际使用了某数据集。
- 不做跨图谱版本（旧图/新图）混合统计。
- AI 第二轮复核是 **candidate-aware**，不是独立盲审；两轮 AI 相互同意**不等于**人工金标准。

**工程现状**

- 本地单机只读演示，**不是已部署、开公网或多人在用的服务**（无 Web 框架、无 CORS、无鉴权体系）。
- 第36轮摘要RE真实训练和四种dev对照已完成，但新RE退化被拒绝，NER组合召回护栏/完整覆盖未通过。仅7个训练负例、同会话AI标签、端点错误与未知对仍限制可靠性，旧模型/31轮图不升级；[错误与拒绝记录已保存](docs/system_status_round36.md)。
- 第37轮扩大NER训练数据并真实训练，但同固定旧RE的pipeline Precision/F1退化，新候选保留且拒绝替换。数据扩量未解决边界/角色问题，完整覆盖和独立参考缺口仍在；[结果](docs/system_status_round37.md)。
- 第40轮开发已判335对/完整7篇仍不能评估完整EVALUATED_ON能力，97对保持未决；组合评测分配给组件的旧标签存在未撤回风险。标签覆盖增长不是模型能力提升，旧数据不改、未来修订须显式撤回；[证据](docs/system_status_round40.md)。

---

## 12. 文档与证据索引

| 文档 | 内容 |
|---|---|
| [docs/course_v4_plan.md](docs/course_v4_plan.md) | 课程实施计划：路线、评估约定、分阶段验收表 |
| [docs/course_v4_runbook.md](docs/course_v4_runbook.md) | **逐步运行说明**（命令层面的上游权威） |
| [docs/system_status_round40.md](docs/system_status_round40.md) | 当前开发关系证据/覆盖、历史标签风险、工程核验与截图，未重训 |
| [docs/system_status_round39.md](docs/system_status_round39.md) | 训练侧评测归属与角色反例补强，train268对，未重训 |
| [docs/system_status_round37.md](docs/system_status_round37.md) | 最近真实NER训练、固定RE对照、错误与拒绝决定 |
| [docs/system_status_round36.md](docs/system_status_round36.md) | 历史关系标签、真实RE训练、四种对照、错误归因和拒绝升级 |
| [docs/system_status_round35.md](docs/system_status_round35.md) | 历史摘要合同、AI dev标注、真实NER训练及未解决缺陷 |
| [docs/system_status_round34.md](docs/system_status_round34.md) | 历史技术复核：指标语义、默认版本、实验路线 |
| [docs/model_optimization_abstract_v1.md](docs/model_optimization_abstract_v1.md) | 摘要NER/RE和对照已执行，数据覆盖与质量仍不满足晋级 |
| [docs/system_status_round33.md](docs/system_status_round33.md) | 整篇训练摘要标注/自复核与隔离验收 |
| [docs/system_status_round32.md](docs/system_status_round32.md) | 历史状态：摘要数据补充与8段试标 |
| [docs/system_status_round31.md](docs/system_status_round31.md) | 作者身份 / 受控概念版本上线 |
| [docs/status_log.md](docs/status_log.md) | 历史滚动正文保留，上方补充最新轮次索引 |
| [docs/course_complete_report_20261007.md](docs/course_complete_report_20261007.md) · [.html](docs/course_complete_report_20261007.html) | 四实验统一报告（可打印 HTML） |
| [docs/course_v4_graph_application.md](docs/course_v4_graph_application.md) | 图谱应用：接口、导入流程、失败记录与局限 |
| [docs/agent_kg_system_proposal.md](docs/agent_kg_system_proposal.md) | **提案（未实现）**：以图谱为底座的文献 Agent 方案 |
| [docs/course_v4_ner_test.md](docs/course_v4_ner_test.md) · [docs/course_v4_relation_test.md](docs/course_v4_relation_test.md) | 封存 NER 最终测试 · 冻结 RE/pipeline 测试 |
| [docs/course_v4_report_evidence.md](docs/course_v4_report_evidence.md) | 报告图注与证据索引 |

**逐轮证据**：`docs/evidence/<YYYYMMDD>_roundNN/`，内含真实浏览器截图、执行日志、源码快照与浏览器 DOM 记录（如 `sources/`、`captures.json`、`browser_dom.json`）。
**机器可读核验**：`kg_datasets/dblp/course_v4_runs/verification_<日期>_roundNN.json`。

---

## 13. 后续路线

当前未完成项（按优先级）：

1. **P0实验可信度**：版本/指标纠错已落实；第09/17/29轮成绩封存，不重跑或用它们调参。独立人工抽检仅作为可选扩展，不改变已选AI标注路线，也不冒充已完成。
2. **P1标注质量**：38轮NER准入50，39轮train268对/1577未决；40轮锁定全部11篇不完整dev后明确335对/97未决，完整7/19仍无EVALUATED_ON参考。原242标签/旧dev包和成绩保留，不按模型错误改变参考。下一步明确复核/撤回组合评测向组件归属的风险，统一直接角色与家族/组件口径；八篇训练隔离、独立参考和稀有支持仍不足，不填未知负例。[数据与边界](docs/system_status_round40.md)。
3. **P2独立摘要实验**：NER/RE与数据扩量实验已实际执行，RE候选及最新NER候选均未通过替换门槛。保持已有结果和开发参考封存；整个pipeline通过声明护栏并锁定后，才一次性评测保留摘要test。目前没有新最终成绩或晋级，不继续盲调RE或盲扩规模。
4. **P3应用扩展**：在知识质量验收后再做语义检索、证据对比和[受引用约束Agent](docs/agent_kg_system_proposal.md)，目前均属提案，不推翻现有pipeline。
5. **报告收尾暂停**：用户先完善系统，再单独写报告；Word渲染与教师终验不是当前实施任务。

---

## 附：核心术语表

| 术语 | 含义 |
|---|---|
| `ai_pseudo` | AI 伪标签来源标记；全部 AI 标签保持此来源，不改名为 human |
| 候选断言 / `candidate` | 模型抽取的关系，带来源与证据哈希，**不是已核实事实** |
| `graphId` | 图谱版本隔离键；新旧图共存，应用只查当前版本 |
| 选择锁 | 测试前冻结的模型/参数选择文件，禁止用 test 调参 |
| 封存（sealed） | 该版本权重与测试结果冻结，改进须另建版本与未暴露测试集 |
| 论文组（group） | 保守的论文字符串分组，用于把相关论文锁在同一 split，防止泄漏 |

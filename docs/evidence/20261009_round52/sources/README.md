# AI-Literature-KG · 人工智能文献知识图谱

第52轮模型数据单因素优化（2026-10-09）：8篇训练侧真实摘要完成AI初标/同会话复核，7篇准入/1隔离，NER58→65/787实体；271条RE及开发原字节保留，新487关系全未知。仅一次NER六轮198步，第6轮最佳、单检查点重载一致；固定46 RE，同7篇开发pipeline P29.59→33.15%、R59.52→70.24%、F1 39.53→45.04%，但错报119不变。NER历史F1 70.84→72.63%、补充dev63.93→67.89%；完整EVAL0/覆盖7/19仍阻断升级。388回归通过；没有保留test/生产模型或在线图变更，作者/概念延续51，详见[第52轮状态](docs/system_status_round52.md)。下方51及更早为历史记录。

第51轮质量补强（2026-10-09）：新增35组分类型受控规则，合并39个重复概念，保留18个版本条目；全XML ORCID交叉核验恢复2个署名，已匹配主页66,093/未决9,062。新图真实入库194,600节点/263,059关系，新只读页面`http://127.0.0.1:8766/`完成32项验收、真实三屏截图和原生导出；旧8765/31图不变。冻结摘要模型在补充dev的NER F1 63.93%，固定证据约束使历史dev P提高但R/F1严重下降，拒绝采用；没有新训练或最终test，可靠性仍未晋级。详见[第51轮状态](docs/system_status_round51.md)。下方50及更早为历史记录。

第50轮真实在线终验（2026-10-09）：用户通过Desktop启动（实际JRE21）后，8765只读应用已恢复。31图实际20,000文献/194,639节点/263,059关系；32综合HTTP＋15图探索HTTP＋8数据库只读检查通过，5组中英文首页一致；真实清单/JSON/TXT下载和桌面/平板/手机截图保存，三张局部图与31基线字节相同。378项本轮D隔离回归及现有Node界面检查通过；旧模型/图/保留test未改。现有候选检索工程闭环验收完成，高可靠模型仍未晋级、报告暂停；服务当前运行。详见[第50轮当前状态](docs/system_status_round50.md)。下方49及更早为历史记录。

第49轮补充开发参考（2026-10-09）：固定8篇外部摘要已采集、实际AI初标及同会话复核，7篇BIO通过/1篇隔离，109实体、88明确对（评测14/来自3论文）、390/478对未决；完整文档0/8，不能支持完整pipeline验收，暂缓新训练与质量晋级。378项D隔离回归、结果截图及来源链封存，生产20,000篇/31图不变。转向系统终验时发现CLI未接受许可、Java23不受支持；测试启动已正常停止，当前在线验收阻塞，需先由用户从Desktop正常启动实例。详见[第49轮当前状态](docs/system_status_round49.md)。下方48及更早为历史记录。

第48轮结构性弃权（2026-10-08）：复用46冻结权重/47封存logits与精确RE缓存，仅弃权冲突I截断前缀和词内边界；58篇/678训练参考实体全部保留。6实体/2关系对弃权，NER F1 70.84%→72.02%、完整pipeline39.53%→39.84%、错报119→117，TP仍50。改善很小，仍低于42同范围54.35%，完整EVAL0/覆盖7/19，拒绝晋级。376项D隔离回归、实际结果截图与共同机器核验封存；没有新训练、改标签、使用保留test或更新31生产图。详见[第48轮当前状态](docs/system_status_round48.md)。

第47轮冻结合法BIO对照（2026-10-08）：同16篇dev只做一次冻结推理，argmax精确重现46；合法BIO虽将非法65→0，却使NER F1降至69.84%、pipeline36.10%、错报143，已拒绝。375回归通过；[第47轮历史状态](docs/system_status_round47.md)。下方46及更早为历史记录。

第46轮真实训练（2026-10-08）：第45轮输入已用于NER58篇/174步和RE271对/408步各6轮固定实验。与第42轮冻结模型重跑同16篇NER开发、333已判关系对及7篇完整开发文档：DATASET召回40.00%→66.67%，条件RE正关系F1 92.06%→94.18%，但完整流程F1 54.35%→39.53%，错报正边50→119；完整EVAL0/覆盖7/19，拒绝晋级。374项D隔离回归通过，两张结果截图与机器核验已封存，保留测试未用、生产31图/旧模型不替换。详见[第46轮状态](docs/system_status_round46.md)。下方45及更早为历史记录。

第45轮训练基准补充（2026-10-08）：四个训练专用阅读理解基准在获取原文前锁定、身份元数据重叠拒绝、官方HTML采集/整篇AI初标及实际同会话复核完成。摘要资产100（87DBLP对应＋13外部训练），NER58/4隔离，DATASET44→55提及、16→20独立论文、27→31字面名（未归一）；METHOD405/TASK218。明确271（184用途/61评测/26负例）、未决1659，新增3评测仅来自1论文，3篇新增真零候选不当负例。58旧收据/267旧关系和9dev文件不变，58BIO/271标记对通过；D隔离tmp373回归通过234.89秒，C历史rename未修。新输入未训练/推理，无新F1/晋级/31图更新，AI非独立gold，定向训练不当代表性评测，报告暂停。下方44及更早为历史记录。

第44轮训练侧范围清洗（2026-10-08）：固定11篇原文初判/实际同会话复核，4篇旧隔离准入，NER50→54/隔离8→4；修复SmoothGuard任务对象边界及MMLU-Pro首句方法漏标，45旧关系按跨度重绑定并保留证据、15新对全部未知。最终METHOD403/TASK196/DATASET44，明确267/未决1647，6份新收据/52行字节不变；54篇BIO及9个dev文件原字节核验通过。D隔离tmp完整回归372通过144.86秒，C历史rename未修。DATASET独立支持未增加、标签尚未训练，无新F1/晋级/线上更新；AI参考非独立gold，报告暂停。下方43及更早为历史记录。

第43轮训练侧诊断与边界修订（2026-10-08）：实际推理50篇train，新42样本内F1 99.75%、DATASET44/44匹配，不能当新dev/test成绩；44个DATASET来自16篇，14个集中同一摘要，27个字面名尚未归一。已按预测前源文审查修复1处TASK跨度，1份新初标/同会话复核、57篇收据字节不变，dev文件仅按字节复制，未知1578对不填负，50篇BIO通过。最终D隔离tmp回归371项通过162.27秒；C默认tmp历史rename问题未解决。修订未训练，泛化/完整EVAL/独立评估仍缺，旧模型/31图不更新，报告暂停。下方42及更早为历史记录。

第42轮修订摘要模型实验（2026-10-08）：41版50篇NER/267个RE训练对已实际训练6轮，150/402步，均选epoch6；同7篇完整dev重新推理四种组合，旧35NER/旧15RE的pipeline F1 40.50%→新组合54.35%（P50.00%/R59.52%）。NER总体F1 72.09%，但DATASET召回86.67%→40.00%、F1 66.67%→46.15%，不能掩盖稀有类退化。完整EVAL支持0、覆盖7/19阻断晋级；D盘隔离pytest临时目录下370项回归通过（136.57秒），C默认临时目录两次rename拒绝访问仍未解决，失败XML保留、源码未改、无skip。训练及有条件工程通过不等于可靠性通过；线上31图/旧模型不更新，报告暂停。下方41及更早为历史记录。

第41轮评测归属审计（2026-10-08）：检查锁定train/dev全部15篇含旧EVALUATED_ON的原文、69个旧跨度对；65保持、3明确撤回至UNRESOLVED、1补齐摘录，只有2篇产生新初标/实际同会话复核收据，其余75份原样继承。当前train267对/1578未决，dev333对/99未决；NER50/16与隔离8/3不变，完整dev7/19仍无EVALUATED_ON正例。369正式回归、66篇BIO往返及600对标记编码通过；没有训练、推理或新成绩，旧模型/31图不更新，报告暂停。下方第40轮及更早为历史版本记录。

第40轮开发关系复核（2026-10-08）：固定dev中全部11篇关系未完整的合格NER摘要逐篇检查/同会话复核，6篇新增93对（57用途/36局部角色反例）；明确dev242→335，97/432对未决，完整文档5→7/19但EVALUATED_ON参考仍0。原NER/隔离/242明确标签及旧分数不改，发现组合评测向组件归属的历史风险，单独留待复核撤回。368正式回归与严格编码通过；没有训练/推理或新F1。39轮train268对、31图、旧权重和保留test不变，可靠性仍未通过，报告暂停。

> 从本地 DBLP XML 中筛选 2015–2025 年人工智能相关论文，用 **AI 伪标签（弱监督）** 训练 SciBERT 做实体抽取与关系抽取，将抽取结果作为**带证据链的候选断言**写入 Neo4j，并提供一个本地只读的文献检索应用。

- **领域**：人工智能文献检索与候选参考文献发现
- **标注路线**：AI 伪标签（`ai_pseudo`），**不要求人工标注**；AI 是标注工具，不代替深度学习模型训练
- **当前生产配置**：第 31 轮图谱（194,639 节点 / 263,059 关系 / 21,497 候选断言），应用地址 `http://127.0.0.1:8765/`；50轮实际在线验收通过，当前服务运行
- **质量补强版本**：第51轮图谱，194,600节点/263,059关系；`http://127.0.0.1:8766/`，单独配置/服务，不替代原默认版本
- **最新文档轮次**：第 51 轮（身份/概念补强与真实验收；失败证据约束未上线，最近真实训练仍为46轮）
- **最新状态**：见 [docs/system_status_round52.md](docs/system_status_round52.md)；历史滚动记录见 [docs/status_log.md](docs/status_log.md)

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

截至 2026-10-09（最新训练输入第45轮；最近真实训练第46轮；冻结开发重放第48轮；补充dev参考第49轮；50轮真实应用终验通过，当前运行31图）：

| 层级 | 数量 | 说明 |
|---|---:|---|
| 原始语料 | 20,000 篇 | DBLP 结构化 XML 解析的**书目**，标题规则筛选，不是神经 NER 输出 |
| AI 标注队列 | 2,000 篇 | 训练 1,600 / 验证 200 / 测试 200，按论文组隔离划分 |
| 训练输入（累计） | NER 1,530 篇可用 · RE 1,357 篇完整 | 两轮 AI 判断 + 同会话自复核后的可用样本；含未决与隔离集 |
| 摘要资产 | 108 篇整篇摘要（新8篇独立封存） | 原100为87篇DBLP对应 + 13篇外部训练；新8篇外部**补充dev**，未混入训练、test或生产图 |
| 整篇摘要训练标注 | 45轮队列62篇；58篇NER准入、隔离4篇，已用于46轮候选训练 | METHOD405 / TASK218 / DATASET55（20独立论文）；58旧收据字节不变，4新AI同会话复核非独立gold |
| 摘要明确关系对 | 45轮train271（USED_FOR184 / EVALUATED_ON61 / NO_RELATION26）；dev仍333（259 / 8 / 66） | train1659/1930、dev99/432对未决，不填负例；新增3评测来自1源论文，不冒充独立试验 |
| 摘要验证/测试 | dev19篇已自复核，NER16篇可用、3篇隔离 / test19篇保留 | dev METHOD116 / TASK53 / DATASET15提及；测试内容未消费或推理 |
| 49轮独立补充dev资产 | 固定8篇；7篇BIO/1篇隔离；METHOD55/TASK39/DATASET15 | 88明确（70用途/14评测/4负例）、390/478未决；评测3源论文、完整文档0/8，无新成绩或晋级 |
| 摘要NER候选 | 46轮train58 / dev16，6轮/174步，选epoch4；48轮仅结构性弃权 | 同dev总体F1 46轮70.84%→48轮72.02%；DATASET召回66.67%不变，未晋级 |
| 摘要RE候选 | 46轮train271 / 条件dev333对，6轮/408步，选epoch6 | 同dev条件正关系F1 42轮92.06%→46轮94.18%，不能替代完整流程 |
| 摘要pipeline对照（旧范围） | 历史完整dev5/19，含1篇零参考对；46条正例均USED_FOR | 35轮NER/旧RE F1 30.00%；37轮扩充NER/旧RE26.49%，拒绝晋级；不套用新7/19范围 |
| 最新完整关系开发对照 | 同dev7/19完整（36.84%）；107参考对为84用途/23负例 | 冻结42 F1 54.35%；46为39.53%、48为39.84%，错报119→117，完整EVAL仍0，不晋级 |
| 图谱（第 31 轮） | 194,639 节点 / 263,059 关系 / 21,497 候选断言 | 与旧图按 `graphId` 隔离共存，应用只查当前版本 |
| 当前工程回归 | 50轮D盘隔离临时目录下378项通过，136.29秒 | `tests_20261009_round50_complete.xml`；C默认tmp历史rename未修，零失败/错误/skip，不是语义正确率 |

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
│   ├── course_abstract_eval_attribution_v1.json # 41轮归属审计/显式撤回合同，不是新训练合同
│   ├── course_abstract_revised_training_v1.json # 42轮固定训练/四种dev对照合同，禁止test与晋级
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
│   ├── review_eval_attribution.py    # 旧EVAL逐对审计/撤回/证据扩张，不改NER或封存编译器
│   ├── train_revised_abstract_models.py # 41版输入薄适配，固定NER/RE训练与同dev对照
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
    ├── system_status_round31.md .. round48.md       # 48最新冻结解码/弃权；46最近真实训练
    ├── model_optimization_abstract_v1.md            # NER/RE开发及四种对照已执行，未达晋级门槛
    ├── status_log.md                # 历史滚动状态日志
    └── evidence/<日期>_roundNN/sources/             # 每轮真实截图、日志与源码快照
```

> `.venv-validation/` 与 `.venv-training/` 为本地虚拟环境（不入库），见 §7。

---

## 5. 数据与标注契约

**在用题名模型契约**：`resources/course_v4_config.json` + `schemas/annotation_course_v4.schema.json`。摘要标注有独立的 `course_abstract_queue_20261008_32/contract.json`；第35轮摘要模型合同为 `resources/course_abstract_v1.json`，训练/验证输入保持整篇原文、512token超长拒绝、不拼题名。来源manifest与收据哈希在输入快照中绑定；题名配置和最终测试入口原样保留。

41轮 `EVALUATED_ON` 口径：连接文中实际报告被测的方法、模型或评测协议配置与benchmark，**不要求独立消融，不蕴含因果改善或高性能**。完整组合可以保持，但二元边若丢失必需的组合/版本，须显式撤回为未决；缺测量证据不改成负例。每条旧/新pair和原文判断分别保存并绑定上游收据，旧快照不覆盖。

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

第41轮仅修归属与摘录：train267/1845明确（14.47%）、dev333/432明确（77.08%），完整dev仍7/19且EVALUATED_ON正例0。三条旧EVAL撤回至未决、一条原EVAL仅扩张证据；没有新Precision/Recall/F1，不能据标签减少称模型效果改变，也不将旧成绩套入新分母。[逐对变化与边界](docs/system_status_round41.md)。

第42轮实际训练与新同范围对照：NER50篇/150步、RE267对/402步，各6轮/epoch6；333已判对的条件模块宏F1 77.89%→82.13%，同7篇完整dev上新pipeline P50.00% / R59.52% / F1 54.35%，旧35NER/旧15RE重新推理为31.01% / 58.33% / 40.50%。**不能与旧5篇30.00%或26.49%直接比较**。NER DATASET的R86.67%→40.00%、F1 66.67%→46.15%，完整EVAL0/覆盖36.84%仍不达门槛；AI已暴露dev，不是独立金标准或最终测试。[完整指标与未解决问题](docs/system_status_round42.md)。

第46轮使用45版输入固定训练NER58篇/174步、RE271对/408步，并与冻结42在相同16篇NER与7篇完整关系开发范围重跑。NER总体F1 72.09%→70.84%，DATASET召回40.00%→66.67%；条件RE正关系F1 92.06%→94.18%，**完整流程F1 54.35%→39.53%**，错报正边50→119。质量门槛拒绝晋级；上述均为已暴露AI参考开发成绩，未运行本轮保留测试。[训练、对照和实际截图](docs/system_status_round46.md)。

第47/48轮不重新训练：47合法BIO虽然将非法转移65→0，完整流程F1反降至36.10%，已拒绝；48仅弃权冲突前缀/词内边界，58篇678训练实体原样，6实体/2对弃权，NER F1 72.02%、pipeline P29.94% / R59.52% / F1 39.84%。仍低于42同范围54.35%，完整EVAL0/覆盖不足，不晋级。原非法65仍记录、仅尾端点错报83未解，不能声称可靠性已解决。[共同核验与真实结果截图](docs/system_status_round48.md)。

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
# 默认回归命令：C默认临时目录历史rename失败尚未修；pytest.ini限定tests
& '.\.venv-validation\Scripts\python.exe' -m pytest tests -q

# 第50轮D盘隔离tmp流程378项通过；每次生成新目录/XML，不覆盖已有证据
& '.\.venv-validation\Scripts\python.exe' -c "import pathlib,sys,tempfile,pytest; validation_temp50=tempfile.mkdtemp(prefix='round50-validation-',dir='kg_datasets/dblp/course_v4_runs'); tempfile.tempdir=validation_temp50; sys.exit(pytest.main(['-q','--basetemp',str(pathlib.Path(validation_temp50)/'pytest'),'--junitxml',str(pathlib.Path(validation_temp50)/'regression.xml')]))"

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
- 摘要资产仅108篇，新增8篇是独立补充dev，未改旧训练/评测输入；**全文 PDF 不托管**（版权/付费墙），只给DBLP / DOI / arXiv外链。原外部基准13篇**仅训练侧**，不冒称DBLP子集或独立评测样本。
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
- 第42轮修订输入已接入真实NER/RE训练，新同7篇dev pipeline F1 54.35%，但FP50/FN34、DATASET召回退化、完整EVAL0和低覆盖仍阻断可靠性；不替换线上模型。工程在D盘隔离tmp下370项通过，C默认tmp两次rename失败根因仍未知，原失败保留、代码未改且未skip。[结果与边界](docs/system_status_round42.md)。
- 第44轮训练侧范围与漏标修复后NER54篇/隔离4篇，54篇BIO和372项D隔离tmp回归通过；DATASET仍44/16论文，未提升稀有支持，未重训或产生新成绩。仍缺独立评估及完整EVAL支持，不声称可靠性问题已解决。[当前数据及证据](docs/system_status_round44.md)。
- 第45轮四篇训练专用基准使NER58篇、DATASET55提及/20独立论文；373工程回归及严格编码通过。新增评测仅3跨度对/1论文，完整dev仍EVAL0/覆盖7/19；该轮当时尚未训练。[该轮输入、失败与证据](docs/system_status_round45.md)。
- 第46轮使用上述输入训练NER174步和RE408步；DATASET开发召回改善，但同7篇完整dev的端到端F1由54.35%退至39.53%，错报正边50→119，质量门槛拒绝晋级。374项D隔离回归、原始日志、四组合预测及两张真实结果图已封存。[历史训练结果](docs/system_status_round46.md)。
- 第48轮结构性弃权使完整F1小幅升至39.84%、错报117，但原BIO非法65和仅尾端点错报83仍在，完整EVAL0/覆盖不足使候选不晋级。376项D隔离回归与截图封存，不是重新训练、知识正确率验证或上线验收。[当前结果](docs/system_status_round48.md)。
- 第49轮固定补充8篇dev取得14条明确评测参考，但只3源论文且完整文档0/8，不能证明稀有关系泛化或完整流程质量。378回归及来源核验通过；该轮当时在线服务停止，未完成新应用验收，50轮已恢复并终验。[历史结果与阻塞](docs/system_status_round49.md)。
- 第50轮用户Desktop启动后当前JRE21、在线服务恢复，47项HTTP与8数据库只读检查、真实导出和三屏截图完成；31图/原题名模型冻结为候选检索工程交付。可靠性门槛、完整WCAG、教师终验和公网/多人运行未完成，不把功能通过说成知识正确。[当前在线结果](docs/system_status_round50.md)。

---

## 12. 文档与证据索引

| 文档 | 内容 |
|---|---|
| [docs/course_v4_plan.md](docs/course_v4_plan.md) | 课程实施计划：路线、评估约定、分阶段验收表 |
| [docs/course_v4_runbook.md](docs/course_v4_runbook.md) | **逐步运行说明**（命令层面的上游权威） |
| [docs/system_status_round50.md](docs/system_status_round50.md) | 当前真实候选检索闭环、47 HTTP/8数据库检查、三屏基线一致、导出与工程冻结 |
| [docs/system_status_round49.md](docs/system_status_round49.md) | 历史固定补充dev参考、378回归/截图及当时CLI环境阻塞 |
| [docs/system_status_round48.md](docs/system_status_round48.md) | 历史结构性弃权、精确缓存重放、376回归/结果截图，小幅改善但不晋级 |
| [docs/system_status_round47.md](docs/system_status_round47.md) | 历史冻结合法BIO对照：非法清零但完整流程退化，375回归 |
| [docs/system_status_round46.md](docs/system_status_round46.md) | 最近真实NER/RE重训、同范围四组合完整流程退化、晋级拒绝与结果截图 |
| [docs/system_status_round45.md](docs/system_status_round45.md) | 历史四篇训练基准补充、独立DATASET来源与58篇BIO/373回归，当轮未重训 |
| [docs/system_status_round44.md](docs/system_status_round44.md) | 历史训练侧范围清洗、四篇准入、两处实体修正、54篇BIO/372回归 |
| [docs/system_status_round43.md](docs/system_status_round43.md) | 历史训练侧诊断、遥感TASK边界修正与371回归 |
| [docs/system_status_round42.md](docs/system_status_round42.md) | 历史NER/RE真实训练、同dev四种对照、稀有类退化与拒绝晋级，有条件370回归 |
| [docs/system_status_round41.md](docs/system_status_round41.md) | 历史逐对评测归属、显式撤回/摘录修复与截图，未重训 |
| [docs/system_status_round40.md](docs/system_status_round40.md) | 历史开发关系证据/覆盖、标签风险与截图，未重训 |
| [docs/system_status_round39.md](docs/system_status_round39.md) | 训练侧评测归属与角色反例补强，train268对，未重训 |
| [docs/system_status_round37.md](docs/system_status_round37.md) | 历史扩量NER训练、固定RE对照、错误与拒绝决定 |
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

1. **P0实验可信度**：版本/指标纠错已落实；第09/17/29轮成绩封存，不重跑或用它们调参。继续AI标注路线并如实标记来源；独立人工抽检是可选扩展，不作为训练前提。
2. **P1标注质量**：45版四个新训练基准已加入，NER58/4隔离、明确271/未决1659，dev不改；DATASET55提及/20论文/31字面名（未归一），跨领域与独立支持仍不足。新增3评测仅1论文，不按已见dev/test选训练词或填未知负例。[当前输入与留痕](docs/system_status_round45.md)。
3. **P2摘要升级暂缓**：46真实重训、47/48固定解码实验与49固定8篇补充dev已完成，仍未满足质量晋级；新切片完整0/8、旧完整EVAL0。不继续盲训或消费保留test；摘要高可靠升级作为后续独立研究缺口，不能宣称已解决。378工程回归仅限定D隔离tmp，C默认rename未修。
4. **P3有限系统收尾已完成**：50轮真实只读验收（版本/计数、中文/作者检索、详情证据、多跳、候选清单实际导出和三屏截图）通过，当前31图/原模型冻结为本地候选检索工程交付。用户可直接试用；未完成的高可靠模型升级、全面无障碍、公网部署和教师终验不混称完成。语义检索和[文献Agent](docs/agent_kg_system_proposal.md)仍是后续提案。
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

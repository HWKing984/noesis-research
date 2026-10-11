# 以知识图谱为底座的文献 Agent —— 系统方案提案（v0）

> 状态：提案，未实现。本文只描述「要做什么、怎么做、边界在哪」，不对现有图谱、模型、标签做任何改动。
> 写于 2026-10-08，基于当前仓库实际代码与产物。
> 历史提案数据，不是当前实现状态。2026-10-09更正指标解释；最新系统状态见 `system_status_round55.md`。

---

## 0 结论

你的方向成立，而且底座已经现成：图谱、只读 API、前端、证据链都已在跑，缺的只是最上面的一层「用自然语言驱动检索与证据回溯」的 Agent。

但直接按「LLM 自由问答 + 图谱」做，会踩两个明确的坑，必须先修正前提：

1. **当前图谱是「候选断言图」，不是事实图。** 历史固定队列的完整 pipeline 正关系 F1 为60.07%（AI参考标签，69%覆盖），不能由此推导错误边比例。该子集Precision为58.57%，只描述这部分参考范围，不能外推全量图谱。Agent须保留候选标记并逐条引用证据，不能把预测当已核实事实；不同新留出和摘要开发结果见最新状态。
2. **「直接给出原文」现在拿不到全文。** 现有文本资产只有 20,000 条**题名**，加 75 篇**整篇摘要**（66 篇对应 DBLP 文献 + 9 篇 arXiv 外部基准，后者仅训练侧）。全文在出版商页面，有版权与付费墙，DBLP 不托管。所以「给原文」只能做成外链跳转 + 摘要级引用。

一句话：**Agent = 自然语言 → 结构化查询 → 结果 + 原文证据，每个事实性断句都能点开溯源。** 这是「能用的系统」，也是唯一不会被模型误差反噬的做法。

---

## 1 先修正的两个前提

### 1.1 图谱的可靠性边界（决定 Agent 形态）

| 指标 | 数值 | 对 Agent 的含义 |
|---|---|---|
| NER 严格 test F1 | 74.37%（AI 参考，72% 覆盖） | 实体边界会截短，端点可能错 |
| RE 模块（给参考实体）正关系 F1 | 99.25% | 只说明「给定正确实体时分类准」 |
| **完整 pipeline 正关系 F1** | **60.07%** | 这才是 Agent 实际面对的质量 |
| DATASET 类 dev F1 | 33.33%（参考仅 3 个） | 数据集相关回答最不可靠 |
| 断言性质 | `status: candidate`，`confidenceCalibrated: false` | 不许升格为事实 |

**设计约束（必须写进 Agent 契约）**：

- 每个事实性断句后面必须挂 `publicationId` / `assertionId`，没有证据的句子不允许输出。
- 模型抽取的方法—任务 / 方法—数据集关系，在回答里必须显式标「候选」，与书目字段（确定）在视觉和文案上分开。
- 明确拒答类问题：某论文是否「必引」、被引次数、引用链——图谱没有 CITES 关系，作者身份也只做到主页匹配而不做现实身份核验。

### 1.2 「原文」的真实可得性（决定功能边界）

| 层级 | 现有量 | 可否在系统内展示 | 做法 |
|---|---|---|---|
| 题名 | 20,000 | 可以 | 已在图谱，直接展示 |
| 整篇摘要 | 75（且有官方来源与许可记录） | 可以，需带来源标注 | 引用原文 + 标 `reference_provider` |
| 全文 PDF | 0 | **不托管** | 只给外链（DOI / arXiv / 出版商） |
| 引用网络 | 0 | 不可 | 不提供被引/必引类功能 |

摘要采集走的是 arXiv 官方页面的 `citation_abstract` / `citation_title` 元数据，带限速（≥3.1 秒/次）、内容哈希、政策记录（见 `scripts/collect_course_abstract_pages.py`）。**这是可以继续扩的合规通道**——想扩大摘要覆盖率，就沿这条路加量，而不是去抓全文。

**默认拍板**：MVP 只做「摘要级引用 + 权威外链」。系统内不存 PDF、不改写摘要、不提供无许可的全文摘录。

---

## 2 系统架构（四层）

```text
┌─ 交互层 ─────────────────────────────────────────────┐
│  自然语言输入 + 结构化筛选表单（保留） + 结果/证据面板  │
│  每条回答可点开：原文题名/摘要片段 · 模型哈希 · 候选标记 │
└───────────────────────┬──────────────────────────────┘
                        │
┌─ Agent 层（新建）──────▼──────────────────────────────┐
│  LLM planner + tool calling                          │
│  · 把自然语言翻译成结构化查询参数                      │
│  · 编排多个 tool 调用（检索 → 详情 → 证据 → 来源）     │
│  · 受约束生成：结构化摘要 + 逐条引用，不做开放式推理     │
└───────────────────────┬──────────────────────────────┘
                        │  只读 tool 调用
┌─ 工具层（扩展现有只读 API）───────────────────────────┐
│  search_publications   ← 已有 /api/publications       │
│  get_publication       ← 已有 /api/publication        │
│  explore_graph         ← 已有 /api/graph              │
│  get_abstract          ← 新增（读摘要包 + 许可记录）    │
│  find_sources          ← 新增（DBLP / DOI / arXiv 外链）│
└───────────────────────┬──────────────────────────────┘
                        │  参数化 Cypher
┌─ 图谱底座（已有）──────▼──────────────────────────────┐
│  Neo4j：194,639 内容节点 / 263,059 关系 / 21,497 候选断言 │
│  两版图共存，按 graphId 隔离；应用只查当前版本           │
└──────────────────────────────────────────────────────┘
```

关键点：**Agent 不直接连数据库**，只调用工具层。工具层的返回值已经是「带候选标记 + 证据哈希」的结构化结果，Agent 只做编排和措辞，无法凭空造事实。

---

## 3 复用现有能力 vs 需要新建

| 能力 | 现状 | 处置 |
|---|---|---|
| Neo4j 图谱与导入 | ✅ 已有（幂等、哈希校验、计数核对） | 直接用 |
| 只读 API（检索/详情/局部图） | ✅ 已有 4 个 endpoint | 直接作为 tool |
| 中文术语词表（22 条） | ✅ 已有 `zh_alias_v1` | 直接复用 |
| 证据回溯（题名/哈希/模型版本） | ✅ 已有 | 直接复用 |
| 候选清单导出（JSON/TXT） | ✅ 已有 | 直接复用 |
| 前端页面 | ✅ 已有单文件应用 | 上面加对话面板 |
| **摘要检索接口** | ❌ 无 | 新建 `get_abstract` |
| **外部来源解析（DOI/arXiv）** | ❌ 无 | 新建 `find_sources` |
| **LLM 运行时** | ❌ 无（此前标注是会话内人工驱动） | 需引入，见第 8 节 |
| **Agent 评测** | ❌ 无 | 新建，见第 7 节 |

---

## 4 MVP 范围（第一版就做这些）

1. **自然语言 → 结构化查询**：例如「找 2023 年以后用扩散模型做图像生成的论文」，由 Agent 翻译成 `method=diffusion model & task=image generation & year>=2023`，并在界面回显实际展开的参数（复用现有 `expandedTerms` 机制）。
2. **结果卡片 + 证据展开**：每条结果可展开作者、会议、模型提及跨度、候选断言，以及对应的原文题名证据与模型权重哈希。
3. **摘要展示**：图谱内有摘要的（当前 75 篇）展示摘要原文并标注来源；没有的明确写「本系统未收录该文摘要」，并给外链。
4. **来源跳转**：DBLP 原始记录、DOI、arXiv，按可访问性排序。
5. **候选清单 + 导出**：沿用现有 50 篇上限与 JSON/TXT 导出。

这五项合起来就已经是「老师要求的一个能用的系统」：能自然语言提问、能查到论文、能看到相关来源、能回溯证据。

---

## 5 明确不做的（边界，写进系统说明）

- 不做「某论文是否必须引用」的判定。
- 不做被引次数、引用链、影响力排序（无 CITES 数据）。
- 不在系统内托管或展示全文 PDF。
- 不把模型候选断言表述为已核实事实。
- 不用作者的姓名相似度自动合并身份。
- 不做跨版本（旧图 / 新图）混合统计。

---

## 6 关键设计约束（防幻觉、防升格）

1. **强制引用**：Agent 输出的每个事实性断句必须携带 tool 返回的标识；无标识则整句丢弃。
2. **候选标记透传**：`status: candidate` 必须原样出现在回答里，不允许改写成肯定语气。
3. **拒答白名单**：命中「必引 / 被引 / 引用链 / 影响力」类意图时返回固定说明，不检索、不生成。
4. **参数回显**：Agent 实际使用的查询参数必须显示给用户，避免「它到底搜了什么」不可见。
5. **无证据回退**：检索为空时明确返回「图谱无匹配」，不用 LLM 常识补内容。
6. **数值不臆造**：所有计数来自 `/api/health`，禁止 LLM 记数字。

---

## 7 评测方法（Agent 也要能被验收）

不评「回答好不好看」，评四条确定性指标：

| 指标 | 定义 | 判定方式 |
|---|---|---|
| 引用可溯率 | 回答中事实性断句带有效标识的比例 | 应为 100%，低于即失败 |
| 无证据断言率 | 出现无 tool 依据的句子比例 | 应为 0% |
| 参数回显一致率 | 回显参数与实际 tool 入参一致 | 应为 100% |
| 拒答准确率 | 命中边界意图时正确拒答的比例 | 需覆盖到全部边界意图 |

另加一条端到端：对现有 18 项 HTTP 验收所覆盖的查询，Agent 走一遍，结果集须与直接调用 API 一致（Agent 只做编排，不应改变检索结果）。

---

## 8 风险与默认假设

| 风险 | 说明 | 应对 |
|---|---|---|
| 模型精度（60.07% pipeline F1） | 错误边会进入回答 | 强制候选标记 + 逐条证据，用户可自行判断 |
| 稀有类不可靠（DATASET/EVALUATED_ON） | 数据集类回答最易错 | 该两类结果额外加显著提示 |
| 覆盖率低 | 21,497 断言只覆盖部分文献；摘要仅 75 篇 | 界面如实显示「本系统未收录」而非留空 |
| 版权 | 全文不可托管 | 只给外链，摘要用官方元数据通道 |
| LLM 供应商 | 现有仓库无运行时 LLM，此前标注靠会话内驱动 | 需选定一个 provider；建议配置化，默认走可替换的接口层，不写死单一厂商 |
| 中文检索 | 仅 22 条固定词表，非翻译 | 保持现状，未知中文原样检索 |

**默认假设（我按此推进，如与实际不符再改）**：

- 摘要仅用于展示与检索，不进入训练，不改变现有文本单位契约。
- Agent 只读，不写图谱、不改标签、不触发训练。
- 系统仍在 127.0.0.1:8765 单机只读运行。

---

## 9 实施顺序（可执行步骤）

1. 新增 `scripts/course_agent_api.py`：在现有只读 API 之上加 `/api/abstract` 与 `/api/sources` 两个 endpoint，复用 `course_graph.py` 的客户端与校验逻辑。
2. 新增 `scripts/course_agent.py`：定义 tool schema（包装现有 4 个 endpoint + 新增 2 个），实现 planner 与受约束生成、拒答白名单、参数回显。
3. 前端 `resources/course_literature.html` 增加对话面板，与现有表单检索并存；回答内嵌证据展开。
4. 新增 `tests/test_course_agent.py`：覆盖第 7 节的四项指标 + 端到端结果一致性。
5. 补齐摘要覆盖：沿现有 arXiv 官方元数据通道扩量（保持限速与许可记录），不进全文。
6. 出一份「Agent 能力与边界」说明页，把第 5 节的不做项直接写给用户看。

---

## 附：本方案依赖的现有产物

- 图谱包：`kg_datasets/dblp/course_v4_graph_*`
- 只读服务：`scripts/course_graph.py`（`export` / `verify` / `import` / `serve` / `check`）
- 前端：`resources/course_literature.html`
- 摘要包：`kg_datasets/dblp/course_abstract_*_20261008_32`
- 契约与配置：`schemas/annotation_course_v4.schema.json`、`resources/course_v4_config.json`
- 四实验总报告：`docs/course_complete_report_20261007.md`

---

## 10 复用策略：NOESIS 与开源底座（2026-10-08 补充）

### 10.1 结论

两条路都能走，但分工不同：**以「参考/移植 NOESIS 的机制」为主，「拿开源 agent 项目当底座」要严格筛选**。

原因：本项目的核心资产是**已经建成、带证据链的领域图谱**（21,497 条候选断言，每条带原文题名证据与模型权重哈希）。任何会自己重建数据层、或默认做开放式生成的底座，都会把这套可追溯性丢掉。所以选底座的唯一标准是：**它是否愿意把数据层让给你。**

### 10.2 NOESIS 可直接复用/参考的模块（均经源码核对）

| NOESIS 模块 | 路径 | 对本系统的用途 | 处置 |
|---|---|---|---|
| 能力编排（planner / executor / validator / evaluator / replay_gate） | `backend/app/langgraph_runtime/orchestration/` | Agent 层骨架：计划→校验→执行→评估 | 移植机制（同为 LangGraph，风格一致） |
| 能力契约（import-free descriptor + activation 谓词 + `to_planner_dict` 锁 keys） | `orchestration/capabilities.py`、`capability_protocol.py` | 定义 6 个只读工具的能力契约 | 复用形态 |
| MCP 工具层（registry / executor / envelope / loop_breaker） | `backend/app/langgraph_runtime/mcp/` | 工具注册、schema 指纹校验、结果封装、死循环熔断 | 复用形态（自带输入校验与安全边界） |
| 句子级引用追溯（纯函数、无 LLM、精确+模糊匹配） | `backend/app/services/citation_trace/` | 直接对应第 7 节的「引用可溯率 / 无证据断言率」 | 直接复用 |
| SSE 流式输出 | `backend/app/rag/streaming/sse.py`、`backend/app/streaming/turn_stream_hub.py` | 对话逐字输出 | 复用 |
| LLM 接入与降级 | `backend/app/rag/llm_client.py` | provider 抽象 | 复用 |
| 前端 Agent 过程与证据 UI | `frontend/src/components/`（`AgentPanel.jsx`、`AgentSwimlane.jsx`、`AgentWorkspace.jsx`、`agentEvidence.helpers.js`、`AnswerSummary.jsx`） | 对话 + 执行过程 + 证据展示 | 只做行为对齐，不复制样式 |
| 知识图谱前端辅助 | `frontend/src/components/graph/wanderForce.ts`（力导向布局） | 局部图布局算法 | 参考 |

### 10.3 必须修改的一处（关键差异）

`backend/app/knowledge/graph/neo4j_client.py` 的策略是**失败静默降级**：`execute()` 在驱动不可用时返回 `[]`，`_get_driver()` 失败时注释写的是走 in-memory fallback。这与本项目的既有铁律冲突——`scripts/course_graph.py` 的 `DatabaseUnavailable` 会明确返回 503，并在页面上写「未使用离线替代数据」。

**文献 Agent 若沿用 NOESIS 的客户端，会把「数据库不可用」伪装成「检索无结果」。** 必须替换为 `course_graph.py` 那套：连接失败即 `DatabaseUnavailable` → HTTP 503，不返回空列表。

### 10.4 NOESIS 不适合整仓搬的部分

NOESIS 是 Postgres + SQLAlchemy + Alembic 的**学习域**系统，带账号、课程空间、掌握度、语音记忆等大量与文献检索无关的领域模型。整仓迁移会引入无关依赖与鉴权体系。正确做法是**移植机制，不移植应用**。

另注：NOESIS 有 `THIRD_PARTY_NOTICES.md` 与 vendored 树约束，其中 `citation_trace` 是 Apache-2.0 移植的产物。若复用这些模块，需保留相应归属声明。

### 10.5 开源 agent 项目作底座的筛选

| 类型 | 代表项目 | 与本项目的契合 | 结论 |
|---|---|---|---|
| 从文本自动建图（GraphRAG 系） | Microsoft GraphRAG、LightRAG、nano-graphrag | 会重建自己的图（社区摘要、自己的实体消歧），与本项目手工构建、证据绑定的断言冲突，等于丢掉可追溯性 | 不用 |
| 全平台 / 低代码工作流 | Dify、RAGFlow、FastGPT、Langflow | 要求接管数据层与回答范式，接入只读 API 需自定义工具，且难保证候选标记透传 | 不用 |
| 轻量机制库 | LangGraph（NOESIS 已用）、Neo4j 官方 `neo4j-graphrag-python`（内置 Vector / Text2Cypher / Hybrid 检索器）、OpenAI Agents SDK | 只提供机制，数据层仍归本项目 | 推荐 |

**推荐的组合**：LangGraph（编排）+ `neo4j-graphrag-python` 的 retriever（图谱检索）+ 本项目自己的只读工具。

注意：`Text2CypherRetriever` 能省掉「自然语言→Cypher」那一层，但 LLM 生成的 Cypher **必须经过白名单校验**——只允许只读语句、必须带 `graphId` 过滤、必须复用第 6 节的参数校验，否则会绕过现有全部参数边界。

### 10.6 推荐路线

1. 以 `scripts/course_graph.py` 的只读 API 为唯一数据出口，扩出 `get_abstract` / `find_sources`（第 9 节步骤 1）。
2. Agent 层按 `langgraph_runtime/orchestration/` 的能力契约形态实现，工具层按 `mcp/registry.py` 的注册与校验形态实现（第 9 节步骤 2）。
3. 引用校验直接采用 `services/citation_trace/` 的句级归因，作为交付前的确定性闸门（第 7 节四项指标）。
4. 前端在现有 `resources/course_literature.html` 上加对话面板，交互结构参考 `AgentPanel` / `AgentSwimlane` / `AnswerSummary` 的信息层级，样式自行实现。
5. 不引入 GraphRAG 系与全平台系；不整仓迁移 NOESIS。

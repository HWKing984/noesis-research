# 第一阶段 · 可执行计划

> 目标（来自方案 B 阶段 1）：**基础系统可以真正运行** —— 接入前端 / FastAPI / Deep Agents / 现有只读 KG API，完成论文检索、论文详情、局部图谱、Agent 问答与流式输出。
> 验收：**一次真实研究查询能返回真实论文，并能在页面点击查看证据。**

前置：`docs/01_source_audit.md` 审计已完成（本计划的路径 / 行号均出自该报告）。

---

## 0 从第一阶段就必须设计好的四项（不留给上线补）

| # | 项 | 落地方式 | 对应任务 |
|---|---|---|---|
| A | **KG 只读边界** | 研究 Agent 无 Cypher 入口；唯一数据出口是 KG 只读 HTTP API；仓库内不出现任何写语句 | T2 |
| B | **引用来源 ID** | 每条事实性断句必须挂 `publicationId` / `assertionId`，无标识则整句丢弃 | T5 |
| C | **任务状态持久化** | `research_runs` 表 + SSE 事件落库，断线可重连、失败可重试 | T4 |
| D | **权限收紧** | Agent 无宿主机 Shell；文件操作限定在隔离工作目录 | T6 |

---

## 1 任务分解

### T1 · 工程骨架与依赖隔离 ✅ 已完成（2026-10-08）

- 产出：本仓库目录结构 + `README.md` + 本文档 + `docs/01_source_audit.md`。
- 验证：目录存在；审计报告含路径 / 行号 / 版本三类证据。

### T2 · 只读 KG Adapter（安全集成第一块砖）✅ 已完成（2026-10-08，含评审整改）

- 产出：`integrations/knowledge-graph/kg_client.py`，纯标准库，封装 4 个端点：`health` / `search` / `publication` / `graph`。
- 硬约束：
  1. `503` → `KGUnavailable` 抛出，**绝不返回空结果**（取代 NOESIS `neo4j_client.execute() -> []`）。
  2. `400` → `KGInvalidRequest`；`404` → `KGNotFound`；非 JSON → `KGError`。
  3. **200 但结构不符也失败**：`data` 必须是数组/对象且元素类型正确，缺失或类型错一律 `KGError`（`data: []` 仍是合法空结果）。
  4. 入参边界与 `course_graph.py:379 / :418` 一致（白名单字段、limit 1–100、offset ≤ 20000、year 2015–2025、graph limit 1–50）。
  5. `meta.expandedTerms` / `meta.aliasVersion` 原样透传给上层，供"参数回显"。
  6. **服务地址可配置**：`resolve_base_url()` = 显式参数 > `KG_BASE_URL` 环境变量 > 环回默认（容器部署用）。
  7. **图谱版本一致**：`KGGraphMismatch` + `expected_graph_id` / `KG_EXPECTED_GRAPH_ID`；`assert_graph_version()` 要求服务 `ready` 且 graphId 等于锁定值。仅在响应确实携带 `graphId` 且已设锁时比对，字段缺失不误报。
  8. **断言按真实形状建模**：`Assertion`（`assertion` / `head` / `tail` 三个子对象），因为 `/api/publication` 返回的是包装结构而非断言属性本身。
- 验证：
  - 离线单测 `test_kg_client.py` **40 项**（注入假 transport，覆盖 4 种错误映射 + 12 项结构校验 + 版本一致性 + 配置优先级）。
  - 真实集成 `tests/integration/test_kg_live.py` **11 项**，对 `127.0.0.1:8765` 实跑通过。

### T3 · 业务 API（`apps/api`）✅ 已完成（2026-10-08，3 个端点）

- 产出（**仅这三个业务端点 + 一个就绪探针**，第一轮要的就是闭环）：
  `GET /api/health` · `GET /api/papers/search` · `GET /api/papers/{publication_id}` · `GET /api/graph/neighbors`
- 移出第一阶段（评审 P1-7）：`POST /api/library/papers`（收藏）、`POST /api/documents/upload`（上传）、`POST /api/reports/{id}/export`（导出）→ 阶段 2 / 3；`POST /api/research/runs` 等任务类接口 → T6。
- 错误语义（**没有任何一条把失败变成"空结果"**）：503 `kg_unavailable` / 503 `kg_graph_version_mismatch` / 400 `invalid_request` / 404 `not_found` / **502 `kg_bad_response`（上游 200 但结构不符）** / 500 `internal_error`。
- 证据随数据走：每条论文与每条候选断言都带 `evidence`；候选断言 `status` 恒为 `candidate`、`confidenceCalibrated` 恒为 `false`。
- 两个实机才会踩的实现点：`{publication_id:path}` 必须用 `:path`（DBLP 键含斜杠）；该路由必须注册在 `/papers/search` 之后。
- 验证：`apps/api/test_api.py` **18 项**（HTTP 边界，真实 app + 真实适配器 + 真实 Pydantic，只换 socket）；`tests/integration/test_api_live.py` **8 项**对真实服务跑通；另起真实 uvicorn 打真实 Neo4j 验证通过（见 §5）。

### T4 · 最小 Deep Agent（`services/research-agent`）

- 产出：一个主 Agent + 5 个只读工具（`search_papers` / `get_paper` / `explore_graph` / `get_paper_evidence` / `read_paper` 留待阶段 2）。
- 形态对齐：能力契约参考 `orchestration/capability_protocol.py:74-91`；工具注册参考 `mcp/registry.py:36-63`（schema 指纹 + 默认串行）。
- 硬约束：**只用主 Agent，不上子 Agent**（普通检索不经多模型，避免延迟与成本翻倍）；子 Agent 仅保留给长篇综述 / 多主题比较。
- 依赖：**独立 venv**（`deepagents 0.7.23`，`langchain-openai` 指向 `LLM_BASE_URL`）。不得装进 NOESIS / KG 的 venv。
- 验证：给定一条真实查询，工具调用链与直接调 KG API 的结果集一致。

### T5 · 引用闸门（交付前确定性校验）

- 产出：`packages/citation-validator/`，**移植** `services/citation_trace/verify.py:134` 的三阶段降级（精确 → 有界 difflib → 批量 LLM），保留 Apache-2.0 归属头。
- **证据契约先行（已完成）**：`packages/contracts/evidence.py` 定义统一 `EvidenceRef`，把三件常被混为一谈的事分开：
  1. `sourceType` / `sourceId` —— 来自哪条记录（`kg_bibliography` / `kg_assertion` / `paper_passage` / `external_record`）
  2. `evidenceLevel` —— 证据深度（`title` / `abstract` / `fulltext`）：**标题级命中只能证明论文存在**
  3. `verificationStatus` —— 核验到哪一步了（四级阶梯，见下）
- **四级阶梯**（准入条件由代码强制，违反即 `EvidenceError`）：

  | `verificationStatus` | 含义 | 硬准入 |
  |---|---|---|
  | `unverified` | 尚未核 | — |
  | `id_valid` | id 能解析到真实记录 | — |
  | `evidence_supports` | 引文支持该句 | 必须非空 `evidenceText` |
  | `semantic_verified` | 蕴含成立 | 必须有引文 **且** `evidenceLevel ∈ {abstract, fulltext}` |

- 四项指标（阶段 1 即纳入 CI）：
  1. 引用可溯率 = 事实性断句带有效标识比例（应 100%）
  2. 无证据断言率（应 0%）
  3. 参数回显一致率（应 100%）
  4. 拒答准确率（覆盖全部边界意图：必引 / 被引次数 / 引用链 / 影响力）
- 验证：`packages/contracts/test_evidence.py` **29 项** + 对现有 18 项 HTTP 验收查询跑端到端一致性。

### T6 · SSE 与运行记录

- 产出：流式输出 + `research_runs` / `research_run_events` 持久化。
- 复用参考：`streaming/turn_stream_hub.py`、`rag/streaming/sse.py` 的行为形态（不复制实现）。
- 验证：断开连接后重连可取回已产生的全部事件；取消后任务状态为 `cancelled`。

### T7 · 前端承载（`apps/web`）

- 产出：在 NOESIS 前端体系内实现统一研究工作区（概览 / 科研助手 / 论文库 / 知识图谱 / 研究项目 / 研究报告），右侧可切换 论文详情 / PDF 阅读 / 图谱 / 报告 Artifact 面板。
- 复用参考（**只做行为对齐，不复制样式**）：`AgentPanel.jsx` / `AgentSwimlane.jsx` / `AnswerSummary.jsx` / `ArtifactPanel.jsx` / `GraphPanel.jsx`。
- 硬约束：候选断言在 UI 上必须与书目字段在文案与视觉上分开显示。
- 验证：无头浏览器截图 + 局部图交互断言。

### T8 · 外部学术源连接器（`integrations/openalex` `crossref` `semantic-scholar`）

- 产出：三个连接器，覆盖 2026 年及以后的论文发现。
- **优先复用，不重写**（2026-10-08 核实）：`reference/paper-qa` 的 `src/paperqa/clients/` 里 **已存在 `openalex.py` / `crossref.py` / `semantic_scholar.py`**（另有 `unpaywall.py` / `retractions.py`），是 `httpx` + `tenacity` 的完整实现。按评审"能直接复用就直接复用"的原则，这层应优先复用其网络与解析，而不是另写一套。见 `docs/04_reference_clones.md` §2.2。
- 硬约束：匹配优先级 = **DOI → 精确 arXiv ID → 明确来源标识**；仅标题相似度匹配一律留为「待确认候选」，**不得合并论文身份**。
  → 注意上游用 `strings_similarity` 做标题相似度匹配；**判定层按本项目规则收紧**，不能沿用其"标题匹配即可定身份"的宽松度。
- 外部记录进独立业务表，不回写 SciBERT 图谱。
- 验证：连接器离线契约测试（录制响应）+ 身份匹配的负例测试（相似标题不得自动合并）。

---

## 2 依赖与许可台账

| 组件 | 来源 | 许可 | 备注 |
|---|---|---|---|
| Deep Agents | PyPI `deepagents 0.7.23` | 见上游仓库 | 不 Fork 框架核心 |
| LangGraph | PyPI `langgraph>=1.2.9` | MIT | NOESIS 已在用，风格一致 |
| LangChain / langchain-core / langchain-openai | PyPI | MIT | 研究 Agent 独立 venv 内升级，不动 NOESIS |
| PaperQA2 | PyPI `paper-qa 2026.8.12` | Apache-2.0（上游仓库） | 独立服务 |
| NOESIS 移植模块 | `D:\a-Soft` | 见 `THIRD_PARTY_NOTICES.md` | `citation_trace` 为 openJiuwen Apache-2.0 算法移植，须保留归属 |
| AI-Literature-KG API | `D:\a-open_source\neo4j` | 本地项目 | 只读消费 |

### 锁定策略（评审 P1-5）

- **现状**：`integrations/` 与 `packages/` 的代码**零第三方依赖**，只 import 标准库 —— 这是刻意的，因为这是 Deep Agents 工具的直接底座。API 层（`apps/api`）是第一处引入第三方依赖的地方，因此依赖按层拆开维护（`apps/api/requirements.txt`），不与 Agent 层的 LangChain 栈混在一起。
- **CI 分两个 job**：
  - `core`（**不装任何依赖**）：Python 3.11 / 3.13 双版本跑 `compileall` + 离线套件；并断言 `api` / `live` 套件**确实是被跳过**（`--expect-skip`），避免"因为 import 坏了而静默变绿"。
  - `api`（装 `apps/api/requirements.txt`）：跑 HTTP 套件，并断言 `api` 套件**没被跳过**（`--require`）。
- **服务级锁随服务落地**：`services/research-agent/requirements.txt` 目前是**直接依赖 pin**（`deepagents==0.7.23` 等，取自 PyPI 元数据实测）；完整传递闭包锁（`pip-compile` / `uv lock`）在 T4 建 venv 时生成并回填，不预先写一份假锁。

### 复用策略（评审策略调整，已生效）

> **能直接复用的模块就直接复用；有冲突的模块才通过 Adapter 隔离；需要独立业务能力的部分再开发。**

前端相应改为**优先原组件移植**（聊天、Agent 过程、Artifact、局部知识图谱、研究状态展示），只有数据契约或样式冲突时才在边界层隔离 —— 不再只做"行为对齐"。

---

## 3 风险表

| 风险 | 证据 | 应对 | 触发任务 |
|---|---|---|---|
| Deep Agents 抬升 `langchain-core` 下界至 `>=1.6.7`（NOESIS 现 `>=1.4.9`） | PyPI 元数据 | 独立 venv；若需回灌 NOESIS，先跑其全量回归区分 pre-existing / 新引入失败 | T4 |
| KG 与 NOESIS 可能共用同一 Neo4j 实例 | `NEO4J_URI` 形态 vs KG `7474` | 只走 KG 只读 HTTP API；禁用 NOESIS `neo4j_client`；直连路线（当前不采用）一律要求只读账号 | T2 / T4 |
| 模型精度：完整 pipeline 正关系 F1 仅 **60.07%**（AI 参考，69% 覆盖） | README §6 | 强制候选标记 + 逐条证据，不做开放式生成 | T5 |
| 稀有类不可靠：DATASET / EVALUATED_ON | README §11 | 这两类结果额外加显著提示 | T5 / T7 |
| 摘要仅 75 篇、全文 0 篇 | README §2 / §11 | UI 如实显示「本系统未收录」，不留空、不给外链以外的承诺 | T7 |
| 中文检索仅 22 条固定别名（精确匹配，非翻译） | `zh_alias_v1` | 保持现状，未知中文原样检索；界面回显 `expandedTerms` | T2 / T7 |

---

## 4 明确不做（写进系统说明）

- 不做「某论文是否必须引用」判定；不做被引次数 / 引用链 / 影响力排序（无 CITES 数据）。
- 不在系统内托管或展示全文 PDF。
- 不把模型候选断言表述为已核实事实。
- 不用作者姓名相似度自动合并身份。
- 不做跨图谱版本混合统计。
- 研究 Agent 不对 Neo4j 执行任何写操作。

---

## 5 当前进度

| 任务 | 状态 | 证据 |
|---|---|---|
| T1 工程骨架 | ✅ | 目录 + 三份文档 |
| T2 只读 KG Adapter | ✅ | 离线 40 项 + 真实集成 11 项 |
| 证据契约（T5 前置） | ✅ | `packages/contracts/evidence.py`，29 项 |
| T3 业务 API（3 端点） | ✅ | HTTP 18 项 + 真实集成 8 项 + 真实 uvicorn 冒烟 |
| CI / 统一测试入口 | ✅ | `.github/workflows/ci.yml` 双 job、`scripts/run_all_tests.py` |
| T4 Deep Agents | ⏭ 下一步 | — |
| T7 前端移植 | ⏭ | — |

**T3 实机冒烟结果**（真实 uvicorn `127.0.0.1:8100` → 真实 Neo4j）：

```text
GET /api/health                -> 200  status=ready graphId=ai-literature-ed16399925fac2a599ed
GET /api/papers/search?q=transformer&limit=3
                               -> 200  papers=3  applied={"q":"transformer","limit":"3","offset":"0"}
GET /api/papers/conf/IEEEwisa/LinGHW25
                               -> 200  authors=4 venues=1 mentions=3 assertions=2
                                   assertion: USED_FOR / candidate / calibrated=False / 0.9999832
GET /api/graph/neighbors?id=…&limit=5
                               -> 200  nodes=6 edges=5 rootId_in_nodes=True
GET /api/papers/no-such-…      -> 404  code=not_found
GET /api/graph/neighbors?mode=everything -> 400 code=invalid_request
```

本轮验收目标（评审给定）：**Deep Agents 完成一次真实的 Neo4j 文献检索并返回可点击证据** —— 数据侧已全部打通且可点（每条论文/断言都带 `evidence` 引用），剩下的是把 Agent 接上去。



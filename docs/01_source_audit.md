# 第一阶段 · 源码审计报告

> 审计对象：`D:\a-open_source\neo4j`（AI-Literature-KG）、`D:\a-Soft`（NOESIS）、PyPI（新增依赖）。
> 审计日期：2026-10-08。方法：直接读取源码与配置，逐条核对路径 / 行号 / 版本；非推测。
> 结论先行：**方案 B 的接入路线成立，且可复用面比 v0 提案更大；最大的两个硬约束是「Neo4j 只读边界」与「Deep Agents 的依赖升级」。**

---

## 0 结论摘要

1. **NOESIS 源码可直接读到**（`D:\a-Soft`，git 仓库），v0 提案里"尚无 NOESIS 源码快照"这一阻塞项**已解除**。
2. v0 提案列出的 8 个 NOESIS 复用模块**全部核实存在**，并新增一处提案未发现的资产：`backend/app/research/`（自带 `Evidence` / `Citation` / `ResearchResult` 数据模型与引用校验），与本方案「研究报告工作区 + 引用核验」高度同构。
3. **必须替换而非复用**：NOESIS 的 `knowledge/graph/neo4j_client.py` 在数据库不可用时静默返回 `[]`，并暴露 `delete_all()` 全库删除。与 KG「不可用即 503、绝不返回离线替代数据」铁律直接冲突，且具破坏性。
4. **新增依赖有真实升级成本**：`deepagents` 要求 `langchain-core>=1.6.7`（NOESIS 现为 `>=1.4.9`）并引入 `langchain` 元包、`langchain-anthropic`、`langchain-google-genai`。必须独立 venv，**不得装进 NOESIS 或 KG 的现有 venv**。
5. **前端图技术栈已经对齐**：NOESIS 前端已含 `sigma` / `reactflow` / `graphology` / `d3-force` / `echarts` / `three`，计划中的「Sigma.js + React Flow」**无需新增前端依赖**。
6. **LLM provider 已有可用配置**：`a-Soft/backend/.env` 存在且 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` 均已设置（OpenAI 兼容）。研究 Agent 复用即可，**不需要用户提供新密钥**。

---

## 1 AI-Literature-KG（`D:\a-open_source\neo4j`）—— 数据与图谱底座

### 1.1 可复用资产（直接作为工具层）

| 资产 | 位置 | 实测证据 | 处置 |
|---|---|---|---|
| 只读 HTTP API（4 个） | `scripts/course_graph.py` | `api()` @ **L458**；路由白名单 L459 = `/api/health` `/api/publications` `/api/publication` `/api/graph` | 直接作为 4 个 tool |
| 数据库不可用语义 | 同上 | `class DatabaseUnavailable` @ **L285**；`Neo4j.query` @ **L298**；HTTP **503** + 文案「未使用离线替代数据」@ **L518-519** | **契约必须继承** |
| 参数校验边界 | 同上 | `search_parameters()` @ **L379**（白名单 = `q/author/authorId/venue/method/task/dataset/year/limit/offset`；limit 1–100；offset 0–20000；year 2015–2025）；`graph_parameters()` @ **L418**（mode ∈ {paper,coauthors,methods}；limit 1–50） | 工具入参复用同一套边界 |
| 中文别名检索 | `resources/course_v4_config.json` | `TERMINOLOGY` 经 `/api/publications` 的 `meta.aliasVersion` 与 `meta.expandedTerms` 回显（L481-483） | 直接复用，工具层须回显 `expandedTerms` |
| 局部图谱响应 | `course_graph.py` | `graph_response()` @ **L427**，返回 `nodes/edges/paths/rootId` + `meta.wholeGraph=false` + 免责 `notice`（L452-455） | 直接复用 |
| 文献详情 | 同上 | `/api/publication` 返回 `publication/authors/venues/mentions/assertions/citationDraft` + `notice`（L497-499） | 直接复用；`citationDraft` 是**草稿**不是正式引用 |
| 前端单文件应用 | `resources/course_literature.html` | 由 `serve` 在 `127.0.0.1:8765` 提供（Handler @ **L502-526**） | 只做交互参考，不直接搬进新前端 |
| 图谱包与版本锁 | `kg_datasets/dblp/course_v4_graph_resolved_20261007_31_ready/`、`resources/course_graph_runtime.json` | README §9：默认入口先校验路径 / `graphId` / manifest 哈希，漂移即停止 | **只读**；Agent 不得触发导入 |
| 机器可读契约 | `schemas/annotation_course_v4.schema.json` | Draft2020-12 | 参考，不修改 |

### 1.2 不可动资产（形成硬边界）

- **训练 / 推理 / 导入流水线**（`scripts/train_course_*.py`、`infer_course_corpus.py`、`course_graph.py import/export`）：研究 Agent **不得触发**。图谱是版本化、有封存测试的产物。
- **图谱写入**：`scripts/course_graph.py` 的 `import` 是唯一写入口，且依赖交互式密码输入；新系统不得实现任何 Cypher 写路径。

### 1.3 数据分级能力（决定"系统是否真实可用"）

| 资料级别 | 现有量 | 系统可做 |
|---|---|---|
| 只有书目 | 20,000 | 搜索 / 过滤 / 收藏 / 元信息 |
| 标题 + KG 候选关系 | 21,497 条候选断言 | 方法 / 任务探索，**必须标 `status: candidate`** |
| 真实摘要 | 75 篇（66 DBLP + 9 arXiv 外部基准，后者仅训练侧） | 摘要级检索与分析，须标来源 |
| 合法全文 | **0** | 不托管；只给 DOI / arXiv / 出版商外链 |
| 引用网络 | **0**（无 CITES 数据） | 不提供被引 / 必引 / 影响力功能 |

---

## 2 NOESIS（`D:\a-Soft`）—— 产品框架（移植机制，不整仓搬）

### 2.1 已核实的可复用模块

| 模块 | 路径 | 实测证据 | 用途 |
|---|---|---|---|
| 能力编排 | `backend/app/langgraph_runtime/orchestration/` | 含 `planner.py` `executor.py` `plan_validator.py` `evaluator.py` `replanner.py` `replay_gate.py` `capabilities.py` `understanding.py` | Agent 层骨架：计划 → 校验 → 执行 → 评估 |
| 能力契约（import-free） | `orchestration/capability_protocol.py` | `register_capability_protocol()` @ **L74-91**：注册期即校验 `name == capability_id`（漂移即报错）、`is_active` 必须可调用；可选钩子 `pre_task` 走 `getattr`，不实现也算合法实现；不变量「augment, don't suppress」+「fail open」@ L27-33 | 6 个只读工具的能力契约形态 |
| 工具注册与安全边界 | `backend/app/langgraph_runtime/mcp/` | `registry.py`：`RegisteredTool.schema_fingerprint` @ **L59**、`parallel_safe: bool = False` @ **L63**（默认串行）；模块 docstring 声明**不依赖 MCP SDK**，先造确定性安全边界 | 工具注册 / schema 指纹 / 结果封装 / 死循环熔断 |
| 工具结果封装 | `mcp/tool_result_envelope.py` | 移植自 openJiuwen `mcp-tool-protocol`，含 `untrusted: true` 常量标记 + 归属字段 | 工具返回统一封装 |
| 死循环熔断 | `mcp/tool_loop_breaker.py` | `RoundFingerprintTracker`，连续相同 tool-call/args 轮次 warn→bailout | Agent 稳定性 |
| **句级引用追溯** | `backend/app/services/citation_trace/` | `tracer.py` `text_match.py` `verify.py`；`verify_citations()` @ **verify.py L134**：三阶段降级 精确 `str.find` → 有界窗口 difflib → 批量 LLM（`MAX_LLM_RETRY_TIMES=3` @ L49，`DEFAULT_LLM_BATCH_SIZE=12` @ L52）；**stages 1-2 零成本**，LLM 只处理残差 | 直接对应验收指标「引用可溯率 / 无证据断言率」 |
| **研究报告数据模型**（v0 提案未发现） | `backend/app/research/` | `models.py`：`SearchResult` / `Source` / `Evidence` / `Citation(claim_index, evidence_id, source_id, verified)` / `ResearchResult(status, warnings, trace_id)`；`service.py` L19-81 `ResearchService.research()`（Firecrawl 搜索→抓取→证据→引用校验，含 `Semaphore(5)` 并发与 `validate_public_url` SSRF 防护） | **报告工作区 + 引用核验的同构模板** |
| SSE 流式 | `backend/app/rag/streaming/sse.py`、`backend/app/streaming/turn_stream_hub.py`、`services/turn_stream_scheduler.py` | 目录实测存在 | 对话逐字输出、断线重连 |
| LLM 接入 | `backend/app/rag/llm_client.py` | 含 `chat_with_meta` / `_stream_typed`，已接 openJiuwen rate-limiter（见 NOTICES L65-66） | provider 抽象，按 host 限流 |
| 导出 | `backend/app/services/exporters/` | `pdf_png_exporter.py` `pptx_exporter.py`；另有 `services/lecture_docx_exporter.py` | 报告导出（Markdown / DOCX / PDF / BibTeX 的落点） |
| 前端 Agent 过程与证据 | `frontend/src/components/` | 实测存在 `AgentPanel.jsx` `AgentSwimlane.jsx` `AgentWorkspace.jsx` `AnswerSummary.jsx` `agentEvidence.helpers.js` `agentEvidenceLog.helpers.js` `toolCallTimeline.helpers.js` `RuntimeTimeline.jsx` | **只做行为对齐，不复制样式** |
| 前端 Artifact 工作区 | 同上 | `ArtifactPanel.jsx` `ArtifactTaskCard.jsx`；后端 `services/artifact_store.py` `artifact_version_service.py` `artifact_storage.py` | 报告 / 导出文件的版本化落点 |
| 前端图谱 | 同上 | `GraphPanel.jsx` `KnowledgeGraphSigma.jsx` `KnowledgeGraphTab.jsx` `KnowledgeForceGraph.tsx` `components/graph/wanderForce.ts` | 局部图交互参考 |

### 2.2 必须替换的一处（关键冲突）

`backend/app/knowledge/graph/neo4j_client.py`：

- `_get_driver()` @ **L30-47**：连接异常时 `logger.warning("... Using in-memory fallback.")` 并返回 `None`。
- `execute()` @ **L81-97**：docstring 明写「不可用时返回空列表而不是抛错」，异常路径 `return []`。
- 另含**写方法**：`create_node` L104、`create_relationship` L110、`delete_all` @ **L153-155**（`MATCH (n) DETACH DELETE n`）。

**判定**：研究 Agent 若沿用此客户端，会把「数据库不可用」伪装成「检索无结果」——正是 KG 铁律禁止的行为；`delete_all()` 在共享 Neo4j 实例上更是不可接受的爆炸半径。**必须替换为 `course_graph.py` 那套：可预期失败 → `DatabaseUnavailable` → 503。**

### 2.3 许可与归属（复用前须保留）

`a-Soft/THIRD_PARTY_NOTICES.md` 实测内容：

| 上游 | 许可 | 与本方案的关系 |
|---|---|---|
| DeepSeek Harness | MIT | SSE framing / 流式翻译 |
| VoiceMem | Apache-2.0 | 无关 |
| **openJiuwen（agent-core / agent-memory / deepsearch / sciencediscovery）** | Apache-2.0 | **`services/citation_trace/` 三个文件均为其算法移植**（`text_match.py` ← `citation_verify_research.py:65-115`；`tracer.py` ← `source_tracer.py`；`verify.py` ← 同文件的分级降级）。移植须保留文件头归属与 file:line 引用 |
| yt-dlp | Unlicense | 无关 |

### 2.4 依赖基线（`backend/requirements.txt` 实测）

`fastapi>=0.109` · `uvicorn` · `pydantic>=2.5` · `neo4j>=5.18` · `sqlalchemy>=2.0` · `psycopg2-binary` · `redis>=5.0` · `chromadb>=0.4.22` · `mcp>=1.5.0` · `mem0ai` · `openai>=1.0` · **`langchain-core>=1.4.9`** · `langchain-openai>=1.3.5` · **`langgraph>=1.2.9`** · `python-docx` / `python-pptx` / `reportlab` / `pdfplumber` / `openpyxl` / `markdown-it-py` / `latex2mathml`。

> 注意：**没有** `langchain` 元包、**没有** `deepagents`、**没有** `paper-qa`。

---

## 3 新增依赖可行性（PyPI 实测，2026-10-08）

| 包 | 最新版 | requires_python | 关键依赖 | 判定 |
|---|---|---|---|---|
| **`deepagents`** | `0.7.23` | `>=3.11,<4.0` | `langchain>=1.4.3` · **`langchain-core>=1.6.7`** · `langchain-anthropic>=1.7.5` · `langchain-google-genai>=4.4.0` · `langsmith>=0.14.4` · `packaging` · `wcmatch`（extras: aws / quickjs / video） | **可装，但必须独立 venv**。相对 NOESIS 会新引入 `langchain` 元包 + Anthropic + Google GenAI SDK，并把 `langchain-core` 下界从 `1.4.9` 抬到 `1.6.7` → 有依赖升级风险 |
| **`paper-qa`** | `2026.8.12` | `>=3.11` | `fhaviary[llm]>=0.34` · `fhlmi>=0.45` · `httpx-aiohttp` · `paper-qa-pypdf` · `pybtex` · `tantivy`（Rust wheel）· `tiktoken` · `pydantic>=2.10.1` · `numpy` | 与 NOESIS 依赖几乎不重叠，**按计划独立服务**，成本可控 |

> Deep Agents 的正典接线是 Anthropic / Google，但它是 LangChain 生态组件，可注入任意 `BaseChatModel`；本工程用 NOESIS 已有的 OpenAI 兼容端点（见 §4）。

---

## 4 环境实测

| 项 | 实测结果 | 影响 |
|---|---|---|
| NOESIS 后端 `.env` | `a-Soft/backend/.env` **存在**；`LLM_API_KEY`(35) / `LLM_BASE_URL`(24) / `LLM_MODEL`(17) / `DEEPSEEK_API_KEY`(35) 均已设置 | 研究 Agent **复用同一 provider，无需用户提供密钥** |
| LLM 配置口径 | `core/config.py` L165-166 定义 `LLM_*` 为规范来源，L340-342 `DEEPSEEK_*` 为 legacy 镜像（默认 `https://api.deepseek.com` / `deepseek-v4-flash`） | 适配层读 `LLM_*`，不硬编码厂商 |
| NOESIS 的 Neo4j 连接 | `NEO4J_URI` 长度 21（`)` 形态指向 `bolt://127.0.0.1:7687`）；KG API 默认 `http://127.0.0.1:7474` | **阶段 1 必须先确认两者是否同一实例**；若是，必须为研究 Agent 建**只读账号**并禁用一切写路径 |
| NOESIS 前端技术栈 | `frontend/package.json`：`sigma ^3.0.3` · `reactflow ^11.11.4` · `graphology ^0.26` + `graphology-layout-forceatlas2` · `d3-force ^3` · `react-force-graph-2d` · `echarts ^6` · `three ^0.185` · react 18 · vite 5 · pnpm 9.15.9 · node>=20 | 计划的「Sigma.js + React Flow」**无新增前端依赖**；可直接在 NOESIS 前端体系内实现 |
| 现有 venv | `neo4j` 仓库：`.venv-validation`(Py3.13) / `.venv-training`(Py3.12.4+CUDA)；`a-Soft` 仓库内**未见 venv 目录** | 两个新服务各自独立 venv：`research-agent`(Py≥3.11)、`paper-reader`(Py≥3.11) |
| 部署资产 | `a-Soft/deploy/`：`docker-compose.yml` · `Dockerfile.api` · `Dockerfile.worker` · `.env.example` · `cloud/ load/ monitoring/ windows/` | 新工程 `infra/` 可对齐同一 compose 风格 |

---

## 5 与 v0 提案（`neo4j/docs/agent_kg_system_proposal.md` §10）的差异

| 项 | v0 提案判断 | 本次审计更新 |
|---|---|---|
| NOESIS 源码可得性 | "尚无快照，无法指定可移动组件" | **已解除**：源码在 `D:\a-Soft`，§2.1 已逐条给出行号 |
| 可复用面 | 8 个模块 | **9 个**：新增 `backend/app/research/`（Evidence/Citation 模型 + 引用校验，与报告工作区同构） |
| 前端图依赖 | 计划选用 Sigma.js + React Flow | **已存在于 NOESIS**，零新增依赖 |
| LLM provider | "需选定一个 provider" | **已有可用配置**（`LLM_*`），复用即可 |
| Deep Agents 成本 | 未评估 | 量化为「引入 3 个新 SDK + 抬高 `langchain-core` 下界」，须独立 venv |
| neo4j_client 冲突 | 已识别"静默降级" | **扩大**：除静默降级外，还含 `delete_all()` 等写方法，破坏性更强 |

---

## 6 待拍板项与默认假设

审计阶段无法从源码判定的，已给出**默认假设并按此写计划**；每项的成本影响一并在下表列明。

| # | 事项 | 默认假设 | 改动成本 |
|---|---|---|---|
| Q1 | 新工程落盘位置 | `D:\a-open_source\noesis-research`（与 `neo4j/` 平级，独立仓库；不放进 `a-Soft` 以免污染 NOESIS 仓库） | 低（整目录搬迁） |
| Q2 | NOESIS 与 KG 是否共用 Neo4j 实例 | **按"可能共用"处理**：一律走 KG 只读 HTTP API，不直连 bolt、不使用 NOESIS 的 `neo4j_client` | 低 |
| Q3 | Deep Agents 接入方式 | 独立 `services/research-agent` venv，用 `langchain-openai` 指向 `LLM_BASE_URL`（OpenAI 兼容） | 中（若改用 Anthropic 官方接线） |
| Q4 | 前端承载 | `apps/web` 复用 NOESIS 前端体系（React 18 + Vite + Tailwind 4），在右侧加可切换面板 | 中 |
| Q5 | 用户体系 | 阶段 1 不做多用户；表结构预留 `ownerId` 字段，隔离在阶段 4 落实 | 低 |

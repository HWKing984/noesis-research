# NOESIS Research

基于科学文献知识图谱的智能研究工作平台。定位：**长期使用、管理真实论文、执行完整研究任务、支持多用户与持续扩展**，不以课程演示为终点。

> 状态：**第一阶段链路已通到 Agent —— 只读 KG Adapter + FastAPI + Deep Agents 均已对真实 Neo4j 验收（136 项测试全绿）；真实 LLM 已跑通但被引用闸门判为不合格（详见 `docs/02_phase1_plan.md` §5）；前端与 PaperQA2 尚未接入。**
> 文档：[源码审计](docs/01_source_audit.md) · [第一阶段计划](docs/02_phase1_plan.md) · [评审回应](docs/03_review_response.md) · [参考仓库台账](docs/04_reference_clones.md)

## 0 当前进度

| 模块 | 状态 |
|---|---|
| 源码审计 | ✅ `docs/01_source_audit.md` |
| 架构与阶段计划 | ✅ `docs/02_phase1_plan.md` |
| 只读 KG Adapter | ✅ 含结构校验、可配置地址、图谱版本一致性、**显式禁用环境代理** |
| 证据契约 | ✅ `packages/contracts/evidence.py` |
| FastAPI 业务服务 | ✅ 3 个业务端点 + 就绪探针，错误语义完整（503/502/400/404） |
| **Deep Agent** | ✅ 1 个主 Agent + 5 个只读工具 + 权限收紧（内存态后端、无宿主 shell） |
| 测试 | ✅ 136 项：适配器 44 · 契约 29 · API 18 · **Agent 21** · 真实集成 24 |
| CI | ✅ 三个 job：core（零依赖 3.11/3.13）· api（真装 FastAPI）· agent（真装 deepagents） |
| PaperQA2 | ⏭ 未集成 |
| NOESIS 前端移植 | ⏭ 未迁入 |
| 用户与研究工作区 | ⏭ 未实现 |
| Docker 部署 | ⏭ 未完成 |

一次跑全：`python scripts/run_all_tests.py`（无 Neo4j 时集成套件自动 skip；缺 FastAPI / deepagents 时对应套件自动 skip，CI 会断言这些 skip 确实发生）。

---

## 1 分工（已拍板）

| 角色 | 承担者 | 边界 |
|---|---|---|
| 产品界面 / 用户体系 / 数据后台 | **NOESIS**（`D:\a-Soft`） | 提供 UI 与基础设施，**不提供文献数据层** |
| 研究任务执行底座 | **Deep Agents**（官方 SDK，不 Fork 框架核心） | 只做编排；不接管数据层 |
| 论文内容理解 | **PaperQA2**（独立 Python 服务） | 只读 PDF，不写图谱 |
| 结构化学术知识来源 | **AI-Literature-KG**（`D:\a-open_source\neo4j`） | SciBERT + Neo4j，**只读、版本化** |

主原则：**能直接复用的模块就直接复用；有冲突的模块才通过 Adapter 隔离；需要独立业务能力的部分再开发。**

具体的隔离点：NOESIS 的图客户端（`app/knowledge/graph/neo4j_client.py`）数据库不可用时静默返回空列表、且带 `delete_all()` 写方法，与本项目"不可用即失败、绝不返回离线替代数据"的规则冲突，因此**换成自己的只读适配器**，而不是复用。前端则优先原组件移植（聊天 / Agent 过程 / Artifact / 局部图谱），只在数据契约或样式冲突时隔离。

## 2 目录

```text
noesis-research/
├── apps/            # api/（FastAPI 业务层，已实现 3 端点）· web/（复用 NOESIS 前端，待建）
├── services/        # research-agent/（Deep Agent + 5 只读工具，已实现）· paper-reader · background-worker
├── integrations/    # knowledge-graph（只读适配器，已实现）· openalex · crossref · semantic-scholar
├── packages/        # contracts/evidence.py（统一证据契约，已实现）· citation-validator（待建）
├── infra/           # docker-compose 等
├── scripts/         # run_all_tests.py（零依赖统一入口，支持 --require / --expect-skip）
├── .github/         # ci.yml（core 零依赖 · api 装 FastAPI · agent 装 deepagents）
├── docs/            # 01 审计 · 02 计划 · 03 评审回应 · 04 参考仓库台账
├── reference/       # 上游参考源码（浅克隆、不提交、出处见 docs/04）；git-ignored
└── tests/           # integration/（真实 Neo4j：KG 11 · API 8 · Agent 5）· evaluation · e2e
```

### 起服务

```bash
# 业务 API
python -m venv .venv
.venv/Scripts/python -m pip install -r apps/api/requirements.txt
KG_EXPECTED_GRAPH_ID=<graphId> .venv/Scripts/python -m uvicorn \
    noesis_research_api.app:app --app-dir apps/api --port 8100

# 科研 Agent（独立 venv，与 API 依赖分层）
python -m venv services/research-agent/.venv
services/research-agent/.venv/Scripts/python -m pip install -r services/research-agent/requirements.txt
LLM_API_KEY=... LLM_MODEL=... KG_EXPECTED_GRAPH_ID=<graphId> \
    services/research-agent/.venv/Scripts/python services/research-agent/run.py "有哪些关于 transformer 的论文？"
```

无 KG 服务时所有端点返回 **503**，不会返回空列表。图谱版本锁定后，任何版本漂移都会变成 503 而不是静默换一版数据。`run.py` 会打印**工具调用轨迹 + 回答 + 可引用证据 id**；一条引用都挂不上的回答退出码为 1。

### 参考源码（`reference/`，不进版本库）

| 目录 | 上游 | commit | 许可 |
|---|---|---|---|
| `deepagents` | langchain-ai/deepagents | `caaa7e7c12d2` | MIT |
| `paper-qa` | Future-House/paper-qa | `57e89f7223b0` | Apache-2.0 |
| `neo4j-graphrag-python` | neo4j/neo4j-graphrag-python | `4e3d6dc737c2` | Apache-2.0（部分 PSF-2.0） |
| `agent-chat-ui` | langchain-ai/agent-chat-ui | `28cfb43a62b7` | MIT |

出处、许可以及「每个仓库该看什么」的核实结论见 [`docs/04_reference_clones.md`](docs/04_reference_clones.md)。

## 0.1 起服务

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r apps/api/requirements.txt
KG_EXPECTED_GRAPH_ID=<graphId> .venv/Scripts/python -m uvicorn \
    noesis_research_api.app:app --app-dir apps/api --port 8100
```

无 KG 服务时四个端点都返回 **503**，不会返回空列表。图谱版本锁定后，任何版本漂移都会变成 503 而不是静默换一版数据。

## 3 默认假设（审计阶段所定，未改变时按此推进）

1. **独立仓库**：本工程与 `neo4j/`、`a-Soft/` 平级独立，不并入任一现有仓库。
2. **知识图谱只读**：研究 Agent 对 Neo4j **只有读路径**；写路径一律走 `scripts/course_graph.py` 的人工入口。
3. **LLM provider 复用 NOESIS**：`a-Soft/backend/.env` 已配置 OpenAI 兼容端点（`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`），研究 Agent 复用同一配置，不新增密钥。
4. **不返回离线替代数据**：数据库不可用即失败（503 语义），绝不返回空结果冒充"检索无命中"。这条取代 NOESIS `neo4j_client` 的静默降级策略。

## 4 上游依赖与许可

复用 NOESIS 模块时须保留其归属声明（见 `a-Soft/THIRD_PARTY_NOTICES.md`）：DeepSeek Harness（MIT）、VoiceMem（Apache-2.0）、openJiuwen 算法移植含 `services/citation_trace/`（Apache-2.0）、yt-dlp（Unlicense）。本工程新增依赖的许可在 `docs/02_phase1_plan.md` 记录。

# NOESIS Research

基于科学文献知识图谱的智能研究工作平台。定位：**长期使用、管理真实论文、执行完整研究任务、支持多用户与持续扩展**，不以课程演示为终点。

> 状态：**科研 Agent Web 闭环已通 —— 在网页里提问 → Agent 自主调工具 → 看着它检索 → 回答带引用 → 点引用看证据（28 项浏览器断言全过）。检索界面降级为二级功能。**
> 文档：[源码审计](docs/01_source_audit.md) · [第一阶段计划](docs/02_phase1_plan.md) · [评审回应](docs/03_review_response.md) · [参考仓库台账](docs/04_reference_clones.md)

## 0 当前进度

| 模块 | 状态 |
|---|---|
| 源码审计 | ✅ `docs/01_source_audit.md` |
| 架构与阶段计划 | ✅ `docs/02_phase1_plan.md` |
| 只读 KG Adapter | ✅ 含结构校验、可配置地址、图谱版本一致性、**显式禁用环境代理** |
| 证据契约 | ✅ `packages/contracts/evidence.py` |
| FastAPI 业务服务 | ✅ 3 个业务端点 + 就绪探针，错误语义完整（503/502/400/404） |
| **Deep Agent** | ✅ 1 主 Agent + 5 只读工具；权限收紧（内存态后端、无宿主 shell）；工具返回值分「给模型 / 给界面」两个契约 |
| **Agent 服务（HTTP + SSE）** | ✅ `POST /runs` · `GET /runs/{id}/events`（SSE 事件流）· `GET /runs/{id}` · `GET /health` |
| **科研助手界面（主界面）** | ✅ 提问 → 看着它检索 → 回答带引用核查结论 → 点引用跳证据抽屉 |
| 论文库与图谱（二级视图） | ✅ 检索 / 详情 / 局部图谱；证据可点开抽屉 |
| 测试 | ✅ Python 159 项（适配器 44 · 契约 29 · API 18 · agent 44 · 真实集成 24）+ 前端 18 项 + **浏览器 28 项** |
| CI | ✅ 四个 job：core · api · agent · web（`packageManager` 钉到 pnpm@10.33.2） |
| 运行记录持久化 | ⏭ 只存内存，进程重启即丢 |
| PaperQA2 / PDF 阅读 | ⏭ 未集成 |
| 交互式图谱（Sigma 移植） | ⏭ 未做 |
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
├── apps/            # api/（FastAPI，3 端点）· web/（研究工作区，Vite+React+Tailwind）
├── services/        # research-agent/（1 主 Agent + 5 只读工具）· paper-reader · background-worker
├── integrations/    # knowledge-graph（只读适配器，已实现）· openalex · crossref · semantic-scholar
├── packages/        # contracts/evidence.py（统一证据契约，已实现）· citation-validator（待建）
├── infra/           # docker-compose 等
├── scripts/         # run_all_tests.py（零依赖统一入口，支持 --require / --expect-skip）
├── .github/         # ci.yml（core / api / agent / web 四个 job）
├── docs/            # 01 审计 · 02 计划 · 03 评审回应 · 04 参考仓库台账
├── reference/       # 上游参考源码（浅克隆、不提交、出处见 docs/04）；git-ignored
└── tests/           # integration/（真实 Neo4j：KG 11 · API 8 · Agent 5）· evaluation · e2e
```

### 起服务

```bash
# 一键起全部（KG 8765 + API 8100 + Agent 8101 + 前端 4173），常驻运行
#   最省事：双击仓库根目录的 start.cmd（停止：双击 stop.cmd）
#   凭据优先取环境变量；本机开发缺省只读 NOESIS 工作树的 backend/.env
#   （LLM_* 与 NEO4J_PASSWORD 都从这里取；只读、不打印、不落盘）
python scripts/dev_serve.py start     # 前台常驻；等端口就绪后自动开浏览器；Ctrl+C 或 stop 停止
python scripts/dev_serve.py stop      # 只停"本次启动记录下来的、且仍在监听"的进程
```

依赖链**少一层整体就不可用**：

| 层 | 地址 | 谁提供 |
|---|---|---|
| Neo4j Desktop | `7474` / `7687` | **thome 在 GUI 启动**（`AI-Literature-KG` 实例），本脚本不代管 |
| AI-Literature-KG 只读应用 | `8765` | `D:\a-open_source\neo4j` 的 `scripts/course_graph.py serve`，由 `start.cmd` **尽力代起** |
| NOESIS Research API | `8100` | 本仓库 `apps/api` |
| 研究工作区前端 | `4173` | 本仓库 `apps/web`（同源代理到 8100，后端不开 CORS） |

`start.cmd` 会先做前置检查（两个 venv、`apps/web/node_modules`、前端 `dist` 是否在；`dist` 缺失自动构建一次），
核心端口（8100/8101/4173）被占用时直接报错退出而不抢端口，然后**并行**等待就绪（上限 `DEV_START_TIMEOUT`，默认 180s ——
research-agent 首次导入 deepagents/langchain 冷启动实测 15~65s）。

**KG 是"尽力代起"**：仓库/venv 缺失、取不到 Neo4j 密码、或 8765 已被占用时**只告警不失败** ——
被占用时复用它且 `stop` 不会去动它；起不来时 API 按设计返回 **503**（本项目不返回离线替代数据）。
启动器还会把 `resources/course_graph_runtime.json` 里钉住的 `graphId` 与 `KG_EXPECTED_GRAPH_ID` 比对，
不一致就提前告警（否则会在请求时表现为 503 `kg_graph_version_mismatch`）。

> 注：`start.cmd` / `stop.cmd` 保持**纯 ASCII**。cmd.exe 按系统 OEM 代码页（简中为 GBK）逐行解析批处理文件，
> 文件里的非 ASCII 字节会被误解码并可能被当成命令分隔符，把脚本打散 —— 中文提示统一由 Python 侧输出。
> 就绪判定用 **TCP 连通**而非 HTTP 探测：宿主注入的 `HTTP_PROXY` 会在环回上拦截 HTTP，端口已监听时 urllib 仍可能长时间报 `WinError 10061`。

手动起 KG（`8765`）：

```bash
# Neo4j Desktop 里先启动 AI-Literature-KG（7474/7687）
cd D:/a-open_source/neo4j
NEO4J_PASSWORD=<pw> .venv-validation/Scripts/python.exe -B scripts/course_graph.py serve \
    --database neo4j --user neo4j --port 8765     # 默认 bundle 的 graphId = ai-literature-ed16399925fac2a599ed
```

```bash
# 业务 API
python -m venv .venv
.venv/Scripts/python -m pip install -r apps/api/requirements.txt
KG_EXPECTED_GRAPH_ID=<graphId> .venv/Scripts/python -m uvicorn \
    noesis_research_api.app:app --app-dir apps/api --port 8100

# 研究工作区（前端走同源代理到 8100，后端不需要开 CORS）
cd apps/web && pnpm install && pnpm build && pnpm preview   # http://127.0.0.1:4173

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

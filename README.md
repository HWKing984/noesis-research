# NOESIS Research

基于科学文献知识图谱的智能研究工作平台。定位：**长期使用、管理真实论文、执行完整研究任务、支持多用户与持续扩展**，不以课程演示为终点。

> 状态：**第一阶段 · 源码审计完成，工程骨架已建立，尚未写入业务代码。**
> 审计结论见 [`docs/01_source_audit.md`](docs/01_source_audit.md)，第一阶段任务分解见 [`docs/02_phase1_plan.md`](docs/02_phase1_plan.md)。

---

## 1 分工（已拍板）

| 角色 | 承担者 | 边界 |
|---|---|---|
| 产品界面 / 用户体系 / 数据后台 | **NOESIS**（`D:\a-Soft`） | 提供 UI 与基础设施，**不提供文献数据层** |
| 研究任务执行底座 | **Deep Agents**（官方 SDK，不 Fork 框架核心） | 只做编排；不接管数据层 |
| 论文内容理解 | **PaperQA2**（独立 Python 服务） | 只读 PDF，不写图谱 |
| 结构化学术知识来源 | **AI-Literature-KG**（`D:\a-open_source\neo4j`） | SciBERT + Neo4j，**只读、版本化** |

主原则：**复用机制，不复用应用**。NOESIS 是学习域系统（账号 / 课程 / 掌握度），整仓迁移会引入无关依赖与鉴权体系。

## 2 目录

```text
noesis-research/
├── apps/            # web（复用 NOESIS 前端）· api（FastAPI 业务 API）
├── services/        # research-agent（Deep Agents）· paper-reader（PaperQA2 适配）· background-worker
├── integrations/    # knowledge-graph（只读适配器）· openalex · crossref · semantic-scholar
├── packages/        # evidence（统一证据模型）· contracts（API / Event 契约）· citation-validator
├── infra/           # docker-compose 等
├── docs/            # 审计、计划、决策记录
└── tests/           # integration / evaluation / e2e
```

## 3 默认假设（审计阶段所定，未改变时按此推进）

1. **独立仓库**：本工程与 `neo4j/`、`a-Soft/` 平级独立，不并入任一现有仓库。
2. **知识图谱只读**：研究 Agent 对 Neo4j **只有读路径**；写路径一律走 `scripts/course_graph.py` 的人工入口。
3. **LLM provider 复用 NOESIS**：`a-Soft/backend/.env` 已配置 OpenAI 兼容端点（`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`），研究 Agent 复用同一配置，不新增密钥。
4. **不返回离线替代数据**：数据库不可用即失败（503 语义），绝不返回空结果冒充"检索无命中"。这条取代 NOESIS `neo4j_client` 的静默降级策略。

## 4 上游依赖与许可

复用 NOESIS 模块时须保留其归属声明（见 `a-Soft/THIRD_PARTY_NOTICES.md`）：DeepSeek Harness（MIT）、VoiceMem（Apache-2.0）、openJiuwen 算法移植含 `services/citation_trace/`（Apache-2.0）、yt-dlp（Unlicense）。本工程新增依赖的许可在 `docs/02_phase1_plan.md` 记录。

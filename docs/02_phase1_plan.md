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

### T4 · 最小 Deep Agent（`services/research-agent`）✅ 已完成（2026-10-08）

- 产出：**一个主 Agent + 5 个只读工具**（`report_graph_scope` / `search_papers` / `get_paper` / `get_paper_evidence` / `explore_graph`）+ CLI `run.py`。
- **工具返回与 HTTP API 完全同源**：工具调用同一套映射函数（`noesis_research_api.mapping`），所以「Agent 只做编排、不改变检索结果」是可验证的；检索参数回显（`applied` / `expandedTerms`）在模型**之下**生成，模型改不了。
- 硬约束：**只用主 Agent，不上子 Agent**（子 Agent 仅保留给长篇综述 / 多主题比较）。系统提示词把 4 条硬规则写死并**有测试守着**：每个事实性断句必须挂来源 id、候选断言必须保持「候选」、证据深度只有题名、数字只能来自工具、必须回显参数、区分空结果与图谱不可用、必引/被引/引用链一律拒答。
- **权限收紧（有测试守着）**：显式传 `backend=StateBackend()`（内存态，**非宿主文件系统**）。已从克隆源码核实：上游 `libs/deepagents/deepagents/graph.py:653` 的默认也是 `StateBackend()`；`execute` 只有在后端实现 `SandboxBackendProtocol` 时才真能跑命令，本服务**从不提供沙箱后端** → 研究 Agent 没有通往宿主 shell 的路径。官方的工具排除入口 `_ToolExclusionMiddleware` 是**私有**的，本服务不依赖它。
- 依赖：**独立 venv**（`deepagents==0.7.23`；完整 55 包传递锁见 `services/research-agent/requirements.lock.txt`）。不得装进 NOESIS / KG / apps-api 的 venv。
- 验证：
  - 离线 **15 项**（假 transport + 记录 `bind_tools` 的假模型；含后端非沙箱断言、工具面断言、提示词契约断言）；
  - **真实集成 5 项**（脚本化假模型 + 真实 Neo4j）：Agent 闭环跑到真实 Neo4j、拿到真实 `publicationId`、并在**回答文本里引用它** —— 这就是「返回可点击证据」的机器可验证形式。
- **一件事需要 operator**：真实 LLM 那一步要 `LLM_API_KEY` / `LLM_MODEL`；本机进程与用户环境实测**都不含任何 LLM 凭据**，且 `D:\a-Soft` 按约定不读，所以这一步留给部署时注入环境变量。模型被替换为脚本化假模型的那部分是**明确标注**的，不是冒充。

#### 2026-10-10 改版：回应「像查询器不像 agent」

现象（用户反馈）：用户问了直接甩出一大堆论文、格式看不懂、像给机器看的。定位到三层机制：

| 感受 | 机制 | 位置（改版前） |
|---|---|---|
| 完全没有思考 | ① 提示词是合规检查表（6 条"违反即失败" + 拒答节 + 免责节），无一句关于"判断意图 / 给判断 / 给几篇"；② 5 个工具全是检索原语且**只返回题名**，模型拿不到任何论文内容 | `agent.py:43-85`、`tools.py:57-65` |
| 甩一大堆 | 工具单次最多 25 篇平铺列表；提示词要求"逐句挂来源 id"，反而奖励"多列"；闸门口径 `passes = 引用数 > 0` | `tools.py:40-41`、`evidence.js:111` |
| 格式看不懂 | 渲染器只认 `#` / `- ` / `**` / id 上标，**不认表格与有序列表** —— 模型写的 markdown 表格被当纯文本原样吐出；正文必须内嵌 DBLP 键才被识别成引用 | `answerRender.jsx:96-161` |

处置：

- **提示词改为「研究工作法」**：先判断意图 → 结论先行 → 精选 3–5 篇并说明取舍与排除理由 →
  可用表格/有序列表组织 → **观点级**引用（一个结论挂一次，不再逐句硬挂）；
  机械元信息（`meta.applied` / evidence level / 覆盖范围）移到界面常驻展示，不再逐轮抄进正文。
  硬约束一条未删（候选保持候选、题名级证据、数字只来自工具、空结果 vs 图谱不可用、CITES 拒答），
  由 `test_agent.py::PromptContractTests` **5 条**守着（原 2 条 + 新增 3 条守"改版意图"，防止滑回清单形态）。
- **渲染器升级并改名**：`answerRender.jsx` → `answerRender.js` —— 该模块刻意不含 JSX 字面量
  （全用 `React.createElement`），而 Node 不认 `.jsx`（`ERR_UNKNOWN_FILE_EXTENSION`），
  改名前后者意味着"由单测守住渲染器"这件事**从未真正成立**（17 条断言一次都没被执行过，
  其中 2 条本身写错）。现在支持**表格 / 有序列表 / http(s) 链接 / 引用上标可读标签**。
- **`AgentChat.jsx`**：研究笔记**默认展开**（最后一轮；历史轮收起，点过则取反）；
  过程卡标题改「研究笔记 · N 步」；引用上标 hover 显示「题名（年份）」而不是裸 id。
- 验证：`research-agent` **63 项 OK**；前端 **36 项 OK**（含新增 8 项 + 修正 2 条因从未执行而写错的旧断言）；
  `vite build` 通过（1111 modules）；`react-dom/server` 真实渲染 + 无头 Chrome 明暗两版核对
  （`outputs/answer-render-check-light.png` / `-dark.png`）。
- 方向对照原型：`outputs/answer-presentation-compare.html`（同一批数据的「现状 vs 重设计」并排）。
- **未做**（下一阶段）：让 agent 真正有"内容"可读 —— 接 OpenAlex/Crossref/S2 + PaperQA2 把
  `evidenceLevel` 从 `title` 抬到 `abstract`。只改提示词与呈现，天花板仍是"只有题名"。

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

### T6 · SSE 与运行记录 → 已实现为 Agent 服务 + 科研助手界面 ✅（2026-10-08）

评审给定的下一版核心目标 —— **「用户提出研究问题 → Deep Agents 自动调用检索工具 → 返回真实文献 → 展示研究过程 → 点击引用查看证据」**，已实现：

- **Agent 自身成为服务**（`services/research-agent/noesis_research_agent/server.py`）：
  `POST /runs` 提问即返回 `runId`（后台线程开跑）、`GET /runs/{id}/events` 为 **SSE** 事件流
  （`run_started` / `tool_call` / `tool_result` / `tool_error` / `answer` / `failed` / `done`）、
  `GET /runs/{id}` 取最终记录、`GET /health` 报就绪状态。事件翻译**按消息类型**判断而非节点名
  （节点名是实现细节，消息类型是稳定契约）。
  **运行记录只存内存**（进程重启即丢）—— 评审要求的 `research_runs` / `research_run_events`
  持久化**尚未做**，是后续增量；界面上如实按"会话级"呈现，不假装有历史。
- **工具返回值分两个契约**：给模型的是**精简视图**（id/题名/年份/谓词/证据引用，有单测锁住
  「只许这几列」），给界面的是事件里的规模摘要；完整数据由界面自己调 API 拿。
  这是实测逼出来的：原始载荷会让本地 8B 模型每轮吞几千 token，慢到不可用。
- **界面改为 agent 优先**（回应"是做 agent，不是做复杂数据浏览工具"）：默认视图就是
  「科研助手」—— 一个输入框 + 一串步骤 + 一段回答 + 一个引用核查结论；
  论文库/图谱降级为二级视图，并从回答里的引用 id 一键跳入。
- **引用核查升级**（评审第 4 条）：服务端在 `answer` 事件里给出 `citation` 报告
  （`available` / `cited` / `citedIds` / 按句可溯率 / `evidenceLevels` / `titleOnly`），
  与 CLI、前端是**同一条纯函数规则**；`titleOnly` 时界面明确显示「题名级证据只能证明论文存在，
  不能证明它做了回答里描述的事」。
- **验证（`apps/web/tools/e2e.py`：一次调用内起三个服务 → 真实 Chrome → 收尾清理）**：
  **28 项断言全过**。agent 段：自主 **14 步工具调用**（换关键词、逐年检索），
  回答 4854 字，**引用核查通过：回答里实际引用 39 / 可用 49 条，按句可溯率 22/54 = 41%**，
  页面上的引用 id 与结论自洽，无控制台报错。模型：DeepSeek（OpenAI 兼容端点）。
  对照：本地 ollama 8B 同一条闸门下 **0 引用、判失败** —— 闸门没变，是模型能力差异。
- **证据真正可点**（评审第 2 条）：`EvidenceChip` 从 `<span>` 改成真按钮，点开证据抽屉，
  显示来源 id、来源类型、证据深度、核验状态、断言状态、图谱版本，并把「不能证明什么」放在
  第一屏，可跳到对应论文详情；无头断言覆盖「点击 → 抽屉 → 跳转后详情 id 与证据一致」。
- **异步竞态修复**（评审第 3 条）：详情/图谱请求改为 `AbortController` + 序号双重保险，
  先点 A 再点 B 不会让 A 的慢响应覆盖 B；图谱与详情错误分开，图谱成功后清掉旧错误。

### T7 · 前端承载（`apps/web`）—— 第一阶段已落地数据侧三段

- 产出：Vite 5 + React 18 + Tailwind 4 的 `apps/web`，覆盖**检索 → 详情 → 局部图谱**，
  全程带证据引用。第一个可点开的界面已经能对着真实图谱工作。
- **移植纪律（评审调整后的口径）**：能直接复用就复用，冲突才隔离。已核实 `agent-chat-ui` 是
  Next 16 + React 19，与本项目 Vite + React 18 **不兼容**，只作交互参考；
  移植对象是 **NOESIS 自身组件**（同栈）。本次实际移植的是
  `agentEvidence.helpers.js` 的三段式证据闸门**形态**（`covered`/`missing`/`not_required`），
  按其 `write_id` 形状与本项目不同，故按 `EvidenceRef` 契约重写。
- 硬约束（有单测守着）：候选断言在 UI 上**恒为「候选」**；证据深度是独立维度
  （`title` 显示为「仅题名」并附限制说明）；证据缺失显示为「缺失」，不伪装成有来源。
- 与后端走**同源代理**（Vite `/api` → 8100），所以后端不需要开 CORS。
- 验证：
  - 纯逻辑单测 9 项（`node --test`，含与 CLI 同规则的 `citationReport`）；
  - **无头浏览器 15 项断言全过**（真实 Chrome + CDP，打真实 API + 真实 Neo4j）：
    状态条真拿到 graphId、检索真返回 10 篇真实论文、**10/10 结果都带可点击证据**、
    详情与列表 id 一致、断言 `status=candidate` 两条都保持候选、局部图谱 14 节点 / 17 边、
    无横向溢出、控制台无报错。
- 尚未实现（后续阶段）：科研助手对话面板（等 T6 的 research runs + SSE）、PDF 阅读、
  报告 Artifact、研究项目/任务管理。

### T8 · 外部学术源连接器（`integrations/openalex` `crossref` `semantic-scholar`）

- 产出：三个连接器，覆盖 2026 年及以后的论文发现。
- **优先复用，不重写**（2026-10-08 核实）：`reference/paper-qa` 的 `src/paperqa/clients/` 里 **已存在 `openalex.py` / `crossref.py` / `semantic_scholar.py`**（另有 `unpaywall.py` / `retractions.py`），是 `httpx` + `tenacity` 的完整实现。按评审"能直接复用就直接复用"的原则，这层应优先复用其网络与解析，而不是另写一套。见 `docs/04_reference_clones.md` §2.2。
- 硬约束：匹配优先级 = **DOI → 精确 arXiv ID → 明确来源标识**；仅标题相似度匹配一律留为「待确认候选」，**不得合并论文身份**。
  → 注意上游用 `strings_similarity` 做标题相似度匹配；**判定层按本项目规则收紧**，不能沿用其"标题匹配即可定身份"的宽松度。
- 外部记录进独立业务表，不回写 SciBERT 图谱。
- 验证：连接器离线契约测试（录制响应）+ 身份匹配的负例测试（相似标题不得自动合并）。

#### T8 已落地（2026-10-10）：摘要级证据接入 agent

起因：只改提示词与呈现（A+C）治不了根 —— **图谱只存题名，agent 物理上没有可读的材料**，
再会组织语言也只能对着标题说话。这一轮把材料补上。

- **产出**：`integrations/external-sources/`（纯标准库，零第三方依赖 —— 这是 agent 工具底座，
  不能引入 httpx/tenacity）。三源按实测可靠性排序回退：**Semantic Scholar → OpenAlex → Crossref**。
  2026-10-10 实测（本机，沙箱注入的 `HTTP_PROXY` 在场）：三个 host 均 <1.1s 可达；
  S2 对两个样例 DOI 均给纯文本摘要（1293 / 1117 字符）+ venue；OpenAlex 给可重建的
  `abstract_inverted_index`；Crossref 两个样例都是 0 长度摘要。
- **不照搬 paper-qa**：其三个 client 依赖 httpx/tenacity，且**只取 metadata、不取摘要**
  （`abstract` 字段从未被使用）。因此复用的是端点与查询形状，解析另写并在真实 API 上校准。
- **身份纪律照做**：只接受 DOI / 精确 arXiv ID 作查询键，**不提供按标题查询的入口**；
  每个响应都要过 DOI 一致性校验。实测抓到一个真实案例：OpenAlex 对
  `10.48550/arXiv.1706.03762` 返回的是另一条记录（DOI `10.65215/2q58a426`）——被校验挡下。
- **失败语义**（本轮被真实流量打出两个 bug，都已修 + 有回归用例）：
  1. **「源不适用」曾被当成「已查无摘要」**：arXiv-only 查询时 OpenAlex/Crossref 拿不到 DOI，
     实现里直接 `return None`，被计为"该源无摘要"；于是 S2 一返回 429（无 key 共享池极易触发），
     整个查询对外表现为「这篇论文没有摘要」——正是本仓库禁止的那种伪装。
     现在「不适用」是独立的 `ExternalNotApplicable`，不计入任何判定。
  2. **arXiv 记录无 DOI 会被证据契约拒绝**：现在用 arXiv 的规范 DOI `10.48550/arxiv.<id>` 作稳定 key。
  另收紧判定：「无摘要」只有在**没有任何源失败**时才成立（有源不可达就不下结论）。
- **agent 侧**：新增工具 `read_paper_abstract(publication_id)`（图谱取 DOI → 外部源取摘要 →
  返回 `evidenceLevel=abstract` / `verificationStatus=id_valid` / `evidenceText` 原文，
  给模型截断 2000 字符）；`available:false` 会说明 `no_identifier` / `no_abstract` / `disabled`，
  **工具抛错才是外部源不可达**。提示词新增「两种证据深度」一节（title 只能证明存在、
  abstract 才能谈内容），并删掉旧的「证据深度只有题名」。
- **让摘要真的看得见**：`tool_step` 事件新增 `evidenceRefs`（完整引用含原文，截断 1200 字符、
  最多 12 条）；前端 `App.onCited` 优先用事件里的完整 ref（而不是回落到只有 id 的题名级 ref）；
  证据抽屉新增「摘要原文」区块，「打开来源」按 `locator.url` 走外部源页而不是 DBLP 搜索。
- 验证：`integrations/external-sources` **50 项**（43 离线 + 6 真实 API + 1 配置）；
  `research-agent` **71 项**；前端 **36 项**；`run_all_tests.py` **6 suites / 223 tests executed 全绿**；
  `vite build` 通过。真实 API 的 6 项在本机是真跑的（不是 skip）。
- **仍是外部数据**：摘要来自第三方源，不写回 SciBERT 图谱；`EXTERNAL_SOURCES` 置空即禁用
  （此时工具如实报 `disabled`）。S2 无 key 时限流很紧，需要稳定使用就配 `EXTERNAL_S2_API_KEY`。

#### 点击翻译（方向 A：钉住气泡）已落地（2026-10-10 晚）

thome 拍板方向 A。NOESIS「钉住」（`D:\a-Soft\frontend\src\components\Term.jsx`）的交互契约逐条移植：

- **后端**：`apps/api` 新增 `POST /api/translate`（`translate.py` + `translate_routes.py`）。
  **零新增依赖**（标准库 urllib 调 OpenAI 兼容 `LLM_*` 端点，硬化模式同 external-sources：
  `ProxyHandler({})`、超时映射顺序、响应上限）；术语保护表 `GLOSSARY_KEEP`（版本号参与缓存键，
  改表即整体失效）；磁盘缓存 `.data/translations`。错误映射：
  未配置 → 503 `llm_not_configured`，不可达/429/5xx → 503 `translate_unavailable`，
  坏响应 → 502 `translate_bad_response`。**没有一条路径会把原文当译文返回**：
  后端校验译文必须含中文、不得与输入空白归一后相同；前端 `parseTranslateResponse` 再独立拦一次。
- **前端**：`TranslatePop.jsx`（`TranslateHost` document 级 **capture** 事件委托 + `TranslatePop` 展示）。
  交互参数与 NOESIS 逐条一致：hover 140ms / CLOSE_DELAY 220ms / 钉住后 hover 不抢 /
  mousemove 滚轮守卫 / `placeNear` 定位 / portal 到 body。CSS 照搬 `Term.css`
  （本仓 token 与其同名同值，几乎原样）。锚点三处：rail 论文卡标题、详情面板标题、
  证据抽屉摘要原文 —— 标题点击由 capture 阶段 `stopPropagation` 拦下，不再触发卡片自身的
  `onInspect`（这正是 NOESIS `TermPopoverHost` capture 参数的用途）。浮层常驻声明：
  **译文不是证据**——不产生 EvidenceRef、不进引用核查。
- **验证**：api 套件 **51 项**（翻译用例 +14：真实 app + 真实错误映射，只桩 LLM socket；
  含缓存命中不打网络、GLOSSARY_VERSION 变更使缓存失效、无中文/复读输入一律 502）；
  前端 **44 项**（`translate.test.mjs` +8）；`vite build` 通过；`TranslatePop` 三形态 SSR 核对
  （钉住成功 / 钉住失败 / hover 预览，`outputs/translate-pop-check.html|.png`）；
  本机 ollama 实测**真实翻译链路**（标题译文返回；60s 超时被如实映射为 `translate_unavailable`
  ——本地 8B 模型冷加载慢属模型侧，生产走 `LLM_*` 配置的更强模型）。
- **运维**：需配 `LLM_API_KEY` / `LLM_MODEL` 才可用；未配时浮层显示「翻译服务未配置」，不假装。
  发现的顺带修正：`translate.py` 一度漏 `import dataclass`，导致整个 api 套件在 import 阶段
  skip —— skip 消息里的真实异常（NameError）才是定位线索，"fastapi 未安装"是误导性包装。

#### 点击解释（NOESIS 概念卡移植）已落地（2026-10-10）

thome 指出 Term 卡的主业——**概念解释**——上轮没移植。补齐，与翻译共用同一钉住卡：

- **后端**：`POST /api/explain`（`explain.py` + `explain_routes.py`，Explainer 与 Translator
  同骨架：共享 transport/缓存/错误纪律）。入参 `{text, kind: term|title|abstract|text,
  style: normal|simple, context}`；prompt 约定模型只输出 JSON
  `{category, brief, detail, whyItMatters, example}`（照 NOESIS 卡的 类别/一句话/详解/
  为什么重要/例子），支持围栏剥离与首个 `{...}` 提取。校验：缺字段、brief/detail 无中文
  → 502 `explain_bad_response`（app.py 新增映射；outage 仍复用 503 `translate_unavailable`）。
  **响应不带 sources 字段**——不能核实的出处不给。缓存键含 `EXPLAIN_VERSION|kind|style|context|text`：
  `style=simple`（"更简单一点"）换缓存条目，必然真的再问模型。`FileCache` 泛化
  `required_field`（翻译校验 `zh`、解释校验 `brief`），默认行为不变。
- **前端**：`TranslatePop.jsx` 升级双 tab——hover 预览保持翻译（快）；钉住后 head 出
  「翻译 | 解释」tab（`pop-tab-tr` / `pop-tab-ex`）。解释卡 = 类别 chip + brief +
  是什么（按 `\n` 分段）+ 为什么重要 + 例子 + 常驻"AI 生成的解释，**不是证据**" +
  复制解释 / 更简单一点（style=simple 后显示"已是简化版"）。失败卡 `explain-error`，
  文案 `describeExplainError` 三种失败可辨。锚点可选 `data-tr-context`（论文题名）
  作"结合当前内容"语境：前端宿主与缓存键已支持，锚点侧暂未填。
- **验证**：api `test_explain.py` 13 项（真实 app + 真实错误映射，桩 LLM socket；含
  围栏 JSON、style 换缓存、context 进 prompt 与缓存键、纯散文/缺字段/全英文一律 502）；
  前端 `translate.test.mjs` 13 项（+5）；api 全套件 discover exit=0；`vite build` 通过；
  三态 SSR 核对 `apps/web/tools/explain_pop_check.mjs` → `outputs/explain-pop-check.html|.png`
  （钉住·翻译 tab / 钉住·解释 tab / 解释失败），并断言 10 个关键 testid 在 SSR HTML 中。

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
| T1 工程骨架 | ✅ | 目录 + 四份文档 |
| T2 只读 KG Adapter | ✅ | 离线 44 项 + 真实集成 11 项 |
| 证据契约（T5 前置） | ✅ | `packages/contracts/evidence.py`，29 项 |
| T3 业务 API（3 端点） | ✅ | HTTP 18 项 + 真实集成 8 项 + 真实 uvicorn 冒烟 |
| T4 Deep Agent（工具层） | ✅ | agent 套件 44 项（含 HTTP/SSE 面 + 事件翻译） |
| **Agent Web 闭环（SSE + 科研助手）** | ✅ | **无头浏览器 28 项断言**：14 步真实工具调用、回答 4854 字、引用核查通过 39/49 |
| **T7 前端（证据可点 + 竞态修复）** | ✅ | 前端单测 18 项 + 上述浏览器断言 |
| CI（packageManager 钉版） | ✅ 修复 | `pnpm@10.33.2`（本地生成 lock 的同一版本）；待远端复核 |
| 运行记录持久化 | ⏭ 下一步 | 当前只存内存 |
| PaperQA2 / PDF 阅读 | ⏭ | — |
| 交互式图谱（移植 Sigma） | ⏭ | 评审已指明优先级 |

**T2 + T3 实机冒烟结果**（真实 uvicorn `127.0.0.1:8100` → 真实 Neo4j）：

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

**T4 Agent 闭环**（脚本化假模型 + 真实 Neo4j；模型只被替换，链路全真）：

```text
问：有哪些关于 transformer 的论文？
→ Agent 调用 search_papers(query="transformer", limit=3)
→ 真图谱返回真实论文（publicationId 形如 conf/…，含斜杠）
→ 回答里引用了该 publicationId，并标注 evidenceLevel=title / verificationStatus=unverified
```

本轮验收目标（评审给定）：**Deep Agents 完成一次真实的 Neo4j 文献检索并返回可点击证据** —— 已达成（模型环节用脚本化假模型替代，真实 LLM 需 operator 注入 key）。

### 真实 LLM 也跑了一次，结论是「链路通、模型不合格、闸门拦下」

本机装的是 **ollama（11434）**，有 OpenAI 兼容接口与 `qwen3-vl:8b`，所以真实 LLM 这一步不需要外部凭据、也不需要读 `a-Soft`：

```text
[kg]    status=ready graphId=ai-literature-ed16399925fac2a599ed scope={bibliographyTitles:20000, ..., candidateAssertions:21497}
[llm]   model=qwen3-vl:8b base_url=http://127.0.0.1:11434/v1
--- 工具调用（1 次）---  1. search_papers {"query": "transformer", "limit": 25}
--- 引用核查 ---
  工具返回的可用证据 id：25 条
  回答中实际引用：0 条
  引用可溯率（按句，启发式）：0/30 = 0%
  [失败] 回答没有引用任何证据 id —— 按本项目验收口径，这是一次失败的问答，不是成功。
EXIT=1
```

三件事同时被证实：

1. **链路是通的**：Agent 自己选了正确的工具、参数打到真实 Neo4j、拿回 25 条真实 `publicationId`；
2. **闸门是有效的**：这次回答流畅、结构完整、读起来像一篇综述 —— 但它**一条来源都没引用**，闸门据此判失败并返回退出码 1。这正是计划里预警过的失败形态（把约四成的候选边/模型先验揉进流畅回答里）；
3. **本地 8B 模型不满足契约**：除了 0 引用，它还**编造了工具没有返回的内容**（工具只给题名，回答却给出任务、创新点、会议归属，并断言 "six papers from CVPR 2025 and CVM 2025"），也没有按提示用中文。

因此：数据侧、工具侧、闸门侧都已就绪；**换一个遵守引用契约的模型即可上线问答**。这一步的模型选择属部署决策。



# 评审回应 · 逐条归因

> 对象：《NOESIS Research 仓库评审》对 commit `de4d8bc` 的评审意见。回应日期 2026-10-08。
> 原则：每条都给**判定 + 证据**；评审说得对的照改，说得不准的说明实际差异；不接受空口"已修复"。
> 代码改动落在 commit `评审整改`（见仓库历史），测试命令见本文末。

---

## 0 结论先行

| # | 评审意见 | 判定 | 处置 |
|---|---|---|---|
| P0-1 | `search()` 在 200 但缺 `data` 时按空列表处理 | **成立** | 已改：新增 `_items()` 严格校验；补 5 项用例 |
| P0-2 | 证据模型应扩为通用 `sourceId` | **成立** | 已改：`packages/contracts/evidence.py` 统一契约 + 29 项测试 |
| P0-3 | 硬编码 `127.0.0.1:8765`，Docker 需可配置 | **成立** | 已改：`resolve_base_url()` 参数 > `KG_BASE_URL` > 默认 |
| P1-4 | 缺真实 KG 集成测试 | **成立** | 已补：`tests/integration/test_kg_live.py`，**11 项对真实服务跑通** |
| P1-5 | 缺依赖锁定与 CI | **部分成立** | 已补 CI（3.11/3.13 矩阵）+ 统一测试入口 + 直接依赖 pin；完整传递锁待建 venv 时生成 |
| P1-6 | 引用验证计划过于理想化 | **成立** | 已改：拆成 4 级 `verification_status` 阶梯 + 证据等级硬规则 |
| P1-7 | 第一阶段 API 范围过大 | **成立** | 已改：T3 裁剪为 3 个端点，收藏/上传/导出移到阶段 2/3 |
| 策略 | "复用机制，不复用应用"应收紧 | **接受** | 已改：README/计划改为"能直接复用就直接复用，冲突才 Adapter 隔离，独立业务再开发" |

**另有 1 条评审未发现的真实契约差异**（§3），只有跑真实服务才会暴露，已建模进适配器。

评审对"测试通过情况"的保留是对的：本文所有数字都是本轮**实测复核**的结果，不是引用上一轮的声明。

---

## 1 逐条处置

### P0-1 · `search()` 的静默失败 —— 成立

评审指出的正是这段：

```python
publications=tuple(payload.get("data") or ())   # 200 + {"meta": {}} → 空列表
```

它与本项目"失败不能伪装成无结果"的原则直接冲突，而且**只有 `search()` 绕过了严格校验**（`health` / `publication` / `graph` 走的都是 `_data()`）。已改：

- 新增 `_items()`：要求 `data` 必须是**数组**，且每个元素必须是对象；缺失 → `KGError("… expected 'data' to be an array, got missing")`。
- `health()` 补 `status` / `graphId` / `source` 非空校验、`scope` 必须是非空对象且值是非负整数（`bool` 也拒绝）。
- `publication()` 要求 `data.publication` 是对象，`authors`/`venues`/`mentions` 必须是数组。
- `graph()` 要求 `data.nodes` / `data.edges` / `data.paths` 是数组，节点必须有 `props.id`，边必须有 `id/kind/source/target`，且 `meta.graphId` 必填、`rootId` 必须在返回节点中。
- 新增 `StrictPayloadTests`（12 项），**明确包含评审点出的 `{"meta": {}}` 场景**。
- 同时保留一条反向用例：`data: []` 是**合法空结果**，必须照常返回 `()` —— 严格不等于把真·空结果也判成故障。

### P0-2 + 特别指出 2 · 通用证据契约 —— 成立，已实现

`packages/contracts/evidence.py`，字段与评审建议逐一对齐：

```json
{"sourceType":"kg_assertion","sourceId":"…:Assertion:780c1091…","publicationId":"conf/aaai/0002LCWHL25",
 "graphId":"ai-literature-ed16399925fac2a599ed","evidenceLevel":"title","assertionStatus":"candidate",
 "evidenceText":"Infer the Whole from a Glimpse of a Part.","verificationStatus":"unverified"}
```

- `SOURCE_TYPES`：`kg_bibliography` / `kg_assertion` / `paper_passage` / `external_record` —— 后两者就是 OpenAlex / Crossref / PaperQA2 的接入位。
- 全文证据按评审的写法支持 `sourceType: "paper_passage"` + `documentId` + `locator`（页码 / 段落）。
- 校验是纯函数，全部可单测（29 项），例如：`kg_*` 必须给 `publicationId`；`paper_passage` 必须给 `documentId`；`kg_assertion` 的 `assertionStatus` 不能是 `none`。

### P0-3 · 服务地址可配置 —— 成立

原来 `DEFAULT_BASE_URL` 只能靠构造参数覆盖，Docker 里没有环境变量入口。已改：

`resolve_base_url()` 优先级 = **显式参数 > `KG_BASE_URL` 环境变量 > 环回默认**；`HttpTransport` 与 `KGClient` 都走同一解析。容器部署设 `KG_BASE_URL=http://kg-service:8765` 即可。另有 3 项配置测试覆盖优先级与默认回退。

### P1-4 · 真实 KG 集成测试 —— 成立，已补并**实跑**

本机 KG 服务当时是活的（`/api/health` → 200 / `status: ready`），所以这一条不是"写了但没跑"：

```text
=== live / knowledge graph (self-skips when unreachable) ===
...........
Ran 11 tests in 1.710s
OK
```

覆盖：健康状态与 scope 计数、**版本锁一致性**、真实检索、中文别名展开（`method=扩散模型` → `diffusion model(s)`）、检索命中 → 详情 → 可引用 `EvidenceRef` 的完整走链、候选断言不被升格、三种局部图模式、未知 id 必须是 404 而不是空页。

无服务时整类自动 `skipUnless`，CI 因此保持绿色（CI 另加一步断言"确实是 skip 而不是静默通过"）。

### P1-5 · 依赖锁定与 CI —— 部分成立，说明差异

需要澄清一个事实：**当前仓库的代码零第三方依赖**（`integrations/`、`packages/` 全部只 import 标准库），这是刻意的 —— 这层是 Deep Agents 工具的直接底座，多一个依赖树就会被工具层继承。因此"锁"暂时没有可锁的对象，而"CI 装不装依赖"也不改变结果。

已落地：
- `.github/workflows/ci.yml`：Python **3.11 / 3.13** 双版本矩阵（3.11 是 `deepagents` / `paper-qa` 声明的地板）、`compileall` 语法门、统一测试入口、live 套件必须 skip 的断言。
- `scripts/run_all_tests.py`：零依赖统一入口，本地与 CI 同一条命令。
- `services/research-agent/requirements.txt`：**直接依赖 pin**（`deepagents==0.7.23` 等，取自 PyPI 元数据实测）。
- **未做**：完整传递闭包锁（`pip-compile` / `uv lock`）。它必须建 venv 时生成，凭空写一份假锁没有意义 —— 这条随 T4 落地。

### P1-6 · 引用验证过于理想化 —— 成立

原计划只有一句"引用可溯率 100%"。现在拆成**四级阶梯**，且每级的准入条件由代码强制：

| `verificationStatus` | 含义 | 硬准入（违反即 `EvidenceError`） |
|---|---|---|
| `unverified` | 尚未核 |
| `id_valid` | id 能解析到真实记录 | — |
| `evidence_supports` | 引文支持该句 | 必须非空 `evidenceText` |
| `semantic_verified` | 判断蕴含成立 | 必须有引文 **且** `evidenceLevel ∈ {abstract, fulltext}` |

同时把"证据深度"独立成 `evidenceLevel`（title / abstract / fulltext）：**标题级命中只能证明"这篇论文存在"**，不能证明它做了句子里说的事。三级阶梯 + 四级深度，正好对应评审要求区分的三件事。

### P1-7 · 第一阶段范围过大 —— 成立

T3 从 9 个端点裁剪为 **3 个真实可用端点**：`/api/papers/search`、`/api/papers/{id}`、`/api/graph/neighbors`。收藏、PDF 上传、报告导出移到阶段 2 / 阶段 3。第一轮的验收目标就是评审说那条闭环：**NOESIS 研究界面 → FastAPI + Deep Agents → KGClient → 真实 Neo4j → 真实论文 + 候选关系 + 原始证据**。

### 策略调整 —— 接受

README 与计划里的"复用机制，不复用应用"已改写为：

> **能直接复用的模块就直接复用；有冲突的模块才通过 Adapter 隔离；需要独立业务能力的部分再开发。**

前端相应改为**优先原组件移植**（聊天、Agent 过程、Artifact、局部图谱、研究状态），只有样式/数据契约冲突时才在边界层隔离 —— 不再只做"行为对齐"。

---

## 2 评审无法独立确认、我方可以给证据的部分

评审说"没有直接读取本地 `D:\a-Soft` 的代码，还不能独立确认这些模块的真实兼容性"。这部分我方有实测证据，列出来便于复核：

| 断言 | 证据 |
|---|---|
| `orchestration/capability_protocol.py` 是 import-free 能力契约 | `register_capability_protocol()` @ L74-91：注册期即校验 `name == capability_id`（漂移报错）、`is_active` 必须可调用 |
| `mcp/registry.py` 有 schema 指纹与安全边界 | `RegisteredTool.schema_fingerprint` @ L59、`parallel_safe: bool = False` @ L63；模块 docstring 声明不依赖 MCP SDK |
| `services/citation_trace/` 可直接对应引用闸门 | `verify.py` @ L134 三阶段降级（精确 → 有界 difflib → 批量 LLM），`MAX_LLM_RETRY_TIMES=3` @ L49 |
| NOESIS 的图客户端**不可复用** | `knowledge/graph/neo4j_client.py`：`execute()` @ L81-97 不可用即 `return []`；另有 `delete_all()` @ L153-155 |
| NOESIS 已有 Evidence/Citation 模型 | `backend/app/research/models.py`（`SearchResult`/`Source`/`Evidence`/`Citation`/`ResearchResult`） |

---

## 3 评审未发现、真实集成才暴露的契约差异

跑真实服务时暴露了两处**文档与实现的偏差**，任何只读代码的评审都看不到：

1. **`/api/publication` 的 `assertions` 是包装结构**，不是断言属性本身：

   ```
   assertions[i] = {"assertion": {...}, "head": {...}, "tail": {...}}
   ```

   断言的 `status` / `predicate` / `confidence` / `evidence` 都在 `assertion` 子对象里。评审的 P0-1 关注点同类：若直接 `item["status"]` 会拿到 `None`，然后被当成"没有状态"静默放过。已建模为 `Assertion` 类型（带 `predicate` / `status` / `is_candidate` / `evidence`），并在适配器里强制校验三个子对象齐备。

2. **`/api/graph` 的 `rootId` 是节点内部复合 id**（`<graphId>:Publication:<sha256>`），DBLP 键在 `props.publicationId`。若按直觉拿 `rootId` 去和 `publicationId` 比，会得到"根节点不在返回图里"的假阳/假阴。适配器改为：校验 `rootId` 必须在返回节点集合中、根节点 `kind` 必须是 `Publication`、根节点 `props.publicationId` 必须等于请求的 id、每条边的两端必须都在返回节点集合内。

另外顺手补上的**版本一致性检查**（评审建议第 1 条要求）：

- `KGGraphMismatch` + `expected_graph_id`（或 `KG_EXPECTED_GRAPH_ID`）；任一响应携带的 `graphId` 与锁定值不符即抛错。
- `assert_graph_version()`：服务状态必须是 `ready`，且 graphId 必须等于锁定值。
- **不会误报**：只有当响应里**真的带了** `graphId` 且确实设置了锁时才比对，字段缺失一律不判错（已有专门用例 `test_absent_graph_id_is_not_a_mismatch`）。
- 实测：本机锁文件 `neo4j/resources/course_graph_runtime.json` 的 `graphId = ai-literature-ed16399925fac2a599ed` 与线上服务一致，测试通过。

---

## 4 复核命令与结果

```powershell
# 一次跑全（含真实集成，无服务时会自动 skip）
python scripts/run_all_tests.py
```

本轮实测（2026-10-08，Python 3.13.12，KG 服务在 127.0.0.1:8765）：

| 套件 | 数量 | 结果 |
|---|---:|---|
| `offline / knowledge-graph adapter` | 40 | OK |
| `offline / evidence contract` | 29 | OK |
| `live / knowledge graph` | 11 | OK |
| **合计** | **80** | **all 3 suites passed** |

评审提到"仓库写了 16 个适配器单元测试" —— 16 是上一轮的数字，本轮已扩到 40（离线）+ 11（真实）。

---

## 5 下一步（按评审给的顺序）

1. ✅ 补全并验证 KG Adapter（响应校验 / 真实 API / 版本一致性）—— **本轮完成**
2. ✅ 落地 FastAPI：`/api/health`、`/api/papers/search`、`/api/papers/{publication_id}`、`/api/graph/neighbors` —— **已完成并对真实 Neo4j 验收**（HTTP 18 项 + 真实集成 8 项 + 真实 uvicorn 冒烟；详见 `docs/02_phase1_plan.md` §5）
3. ⏭ 接入 Deep Agents：用 `kg_client.py` 注册研究工具，跑通真实论文问答
4. ⏭ 复用 NOESIS 前端组件（原组件移植优先）
5. ⏭ 持久化与引用体系（`research_runs`、SSE 重连、证据闸门）
6. ⏭ 接入 PaperQA2

下一次提交的交付目标按评审定：**Deep Agents 完成一次真实的 Neo4j 文献检索并返回可点击证据。** 数据侧已就绪 —— 三个端点的每条返回都自带 `evidence` 引用，Agent 只需接线与措辞。

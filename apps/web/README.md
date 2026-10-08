# apps/web · NOESIS Research 研究工作区

前端。**技术栈与 NOESIS 前端一致**（Vite 5 + React 18 + Tailwind 4），这样从 NOESIS 移植组件
不需要跨栈改写；`agent-chat-ui` 是 Next 16 + React 19，搬不过来，只作交互参考
（见 `docs/04_reference_clones.md` §2.4）。

## 当前实现范围

第一阶段闭环的**数据侧三段**：检索 → 详情 → 局部图谱，全程带证据引用。

| 区域 | 内容 |
|---|---|
| 状态条 | `graphId`、**版本锁定状态**、书目/已建模型/候选断言计数 —— 全部只来自 `/api/health` |
| 检索表单 | 与后端 `search_parameters()` 的白名单字段一一对应 |
| 实参回显 | `meta.applied` + `meta.expandedTerms` + `aliasVersion` —— 用户看得见实际搜了什么 |
| 结果列表 | 每条带可点击证据引用、以及「仅书目 / 已建模型提及」标注 |
| 论文详情 | 作者（含 `identityStatus`）、场馆、实体提及、**候选断言**、引文草稿、系统 notice |
| 局部图谱 | `paper` / `coauthors` / `methods` 三种局部视图，标注节数、graphId、是否截断 |
| 边界说明 | 直接把「本系统不做什么」写给用户看（无 CITES 数据、无全文、候选≠事实） |

**尚未实现**（属后续阶段）：科研助手对话面板（等 T6 的 research runs + SSE）、PDF 阅读、
报告 Artifact、研究项目/任务管理。

## 两条不许违反的显示规则（有单测守着）

1. **候选关系必须显示成「候选」**。`assertion.status === 'candidate'` 在 UI 上恒为候选徽标，
   不得改写成肯定语气。测试：`evidence.test.mjs` 的「候选断言在 UI 上恒为『候选』」。
2. **证据深度是独立维度**。`evidenceLevel: 'title'` 只能证明论文存在，UI 上必须显示
   「仅题名」并给出限制说明，不能讲成全文结论。

另外，`citationReport()` 与 `services/research-agent/run.py::citation_report` 是**同一条规则**
（统计回答里实际引用的 id，而不是工具结果里的 id）—— 两边算出来的引用可溯率必须一致。

## 移植说明

`src/lib/evidence.js` 里三段式证据闸门（`covered` / `missing` / `not_required`）的**形态**
移植自 NOESIS 的 `frontend/src/components/agentEvidence.helpers.js::evidenceState`；
其数据形状（`write_id` / `observations` / `inputs`）属 NOESIS 学习域，因此按本项目
`EvidenceRef` 契约重写，只保留形态与用语。

局部图谱这一版用**纯 SVG 环形布局**（零图库依赖），目的是先把节点/边/证据/边界声明的
数据通路与文案定下来。真正的图交互（缩放、力导向、点击展开）应移植 NOESIS 的
`GraphPanel` / `KnowledgeGraphSigma`（同栈）。

## 与后端的关系

走**同源代理**：`vite.config.js` 把 `/api` 代理到 `RESEARCH_API_TARGET`（默认
`http://127.0.0.1:8100`），浏览器看到的是同源请求，因此后端不需要开 CORS。
部署时用 `VITE_API_BASE` 指向真实后端地址。

失败语义与后端一致：503 / 502 一律抛 `ApiError` 并在界面上显示错误横幅，
**不会退化成"没有搜到"**。

## 运行与验证

```bash
# 依赖
pnpm install

# 单测（纯逻辑，node 内置 runner，无额外依赖）
pnpm test

# 起后端（另开一个终端）
../..\.venv\Scripts\python -m uvicorn noesis_research_api.app:app --app-dir ../api --port 8100

# 构建 + 预览
pnpm build && pnpm preview        # http://127.0.0.1:4173

# 无头浏览器验收（真实 Chrome + CDP，15 项断言）
node tools/verify_ui.mjs --shot shot.png
```

`tools/verify_ui.mjs` 验的是**渲染结果**而不是代码：状态条是否真拿到 graphId、检索是否真打到
后端、每条结果是否真带可点击证据、断言是否真显示为候选、图谱是否真画出节点、控制台有没有报错。

# apps/ · 应用层

- `web/` —— 复用 NOESIS 前端体系（React 18 + Vite 5 + Tailwind 4）。统一研究工作区：概览 / 科研助手 / 论文库 / 知识图谱 / 研究项目 / 研究报告，右侧可切换 论文详情 · PDF 阅读 · 图谱 · 报告 Artifact 面板。**只做行为对齐，不复制 NOESIS 样式。**
- `api/` —— FastAPI 业务 API。用户认证、权限、搜索聚合、SSE、研究任务管理。

接口清单见 `docs/02_phase1_plan.md` T3。契约定义放 `packages/contracts/`。

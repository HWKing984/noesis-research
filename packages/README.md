# packages/ · 跨服务共享包

- `evidence/` —— 统一证据模型。每条事实性断句必须挂 `publicationId` / `assertionId`，无标识则整句丢弃。
- `contracts/` —— API / Event 契约（Pydantic）。
- `citation-validator/` —— 引用核对。**移植** NOESIS `backend/app/services/citation_trace/verify.py` 的三阶段降级（精确 → 有界 difflib → 批量 LLM），保留其 Apache-2.0 归属头（源自 openJiuwen `citation_verify_research.py`）。

确定性闸门（阶段 1 即纳入 CI）：引用可溯率 100% · 无证据断言率 0% · 参数回显一致率 100% · 边界意图拒答覆盖。

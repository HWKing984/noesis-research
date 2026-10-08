# integrations/knowledge-graph · 只读 KG 适配器

研究 Agent 的**唯一**文献数据出口。封装 AI-Literature-KG 现有服务的 4 个只读端点。

## 为什么不用 NOESIS 的 neo4j_client

| | NOESIS `knowledge/graph/neo4j_client.py` | 本适配器 |
|---|---|---|
| 数据库不可用 | `execute()` 返回 `[]`，日志写 "Using in-memory fallback" | 抛 `KGUnavailable` |
| 写能力 | 有 `create_node` / `create_relationship` / **`delete_all()`** | 只有 4 个读方法（有单测守着） |
| 与 KG 铁律 | 冲突（把"库挂了"伪装成"没搜到"） | 一致（失败即失败） |

## 契约

| 方法 | 上游端点 | 错误映射 |
|---|---|---|
| `client.health()` | `GET /api/health` | 503 → `KGUnavailable` |
| `client.search(q=, author=, venue=, method=, task=, dataset=, year=, limit=, offset=)` | `GET /api/publications` | 400 → `KGInvalidRequest` |
| `client.publication(id)` | `GET /api/publication?id=` | 404 → `KGNotFound` |
| `client.graph(id, mode=paper\|coauthors\|methods, limit=)` | `GET /api/graph` | 其他 → `KGError` |

入参边界与 `scripts/course_graph.py:379 / :418` 一致（limit 1–100、offset ≤ 20000、year 2015–2025、graph limit 1–50），越界在**本地**就抛错，不发无效请求。

`search()` 返回的 `expandedTerms` / `aliasVersion` 原样透传 —— Agent 的"参数回显"直接用这两个字段，不做二次推断。

## 用法

```python
from kg_client import KGClient, KGUnavailable

client = KGClient("http://127.0.0.1:8765")
try:
    page = client.search(method="扩散模型", year=2023, limit=10)
except KGUnavailable as exc:
    # 必须把失败透传给用户；不要在这里返回空结果
    raise
```

## 测试

```powershell
& "<python>" -m unittest discover -s integrations/knowledge-graph -t integrations/knowledge-graph -v
```

16 项，纯标准库，无需 Neo4j 或 HTTP 服务（注入 `FakeTransport`）。覆盖：4 种状态映射、非 JSON / 缺 `data` 映射、参数本地校验先于请求、`expandedTerms` 透传、只读表面断言。

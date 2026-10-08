# apps/api · NOESIS Research API

FastAPI 业务层，架在只读 KG 适配器（`integrations/knowledge-graph/kg_client.py`）之上。第一阶段**只有 3 个业务端点 + 1 个就绪探针**。

## 端点

| 方法 | 路径 | 作用 |
|---|---|---|
| `GET` | `/api/health` | 就绪探针：图是否可用、是否为锁定版本。不可用即 **503** |
| `GET` | `/api/papers/search` | 书目检索；返回 `applied`（实参回显）与 `expandedTerms`（中文别名展开） |
| `GET` | `/api/papers/{publication_id}` | 单篇详情：作者 / 场馆 / 提及 / 候选断言 / 引文草稿 |
| `GET` | `/api/graph/neighbors` | 局部有界图（`paper` / `coauthors` / `methods`） |

**没有的东西（有意）**：文献收藏、PDF 上传、报告导出 —— 移到阶段 2 / 3，见 `docs/02_phase1_plan.md`。

## 两个容易踩的实现细节

1. **`{publication_id:path}` 必须用 `:path` 转换器。** DBLP 键含斜杠（`conf/aaai/0002LCWHL25`），普通路径段会让每个真实 id 都 404。
2. **`/api/papers/{id}` 必须注册在 `/api/papers/search` 之后**，否则会把 `search` 吞成 id。已有专门回归用例守着。

## 错误语义（没有任何一条会把失败变成"空结果"）

| 上游情况 | HTTP | `error.code` |
|---|---|---|
| 图 / Neo4j 不可用 | 503 | `kg_unavailable` |
| 图谱版本与锁定值不符 | 503 | `kg_graph_version_mismatch` |
| 请求参数非法 | 400 | `invalid_request` |
| 文献不存在 | 404 | `not_found` |
| 上游 200 但结构不符 | 502 | `kg_bad_response` |
| 其他 | 500 | `internal_error` |

## 证据随数据走

每条 `PaperSummary` 与每条 `AssertionModel` 都带一个 `evidence`（`EvidenceRefModel`）。候选断言的 `status` 恒为 `candidate`、`confidenceCalibrated` 恒为 `false` —— API 不做任何升格。

## 配置

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `KG_BASE_URL` | `http://127.0.0.1:8765` | KG 服务地址（容器里指向 `http://kg-service:8765`） |
| `KG_EXPECTED_GRAPH_ID` | 空（不校验） | 锁定图谱版本；设置后任何版本不符即 503 |
| `KG_TIMEOUT` | `20` | 上游超时（秒） |

## 本地运行

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r apps/api/requirements.txt
.venv/Scripts/python -m uvicorn noesis_research_api.app:app --app-dir apps/api --port 8100
```

无 KG 服务时，`/api/health` 与三个业务端点都会返回 **503**（不会返回空列表）。

## 测试

```bash
# 无数据库：真实 app + 真实适配器 + 真实 Pydantic 模型，只换掉最底层的 socket
.venv/Scripts/python -m unittest discover -s apps/api -t apps/api -v
```

测试打的是 HTTP 边界，因此"上游 200 但缺 `data`"这类缺陷会以 **502** 暴露，而不是静默变成空结果。

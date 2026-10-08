# services/research-agent · Deep Agents 科研助手

单个主 Agent + 5 个只读工具，架在 `integrations/knowledge-graph/kg_client.py` 之上。
**不做子 Agent**（普通检索不该过多个模型；子 Agent 留给长篇综述与多主题比较，属后续阶段）。

## 工具面

| 工具 | 作用 |
|---|---|
| `report_graph_scope` | 图谱版本 + 各层级真实计数（回答里的数字只能来自这里） |
| `search_papers` | 书目检索，返回 `applied`（实参回显）与 `expandedTerms`（中文别名展开） |
| `get_paper` | 单篇详情：作者 / 场馆 / 提及 / 候选断言 / 引文草稿 |
| `get_paper_evidence` | 可引用证据清单（题名级证据 + 每条候选断言的证据引用） |
| `explore_graph` | 局部有界图（`paper` / `coauthors` / `methods`） |

工具返回的是**和 HTTP API 完全一样**的载荷 —— 因为它调用的是同一套映射函数
（`noesis_research_api.mapping`）。所以「Agent 只做编排、不改变检索结果」这件事是可验证的，
不是口号。每个工具结果里都带 `evidence` 引用，检索参数回显在模型**之下**生成，模型改不了。

## 安全姿态（有测试守着，不靠文档承诺）

`create_deep_agent` 自带文件工具和一个 `execute`（跑 shell）工具。上游 `deepagents==0.7.23`
的处理方式（`libs/deepagents/deepagents/graph.py`）：

- 后端默认 `StateBackend()`（graph.py:653）——**内存态，不是宿主文件系统**；本服务**显式传**它，不依赖默认值；
- `execute` 只有在后端实现 `SandboxBackendProtocol` 时才真能跑命令，否则返回错误信息。本服务**从不提供沙箱后端**。

因此研究 Agent 没有任何通往宿主 shell 的路径，文件工具也只能碰内存态。
`test_agent.py::SafetyPostureTests` 断言了这两点。官方的工具排除入口
（`_ToolExclusionMiddleware`）是**私有**的，本服务不去依赖它。

## 配置

| 环境变量 | 必填 | 说明 |
|---|---|---|
| `LLM_API_KEY` | ✅ | OpenAI 兼容端点的 key（与 NOESIS 同名，便于复用同一份配置） |
| `LLM_MODEL` | ✅ | 模型名 |
| `LLM_BASE_URL` | — | 自建/兼容端点；不填则用 provider 默认 |
| `KG_BASE_URL` | — | 默认 `http://127.0.0.1:8765` |
| `KG_EXPECTED_GRAPH_ID` | — | 锁定图谱版本；设置后任何版本漂移即报错 |
| `KG_TIMEOUT` | — | 默认 20 秒 |

缺 `LLM_API_KEY` / `LLM_MODEL` 时**直接拒绝运行**，不会静默退回某个"默认模型"。

## 运行

```bash
# 建 venv（独立于 apps/api 与 NOESIS）
python -m venv services/research-agent/.venv
services/research-agent/.venv/Scripts/python -m pip install -r services/research-agent/requirements.txt

# 提问
services/research-agent/.venv/Scripts/python services/research-agent/run.py \
    "用扩散模型做图像生成的工作有哪些？" --transcript /tmp/run.json
```

`run.py` 依次打印：**工具调用轨迹**（含实参）、**回答**、**可引用的证据 id 清单**。
第三块才是重点 —— 一条引用都挂不上的回答算失败，不算流畅的成功。
若一个证据 id 都没有，进程退出码为 `1`；图谱不可用为 `3`；配置缺失为 `2`。

## 测试

```bash
services/research-agent/.venv/Scripts/python -m unittest discover \
    -s services/research-agent -t services/research-agent -v
```

离线：KG 侧用假 transport，模型侧用记录 `bind_tools` 的假模型。不需要 LLM、不需要 Neo4j。
没有装 deepagents 时本套件整体 **skip**（不是报错），CI 会断言这个 skip 确实发生。

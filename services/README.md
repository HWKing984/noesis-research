# services/ · 独立服务

- `research-agent/` —— **Deep Agents** 执行底座。主 Agent + 只读工具（`search_papers` / `get_paper` / `explore_graph` / `get_paper_evidence` / `compare_papers` / `write_review`）。子 Agent 只留给长篇综述与多主题比较。
- `paper-reader/` —— **PaperQA2** 适配服务（独立 venv，Python ≥ 3.11）。PDF 解析、段落检索、引用。
- `background-worker/` —— 异步研究任务与索引任务（Redis 队列）。

## 依赖隔离（硬要求）

`deepagents 0.7.23` 要求 `langchain-core>=1.6.7`，高于 NOESIS 现用的 `>=1.4.9`，并会引入 `langchain` / `langchain-anthropic` / `langchain-google-genai`。**一律在本目录各自建 venv，不装进 NOESIS 或 KG 的 venv。**

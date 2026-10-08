"""Read-only research tools exposed to the Deep Agent.

Every tool returns the **same payload the HTTP API returns**, because it calls
the same mapping functions (``noesis_research_api.mapping``). Two consequences
that matter:

* the agent cannot change a retrieval result — it can only choose which query to
  run, and the echo (``applied`` / ``expandedTerms``) is generated below the
  model, not by it;
* every paper and every candidate assertion arrives with an ``evidence`` ref, so
  a sentence the agent cannot attach a source id to is a sentence it should not
  have written.

Nothing here writes: the tools wrap a read-only client, and the agent has no
Cypher, no write verb and no database credential.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, tool

from kg_client import KGClient

from noesis_research_api.mapping import graph_slice, paper_summary, publication_detail

__all__ = ["RESEARCH_TOOL_NAMES", "build_tools"]

#: The research tool surface, in the order the model should read it.
RESEARCH_TOOL_NAMES = (
    "report_graph_scope",
    "search_papers",
    "get_paper",
    "get_paper_evidence",
    "explore_graph",
)

#: Hard ceiling on results per call, below the API's own limit, to keep one tool
#: result from flooding the context window.
MAX_SEARCH_LIMIT = 25
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_GRAPH_LIMIT = 15


def build_tools(client: KGClient, *, graph_id: str | None = None) -> list[BaseTool]:
    """Build the tool list bound to one read-only client.

    Built as a closure rather than module-level functions so the client (and the
    pinned graph id) are injected, which is also what makes the tools testable
    without a database.
    """

    @tool
    def report_graph_scope() -> dict[str, Any]:
        """报告当前知识图谱的版本与统计口径。

        做什么：返回 graphId、就绪状态，以及各层级的真实计数
        （bibliographyTitles / modelTitles / rejectedNERTitles / candidateAssertions）。

        什么时候用：任何需要写出数字的回答之前。**回答里的所有计数只能来自这里**，
        不得凭印象或凭常识给出数字。若本工具报错，说明图谱不可用，此时应如实
        说明失败，而不是继续回答。
        """
        report = client.assert_graph_version()
        return {
            "graphId": report.graph_id,
            "status": report.status,
            "source": report.source,
            "scope": report.scope,
            "aliasVersion": report.alias_version,
            "pinnedGraphId": graph_id,
        }

    @tool
    def search_papers(
        query: str = "",
        method: str = "",
        task: str = "",
        dataset: str = "",
        author: str = "",
        venue: str = "",
        year: int | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        """按书目检索论文（标题级）。

        做什么：在版本化图谱里按关键词/方法/任务/数据集/作者/会议/年份检索论文，
        返回每篇的 publicationId、title、year、doi、dblpUrl 以及一个 evidence 证据引用。

        什么时候用：用户提出问题后的第一步，用来找到候选论文。

        参数说明与边界：
        - query/method/task/dataset/author/venue：最多 200 字符。中文只在 22 条固定别名
          上做**精确**展开（如「扩散模型」→ diffusion model(s)），未知中文原样检索，
          因此中文查不到时优先改用英文术语重试。
        - year：只接受 2015–2025（图谱的收录范围）。
        - limit：1–25；offset：0–20000。

        返回里的 meta.applied 是**实际使用的检索参数**，回答里必须回显它；
        meta.expandedTerms 是别名展开结果。检索为空时会返回 data: []，那是真实空结果；
        若工具报错，则是图谱不可用 —— 两者必须区分开说，不能混为一谈。
        """
        bounded = max(1, min(int(limit), MAX_SEARCH_LIMIT))
        page = client.search(
            q=query,
            author=author,
            venue=venue,
            method=method,
            task=task,
            dataset=dataset,
            year=year,
            limit=bounded,
            offset=offset,
        )
        applied: dict[str, str] = {
            key: str(value)
            for key, value in (
                ("q", query),
                ("author", author),
                ("venue", venue),
                ("method", method),
                ("task", task),
                ("dataset", dataset),
                ("year", year),
            )
            if value not in (None, "")
        }
        applied["limit"] = str(bounded)
        applied["offset"] = str(offset)
        return {
            "applied": applied,
            "expandedTerms": {k: list(v) for k, v in page.expanded_terms.items()},
            "aliasVersion": page.alias_version,
            "hasNext": page.has_next,
            "graphId": graph_id,
            "papers": [paper_summary(item, graph_id=graph_id).model_dump() for item in page.publications],
        }

    @tool
    def get_paper(publication_id: str) -> dict[str, Any]:
        """取一篇论文的详情：作者、会议/期刊、实体提及、候选断言、引文草稿。

        做什么：按 publicationId 取单篇记录。作者带 identityStatus（是否匹配到 DBLP 主页
        身份）；mentions 是模型从标题里抽出的 METHOD/TASK/DATASET 提及；assertions 是
        **候选断言**（方法—任务 / 方法—数据集），每条都带 provenance 与 evidence 证据引用。

        什么时候用：已经拿到 publicationId、需要看署名、提及或候选断言时。

        注意：publicationId 是 DBLP 键，形如 `conf/aaai/0002LCWHL25`，**含斜杠**，
        必须原样传入。citationDraft 是**草稿**，引用前须核对原文，不能当成正式参考文献。
        """
        return publication_detail(client.publication(publication_id), graph_id=graph_id).model_dump()

    @tool
    def get_paper_evidence(publication_id: str) -> dict[str, Any]:
        """取一篇论文的可引用证据清单（回答里挂引用就用这个）。

        做什么：返回该论文的题名级证据引用，以及它每条候选断言各自的证据引用
        （含 assertionId、predicate、status、head/tail 提及文本、evidenceLevel、
        verificationStatus）。

        什么时候用：要把某句话挂到来源上之前。**回答中每个事实性断句都必须挂这里返回的
        sourceId**；挂不上的句子就不要写。

        注意：evidenceLevel 目前恒为 `title` —— 图谱只存题名。题名级证据只能证明
        「这篇论文存在、题名里出现了这些词」，**不能证明**论文真的做了你声称的事。
        verificationStatus 恒为 `unverified`。
        """
        detail = client.publication(publication_id)
        payload = publication_detail(detail, graph_id=graph_id).model_dump()
        return {
            "publicationId": payload["publication"]["publicationId"],
            "graphId": payload["publication"].get("graphId"),
            "bibliographyEvidence": payload["publication"]["evidence"],
            "notice": payload["notice"],
            "assertions": [
                {
                    "assertionId": item["id"],
                    "predicate": item["predicate"],
                    "status": item["status"],
                    "confidenceCalibrated": item["confidenceCalibrated"],
                    "head": (item.get("head") or {}).get("text"),
                    "tail": (item.get("tail") or {}).get("text"),
                    "evidence": item["evidence"],
                }
                for item in payload["assertions"]
            ],
        }

    @tool
    def explore_graph(publication_id: str, mode: str = "paper", limit: int = DEFAULT_GRAPH_LIMIT) -> dict[str, Any]:
        """探索某篇论文的局部知识图谱（有界，不是全图）。

        做什么：从一篇论文出发取局部子图。
        - mode="paper"：这篇论文的署名作者、场馆、提及的概念、候选断言；
        - mode="coauthors"：通过共同署名连接的其它论文（合作关系，**不是**引用关系）；
        - mode="methods"：通过共享方法概念连接的其它论文。

        什么时候用：用户想看「还和什么有关」、想沿方法/作者扩展检索时。

        参数：limit 1–15。

        注意：返回的 meta 明确标注 wholeGraph=false，即这是局部有界路径。共享方法只表示
        **模型提及相同概念**，不代表引用、也不代表已验证的语义相似。作者身份以节点的
        identityStatus 为准；未决署名不跨论文合并。
        """
        bounded = max(1, min(int(limit), DEFAULT_GRAPH_LIMIT))
        return graph_slice(client.graph(publication_id, mode=mode, limit=bounded)).model_dump()

    return [report_graph_scope, search_papers, get_paper, get_paper_evidence, explore_graph]

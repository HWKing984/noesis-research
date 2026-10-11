"""Read-only research tools exposed to the Deep Agent.

Two contracts, kept apart on purpose:

1. **给模型的**：工具返回值。必须**精简** —— 每个字段都会进入上下文，下一轮还要再读一遍。
   原始载荷（全字段论文、全部断言、全部节点）会让模型每轮吞几千 token：本地小模型直接
   慢到不可用，生产模型也会白白烧钱。这里只给 id、题名、年份、谓词、证据引用这类
   「模型做判断真正需要」的东西。
2. **给界面的**：通过事件里的 `summary` 汇报规模（几篇论文、几个节点），完整数据
   由界面自己调 API 拿。

Every result still carries `evidence` 引用 —— 模型要挂引用，界面上那些引用也是从这里来的。

Nothing here writes: the tools wrap a read-only client, and the agent has no
Cypher, no write verb and no database credential.
"""
from __future__ import annotations

from typing import Any, Mapping

from langchain_core.tools import BaseTool, tool

from kg_client import KGClient
from metadata_client import ExternalMetadataClient, ExternalNoIdentifier

from noesis_research_api.mapping import graph_slice, paper_summary, publication_detail

__all__ = ["RESEARCH_TOOL_NAMES", "build_tools"]

#: The research tool surface, in the order the model should read it.
RESEARCH_TOOL_NAMES = (
    "report_graph_scope",
    "search_papers",
    "get_paper",
    "get_paper_evidence",
    "read_paper_abstract",
    "explore_graph",
)

#: Hard ceiling on results per call, below the API's own limit, to keep one tool
#: result from flooding the context window.
MAX_SEARCH_LIMIT = 25
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_GRAPH_LIMIT = 15

#: 局部图谱喂给模型的节点上限（多余的只报数量，界面想要全量自己调 API）。
MAX_GRAPH_NODES_FOR_MODEL = 12

#: 摘要喂给模型的长度上限。摘要在实测里是 800–2000 字符，2000 足以覆盖一整段，
#: 又不至于让一篇摘要把上下文挤满（工具返回值进上下文是要反复读的）。
MAX_ABSTRACT_FOR_MODEL = 2000


def _evidence_view(ref: Mapping[str, Any] | None) -> dict[str, Any]:
    ref = ref or {}
    return {
        "sourceId": ref.get("sourceId"),
        "evidenceLevel": ref.get("evidenceLevel"),
        "verificationStatus": ref.get("verificationStatus"),
    }


def _model_paper(item: Mapping[str, Any]) -> dict[str, Any]:
    """一篇论文的**模型视图**：判断需要什么就给什么，其余留给界面。"""
    return {
        "publicationId": item.get("publicationId"),
        "title": item.get("title"),
        "year": item.get("year"),
        "doi": item.get("doi"),
        "evidence": _evidence_view(item.get("evidence")),
    }


def build_tools(
    client: KGClient,
    *,
    graph_id: str | None = None,
    metadata: ExternalMetadataClient | None = None,
) -> list[BaseTool]:
    """Build the tool list bound to one read-only client.

    Built as a closure rather than module-level functions so the client (and the
    pinned graph id) are injected, which is also what makes the tools testable
    without a database. ``metadata`` is the abstract-level source: when it is
    ``None`` the ``read_paper_abstract`` tool reports ``disabled`` instead of
    pretending the paper has no abstract.
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
        返回每篇的 publicationId、title、year、doi 与 evidence 证据引用。

        什么时候用：用户提出问题后的第一步，用来找到候选论文。

        参数说明与边界：
        - query/method/task/dataset/author/venue：最多 200 字符。中文只在 22 条固定别名
          上做**精确**展开（如「扩散模型」→ diffusion model(s)），未知中文原样检索，
          因此中文查不到时优先改用英文术语重试。
        - year：只接受 2015–2025（图谱的收录范围）。
        - limit：1–25；offset：0–20000。

        返回里的 meta.applied 是**实际使用的检索参数**，回答里必须回显它；
        检索为空会返回 papers: []，那是真实空结果；若工具报错，则是图谱不可用 ——
        两者必须区分开说，不能混为一谈。
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
        summaries = [paper_summary(item, graph_id=graph_id).model_dump() for item in page.publications]
        return {
            "applied": applied,
            "expandedTerms": {k: list(v) for k, v in page.expanded_terms.items()},
            "aliasVersion": page.alias_version,
            "hasNext": page.has_next,
            "graphId": graph_id,
            "papers": [_model_paper(item) for item in summaries],
        }

    @tool
    def get_paper(publication_id: str) -> dict[str, Any]:
        """取一篇论文的详情：作者、会议/期刊、实体提及、候选断言、引文草稿。

        做什么：按 publicationId 取单篇记录。作者带 identityStatus（是否匹配到 DBLP 主页
        身份）；assertions 是**候选断言**（方法—任务 / 方法—数据集），每条都带
        evidence 证据引用。

        什么时候用：已经拿到 publicationId、需要看署名或候选断言时。

        注意：publicationId 是 DBLP 键，形如 `conf/aaai/0002LCWHL25`，**含斜杠**，
        必须原样传入。citationDraft 是**草稿**，引用前须核对原文，不能当成正式参考文献。
        """
        payload = publication_detail(client.publication(publication_id), graph_id=graph_id).model_dump()
        publication = payload["publication"]
        return {
            "publicationId": publication["publicationId"],
            "title": publication["title"],
            "year": publication.get("year"),
            "doi": publication.get("doi"),
            "graphId": publication.get("graphId"),
            "evidence": _evidence_view(publication.get("evidence")),
            "authors": [
                {"name": item.get("name"), "identityStatus": item.get("identityStatus")}
                for item in payload.get("authors", [])
            ],
            "venues": [item.get("name") for item in payload.get("venues", [])],
            "mentions": [item.get("text") for item in payload.get("mentions", [])],
            "assertions": [
                {
                    "assertionId": item["id"],
                    "predicate": item["predicate"],
                    "status": item["status"],
                    "confidenceCalibrated": item.get("confidenceCalibrated"),
                    "head": (item.get("head") or {}).get("text"),
                    "tail": (item.get("tail") or {}).get("text"),
                    "evidenceText": item.get("evidenceText"),
                    "evidence": _evidence_view(item.get("evidence")),
                }
                for item in payload.get("assertions", [])
            ],
            "citationDraft": payload.get("citationDraft", ""),
            "notice": payload.get("notice", ""),
        }

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
        payload = publication_detail(client.publication(publication_id), graph_id=graph_id).model_dump()
        return {
            "publicationId": payload["publication"]["publicationId"],
            "graphId": payload["publication"].get("graphId"),
            "bibliographyEvidence": _evidence_view(payload["publication"].get("evidence")),
            "notice": payload.get("notice", ""),
            "assertions": [
                {
                    "assertionId": item["id"],
                    "predicate": item["predicate"],
                    "status": item["status"],
                    "confidenceCalibrated": item.get("confidenceCalibrated"),
                    "head": (item.get("head") or {}).get("text"),
                    "tail": (item.get("tail") or {}).get("text"),
                    "evidence": _evidence_view(item.get("evidence")),
                }
                for item in payload.get("assertions", [])
            ],
        }

    @tool
    def read_paper_abstract(publication_id: str) -> dict[str, Any]:
        """读一篇论文的摘要原文（来自外部学术源）。

        做什么：用图谱记录里的 DOI（或 arXiv 链接）去外部学术源
        （Semantic Scholar → OpenAlex → Crossref）取这篇论文的**摘要原文**
        与发表信息（会议/期刊、年份）。

        什么时候用：**在谈论一篇论文"做了什么"之前**。题名级证据做不到这件事。
        用户问「它们有什么区别」「谁提出了什么」「这篇的贡献是什么」这类问题时，
        先读摘要再回答。

        返回：available=true 时给出 source（Semantic Scholar / OpenAlex / Crossref ——
        回答里要如实写出摘要来自哪个源）、venue、year、evidenceLevel=`abstract`、
        evidenceText（摘要原文），以及 evidence 引用（sourceId 形如 `doi:10.x/y`，
        挂引用就用它）。

        available=false 是**有依据的「没有」**，reason 说明原因：
        `no_identifier` = 记录里既没有 DOI 也没有 arXiv 链接，无法定位外部记录；
        `no_abstract` = 定位到了记录，但外部源没有存摘要；
        `disabled` = 本服务未配置外部源。
        工具**抛错**是另一回事 —— 那是外部源不可达。此时如实说查询失败，
        绝不要说成「这篇论文没有摘要」。
        """
        payload = publication_detail(client.publication(publication_id), graph_id=graph_id).model_dump()
        publication = payload.get("publication") or {}
        resolved_id = publication.get("publicationId") or publication_id
        base: dict[str, Any] = {
            "publicationId": resolved_id,
            "title": publication.get("title"),
            "doi": publication.get("doi"),
        }
        if metadata is None:
            return {
                **base,
                "available": False,
                "reason": "disabled",
                "detail": "本服务未配置外部学术源（EXTERNAL_SOURCES 为空）",
            }
        try:
            record = metadata.lookup_publication(doi=publication.get("doi"), urls=publication.get("urls") or ())
        except ExternalNoIdentifier as exc:
            return {**base, "available": False, "reason": "no_identifier", "detail": str(exc)}
        if record is None:
            return {
                **base,
                "available": False,
                "reason": "no_abstract",
                "detail": "外部源已定位到该记录，但其中没有摘要",
            }
        return {
            **base,
            "available": True,
            "source": record.source,
            "sourceLabel": record.source_label,
            "venue": record.venue,
            "year": record.year,
            "evidenceLevel": record.evidence_level,
            "verificationStatus": "id_valid",
            "evidenceText": record.abstract_for_model(limit=MAX_ABSTRACT_FOR_MODEL),
            "evidence": record.evidence_ref(publication_id=resolved_id),
            "note": "摘要来自外部源原文，可据此谈论论文做了什么；全文结论仍需读原文。",
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

        注意：wholeGraph=false，即这是局部有界路径。共享方法只表示**模型提及相同概念**，
        不代表引用、也不代表已验证的语义相似。作者身份以节点的 identityStatus 为准；
        未决署名不跨论文合并。
        """
        bounded = max(1, min(int(limit), DEFAULT_GRAPH_LIMIT))
        payload = graph_slice(client.graph(publication_id, mode=mode, limit=bounded)).model_dump()
        nodes = [
            {
                "kind": node["kind"],
                "label": node["props"].get("name") or node["props"].get("title") or "",
                "publicationId": node["props"].get("publicationId"),
            }
            for node in payload["nodes"][:MAX_GRAPH_NODES_FOR_MODEL]
        ]
        return {
            "graphId": payload["graphId"],
            "mode": payload["mode"],
            "rootId": payload["rootId"],
            "nodeCount": len(payload["nodes"]),
            "edgeCount": len(payload["edges"]),
            "hasMorePaths": payload["hasMorePaths"],
            "nodes": nodes,
            "notice": payload["notice"],
        }

    return [
        report_graph_scope,
        search_papers,
        get_paper,
        get_paper_evidence,
        read_paper_abstract,
        explore_graph,
    ]

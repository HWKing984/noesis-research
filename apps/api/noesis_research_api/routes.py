"""Stage-1 business routes: search, detail, local graph neighbours, readiness.

Three business endpoints, no more — library / upload / export are later stages
(``docs/02_phase1_plan.md`` T3).
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from kg_client import KGClient

from .mapping import graph_slice, paper_summary, publication_detail
from .models import (
    GraphSliceModel,
    HealthModel,
    PublicationDetailModel,
    SearchMeta,
    SearchResponse,
)

router = APIRouter(prefix="/api", tags=["research"])

DEFAULT_LIMIT = 20
DEFAULT_OFFSET = 0
DEFAULT_GRAPH_MODE = "paper"
DEFAULT_GRAPH_LIMIT = 30


def _kg(request: Request) -> KGClient:
    return request.app.state.kg


@router.get(
    "/health",
    response_model=HealthModel,
    summary="Readiness: is the knowledge graph usable, and is it the pinned version?",
)
def health(request: Request) -> HealthModel:
    """503 (not 200-with-empty-data) whenever the graph is unusable or the wrong version."""
    report = _kg(request).assert_graph_version()
    return HealthModel(
        status=report.status,
        graphId=report.graph_id,
        source=report.source,
        scope=report.scope,
        aliasVersion=report.alias_version,
        pinnedGraphId=request.app.state.settings.expected_graph_id,
    )


@router.get(
    "/papers/search",
    response_model=SearchResponse,
    summary="Bibliography search over the versioned graph",
)
def search_papers(
    request: Request,
    q: str = "",
    author: str = "",
    author_id: str = Query("", alias="authorId"),
    venue: str = "",
    method: str = "",
    task: str = "",
    dataset: str = "",
    year: int | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> SearchResponse:
    page = _kg(request).search(
        q=q,
        author=author,
        author_id=author_id,
        venue=venue,
        method=method,
        task=task,
        dataset=dataset,
        year=year,
        limit=limit,
        offset=offset,
    )

    applied: dict[str, str] = {
        key: str(value)
        for key, value in (
            ("q", q),
            ("author", author),
            ("authorId", author_id),
            ("venue", venue),
            ("method", method),
            ("task", task),
            ("dataset", dataset),
            ("year", year),
        )
        if value not in (None, "")
    }
    applied["limit"] = str(limit)
    applied["offset"] = str(offset)

    graph_id = request.app.state.settings.expected_graph_id
    return SearchResponse(
        data=[paper_summary(item, graph_id=graph_id) for item in page.publications],
        meta=SearchMeta(
            offset=page.offset,
            limit=page.limit,
            hasNext=page.has_next,
            source=page.source,
            aliasVersion=page.alias_version,
            expandedTerms={field: list(values) for field, values in page.expanded_terms.items()},
            applied=applied,
            graphId=graph_id,
        ),
    )


@router.get(
    "/graph/neighbors",
    response_model=GraphSliceModel,
    summary="Bounded local neighbourhood (paper / coauthors / methods)",
)
def graph_neighbors(
    request: Request,
    id: str,  # noqa: A002 - the wire parameter name is `id`
    mode: str = DEFAULT_GRAPH_MODE,
    limit: int = DEFAULT_GRAPH_LIMIT,
) -> GraphSliceModel:
    return graph_slice(_kg(request).graph(id, mode=mode, limit=limit))


# Registered last on purpose: `{publication_id:path}` would otherwise swallow
# `/papers/search`. The `:path` converter is required because DBLP keys contain
# slashes (e.g. `conf/aaai/0002LCWHL25`) — a plain `{publication_id}` segment
# would 404 on every real publication id.
@router.get(
    "/papers/{publication_id:path}",
    response_model=PublicationDetailModel,
    summary="One paper: bibliography, authors, venues, mentions, candidate assertions",
)
def get_paper(request: Request, publication_id: str) -> PublicationDetailModel:
    detail = _kg(request).publication(publication_id)
    return publication_detail(detail, graph_id=request.app.state.settings.expected_graph_id)

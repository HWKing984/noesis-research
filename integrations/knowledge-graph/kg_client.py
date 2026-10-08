"""Read-only adapter over the AI-Literature-KG HTTP API.

Why this file exists
--------------------
NOESIS ships ``backend/app/knowledge/graph/neo4j_client.py``, which returns
``[]`` when the database is unreachable (``execute()`` docstring: "不可用时返回
空列表而不是抛错") and also exposes write helpers (``create_node``,
``create_relationship``, ``delete_all`` -> ``MATCH (n) DETACH DELETE n``).
The knowledge graph's own rule is the opposite: ``scripts/course_graph.py``
raises ``DatabaseUnavailable`` and the server answers **503 with the text
"未使用离线替代数据"**. A research answer built on a silent empty result is
indistinguishable from a genuinely empty search — that is a fabrication path.

So this adapter deliberately does *not* reuse the NOESIS client. It is a thin,
strict, read-only wrapper over the four documented endpoints of the existing
service:

===============  ==========================================================
endpoint         purpose
===============  ==========================================================
/api/health      real Neo4j + current graph ``completed`` state
/api/publications  filtered bibliography search (q/author/venue/method/…)
/api/publication   one publication: authors, venues, mentions, assertions
/api/graph         bounded local neighbourhood (paper/coauthors/methods)
===============  ==========================================================

Invariants carried over from ``scripts/course_graph.py``:

1. **Failure is loud.** Every non-200 upstream status is raised as a typed
   error. No code path in this module turns an outage into an empty result.
2. **Read-only.** There is no Cypher here and no write verb anywhere on
   :class:`KGClient`. The only writer in the whole system stays
   ``scripts/course_graph.py import``, behind an interactive password prompt.
3. **Parameter bounds are mirrored, not invented.** Limits below match
   ``search_parameters()`` and ``graph_parameters()`` so we fail locally with a
   clear message instead of shipping an invalid request upstream.

Standard library only, on purpose: this is the seam the Deep Agents tools sit
on, so it must import in any Python >= 3.11 without dragging a dependency tree.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

__all__ = [
    "KGError",
    "KGUnavailable",
    "KGInvalidRequest",
    "KGNotFound",
    "Transport",
    "HttpTransport",
    "SearchPage",
    "PublicationDetail",
    "GraphSlice",
    "GraphNode",
    "GraphEdge",
    "Health",
    "KGClient",
    "DEFAULT_BASE_URL",
    "SEARCH_FIELDS",
    "GRAPH_MODES",
]

DEFAULT_BASE_URL = "http://127.0.0.1:8765"

# --- bounds mirrored from scripts/course_graph.py --------------------------
# search_parameters() L379-398 and graph_parameters() L418-424.
SEARCH_FIELDS = frozenset(
    {"q", "author", "authorId", "venue", "method", "task", "dataset", "year", "limit", "offset"}
)
GRAPH_MODES = frozenset({"paper", "coauthors", "methods"})
MIN_LIMIT, MAX_LIMIT = 1, 100
MAX_OFFSET = 20000
MIN_YEAR, MAX_YEAR = 2015, 2025
MAX_TERM_LENGTH = 200
MAX_ID_LENGTH = 300
MIN_GRAPH_LIMIT, MAX_GRAPH_LIMIT = 1, 50
DEFAULT_LIMIT = 20
DEFAULT_OFFSET = 0
DEFAULT_GRAPH_MODE = "paper"
DEFAULT_GRAPH_LIMIT = 30

#: Status codes the upstream server documents (course_graph.py server() L502-525).
_STATUS_INVALID = 400
_STATUS_NOT_FOUND = 404
_STATUS_UNAVAILABLE = 503


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------
class KGError(Exception):
    """Base class for every failure this adapter can raise."""


class KGUnavailable(KGError):
    """Neo4j / the course graph is not ready (upstream HTTP 503).

    Callers MUST surface this as a failure. Returning an empty result instead
    would present "the database is down" as "no such paper".
    """


class KGInvalidRequest(KGError):
    """The request was rejected upstream (HTTP 400) or locally by the mirror."""


class KGNotFound(KGError):
    """The publication id is unknown (HTTP 404)."""


# ---------------------------------------------------------------------------
# transport seam (injectable so tests run with no server)
# ---------------------------------------------------------------------------
class Transport(Protocol):
    """Minimal HTTP GET seam. Returns ``(status_code, raw_body_bytes)``."""

    def get(self, path: str, params: Mapping[str, str]) -> "tuple[int, bytes]":  # pragma: no cover
        ...


class HttpTransport:
    """``urllib``-based transport aimed at the loopback-only KG service."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, *, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)

    def get(self, path: str, params: Mapping[str, str]) -> tuple[int, bytes]:
        query = urllib.parse.urlencode(list(params.items()))
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return int(response.status), response.read()
        except urllib.error.HTTPError as exc:  # 4xx / 5xx carry a JSON error body
            return int(exc.code), exc.read()
        except urllib.error.URLError as exc:  # connection refused, DNS, timeout
            # Not an HTTP status: the service itself is unreachable. This is the
            # clearest possible "unavailable" signal, so do not retry silently.
            raise KGUnavailable(f"knowledge graph service unreachable: {exc.reason}") from exc


# ---------------------------------------------------------------------------
# response shapes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SearchPage:
    """One page of ``/api/publications`` results."""

    publications: tuple[dict[str, Any], ...]
    offset: int
    limit: int
    has_next: bool
    source: str
    alias_version: str | None
    expanded_terms: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class PublicationDetail:
    """``/api/publication?id=...`` — bibliography plus candidate assertions."""

    publication: dict[str, Any]
    authors: tuple[dict[str, Any], ...]
    venues: tuple[dict[str, Any], ...]
    mentions: tuple[dict[str, Any], ...]
    assertions: tuple[dict[str, Any], ...]
    citation_draft: str
    notice: str


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str
    props: dict[str, Any]


@dataclass(frozen=True)
class GraphEdge:
    id: str
    kind: str
    source: str
    target: str


@dataclass(frozen=True)
class GraphSlice:
    """``/api/graph`` — a bounded local slice; never the whole graph."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    paths: tuple[dict[str, Any], ...]
    root_id: str
    mode: str
    graph_id: str
    has_more_paths: bool
    notice: str


@dataclass(frozen=True)
class Health:
    """``/api/health`` — the only source of truth for counts."""

    status: str
    graph_id: str
    source: str
    scope: dict[str, int]
    resolution: dict[str, Any] | None
    alias_version: str | None


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------
class KGClient:
    """Strict, read-only client for the AI-Literature-KG service."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        transport: Transport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._transport: Transport = transport or HttpTransport(self.base_url, timeout=timeout)

    # -- public read surface -------------------------------------------------
    def health(self) -> Health:
        payload = self._get("/api/health", {})
        data = self._data(payload)
        terminology = data.get("terminology") or {}
        return Health(
            status=str(data.get("status", "")),
            graph_id=str(data.get("graphId", "")),
            source=str(data.get("source", "")),
            scope={k: int(v) for k, v in (data.get("scope") or {}).items()},
            resolution=data.get("resolution"),
            alias_version=terminology.get("version") if isinstance(terminology, Mapping) else None,
        )

    def search(
        self,
        *,
        q: str = "",
        author: str = "",
        author_id: str = "",
        venue: str = "",
        method: str = "",
        task: str = "",
        dataset: str = "",
        year: int | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = DEFAULT_OFFSET,
    ) -> SearchPage:
        params = self._search_params(
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
        payload = self._get("/api/publications", params)
        meta = payload.get("meta") or {}
        expanded = {
            field: tuple(values)
            for field, values in (meta.get("expandedTerms") or {}).items()
        }
        return SearchPage(
            publications=tuple(payload.get("data") or ()),
            offset=int(meta.get("offset", offset)),
            limit=int(meta.get("limit", limit)),
            has_next=bool(meta.get("hasNext", False)),
            source=str(meta.get("source", "")),
            alias_version=meta.get("aliasVersion"),
            expanded_terms=expanded,
        )

    def publication(self, publication_id: str) -> PublicationDetail:
        pid = self._publication_id(publication_id)
        payload = self._get("/api/publication", {"id": pid})
        data = self._data(payload)
        return PublicationDetail(
            publication=data["publication"],
            authors=tuple(data.get("authors") or ()),
            venues=tuple(data.get("venues") or ()),
            mentions=tuple(data.get("mentions") or ()),
            assertions=tuple(data.get("assertions") or ()),
            citation_draft=str(data.get("citationDraft", "")),
            notice=str(data.get("notice", "")),
        )

    def graph(
        self,
        publication_id: str,
        *,
        mode: str = DEFAULT_GRAPH_MODE,
        limit: int = DEFAULT_GRAPH_LIMIT,
    ) -> GraphSlice:
        pid = self._publication_id(publication_id)
        if mode not in GRAPH_MODES:
            raise KGInvalidRequest(
                f"mode must be one of {sorted(GRAPH_MODES)}, got {mode!r}"
            )
        bound = self._graph_limit(limit)
        payload = self._get("/api/graph", {"id": pid, "mode": mode, "limit": str(bound)})
        data = self._data(payload)
        meta = payload.get("meta") or {}
        nodes = tuple(
            GraphNode(
                id=str(node["props"]["id"]),
                kind=str(node.get("kind", "")),
                props=dict(node.get("props") or {}),
            )
            for node in (data.get("nodes") or ())
        )
        edges = tuple(
            GraphEdge(
                id=str(edge["id"]),
                kind=str(edge.get("kind", "")),
                source=str(edge.get("source", "")),
                target=str(edge.get("target", "")),
            )
            for edge in (data.get("edges") or ())
        )
        return GraphSlice(
            nodes=nodes,
            edges=edges,
            paths=tuple(data.get("paths") or ()),
            root_id=str(data.get("rootId", pid)),
            mode=str(meta.get("mode", mode)),
            graph_id=str(meta.get("graphId", "")),
            has_more_paths=bool(meta.get("hasMorePaths", False)),
            notice=str(meta.get("notice", "")),
        )

    # -- local validation (mirrors course_graph.py, fails before the network) --
    @staticmethod
    def _search_params(**raw: Any) -> dict[str, str]:
        params: dict[str, str] = {}
        for key in ("q", "author", "venue", "method", "task", "dataset"):
            value = str(raw.get(key) or "").strip()
            if len(value) > MAX_TERM_LENGTH:
                raise KGInvalidRequest(f"{key} must be at most {MAX_TERM_LENGTH} characters")
            if value:
                params[key] = value

        author_id = str(raw.get("author_id") or "").strip()
        if len(author_id) > MAX_ID_LENGTH:
            raise KGInvalidRequest(f"authorId must be at most {MAX_ID_LENGTH} characters")
        if author_id:
            params["authorId"] = author_id

        year = raw.get("year")
        if year is not None:
            try:
                year = int(year)
            except (TypeError, ValueError):
                raise KGInvalidRequest("year must be an integer") from None
            if not MIN_YEAR <= year <= MAX_YEAR:
                raise KGInvalidRequest(f"year must be within {MIN_YEAR}-{MAX_YEAR}, got {year}")
            params["year"] = str(year)

        limit = raw.get("limit", DEFAULT_LIMIT)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            raise KGInvalidRequest("limit must be an integer") from None
        if not MIN_LIMIT <= limit <= MAX_LIMIT:
            raise KGInvalidRequest(f"limit must be within {MIN_LIMIT}-{MAX_LIMIT}, got {limit}")

        offset = raw.get("offset", DEFAULT_OFFSET)
        try:
            offset = int(offset)
        except (TypeError, ValueError):
            raise KGInvalidRequest("offset must be an integer") from None
        if not 0 <= offset <= MAX_OFFSET:
            raise KGInvalidRequest(f"offset must be within 0-{MAX_OFFSET}, got {offset}")

        params["limit"] = str(limit)
        params["offset"] = str(offset)
        return params

    @staticmethod
    def _publication_id(publication_id: str) -> str:
        value = str(publication_id or "").strip()
        if not value:
            raise KGInvalidRequest("publication id is required")
        if len(value) > MAX_ID_LENGTH:
            raise KGInvalidRequest(f"publication id must be at most {MAX_ID_LENGTH} characters")
        return value

    @staticmethod
    def _graph_limit(limit: int) -> int:
        try:
            bound = int(limit)
        except (TypeError, ValueError):
            raise KGInvalidRequest("graph limit must be an integer") from None
        if not MIN_GRAPH_LIMIT <= bound <= MAX_GRAPH_LIMIT:
            raise KGInvalidRequest(
                f"graph limit must be within {MIN_GRAPH_LIMIT}-{MAX_GRAPH_LIMIT}, got {bound}"
            )
        return bound

    # -- transport + status mapping -----------------------------------------
    def _get(self, path: str, params: Mapping[str, str]) -> dict[str, Any]:
        status, body = self._transport.get(path, params)
        if status == 200:
            return self._decode(body, path)
        message = self._error_message(body) or f"HTTP {status}"
        if status == _STATUS_UNAVAILABLE:
            raise KGUnavailable(message)
        if status == _STATUS_INVALID:
            raise KGInvalidRequest(message)
        if status == _STATUS_NOT_FOUND:
            raise KGNotFound(message)
        raise KGError(f"{path}: unexpected upstream status {status}: {message}")

    @staticmethod
    def _decode(body: bytes, path: str) -> dict[str, Any]:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KGError(f"{path}: response was not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise KGError(f"{path}: expected a JSON object, got {type(payload).__name__}")
        return payload

    @staticmethod
    def _error_message(body: bytes) -> str:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ""
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, Mapping):
            return str(error.get("message") or error.get("code") or "")
        return ""

    @staticmethod
    def _data(payload: Mapping[str, Any]) -> dict[str, Any]:
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise KGError("response is missing a 'data' object")
        return dict(data)


def read_methods() -> Sequence[str]:
    """Audit helper: the only verbs this client is allowed to expose."""
    return tuple(
        name
        for name, value in vars(KGClient).items()
        if callable(value) and not name.startswith("_")
    )

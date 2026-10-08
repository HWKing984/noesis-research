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

Invariants
----------
1. **Failure is loud, in both directions.** A non-200 status is raised as a
   typed error, *and* a 200 whose body does not match the documented shape is
   raised as :class:`KGError`. Both directions matter: a missing ``data``
   field on a 200 would otherwise be read as "no papers found" — the same
   fabrication path as swallowing a 503.
2. **Read-only.** There is no Cypher here and no write verb anywhere on
   :class:`KGClient`. The only writer in the whole system stays
   ``scripts/course_graph.py import``, behind an interactive password prompt.
3. **Parameter bounds are mirrored, not invented.** Limits below match
   ``search_parameters()`` and ``graph_parameters()`` so we fail locally with a
   clear message instead of shipping an invalid request upstream.
4. **Graph version is pinned, not assumed.** Set ``expected_graph_id`` (or the
   ``KG_EXPECTED_GRAPH_ID`` environment variable) and any response carrying a
   different ``graphId`` raises :class:`KGGraphMismatch`. The graph is
   versioned (``resources/course_graph_runtime.json`` in the KG repo pins a
   graphId plus a manifest hash); silently serving an older version would
   invalidate every citation.

Deployment
----------
The service address is **not** hard-coded into the request path: it resolves
from the ``base_url`` argument, else the ``KG_BASE_URL`` environment variable,
else the loopback default used for local development. Container deployments set
``KG_BASE_URL`` (e.g. ``http://kg-service:8765``).

Standard library only, on purpose: this is the seam the Deep Agents tools sit
on, so it must import in any Python >= 3.11 without dragging a dependency tree.
"""
from __future__ import annotations

import json
import os
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
    "KGGraphMismatch",
    "Transport",
    "HttpTransport",
    "SearchPage",
    "PublicationDetail",
    "Assertion",
    "GraphSlice",
    "GraphNode",
    "GraphEdge",
    "Health",
    "KGClient",
    "resolve_base_url",
    "resolve_expected_graph_id",
    "DEFAULT_BASE_URL",
    "ENV_BASE_URL",
    "ENV_EXPECTED_GRAPH_ID",
    "SEARCH_FIELDS",
    "GRAPH_MODES",
]

#: Loopback default — local development only. Deployments set ``KG_BASE_URL``.
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
ENV_BASE_URL = "KG_BASE_URL"
ENV_EXPECTED_GRAPH_ID = "KG_EXPECTED_GRAPH_ID"

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

#: Fields the search endpoint documents in ``meta.expandedTerms``.
_EXPANSION_FIELDS = ("q", "venue", "method", "task", "dataset")


def resolve_base_url(explicit: str | None = None) -> str:
    """Resolve the service address: argument > ``KG_BASE_URL`` > loopback default."""
    candidate = explicit or os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL
    return str(candidate).strip().rstrip("/")


def resolve_expected_graph_id(explicit: str | None = None) -> str | None:
    """Resolve the pinned graph version, if one is configured."""
    candidate = explicit or os.environ.get(ENV_EXPECTED_GRAPH_ID) or ""
    value = str(candidate).strip()
    return value or None


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


class KGGraphMismatch(KGError):
    """A response came from a graph version other than the pinned one."""


# ---------------------------------------------------------------------------
# transport seam (injectable so tests run with no server)
# ---------------------------------------------------------------------------
class Transport(Protocol):
    """Minimal HTTP GET seam. Returns ``(status_code, raw_body_bytes)``."""

    def get(self, path: str, params: Mapping[str, str]) -> "tuple[int, bytes]":  # pragma: no cover
        ...


class HttpTransport:
    """``urllib``-based transport for the KG service."""

    def __init__(self, base_url: str | None = None, *, timeout: float = 10.0) -> None:
        self.base_url = resolve_base_url(base_url)
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
class Assertion:
    """One candidate assertion as the service actually returns it.

    ``/api/publication`` returns each assertion as three objects — the
    assertion itself plus its head and tail mentions (``course_graph.py`` L494:
    ``RETURN properties(a) AS assertion, properties(h) AS head, properties(t)
    AS tail``). Modelling the wrapper keeps callers from reading
    ``item["status"]`` when the status actually lives at
    ``item["assertion"]["status"]``.

    The assertion's own ``status`` is ``candidate`` in this graph; it is never
    promoted to a fact (see ``docs/01_source_audit.md`` §1.3).
    """

    assertion: dict[str, Any]
    head: dict[str, Any]
    tail: dict[str, Any]

    @property
    def predicate(self) -> str:
        """``USED_FOR`` (METHOD→TASK) or ``EVALUATED_ON`` (METHOD→DATASET)."""
        return str(self.assertion.get("predicate", ""))

    @property
    def status(self) -> str:
        return str(self.assertion.get("status", ""))

    @property
    def is_candidate(self) -> bool:
        return self.status == "candidate"

    @property
    def evidence(self) -> str:
        """The title-level evidence string the model attributed the edge to."""
        return str(self.assertion.get("evidence", ""))


@dataclass(frozen=True)
class PublicationDetail:
    """``/api/publication?id=...`` — bibliography plus candidate assertions."""

    publication: dict[str, Any]
    authors: tuple[dict[str, Any], ...]
    venues: tuple[dict[str, Any], ...]
    mentions: tuple[dict[str, Any], ...]
    assertions: tuple[Assertion, ...]
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
        base_url: str | None = None,
        *,
        transport: Transport | None = None,
        timeout: float = 10.0,
        expected_graph_id: str | None = None,
    ) -> None:
        self.base_url = resolve_base_url(base_url)
        self.expected_graph_id = resolve_expected_graph_id(expected_graph_id)
        self._transport: Transport = transport or HttpTransport(self.base_url, timeout=timeout)

    # -- public read surface -------------------------------------------------
    def health(self) -> Health:
        payload = self._get("/api/health", {})
        data = self._object(payload, "/api/health")

        status = self._required_str(data, "status", "/api/health")
        graph_id = self._required_str(data, "graphId", "/api/health")
        source = self._required_str(data, "source", "/api/health")
        scope_raw = data.get("scope")
        if not isinstance(scope_raw, Mapping) or not scope_raw:
            raise KGError("/api/health: 'scope' must be a non-empty object")
        scope: dict[str, int] = {}
        for key, value in scope_raw.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise KGError(f"/api/health: scope[{key!r}] must be a non-negative integer")
            scope[str(key)] = value

        self._check_graph_id(graph_id, "/api/health")
        terminology = data.get("terminology")
        alias_version = (
            terminology.get("version")
            if isinstance(terminology, Mapping)
            else None
        )
        resolution = data.get("resolution")
        if resolution is not None and not isinstance(resolution, Mapping):
            raise KGError("/api/health: 'resolution' must be an object or null")
        return Health(
            status=status,
            graph_id=graph_id,
            source=source,
            scope=scope,
            resolution=dict(resolution) if isinstance(resolution, Mapping) else None,
            alias_version=str(alias_version) if alias_version else None,
        )

    def assert_graph_version(self, expected: str | None = None) -> Health:
        """Fail fast unless the live graph is the pinned one.

        Use at service start-up (and in the integration test) so a stale or
        half-imported graph cannot quietly back a citation.
        """
        pinned = resolve_expected_graph_id(expected) or self.expected_graph_id
        report = self.health()
        if report.status != "ready":
            raise KGUnavailable(f"graph status is {report.status!r}, expected 'ready'")
        if pinned and report.graph_id != pinned:
            raise KGGraphMismatch(
                f"graph version mismatch: service reports {report.graph_id!r}, pinned {pinned!r}"
            )
        return report

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
        publications = self._items(payload, "/api/publications")

        meta = payload.get("meta")
        if meta is None:
            meta = {}
        if not isinstance(meta, Mapping):
            raise KGError("/api/publications: 'meta' must be an object")
        expanded = self._expanded_terms(meta.get("expandedTerms"))

        for index, publication in enumerate(publications):
            self._check_graph_id(
                publication.get("graphId"), f"/api/publications[data][{index}]"
            )

        try:
            offset_value = int(meta.get("offset", offset))
            limit_value = int(meta.get("limit", limit))
        except (TypeError, ValueError):
            raise KGError("/api/publications: meta.offset/meta.limit must be integers") from None
        return SearchPage(
            publications=publications,
            offset=offset_value,
            limit=limit_value,
            has_next=bool(meta.get("hasNext", False)),
            source=str(meta.get("source", "")),
            alias_version=str(meta["aliasVersion"]) if meta.get("aliasVersion") else None,
            expanded_terms=expanded,
        )

    def publication(self, publication_id: str) -> PublicationDetail:
        pid = self._publication_id(publication_id)
        payload = self._get("/api/publication", {"id": pid})
        data = self._object(payload, "/api/publication")
        publication = data.get("publication")
        if not isinstance(publication, Mapping):
            raise KGError("/api/publication: 'data.publication' must be an object")
        publication = dict(publication)
        self._check_graph_id(publication.get("graphId"), "/api/publication")

        return PublicationDetail(
            publication=publication,
            authors=self._object_list(data, "authors", "/api/publication"),
            venues=self._object_list(data, "venues", "/api/publication"),
            mentions=self._object_list(data, "mentions", "/api/publication"),
            assertions=self._assertion_list(data, "/api/publication"),
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
        data = self._object(payload, "/api/graph")
        nodes = self._graph_nodes(data, "/api/graph")
        edges = self._graph_edges(data, "/api/graph")

        meta = payload.get("meta")
        if meta is None:
            meta = {}
        if not isinstance(meta, Mapping):
            raise KGError("/api/graph: 'meta' must be an object")
        graph_id = str(meta.get("graphId", ""))
        self._check_graph_id(graph_id or None, "/api/graph")
        if not graph_id:
            raise KGError("/api/graph: meta.graphId is required (unversioned graph slice)")

        paths = data.get("paths")
        if paths is None:
            paths = []
        if not isinstance(paths, list):
            raise KGError("/api/graph: 'data.paths' must be an array")
        for index, path in enumerate(paths):
            if not isinstance(path, Mapping):
                raise KGError(f"/api/graph: data.paths[{index}] must be an object")

        root_id = str(data.get("rootId", "") or pid)
        for node in nodes:
            if node.id == root_id:
                break
        else:
            raise KGError(f"/api/graph: rootId {root_id!r} is absent from the returned nodes")

        return GraphSlice(
            nodes=nodes,
            edges=edges,
            paths=tuple(dict(path) for path in paths),
            root_id=root_id,
            mode=str(meta.get("mode", mode)),
            graph_id=graph_id,
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

    # -- graph version guard -------------------------------------------------
    def _check_graph_id(self, graph_id: Any, where: str) -> None:
        """Compare a response-carried ``graphId`` with the pinned version.

        Only fires when the field is actually present *and* a version is pinned,
        so it can never invent a mismatch out of a missing field.
        """
        if not self.expected_graph_id or not isinstance(graph_id, str) or not graph_id:
            return
        if graph_id != self.expected_graph_id:
            raise KGGraphMismatch(
                f"{where}: graphId {graph_id!r} != pinned {self.expected_graph_id!r}"
            )

    # -- transport + status mapping -----------------------------------------
    def _get(self, path: str, params: Mapping[str, str]) -> dict[str, Any]:
        status, body = self._transport.get(path, params)
        if status == 200:
            return self._decode(body, path)
        message = self._error_message(body) or f"HTTP {status}"
        if status == _STATUS_UNAVAILABLE:
            raise KGUnavailable(f"{path}: {message}")
        if status == _STATUS_INVALID:
            raise KGInvalidRequest(f"{path}: {message}")
        if status == _STATUS_NOT_FOUND:
            raise KGNotFound(f"{path}: {message}")
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

    # -- strict payload accessors -------------------------------------------
    @staticmethod
    def _object(payload: Mapping[str, Any], path: str) -> dict[str, Any]:
        """Require ``data`` to be a JSON object."""
        data = payload.get("data")
        if not isinstance(data, Mapping):
            got = type(data).__name__
            raise KGError(f"{path}: expected 'data' to be an object, got {got}")
        return dict(data)

    @staticmethod
    def _items(payload: Mapping[str, Any], path: str) -> tuple[dict[str, Any], ...]:
        """Require ``data`` to be an array of JSON objects.

        This is the check that stops ``{"meta": {}}`` (no ``data`` at all) from
        being read as "zero papers found".
        """
        data = payload.get("data")
        if not isinstance(data, list):
            got = "missing" if data is None else type(data).__name__
            raise KGError(f"{path}: expected 'data' to be an array, got {got}")
        items: list[dict[str, Any]] = []
        for index, item in enumerate(data):
            if not isinstance(item, Mapping):
                raise KGError(
                    f"{path}: data[{index}] must be an object, got {type(item).__name__}"
                )
            items.append(dict(item))
        return tuple(items)

    @classmethod
    def _object_list(
        cls, data: Mapping[str, Any], key: str, path: str
    ) -> tuple[dict[str, Any], ...]:
        value = data.get(key)
        if value is None:
            return ()
        if not isinstance(value, list):
            raise KGError(f"{path}: '{key}' must be an array")
        return cls._items({"data": value}, f"{path}.{key}")

    @classmethod
    def _assertion_list(
        cls, data: Mapping[str, Any], path: str
    ) -> tuple[Assertion, ...]:
        """Parse ``data.assertions`` — each item is a {assertion,head,tail} wrapper."""
        raw = data.get("assertions")
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise KGError(f"{path}: 'assertions' must be an array")
        assertions: list[Assertion] = []
        for index, item in enumerate(raw):
            where = f"{path}.assertions[{index}]"
            if not isinstance(item, Mapping):
                raise KGError(f"{where} must be an object")
            parts: dict[str, dict[str, Any]] = {}
            for key in ("assertion", "head", "tail"):
                value = item.get(key)
                if not isinstance(value, Mapping):
                    raise KGError(f"{where}.{key} must be an object")
                parts[key] = dict(value)
            assertions.append(Assertion(**parts))  # type: ignore[arg-type]
        return tuple(assertions)

    @staticmethod
    def _expanded_terms(raw: Any) -> dict[str, tuple[str, ...]]:
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise KGError("/api/publications: meta.expandedTerms must be an object")
        expanded: dict[str, tuple[str, ...]] = {}
        for field, values in raw.items():
            if field not in _EXPANSION_FIELDS:
                raise KGError(f"/api/publications: unknown expandedTerms field {field!r}")
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise KGError(
                    f"/api/publications: expandedTerms[{field!r}] must be an array of strings"
                )
            expanded[str(field)] = tuple(values)
        return expanded

    @staticmethod
    def _required_str(data: Mapping[str, Any], key: str, path: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise KGError(f"{path}: '{key}' must be a non-empty string")
        return value

    @classmethod
    def _graph_nodes(cls, data: Mapping[str, Any], path: str) -> tuple[GraphNode, ...]:
        raw = data.get("nodes")
        if not isinstance(raw, list):
            raise KGError(f"{path}: 'data.nodes' must be an array")
        nodes: list[GraphNode] = []
        for index, node in enumerate(raw):
            if not isinstance(node, Mapping):
                raise KGError(f"{path}: data.nodes[{index}] must be an object")
            props = node.get("props")
            if not isinstance(props, Mapping) or not isinstance(props.get("id"), str):
                raise KGError(f"{path}: data.nodes[{index}].props.id must be a string")
            nodes.append(
                GraphNode(id=props["id"], kind=str(node.get("kind", "")), props=dict(props))
            )
        return tuple(nodes)

    @classmethod
    def _graph_edges(cls, data: Mapping[str, Any], path: str) -> tuple[GraphEdge, ...]:
        raw = data.get("edges")
        if not isinstance(raw, list):
            raise KGError(f"{path}: 'data.edges' must be an array")
        edges: list[GraphEdge] = []
        for index, edge in enumerate(raw):
            if not isinstance(edge, Mapping):
                raise KGError(f"{path}: data.edges[{index}] must be an object")
            for field in ("id", "kind", "source", "target"):
                if not isinstance(edge.get(field), str) or not edge[field]:
                    raise KGError(f"{path}: data.edges[{index}].{field} must be a non-empty string")
            edges.append(
                GraphEdge(
                    id=edge["id"],
                    kind=edge["kind"],
                    source=edge["source"],
                    target=edge["target"],
                )
            )
        return tuple(edges)


def read_methods() -> Sequence[str]:
    """Audit helper: the only verbs this client is allowed to expose."""
    return tuple(
        name
        for name, value in vars(KGClient).items()
        if callable(value) and not name.startswith("_")
    )

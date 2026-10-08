"""Offline tests for the read-only KG adapter.

No Neo4j and no HTTP server are needed: :class:`FakeTransport` injects canned
``(status, body)`` pairs, so the error mapping and parameter building are
verified deterministically.

Run:  python -m unittest discover -s integrations/knowledge-graph -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kg_client import (  # noqa: E402
    GRAPH_MODES,
    KGClient,
    KGError,
    KGInvalidRequest,
    KGNotFound,
    KGUnavailable,
    HttpTransport,
    read_methods,
)


def _body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _error(message: str, code: str = "x") -> bytes:
    return _body({"error": {"code": code, "message": message}})


class FakeTransport:
    """Queued transport: pops one response per call and records the request."""

    def __init__(self, *responses: tuple[int, bytes]) -> None:
        self._queue = list(responses)
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, params):  # noqa: ANN001
        self.calls.append((path, dict(params)))
        if not self._queue:
            raise AssertionError(f"unexpected extra request: {path} {dict(params)}")
        return self._queue.pop(0)


class ErrorMappingTests(unittest.TestCase):
    def test_503_raises_unavailable_and_never_returns_empty(self) -> None:
        transport = FakeTransport(
            (503, _error("Neo4j连接、认证或课程图谱未就绪；未使用离线替代数据。", "neo4j_unavailable"))
        )
        client = KGClient(transport=transport)
        with self.assertRaises(KGUnavailable) as ctx:
            client.search(q="diffusion model")
        self.assertIn("未使用离线替代数据", str(ctx.exception))
        self.assertEqual(len(transport.calls), 1)

    def test_400_maps_to_invalid_request(self) -> None:
        transport = FakeTransport((400, _error("查询参数无效", "invalid_request")))
        with self.assertRaises(KGInvalidRequest):
            KGClient(transport=transport).publication("p1")

    def test_404_maps_to_not_found(self) -> None:
        transport = FakeTransport((404, _error("文献不存在", "not_found")))
        with self.assertRaises(KGNotFound):
            KGClient(transport=transport).publication("missing")

    def test_unexpected_status_maps_to_base_error(self) -> None:
        transport = FakeTransport((500, _body({"error": {"code": "internal_error", "message": "Request failed"}})))
        with self.assertRaises(KGError) as ctx:
            KGClient(transport=transport).health()
        self.assertNotIsInstance(ctx.exception, KGUnavailable)
        self.assertIn("500", str(ctx.exception))

    def test_non_json_body_maps_to_base_error(self) -> None:
        transport = FakeTransport((200, b"<html>not json</html>"))
        with self.assertRaises(KGError) as ctx:
            KGClient(transport=transport).health()
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_missing_data_object_maps_to_base_error(self) -> None:
        transport = FakeTransport((200, _body({"meta": {}})))
        with self.assertRaises(KGError) as ctx:
            KGClient(transport=transport).health()
        self.assertIn("data", str(ctx.exception))


class SearchTests(unittest.TestCase):
    def _page(self) -> bytes:
        return _body(
            {
                "data": [{"id": "pub-1", "title": "A", "year": 2023}],
                "meta": {
                    "offset": 20,
                    "limit": 10,
                    "hasNext": True,
                    "source": "live_neo4j",
                    "aliasVersion": "zh_alias_v1",
                    "expandedTerms": {"method": ["diffusion model", "diffusion models"]},
                },
            }
        )

    def test_search_parses_page_and_echoes_expansion(self) -> None:
        transport = FakeTransport((200, self._page()))
        page = KGClient(transport=transport).search(
            q="图像生成", method="扩散模型", year=2023, limit=10, offset=20
        )
        self.assertEqual(page.publications[0]["id"], "pub-1")
        self.assertEqual(page.alias_version, "zh_alias_v1")
        self.assertEqual(page.expanded_terms["method"], ("diffusion model", "diffusion models"))
        self.assertTrue(page.has_next)
        path, params = transport.calls[0]
        self.assertEqual(path, "/api/publications")
        self.assertEqual(params["method"], "扩散模型")
        self.assertEqual(params["year"], "2023")
        self.assertEqual(params["limit"], "10")
        self.assertEqual(params["offset"], "20")

    def test_search_omits_empty_terms_and_absent_year(self) -> None:
        transport = FakeTransport((200, _body({"data": [], "meta": {}})))
        KGClient(transport=transport).search(q="  transformer  ")
        _, params = transport.calls[0]
        self.assertEqual(params, {"q": "transformer", "limit": "20", "offset": "0"})
        self.assertNotIn("year", params)

    def test_local_validation_runs_before_any_request(self) -> None:
        cases = [
            {"limit": 0},
            {"limit": 101},
            {"offset": 20001},
            {"offset": -1},
            {"year": 2014},
            {"year": 2026},
            {"year": "twenty"},
            {"q": "x" * 201},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                transport = FakeTransport()  # no responses queued: a request would abort
                with self.assertRaises(KGInvalidRequest):
                    KGClient(transport=transport).search(**kwargs)
                self.assertEqual(transport.calls, [])


class DetailAndGraphTests(unittest.TestCase):
    def test_publication_parses_detail(self) -> None:
        payload = {
            "data": {
                "publication": {"id": "p1", "title": "T", "year": 2020},
                "authors": [{"name": "A", "position": 1, "identityStatus": "dblp_homepage_resolved"}],
                "venues": [{"name": "NeurIPS", "type": "conference"}],
                "mentions": [{"name": "BERT", "entityType": "METHOD"}],
                "assertions": [{"predicate": "USED_FOR", "status": "candidate"}],
                "citationDraft": "A. T NeurIPS, 2020. DOI: 缺失",
                "notice": "候选参考文献；引用前阅读原文并核验书目信息。",
            }
        }
        transport = FakeTransport((200, _body(payload)))
        detail = KGClient(transport=transport).publication("p1")
        self.assertEqual(detail.publication["id"], "p1")
        self.assertEqual(detail.assertions[0]["status"], "candidate")
        self.assertIn("候选参考文献", detail.notice)

    def test_graph_parses_nodes_edges_and_bounds(self) -> None:
        payload = {
            "data": {
                "nodes": [
                    {"kind": "Publication", "props": {"id": "p1", "graphId": "g31", "title": "T"}},
                    {"kind": "Person", "props": {"id": "a1", "graphId": "g31", "name": "A"}},
                ],
                "edges": [{"id": "e1", "kind": "AUTHORED", "source": "a1", "target": "p1"}],
                "paths": [{"nodes": ["p1", "a1"], "edges": ["e1"]}],
                "rootId": "p1",
            },
            "meta": {"graphId": "g31", "mode": "paper", "hasMorePaths": False, "notice": "局部有界路径"},
        }
        transport = FakeTransport((200, _body(payload)))
        slice_ = KGClient(transport=transport).graph("p1", mode="coauthors", limit=50)
        self.assertEqual([n.id for n in slice_.nodes], ["p1", "a1"])
        self.assertEqual(slice_.edges[0].kind, "AUTHORED")
        self.assertEqual(slice_.graph_id, "g31")
        _, params = transport.calls[0]
        self.assertEqual(params, {"id": "p1", "mode": "coauthors", "limit": "50"})

    def test_graph_rejects_bad_mode_and_limit_locally(self) -> None:
        for kwargs in ({"mode": "everything"}, {"mode": "paper", "limit": 51}, {"mode": "paper", "limit": 0}):
            with self.subTest(kwargs=kwargs):
                transport = FakeTransport()
                with self.assertRaises(KGInvalidRequest):
                    KGClient(transport=transport).graph("p1", **kwargs)
                self.assertEqual(transport.calls, [])
        self.assertEqual(GRAPH_MODES, frozenset({"paper", "coauthors", "methods"}))

    def test_publication_id_validation(self) -> None:
        transport = FakeTransport()
        with self.assertRaises(KGInvalidRequest):
            KGClient(transport=transport).publication("   ")
        with self.assertRaises(KGInvalidRequest):
            KGClient(transport=transport).publication("x" * 301)
        self.assertEqual(transport.calls, [])


class HealthTests(unittest.TestCase):
    def test_health_parses_scope_and_alias_version(self) -> None:
        payload = {
            "data": {
                "status": "ready",
                "graphId": "course_v4_31",
                "source": "live_neo4j",
                "scope": {
                    "bibliographyTitles": 20000,
                    "modelTitles": 19000,
                    "rejectedNERTitles": 3,
                    "candidateAssertions": 21497,
                },
                "resolution": {"version": 31},
                "terminology": {"version": "zh_alias_v1", "aliases": []},
            }
        }
        health = KGClient(transport=FakeTransport((200, _body(payload)))).health()
        self.assertEqual(health.status, "ready")
        self.assertEqual(health.scope["candidateAssertions"], 21497)
        self.assertEqual(health.alias_version, "zh_alias_v1")


class ReadOnlySurfaceTests(unittest.TestCase):
    def test_client_exposes_only_read_verbs(self) -> None:
        self.assertEqual(set(read_methods()), {"health", "search", "publication", "graph"})
        forbidden = ("create", "delete", "write", "update", "merge", "import", "set_", "drop")
        for name in dir(KGClient):
            self.assertFalse(
                name.lower().startswith(forbidden),
                f"write-looking attribute on the read-only client: {name}",
            )


class HttpTransportTests(unittest.TestCase):
    def test_connection_error_maps_to_unavailable(self) -> None:
        transport = HttpTransport("http://127.0.0.1:1", timeout=0.01)
        original = urllib.request.urlopen

        def boom(*_args, **_kwargs):
            raise urllib.error.URLError("connection refused")

        urllib.request.urlopen = boom  # type: ignore[assignment]
        try:
            with self.assertRaises(KGUnavailable):
                transport.get("/api/health", {})
        finally:
            urllib.request.urlopen = original  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Offline tests for the read-only KG adapter.

No Neo4j and no HTTP server are needed: :class:`FakeTransport` injects canned
``(status, body)`` pairs, so status mapping, payload-shape validation and
parameter building are all verified deterministically.

Run:  python -m unittest discover -s integrations/knowledge-graph -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kg_client import (  # noqa: E402
    DEFAULT_BASE_URL,
    ENV_BASE_URL,
    ENV_EXPECTED_GRAPH_ID,
    GRAPH_MODES,
    KGClient,
    KGError,
    KGGraphMismatch,
    KGInvalidRequest,
    KGNotFound,
    KGUnavailable,
    HttpTransport,
    read_methods,
    resolve_base_url,
    resolve_expected_graph_id,
)


def _body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _error(message: str, code: str = "x") -> bytes:
    return _body({"error": {"code": code, "message": message}})


def _health_data(graph_id: str = "g31") -> dict:
    return {
        "data": {
            "status": "ready",
            "graphId": graph_id,
            "source": "live_neo4j",
            "scope": {
                "bibliographyTitles": 20000,
                "modelTitles": 19999,
                "rejectedNERTitles": 1,
                "candidateAssertions": 21497,
            },
            "resolution": {"version": 31},
            "terminology": {"version": "zh_alias_v1", "aliases": []},
        }
    }


def _search_data(items: list, *, meta: dict | None = None) -> dict:
    return {"data": items, "meta": meta if meta is not None else {}}


def _graph_data(graph_id: str = "g31", root: str = "p1") -> dict:
    return {
        "data": {
            "nodes": [
                {"kind": "Publication", "props": {"id": root, "graphId": graph_id, "title": "T"}},
                {"kind": "Person", "props": {"id": "a1", "graphId": graph_id, "name": "A"}},
            ],
            "edges": [{"id": "e1", "kind": "AUTHORED", "source": "a1", "target": root}],
            "paths": [{"nodes": [root, "a1"], "edges": ["e1"]}],
            "rootId": root,
        },
        "meta": {
            "graphId": graph_id,
            "mode": "paper",
            "hasMorePaths": False,
            "notice": "局部有界路径",
        },
    }


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
        with self.assertRaises(KGUnavailable) as ctx:
            KGClient(transport=transport).search(q="diffusion model")
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
        payload = {"error": {"code": "internal_error", "message": "Request failed"}}
        transport = FakeTransport((500, _body(payload)))
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


class StrictPayloadTests(unittest.TestCase):
    """A 200 whose body is malformed must fail, never read as "no results"."""

    def test_search_without_data_key_raises(self) -> None:
        transport = FakeTransport((200, _body({"meta": {}})))
        with self.assertRaises(KGError) as ctx:
            KGClient(transport=transport).search(q="anything")
        self.assertIn("expected 'data' to be an array", str(ctx.exception))

    def test_search_with_object_data_raises(self) -> None:
        transport = FakeTransport((200, _body({"data": {"publicationId": "x"}})))
        with self.assertRaises(KGError) as ctx:
            KGClient(transport=transport).search(q="anything")
        self.assertIn("expected 'data' to be an array", str(ctx.exception))

    def test_search_with_non_object_items_raises(self) -> None:
        transport = FakeTransport((200, _body({"data": ["p1", "p2"]})))
        with self.assertRaises(KGError) as ctx:
            KGClient(transport=transport).search(q="anything")
        self.assertIn("data[0] must be an object", str(ctx.exception))

    def test_search_with_non_object_meta_raises(self) -> None:
        transport = FakeTransport((200, _body({"data": [], "meta": []})))
        with self.assertRaises(KGError) as ctx:
            KGClient(transport=transport).search(q="anything")
        self.assertIn("'meta' must be an object", str(ctx.exception))

    def test_search_with_bad_expanded_terms_raises(self) -> None:
        cases = [
            {"method": "diffusion model"},
            {"unknownField": ["x"]},
            {"method": [1, 2]},
        ]
        for bad in cases:
            with self.subTest(expandedTerms=bad):
                transport = FakeTransport(
                    (200, _body(_search_data([], meta={"expandedTerms": bad})))
                )
                with self.assertRaises(KGError):
                    KGClient(transport=transport).search(q="x")

    def test_search_accepts_empty_result_list(self) -> None:
        """An explicit empty array is a legitimate empty result."""
        transport = FakeTransport((200, _body(_search_data([]))))
        page = KGClient(transport=transport).search(q="nothing-matches")
        self.assertEqual(page.publications, ())

    def test_health_requires_core_fields(self) -> None:
        for missing in ("status", "graphId", "source"):
            with self.subTest(missing=missing):
                data = _health_data()
                del data["data"][missing]
                transport = FakeTransport((200, _body(data)))
                with self.assertRaises(KGError) as ctx:
                    KGClient(transport=transport).health()
                self.assertIn(missing, str(ctx.exception))

    def test_health_rejects_empty_or_non_integer_scope(self) -> None:
        bad_scopes = (
            {},
            {"bibliographyTitles": "many"},
            {"bibliographyTitles": -1},
            {"bibliographyTitles": True},
        )
        for scope in bad_scopes:
            with self.subTest(scope=scope):
                data = _health_data()
                data["data"]["scope"] = scope
                with self.assertRaises(KGError):
                    KGClient(transport=FakeTransport((200, _body(data)))).health()

    def test_publication_requires_publication_object(self) -> None:
        transport = FakeTransport((200, _body({"data": {"authors": []}})))
        with self.assertRaises(KGError) as ctx:
            KGClient(transport=transport).publication("p1")
        self.assertIn("publication", str(ctx.exception))

    def test_publication_rejects_non_array_authors(self) -> None:
        payload = {"data": {"publication": {"id": "p1"}, "authors": {}}}
        with self.assertRaises(KGError) as ctx:
            KGClient(transport=FakeTransport((200, _body(payload)))).publication("p1")
        self.assertIn("authors", str(ctx.exception))

    def test_graph_requires_graph_id_and_present_root(self) -> None:
        missing_meta = _graph_data()
        del missing_meta["meta"]["graphId"]
        with self.assertRaises(KGError) as ctx:
            KGClient(transport=FakeTransport((200, _body(missing_meta)))).graph("p1")
        self.assertIn("graphId", str(ctx.exception))

        bad_root = _graph_data()
        bad_root["data"]["rootId"] = "absent-node"
        with self.assertRaises(KGError) as ctx:
            KGClient(transport=FakeTransport((200, _body(bad_root)))).graph("p1")
        self.assertIn("absent-node", str(ctx.exception))

    def test_graph_rejects_malformed_edges(self) -> None:
        payload = _graph_data()
        del payload["data"]["edges"][0]["target"]
        with self.assertRaises(KGError) as ctx:
            KGClient(transport=FakeTransport((200, _body(payload)))).graph("p1")
        self.assertIn("target", str(ctx.exception))


class GraphVersionPinningTests(unittest.TestCase):
    def test_health_mismatch_raises(self) -> None:
        transport = FakeTransport((200, _body(_health_data("g30"))))
        client = KGClient(transport=transport, expected_graph_id="g31")
        with self.assertRaises(KGGraphMismatch) as ctx:
            client.health()
        self.assertIn("g30", str(ctx.exception))

    def test_search_item_mismatch_raises(self) -> None:
        items = [{"publicationId": "p1", "graphId": "g30"}]
        with self.assertRaises(KGGraphMismatch):
            KGClient(transport=FakeTransport((200, _body(_search_data(items)))), expected_graph_id="g31").search(q="x")

    def test_graph_slice_mismatch_raises(self) -> None:
        transport = FakeTransport((200, _body(_graph_data("g30"))))
        client = KGClient(transport=transport, expected_graph_id="g31")
        with self.assertRaises(KGGraphMismatch):
            client.graph("p1")

    def test_absent_graph_id_is_not_a_mismatch(self) -> None:
        """No false positives: a payload that omits graphId must not be flagged."""
        items = [{"publicationId": "p1", "title": "T"}]
        page = KGClient(
            transport=FakeTransport((200, _body(_search_data(items)))), expected_graph_id="g31"
        ).search(q="x")
        self.assertEqual(page.publications[0]["publicationId"], "p1")

    def test_no_pin_means_no_check(self) -> None:
        transport = FakeTransport((200, _body(_health_data("whatever"))))
        report = KGClient(transport=transport).health()
        self.assertEqual(report.graph_id, "whatever")

    def test_assert_graph_version_rejects_non_ready_status(self) -> None:
        data = _health_data()
        data["data"]["status"] = "importing"
        with self.assertRaises(KGUnavailable):
            KGClient(transport=FakeTransport((200, _body(data)))).assert_graph_version()

    def test_assert_graph_version_passes_when_pinned_version_matches(self) -> None:
        client = KGClient(
            transport=FakeTransport((200, _body(_health_data("g31")))), expected_graph_id="g31"
        )
        report = client.assert_graph_version()
        self.assertEqual(report.status, "ready")
        self.assertEqual(report.graph_id, "g31")


class SearchTests(unittest.TestCase):
    def _page(self) -> bytes:
        return _body(
            _search_data(
                [{"id": "pub-1", "title": "A", "year": 2023, "graphId": "g31"}],
                meta={
                    "offset": 20,
                    "limit": 10,
                    "hasNext": True,
                    "source": "live_neo4j",
                    "aliasVersion": "zh_alias_v1",
                    "expandedTerms": {"method": ["diffusion model", "diffusion models"]},
                },
            )
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
        transport = FakeTransport((200, _body(_search_data([]))))
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
                "publication": {"id": "p1", "publicationId": "p1", "title": "T", "year": 2020},
                "authors": [{"name": "A", "position": 1, "identityStatus": "dblp_homepage_resolved"}],
                "venues": [{"name": "NeurIPS", "type": "conference"}],
                "mentions": [{"name": "BERT", "label": "METHOD"}],
                "assertions": [
                    {
                        "assertion": {"predicate": "USED_FOR", "status": "candidate"},
                        "head": {"text": "BERT", "label": "METHOD"},
                        "tail": {"text": "classification", "label": "TASK"},
                    }
                ],
                "citationDraft": "A. T NeurIPS, 2020. DOI: 缺失",
                "notice": "候选参考文献；引用前阅读原文并核验书目信息。",
            }
        }
        transport = FakeTransport((200, _body(payload)))
        detail = KGClient(transport=transport).publication("p1")
        self.assertEqual(detail.publication["id"], "p1")
        self.assertIn("候选参考文献", detail.notice)
        assertion = detail.assertions[0]
        self.assertTrue(assertion.is_candidate)
        self.assertEqual(assertion.predicate, "USED_FOR")
        self.assertEqual(assertion.head["text"], "BERT")

    def test_publication_requires_the_assertion_wrapper_shape(self) -> None:
        for broken in ({"assertion": {"status": "candidate"}}, {"assertion": {}, "head": {}}, "nope"):
            with self.subTest(broken=broken):
                payload = {"data": {"publication": {"id": "p1"}, "assertions": [broken]}}
                with self.assertRaises(KGError) as ctx:
                    KGClient(transport=FakeTransport((200, _body(payload)))).publication("p1")
                self.assertIn("assertions[0]", str(ctx.exception))

    def test_publication_defaults_empty_collections(self) -> None:
        payload = {"data": {"publication": {"id": "p1"}}}
        detail = KGClient(transport=FakeTransport((200, _body(payload)))).publication("p1")
        self.assertEqual(detail.authors, ())
        self.assertEqual(detail.assertions, ())

    def test_graph_parses_nodes_edges_and_bounds(self) -> None:
        transport = FakeTransport((200, _body(_graph_data())))
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
        health = KGClient(transport=FakeTransport((200, _body(_health_data())))).health()
        self.assertEqual(health.status, "ready")
        self.assertEqual(health.graph_id, "g31")
        self.assertEqual(health.scope["candidateAssertions"], 21497)
        self.assertEqual(health.alias_version, "zh_alias_v1")


class ConfigurationTests(unittest.TestCase):
    def test_base_url_precedence_argument_over_env_over_default(self) -> None:
        with mock.patch.dict(os.environ, {ENV_BASE_URL: "http://kg-service:8765"}):
            self.assertEqual(resolve_base_url("http://explicit:9999/"), "http://explicit:9999")
            self.assertEqual(resolve_base_url(), "http://kg-service:8765")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_BASE_URL, None)
            self.assertEqual(resolve_base_url(), DEFAULT_BASE_URL)

    def test_client_and_transport_read_env_base_url(self) -> None:
        with mock.patch.dict(os.environ, {ENV_BASE_URL: "http://kg-service:8765"}):
            self.assertEqual(KGClient(transport=FakeTransport()).base_url, "http://kg-service:8765")
            self.assertEqual(HttpTransport().base_url, "http://kg-service:8765")

    def test_expected_graph_id_from_env(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_EXPECTED_GRAPH_ID, None)
            self.assertIsNone(resolve_expected_graph_id())
        with mock.patch.dict(os.environ, {ENV_EXPECTED_GRAPH_ID: "g31"}):
            self.assertEqual(resolve_expected_graph_id(), "g31")
            self.assertEqual(KGClient(transport=FakeTransport()).expected_graph_id, "g31")


class ReadOnlySurfaceTests(unittest.TestCase):
    def test_client_exposes_only_read_verbs(self) -> None:
        self.assertEqual(
            set(read_methods()),
            {"health", "search", "publication", "graph", "assert_graph_version"},
        )
        forbidden = ("create", "delete", "write", "update", "merge", "import", "set_", "drop")
        for name in dir(KGClient):
            self.assertFalse(
                name.lower().startswith(forbidden),
                f"write-looking attribute on the read-only client: {name}",
            )


class _RaisingOpener:
    """Stand-in for the private urllib opener, to drive socket-level failures."""

    def __init__(self, error: BaseException) -> None:
        self._error = error

    def open(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
        raise self._error


class HttpTransportTests(unittest.TestCase):
    def _transport(self, error: BaseException) -> HttpTransport:
        return HttpTransport("http://kg.invalid:8765", timeout=1.0, opener=_RaisingOpener(error))

    def test_connection_error_maps_to_unavailable(self) -> None:
        with self.assertRaises(KGUnavailable):
            self._transport(urllib.error.URLError("connection refused")).get("/api/health", {})

    def test_bare_timeout_error_maps_to_unavailable(self) -> None:
        """A timeout while reading the response is NOT wrapped in URLError.

        Regression guard: catching only ``URLError`` let this escape as a raw
        TimeoutError, which the API layer would have turned into a 500 instead of
        a 503 — i.e. an outage disguised as a server bug.
        """
        with self.assertRaises(KGUnavailable) as ctx:
            self._transport(TimeoutError("timed out")).get("/api/health", {})
        self.assertIn("timed out", str(ctx.exception))

    def test_os_error_maps_to_unavailable(self) -> None:
        with self.assertRaises(KGUnavailable):
            self._transport(ConnectionResetError("connection reset")).get("/api/health", {})

    def test_malformed_http_response_maps_to_base_error(self) -> None:
        import http.client

        with self.assertRaises(KGError) as ctx:
            self._transport(http.client.BadStatusLine("garbage")).get("/api/health", {})
        self.assertNotIsInstance(ctx.exception, KGUnavailable)
        self.assertIn("malformed", str(ctx.exception))

    def test_real_local_service_is_reached_despite_a_broken_proxy_env(self) -> None:
        """End-to-end proof that a poisoned HTTP_PROXY cannot intercept the call.

        The control assertion matters: it proves the environment really is
        visible to ``urllib``, so the passing request below is evidence and not
        a test that would pass anyway.
        """
        import http.server
        import threading

        payload = _body(_health_data())

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - stdlib naming
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):  # noqa: ANN002
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            poisoned = {
                "HTTP_PROXY": "http://127.0.0.1:1",
                "http_proxy": "http://127.0.0.1:1",
                "HTTPS_PROXY": "http://127.0.0.1:1",
                "https_proxy": "http://127.0.0.1:1",
            }
            with mock.patch.dict(os.environ, poisoned):
                os.environ.pop("no_proxy", None)
                os.environ.pop("NO_PROXY", None)
                # Control: urllib does see the poisoned proxy in this environment.
                self.assertIn("http", urllib.request.getproxies())

                client = KGClient(f"http://127.0.0.1:{server.server_address[1]}", timeout=5.0)
                report = client.health()
            self.assertEqual(report.status, "ready")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""HTTP-level tests for the research API.

The real application, the real adapter, and the real Pydantic models are all
exercised — only the HTTP socket underneath the adapter is replaced. That keeps
the thing under test equal to the thing that ships (a fake *service* would not).

Run (needs fastapi + httpx, see requirements.txt):
    python -m unittest discover -s apps/api -t apps/api -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The API layer is the one part of this repository with third-party
# dependencies. When they are absent (bare interpreter, core-only CI job) the
# whole module skips instead of erroring — and CI asserts that the skip really
# happened, so "green because nothing ran" cannot pass silently.
_IMPORT_ERROR: str | None = None
try:
    from fastapi.testclient import TestClient

    from noesis_research_api import create_app
    from noesis_research_api.app import Settings
    from noesis_research_api.models import as_link_list, as_optional_str
except Exception as exc:  # pragma: no cover - exercised by the core CI job
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

if _IMPORT_ERROR is not None:
    # A module-level SkipTest makes unittest report this file as a *skipped*
    # test rather than a broken import, so the core CI job (no install) stays
    # green while still echoing why nothing ran.
    raise unittest.SkipTest(
        f"fastapi/httpx not installed ({_IMPORT_ERROR}); "
        "install with: pip install -r apps/api/requirements.txt"
    )

PINNED_GRAPH = "ai-literature-ed16399925fac2a599ed"
PUBLICATION_ID = "conf/aaai/0002LCWHL25"


def body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def error_body(message: str, code: str) -> bytes:
    return body({"error": {"code": code, "message": message}})


class FakeTransport:
    """Answers by path. Records every call so the tests can assert on the query."""

    def __init__(self, routes: dict[str, list[tuple[int, bytes]]]) -> None:
        self._routes = {path: list(responses) for path, responses in routes.items()}
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, params):  # noqa: ANN001
        self.calls.append((path, dict(params)))
        queue = self._routes.get(path)
        if not queue:
            raise AssertionError(f"no stubbed response for {path} {dict(params)}")
        return queue.pop(0) if len(queue) > 1 else queue[0]


def health_payload(graph_id: str = PINNED_GRAPH) -> bytes:
    return body(
        {
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
                "terminology": {"version": "zh_alias_v1"},
            }
        }
    )


def publication_record(publication_id: str = PUBLICATION_ID, graph_id: str = PINNED_GRAPH) -> dict:
    return {
        "id": f"{graph_id}:Publication:4725bc95",
        "publicationId": publication_id,
        "graphId": graph_id,
        "title": "Infer the Whole from a Glimpse of a Part",
        "year": 2025,
        "type": "inproceedings",
        "doi": "10.1609/aaai.v39i1.1",
        "dblpUrl": "https://dblp.org/rec/conf/aaai/0002LCWHL25",
        "urls": ["https://doi.org/10.1609/aaai.v39i1.1"],
        "source": "dblp",
        "modelApplied": True,
        "modelApplicationStatus": "applied",
    }


def search_payload(items: list[dict], *, meta: dict | None = None) -> bytes:
    return body(
        {
            "data": items,
            "meta": meta
            if meta is not None
            else {
                "offset": 0,
                "limit": 20,
                "hasNext": False,
                "source": "live_neo4j",
                "aliasVersion": "zh_alias_v1",
            },
        }
    )


def detail_payload(publication_id: str = PUBLICATION_ID) -> bytes:
    return body(
        {
            "data": {
                "publication": publication_record(publication_id),
                "authors": [
                    {
                        "name": "Alice",
                        "signatureName": "Alice A.",
                        "position": 1,
                        "identityStatus": "dblp_homepage_resolved",
                        "personId": "p-1",
                        "dblpPid": "pid-1",
                        "dblpUrl": "https://dblp.org/pid/1",
                    }
                ],
                "venues": [{"name": "AAAI", "type": "conference"}],
                "mentions": [
                    {
                        "text": "vehicle re-identification",
                        "label": "TASK",
                        "start": 10,
                        "end": 36,
                        "status": "candidate",
                        "offsetUnit": "unicode_codepoint",
                    }
                ],
                "assertions": [
                    {
                        "assertion": {
                            "id": f"{PINNED_GRAPH}:Assertion:780c1091",
                            "pairId": "pair-a8c5",
                            "predicate": "USED_FOR",
                            "status": "candidate",
                            "confidence": 0.9990502,
                            "confidenceCalibrated": False,
                            "source": "model_prediction",
                            "evidence": "Infer the Whole from a Glimpse of a Part.",
                            "graphId": PINNED_GRAPH,
                        },
                        "head": {"text": "keypoint-based", "label": "METHOD"},
                        "tail": {"text": "vehicle re-identification", "label": "TASK"},
                    }
                ],
                "citationDraft": "Alice. Infer the Whole… AAAI, 2025. DOI: 10.1609/aaai.v39i1.1",
                "notice": "候选参考文献；引用前阅读原文并核验书目信息。",
            }
        }
    )


def graph_payload(publication_id: str = PUBLICATION_ID, graph_id: str = PINNED_GRAPH) -> bytes:
    root = f"{graph_id}:Publication:4725bc95"
    return body(
        {
            "data": {
                "nodes": [
                    {"kind": "Publication", "props": {"id": root, "publicationId": publication_id, "graphId": graph_id}},
                    {"kind": "Person", "props": {"id": f"{graph_id}:Person:abc", "graphId": graph_id, "name": "Alice"}},
                ],
                "edges": [{"id": "e1", "kind": "AUTHORED", "source": f"{graph_id}:Person:abc", "target": root}],
                "paths": [{"nodes": [root, f"{graph_id}:Person:abc"], "edges": ["e1"]}],
                "rootId": root,
            },
            "meta": {
                "graphId": graph_id,
                "mode": "paper",
                "hasMorePaths": False,
                "notice": "局部有界路径；同方法仅表示模型提及，不是引用或已验证语义相似。",
            },
        }
    )


def build_client(routes: dict[str, list[tuple[int, bytes]]], *, pinned: str | None = PINNED_GRAPH):
    from kg_client import KGClient

    transport = FakeTransport(routes)
    client = KGClient("http://stub", transport=transport, expected_graph_id=pinned)
    app = create_app(
        settings=Settings(base_url="http://stub", expected_graph_id=pinned, timeout=5.0),
        kg_client=client,
    )
    return TestClient(app), transport


class HealthTests(unittest.TestCase):
    def test_health_reports_pinned_version(self) -> None:
        client, _ = build_client({"/api/health": [(200, health_payload())]})
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["graphId"], PINNED_GRAPH)
        self.assertEqual(payload["pinnedGraphId"], PINNED_GRAPH)
        self.assertEqual(payload["scope"]["candidateAssertions"], 21497)

    def test_health_503_when_graph_unavailable(self) -> None:
        client, _ = build_client(
            {"/api/health": [(503, error_body("Neo4j连接、认证或课程图谱未就绪；未使用离线替代数据。", "neo4j_unavailable"))]}
        )
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "kg_unavailable")

    def test_health_503_on_graph_version_mismatch(self) -> None:
        client, _ = build_client({"/api/health": [(200, health_payload("some-other-graph"))]})
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "kg_graph_version_mismatch")


class SearchRouteTests(unittest.TestCase):
    def test_search_returns_papers_with_evidence(self) -> None:
        client, transport = build_client({"/api/publications": [(200, search_payload([publication_record()]))]})
        response = client.get("/api/papers/search", params={"q": "knowledge graph", "limit": 5})
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(len(payload["data"]), 1)
        paper = payload["data"][0]
        self.assertEqual(paper["publicationId"], PUBLICATION_ID)
        self.assertEqual(paper["evidence"]["sourceType"], "kg_bibliography")
        self.assertEqual(paper["evidence"]["sourceId"], PUBLICATION_ID)
        self.assertEqual(paper["evidence"]["evidenceLevel"], "title")
        self.assertEqual(paper["evidence"]["verificationStatus"], "unverified")
        self.assertEqual(paper["evidence"]["graphId"], PINNED_GRAPH)

        meta = payload["meta"]
        self.assertEqual(meta["applied"], {"q": "knowledge graph", "limit": "5", "offset": "0"})
        self.assertEqual(meta["source"], "live_neo4j")
        self.assertEqual(meta["aliasVersion"], "zh_alias_v1")

        _, params = transport.calls[0]
        self.assertEqual(params["q"], "knowledge graph")
        self.assertEqual(params["limit"], "5")

    def test_search_echoes_alias_expansion(self) -> None:
        meta = {"expandedTerms": {"method": ["diffusion model", "diffusion models"]}}
        client, _ = build_client({"/api/publications": [(200, search_payload([], meta=meta))]})
        response = client.get("/api/papers/search", params={"method": "扩散模型"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["meta"]["expandedTerms"]["method"],
            ["diffusion model", "diffusion models"],
        )

    def test_malformed_200_is_502_never_an_empty_success(self) -> None:
        """The P0-1 defect, checked at the HTTP boundary."""
        client, _ = build_client({"/api/publications": [(200, body({"meta": {}}))]})
        response = client.get("/api/papers/search", params={"q": "anything"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "kg_bad_response")
        self.assertNotIn("data", response.json())

    def test_503_is_not_swallowed_into_an_empty_page(self) -> None:
        client, _ = build_client(
            {"/api/publications": [(503, error_body("未使用离线替代数据。", "neo4j_unavailable"))]}
        )
        response = client.get("/api/papers/search", params={"q": "anything"})
        self.assertEqual(response.status_code, 503)

    def test_out_of_range_limit_is_rejected_before_any_upstream_call(self) -> None:
        client, transport = build_client({"/api/publications": [(200, search_payload([]))]})
        response = client.get("/api/papers/search", params={"limit": 101})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")
        self.assertEqual(transport.calls, [])

    def test_empty_result_is_a_legitimate_200(self) -> None:
        client, _ = build_client({"/api/publications": [(200, search_payload([]))]})
        response = client.get("/api/papers/search", params={"q": "zzzz-nothing"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], [])


class DetailRouteTests(unittest.TestCase):
    def test_slashed_publication_id_routes_correctly(self) -> None:
        client, transport = build_client({"/api/publication": [(200, detail_payload())]})
        response = client.get(f"/api/papers/{PUBLICATION_ID}")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["publication"]["publicationId"], PUBLICATION_ID)
        self.assertEqual(payload["authors"][0]["name"], "Alice")
        self.assertEqual(payload["venues"][0]["name"], "AAAI")
        self.assertIn("候选参考文献", payload["notice"])
        _, params = transport.calls[0]
        self.assertEqual(params["id"], PUBLICATION_ID)

    def test_candidate_assertion_is_labelled_and_carries_evidence(self) -> None:
        client, _ = build_client({"/api/publication": [(200, detail_payload())]})
        assertion = client.get(f"/api/papers/{PUBLICATION_ID}").json()["assertions"][0]
        self.assertEqual(assertion["predicate"], "USED_FOR")
        self.assertEqual(assertion["status"], "candidate")
        self.assertFalse(assertion["confidenceCalibrated"])
        self.assertEqual(assertion["head"]["text"], "keypoint-based")
        self.assertEqual(assertion["tail"]["label"], "TASK")
        self.assertEqual(assertion["evidence"]["sourceType"], "kg_assertion")
        self.assertEqual(assertion["evidence"]["assertionStatus"], "candidate")
        self.assertEqual(assertion["evidence"]["verificationStatus"], "unverified")
        self.assertEqual(assertion["evidence"]["publicationId"], PUBLICATION_ID)

    def test_unknown_publication_is_404(self) -> None:
        client, _ = build_client({"/api/publication": [(404, error_body("文献不存在", "not_found"))]})
        response = client.get("/api/papers/no-such-id")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_search_route_is_not_swallowed_by_the_path_route(self) -> None:
        client, transport = build_client({"/api/publications": [(200, search_payload([]))]})
        response = client.get("/api/papers/search", params={"q": "x"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([path for path, _ in transport.calls], ["/api/publications"])


class GraphRouteTests(unittest.TestCase):
    def test_graph_neighbors_returns_a_versioned_bounded_slice(self) -> None:
        client, transport = build_client({"/api/graph": [(200, graph_payload())]})
        response = client.get("/api/graph/neighbors", params={"id": PUBLICATION_ID, "limit": 10})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["graphId"], PINNED_GRAPH)
        self.assertEqual(payload["mode"], "paper")
        self.assertFalse(payload["hasMorePaths"])
        kinds = {node["kind"] for node in payload["nodes"]}
        self.assertEqual(kinds, {"Publication", "Person"})
        self.assertEqual(payload["edges"][0]["kind"], "AUTHORED")
        _, params = transport.calls[0]
        self.assertEqual(params["id"], PUBLICATION_ID)
        self.assertEqual(params["limit"], "10")

    def test_bad_mode_is_400_before_any_upstream_call(self) -> None:
        client, transport = build_client({"/api/graph": [(200, graph_payload())]})
        response = client.get("/api/graph/neighbors", params={"id": PUBLICATION_ID, "mode": "everything"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(transport.calls, [])


class SchemaTests(unittest.TestCase):
    def test_openapi_schema_builds_and_declares_the_three_business_routes(self) -> None:
        client, _ = build_client({"/api/health": [(200, health_payload())]})
        schema = client.get("/openapi.json").json()
        paths = set(schema["paths"])
        self.assertIn("/api/health", paths)
        self.assertIn("/api/papers/search", paths)
        self.assertIn("/api/graph/neighbors", paths)
        self.assertTrue(any(path.startswith("/api/papers/{publication_id") for path in paths))


class PureHelperTests(unittest.TestCase):
    def test_as_link_list_accepts_only_real_link_shapes(self) -> None:
        self.assertEqual(as_link_list(None), [])
        self.assertEqual(as_link_list(""), [])
        self.assertEqual(as_link_list("https://a"), ["https://a"])
        self.assertEqual(as_link_list(["https://a", "", None]), ["https://a"])
        self.assertEqual(as_link_list({"doi": "https://a", "other": ["https://b"]}), ["https://a", "https://b"])
        self.assertEqual(as_link_list(42), [])
        self.assertEqual(as_link_list({"nested": 42}), [])

    def test_as_optional_str_normalises_blank_to_none(self) -> None:
        self.assertIsNone(as_optional_str(None))
        self.assertIsNone(as_optional_str("   "))
        self.assertEqual(as_optional_str("x"), "x")
        self.assertEqual(as_optional_str(2025), "2025")


if __name__ == "__main__":
    unittest.main(verbosity=2)

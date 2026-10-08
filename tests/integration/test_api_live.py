"""Live HTTP-level checks: the whole stack, no fakes.

``TestClient`` drives the real FastAPI app, which drives the real adapter, which
talks to the real Neo4j-backed service. This is the check that proves the stage-1
loop end to end at the boundary the UI will actually call:

    GET /api/papers/search  →  real papers, each with a clickable evidence ref
    GET /api/papers/{id}    →  candidate assertions, still labelled candidate
    GET /api/graph/neighbors → a version-pinned local slice

Skipped when fastapi is not installed or the KG service is not reachable, so it
is safe in CI.

    KG_BASE_URL=http://127.0.0.1:8765 \
    KG_LOCK_FILE=D:/a-open_source/neo4j/resources/course_graph_runtime.json \
    python -m unittest discover -s tests/integration -t tests/integration -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(_REPO_ROOT / "integrations" / "knowledge-graph"))

BASE_URL = os.environ.get("KG_BASE_URL", "http://127.0.0.1:8765")
LOCK_FILE = os.environ.get("KG_LOCK_FILE", "")

try:
    from fastapi.testclient import TestClient

    from noesis_research_api import create_app
    from noesis_research_api.app import Settings

    from kg_client import KGClient, KGError, KGUnavailable
except Exception as exc:  # pragma: no cover - core CI job has no fastapi
    raise unittest.SkipTest(f"live API suite unavailable ({type(exc).__name__}: {exc})")


def _pinned_graph_id() -> str | None:
    explicit = os.environ.get("KG_EXPECTED_GRAPH_ID")
    if explicit:
        return explicit.strip()
    if LOCK_FILE and Path(LOCK_FILE).is_file():
        value = json.loads(Path(LOCK_FILE).read_text(encoding="utf-8")).get("graphId")
        return str(value).strip() if value else None
    return None


def _probe() -> tuple[bool, str]:
    try:
        report = KGClient(BASE_URL, timeout=5).health()
    except KGUnavailable as exc:
        return False, f"KG service unreachable at {BASE_URL}: {exc}"
    except KGError as exc:
        return False, f"KG service answered but is unusable: {exc}"
    return True, f"live graph {report.graph_id} ({report.status})"


PINNED = _pinned_graph_id()
_AVAILABLE, _PROBE_NOTE = _probe()


@unittest.skipUnless(_AVAILABLE, f"KG service not available — {_PROBE_NOTE}")
class LiveApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        settings = Settings(base_url=BASE_URL, expected_graph_id=PINNED, timeout=20.0)
        cls.app = create_app(settings=settings)
        cls.client = TestClient(cls.app)

    def _first_publication_id(self) -> str:
        response = self.client.get("/api/papers/search", params={"q": "learning", "limit": 10})
        self.assertEqual(response.status_code, 200, response.text)
        items = response.json()["data"]
        self.assertTrue(items, "expected at least one hit for 'learning'")
        return items[0]["publicationId"]

    # -- readiness ---------------------------------------------------------
    def test_health_is_ready_and_reports_the_pinned_graph(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["source"], "live_neo4j")
        self.assertEqual(payload["scope"]["candidateAssertions"], 21497)
        if PINNED:
            self.assertEqual(payload["graphId"], PINNED)
            self.assertEqual(payload["pinnedGraphId"], PINNED)

    # -- search ------------------------------------------------------------
    def test_search_returns_real_papers_each_with_clickable_evidence(self) -> None:
        response = self.client.get("/api/papers/search", params={"q": "transformer", "limit": 5})
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["data"])

        for paper in payload["data"]:
            with self.subTest(publication=paper["publicationId"]):
                self.assertTrue(paper["title"])
                evidence = paper["evidence"]
                self.assertEqual(evidence["sourceType"], "kg_bibliography")
                self.assertEqual(evidence["sourceId"], paper["publicationId"])
                self.assertEqual(evidence["evidenceLevel"], "title")
                self.assertEqual(evidence["verificationStatus"], "unverified")
                # The graph version must be the same across every result.
                if PINNED:
                    self.assertEqual(evidence["graphId"], PINNED)

        meta = payload["meta"]
        self.assertEqual(meta["applied"]["q"], "transformer")
        self.assertEqual(meta["applied"]["limit"], "5")
        self.assertEqual(meta["applied"]["offset"], "0")
        self.assertEqual(meta["source"], "live_neo4j")

    def test_chinese_alias_expansion_reaches_the_response(self) -> None:
        response = self.client.get("/api/papers/search", params={"method": "扩散模型", "limit": 3})
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("method", payload["meta"]["expandedTerms"])
        self.assertIn("diffusion model", payload["meta"]["expandedTerms"]["method"])
        self.assertTrue(payload["data"], "alias expansion should find diffusion-model papers")

    def test_a_real_miss_is_an_empty_200_not_an_error(self) -> None:
        response = self.client.get("/api/papers/search", params={"q": "zzzz-no-such-term-zzzz"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], [])

    # -- detail ------------------------------------------------------------
    def test_detail_exposes_candidate_relations_with_evidence(self) -> None:
        publication_id = self._first_publication_id()

        # Walk a few papers until one carries a candidate assertion.
        candidate = None
        for publication in self.client.get(
            "/api/papers/search", params={"q": "learning", "limit": 20}
        ).json()["data"]:
            response = self.client.get(f"/api/papers/{publication['publicationId']}")
            self.assertEqual(response.status_code, 200, response.text)
            if response.json()["assertions"]:
                candidate = response.json()
                break
        if candidate is None:
            self.skipTest("no candidate assertion found within the sampled page")

        assertion = candidate["assertions"][0]
        self.assertEqual(assertion["status"], "candidate")
        self.assertFalse(assertion["confidenceCalibrated"])
        self.assertEqual(assertion["evidence"]["sourceType"], "kg_assertion")
        self.assertEqual(assertion["evidence"]["assertionStatus"], "candidate")
        self.assertEqual(assertion["evidence"]["verificationStatus"], "unverified")
        self.assertTrue(assertion["evidence"]["sourceId"])
        self.assertTrue(candidate["citationDraft"])
        self.assertIn("候选参考文献", candidate["notice"])

    def test_slashed_dblp_key_round_trips_through_http(self) -> None:
        publication_id = self._first_publication_id()
        self.assertIn("/", publication_id, "DBLP keys contain slashes; this is the case that 404s if mishandled")
        response = self.client.get(f"/api/papers/{publication_id}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["publication"]["publicationId"], publication_id)

    def test_unknown_publication_is_404_over_http(self) -> None:
        response = self.client.get("/api/papers/no-such-publication-id-000")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    # -- local graph -------------------------------------------------------
    def test_graph_neighbors_returns_a_versioned_rooted_slice(self) -> None:
        publication_id = self._first_publication_id()
        for mode in ("paper", "coauthors", "methods"):
            with self.subTest(mode=mode):
                response = self.client.get(
                    "/api/graph/neighbors", params={"id": publication_id, "mode": mode, "limit": 10}
                )
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                if PINNED:
                    self.assertEqual(payload["graphId"], PINNED)
                node_ids = {node["id"] for node in payload["nodes"]}
                self.assertIn(payload["rootId"], node_ids)
                for edge in payload["edges"]:
                    self.assertIn(edge["source"], node_ids)
                    self.assertIn(edge["target"], node_ids)

    def test_bad_mode_is_400_over_http(self) -> None:
        publication_id = self._first_publication_id()
        response = self.client.get(
            "/api/graph/neighbors", params={"id": publication_id, "mode": "everything"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")


if __name__ == "__main__":
    print(f"probe: {_PROBE_NOTE}")
    print(f"pinned graph id: {PINNED}")
    unittest.main(verbosity=2)

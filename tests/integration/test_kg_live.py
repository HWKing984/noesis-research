"""Live end-to-end checks against a running AI-Literature-KG service.

These are the checks the offline suite deliberately cannot make: that the real
Neo4j-backed service answers, that the graph version the service reports is the
one the deployment pinned, and that a search hit can be walked to its detail
page, its local graph slice and a citable :class:`EvidenceRef`.

Skipped automatically when the service is not reachable, so CI stays green
without a database. Locally:

    KG_BASE_URL=http://127.0.0.1:8765 \
    KG_LOCK_FILE=D:/a-open_source/neo4j/resources/course_graph_runtime.json \
    python -m unittest discover -s tests/integration -t tests/integration -v

``KG_LOCK_FILE`` points at the knowledge graph repository's version lock
(``resources/course_graph_runtime.json``). It is optional; without it the test
still verifies that every response agrees on *one* graphId, it just cannot
compare against the recorded pin.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "integrations" / "knowledge-graph"))

from kg_client import (  # noqa: E402
    ENV_BASE_URL,
    KGClient,
    KGError,
    KGUnavailable,
)

from packages.contracts.evidence import EvidenceRef  # noqa: E402

BASE_URL = os.environ.get(ENV_BASE_URL, "http://127.0.0.1:8765")
LOCK_FILE = os.environ.get("KG_LOCK_FILE", "")


def _pinned_graph_id() -> str | None:
    """Version pin, from the env or from the KG repository's runtime lock."""
    explicit = os.environ.get("KG_EXPECTED_GRAPH_ID")
    if explicit:
        return explicit.strip()
    if LOCK_FILE and Path(LOCK_FILE).is_file():
        payload = json.loads(Path(LOCK_FILE).read_text(encoding="utf-8"))
        value = payload.get("graphId")
        return str(value).strip() if value else None
    return None


def _service_probe() -> tuple[bool, str]:
    try:
        report = KGClient(BASE_URL, timeout=5).health()
    except KGUnavailable as exc:
        return False, f"service unreachable at {BASE_URL}: {exc}"
    except KGError as exc:
        return False, f"service answered but is not usable at {BASE_URL}: {exc}"
    return True, f"live graph {report.graph_id} ({report.status})"


_AVAILABLE, _PROBE_NOTE = _service_probe()
_PINNED = _pinned_graph_id()


@unittest.skipUnless(_AVAILABLE, f"KG service not available — {_PROBE_NOTE}")
class LiveKnowledgeGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = KGClient(BASE_URL, expected_graph_id=_PINNED, timeout=20)
        cls.health = cls.client.health()

    # -- the service itself --------------------------------------------------
    def test_health_reports_a_ready_live_graph(self) -> None:
        self.assertEqual(self.health.status, "ready")
        self.assertEqual(self.health.source, "live_neo4j")
        self.assertTrue(self.health.graph_id)
        for key in ("bibliographyTitles", "modelTitles", "candidateAssertions"):
            with self.subTest(scope=key):
                self.assertGreater(self.health.scope[key], 0)

    def test_scope_counts_match_the_readme_numbers(self) -> None:
        """The graph is versioned; its scope must not have silently shrunk."""
        self.assertEqual(self.health.scope["bibliographyTitles"], 20000)
        self.assertEqual(self.health.scope["candidateAssertions"], 21497)

    @unittest.skipUnless(_PINNED, "no version pin configured (set KG_LOCK_FILE or KG_EXPECTED_GRAPH_ID)")
    def test_live_graph_matches_the_pinned_version(self) -> None:
        report = self.client.assert_graph_version()
        self.assertEqual(report.graph_id, _PINNED)

    # -- search ------------------------------------------------------------
    def test_search_returns_real_publications(self) -> None:
        page = self.client.search(q="transformer", limit=5)
        self.assertTrue(page.publications, "expected at least one hit for 'transformer'")
        self.assertLessEqual(len(page.publications), 5)
        self.assertEqual(page.source, "live_neo4j")
        for publication in page.publications:
            with self.subTest(publication=publication.get("publicationId")):
                self.assertTrue(publication.get("publicationId") or publication.get("id"))
                self.assertTrue(publication.get("title"))
                self.assertIsInstance(publication.get("year"), int)

    def test_search_results_agree_on_the_live_graph_id(self) -> None:
        page = self.client.search(q="learning", limit=10)
        present = [p["graphId"] for p in page.publications if p.get("graphId")]
        self.assertTrue(present, "search results should carry graphId (version guard input)")
        with self.subTest(graphIds=set(present)):
            self.assertEqual(set(present), {self.health.graph_id})

    def test_chinese_alias_expands_to_english_terms_end_to_end(self) -> None:
        page = self.client.search(method="扩散模型", limit=3)
        self.assertIn("method", page.expanded_terms)
        self.assertIn("diffusion model", page.expanded_terms["method"])
        self.assertTrue(page.publications, "alias expansion should find diffusion-model papers")

    def test_empty_query_result_is_an_explicit_empty_list(self) -> None:
        """A real miss returns an empty array — distinct from an outage (503)."""
        page = self.client.search(q="zzzz-no-such-term-zzzz", limit=3)
        self.assertEqual(page.publications, ())

    # -- detail + evidence walking -----------------------------------------
    def test_search_hit_walks_to_detail_and_citable_evidence(self) -> None:
        page = self.client.search(q="knowledge graph", limit=1)
        self.assertTrue(page.publications, "expected a hit to walk from")
        publication = page.publications[0]
        publication_id = publication.get("publicationId") or publication["id"]

        detail = self.client.publication(str(publication_id))
        self.assertTrue(detail.publication.get("title"))
        self.assertIn("候选参考文献", detail.notice)
        self.assertTrue(detail.citation_draft)

        ref = EvidenceRef.for_kg_publication(
            detail.publication, graph_id=self.health.graph_id
        )
        self.assertTrue(ref.is_citable)
        self.assertEqual(ref.evidence_level, "title")
        self.assertEqual(ref.verification_status, "unverified")
        self.assertEqual(ref.graph_id, self.health.graph_id)
        self.assertEqual(ref.to_dict()["sourceType"], "kg_bibliography")

    def test_candidate_assertions_are_labelled_and_never_promoted(self) -> None:
        page = self.client.search(q="learning", limit=20)
        detail = None
        for publication in page.publications:
            publication_id = publication.get("publicationId") or publication["id"]
            candidate = self.client.publication(str(publication_id))
            if candidate.assertions:
                detail = candidate
                break
        if detail is None:
            self.skipTest("no candidate assertion found within the sampled page")

        assertion = detail.assertions[0]
        self.assertTrue(assertion.is_candidate, f"status was {assertion.status!r}")
        self.assertIn(assertion.predicate, ("USED_FOR", "EVALUATED_ON"))
        self.assertTrue(assertion.evidence, "assertions carry a title-level evidence string")
        self.assertTrue(assertion.head.get("text"))
        self.assertTrue(assertion.tail.get("text"))

        publication_id = detail.publication.get("publicationId") or detail.publication["id"]
        ref = EvidenceRef.for_kg_assertion(
            assertion.assertion,
            publication_id=str(publication_id),
            graph_id=self.health.graph_id,
        )
        self.assertEqual(ref.source_type, "kg_assertion")
        self.assertEqual(ref.assertion_status, "candidate")
        # A candidate assertion is never citable as a verified fact.
        self.assertEqual(ref.verification_status, "unverified")

    # -- local graph slice -------------------------------------------------
    def test_graph_slice_is_versioned_rooted_and_bounded(self) -> None:
        page = self.client.search(q="neural network", limit=1)
        publication_id = str(
            page.publications[0].get("publicationId") or page.publications[0]["id"]
        )
        for mode in ("paper", "coauthors", "methods"):
            with self.subTest(mode=mode):
                slice_ = self.client.graph(publication_id, mode=mode, limit=10)
                self.assertEqual(slice_.graph_id, self.health.graph_id)
                self.assertEqual(slice_.mode, mode)
                self.assertTrue(slice_.nodes)
                # rootId is the node's internal composite id; the DBLP key lives
                # on props.publicationId.
                node_ids = [node.id for node in slice_.nodes]
                self.assertIn(slice_.root_id, node_ids)
                root = next(node for node in slice_.nodes if node.id == slice_.root_id)
                self.assertEqual(root.kind, "Publication")
                self.assertEqual(root.props.get("publicationId"), publication_id)
                # Every edge must join two nodes that were actually returned.
                known = set(node_ids)
                for edge in slice_.edges:
                    with self.subTest(edge=edge.id):
                        self.assertIn(edge.source, known)
                        self.assertIn(edge.target, known)
                self.assertLessEqual(len(slice_.paths), 10)
                for node in slice_.nodes:
                    self.assertEqual(node.props.get("graphId"), self.health.graph_id)

    def test_unknown_publication_id_is_a_404_not_an_empty_page(self) -> None:
        from kg_client import KGNotFound

        with self.assertRaises(KGNotFound):
            self.client.publication("no-such-publication-id-000")


if __name__ == "__main__":
    print(f"probe: {_PROBE_NOTE}")
    print(f"pinned graph id: {_PINNED}")
    unittest.main(verbosity=2)

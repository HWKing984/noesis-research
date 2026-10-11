"""Offline tests for the external metadata client.

No network: the transport is stubbed, so every branch — fallback order, DOI
identity check, "unreachable is not 'no abstract'", caching — is exercised
deterministically.

Run:
    services/research-agent/.venv/Scripts/python -m unittest discover \
        -s integrations/external-sources -t integrations/external-sources -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
# The shared evidence contract lives at the repo root (three levels up). The
# abstract-level ref must be validated against the *real* contract, not a copy.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))

from metadata_client import (  # noqa: E402
    ExternalMetadataClient,
    ExternalNoIdentifier,
    ExternalNotFound,
    ExternalRecord,
    ExternalRejected,
    ExternalUnavailable,
    FileCache,
    HttpTransport,
    _arxiv_from_url,
    _inverted_index_to_text,
    _strip_markup,
    normalize_arxiv,
    normalize_doi,
    resolve_cache_dir,
    resolve_sources,
    resolve_timeout,
)

DOI = "10.1109/cvpr.2016.90"
ARXIV = "1706.03762"
ABSTRACT = "We present a residual learning framework to ease the training of networks that are substantially deeper than those used previously."


def body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class FakeTransport:
    """Routes by URL substring. Values are ``(status, payload)`` or an exception."""

    def __init__(self, routes: list[tuple[str, object]]) -> None:
        self.routes = list(routes)
        self.calls: list[str] = []

    def get(self, url: str) -> tuple[int, bytes]:
        self.calls.append(url)
        for needle, response in self.routes:
            if needle in url:
                if isinstance(response, Exception):
                    raise response
                status, payload = response  # type: ignore[misc]
                return status, payload if isinstance(payload, bytes) else body(payload)
        raise AssertionError(f"unstubbed url: {url}")


def s2_ok(abstract: str = ABSTRACT, doi: str = DOI.upper()) -> dict:
    return {
        "paperId": "abc123",
        "title": "Deep Residual Learning for Image Recognition",
        "abstract": abstract,
        "year": 2016,
        "venue": "Computer Vision and Pattern Recognition",
        "externalIds": {"DOI": doi},
    }


def openalex_ok(doi: str = DOI, index: dict | None = None) -> dict:
    return {
        "id": "https://openalex.org/W2963403868",
        "doi": f"https://doi.org/{doi}",
        "title": "Deep Residual Learning for Image Recognition",
        "publication_year": 2016,
        "abstract_inverted_index": index if index is not None else {"Deep": [0], "residual": [1], "learning": [2]},
        "primary_location": {"source": {"display_name": "CVPR"}},
    }


def crossref_ok(doi: str = DOI, abstract: str | None = None) -> dict:
    return {
        "message": {
            "DOI": doi.upper(),
            "title": ["Deep Residual Learning for Image Recognition"],
            "abstract": abstract,
            "container-title": ["CVPR"],
            "issued": {"date-parts": [[2016]]},
            "URL": "https://doi.org/10.1109/cvpr.2016.90",
        }
    }


def client(routes: list[tuple[str, object]], sources=("semanticscholar", "openalex", "crossref"), cache=None):
    return ExternalMetadataClient(transport=FakeTransport(routes), sources=sources, cache=cache)


# ---------------------------------------------------------------------------
class IdentifierTests(unittest.TestCase):
    def test_normalize_doi_strips_prefix_and_lowercases(self) -> None:
        for raw in ("10.1109/CVPR.2016.90", "https://doi.org/10.1109/CVPR.2016.90", "doi:10.1109/CVPR.2016.90"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_doi(raw), DOI)
        self.assertEqual(normalize_doi("https://doi.org/10.1109/CVPR.2016.90"), DOI)

    def test_normalize_doi_rejects_non_dois(self) -> None:
        for raw in ("", None, "not-a-doi", " arXiv:1706.03762 ", "https://example.org/paper.pdf"):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_doi(raw))

    def test_normalize_arxiv(self) -> None:
        self.assertEqual(normalize_arxiv("1706.03762"), ARXIV)
        self.assertEqual(normalize_arxiv("arXiv:1706.03762v5"), ARXIV)
        self.assertIsNone(normalize_arxiv("not-an-id"))

    def test_arxiv_from_url_only_accepts_arxiv_hosts(self) -> None:
        self.assertEqual(_arxiv_from_url("https://arxiv.org/abs/1706.03762"), ARXIV)
        self.assertEqual(_arxiv_from_url("http://www.arxiv.org/pdf/1706.03762v2.pdf"), ARXIV)
        self.assertIsNone(_arxiv_from_url("https://evil.example/abs/1706.03762"))
        self.assertIsNone(_arxiv_from_url("https://doi.org/10.1109/cvpr.2016.90"))


class ParserTests(unittest.TestCase):
    def test_inverted_index_rebuilds_by_position(self) -> None:
        index = {"world": [1], "Hello": [0], "again": [2]}
        self.assertEqual(_inverted_index_to_text(index), "Hello world again")

    def test_inverted_index_empty_is_empty(self) -> None:
        self.assertEqual(_inverted_index_to_text(None), "")
        self.assertEqual(_inverted_index_to_text({}), "")

    def test_crossref_jats_markup_is_stripped(self) -> None:
        raw = "<jats:p>Deep   residual <jats:italic>learning</jats:italic></jats:p>"
        self.assertEqual(_strip_markup(raw), "Deep residual learning")


class TransportGuardTests(unittest.TestCase):
    def test_disallowed_host_is_rejected_without_touching_the_network(self) -> None:
        transport = HttpTransport(allowed_hosts=frozenset({"api.openalex.org"}))
        with self.assertRaises(ExternalRejected):
            transport.get("https://api.semanticscholar.org/graph/v1/paper/DOI:10.1/x")

    def test_opener_disables_the_ambient_proxy(self) -> None:
        """No proxy handler at all is installed, so the host's HTTP_PROXY is never consulted.

        ``ProxyHandler({})`` is an *empty map*: ``build_opener`` then installs no
        proxy handler, which is what makes the request direct. Passing ``None``
        (or omitting it) would install the environment-reading handler instead —
        on this machine that proxy answers 502 for public APIs.
        """
        transport = HttpTransport()
        handlers = [type(h).__name__ for h in transport._opener.handlers]
        self.assertNotIn("ProxyHandler", handlers)


class LookupTests(unittest.TestCase):
    def test_semanticscholar_hit_returns_abstract_record(self) -> None:
        records = client([("api.semanticscholar.org", (200, s2_ok()))]).lookup(doi=DOI)
        assert records is not None
        self.assertEqual(records.source, "semanticscholar")
        self.assertEqual(records.source_label, "Semantic Scholar")
        self.assertEqual(records.doi, DOI)
        self.assertEqual(records.abstract, ABSTRACT)
        self.assertEqual(records.year, 2016)
        self.assertEqual(records.venue, "Computer Vision and Pattern Recognition")
        self.assertEqual(records.evidence_level, "abstract")

    def test_evidence_ref_matches_the_shared_contract(self) -> None:
        record = client([("api.semanticscholar.org", (200, s2_ok()))]).lookup(doi=DOI)
        assert record is not None
        ref = record.evidence_ref(publication_id="conf/cvpr/HeZRS16")
        self.assertEqual(ref["sourceType"], "external_record")
        self.assertEqual(ref["sourceId"], f"doi:{DOI}")
        self.assertEqual(ref["evidenceLevel"], "abstract")
        self.assertEqual(ref["verificationStatus"], "id_valid")
        self.assertEqual(ref["publicationId"], "conf/cvpr/HeZRS16")
        self.assertTrue(ref["evidenceText"].strip())
        # The contract itself must accept it — this is the seam that matters.
        from packages.contracts.evidence import EvidenceRef  # noqa: PLC0415

        rebuilt = EvidenceRef.from_mapping(ref)
        self.assertEqual(rebuilt.evidence_level, "abstract")

    def test_falls_back_to_openalex_when_semanticscholar_has_no_abstract(self) -> None:
        routes = [
            ("api.semanticscholar.org", (200, s2_ok(abstract=""))),
            ("api.openalex.org", (200, openalex_ok())),
        ]
        record = client(routes).lookup(doi=DOI)
        assert record is not None
        self.assertEqual(record.source, "openalex")
        self.assertEqual(record.abstract, "Deep residual learning")
        self.assertEqual(record.venue, "CVPR")

    def test_source_order_is_respected(self) -> None:
        routes = [
            ("api.semanticscholar.org", (200, s2_ok())),
            ("api.openalex.org", (200, openalex_ok())),
        ]
        fake = FakeTransport(routes)
        record = ExternalMetadataClient(transport=fake, sources=("openalex", "semanticscholar")).lookup(doi=DOI)
        assert record is not None
        self.assertEqual(record.source, "openalex")
        self.assertTrue(fake.calls[0].startswith("https://api.openalex.org"))

    def test_crossref_jats_abstract_is_usable(self) -> None:
        routes = [("api.crossref.org", (200, crossref_ok(abstract=f"<jats:p>{ABSTRACT}</jats:p>")))]
        record = client(routes, sources=("crossref",)).lookup(doi=DOI)
        assert record is not None
        self.assertEqual(record.abstract, ABSTRACT)

    def test_arxiv_id_is_used_when_no_doi(self) -> None:
        fake = FakeTransport([("api.semanticscholar.org", (200, s2_ok(doi=DOI.upper())))])
        record = ExternalMetadataClient(transport=fake, sources=("semanticscholar",)).lookup(arxiv_id=ARXIV)
        assert record is not None
        self.assertIn("ARXIV:1706.03762", fake.calls[0])

    def test_lookup_requires_a_strong_identifier(self) -> None:
        with self.assertRaises(ExternalNoIdentifier):
            client([]).lookup(doi=None, arxiv_id=None)
        with self.assertRaises(ExternalNoIdentifier):
            client([]).lookup(doi="not-a-doi")

    def test_lookup_publication_prefers_doi_then_arxiv_url(self) -> None:
        c = client([("api.semanticscholar.org", (200, s2_ok()))])
        record = c.lookup_publication(doi=None, urls=["https://arxiv.org/abs/1706.03762"])
        assert record is not None
        self.assertEqual(record.source, "semanticscholar")
        with self.assertRaises(ExternalNoIdentifier):
            client([]).lookup_publication(doi=None, urls=["https://doi.org/10.1109/cvpr.2016.90"])


class IdentityDisciplineTests(unittest.TestCase):
    def test_a_different_doi_is_refused_not_attached(self) -> None:
        """A record for another paper must never be presented as this paper's abstract."""
        routes = [
            ("api.semanticscholar.org", (200, s2_ok(doi="10.9999/other.1"))),
            ("api.openalex.org", (200, openalex_ok(doi="10.9999/other.1"))),
        ]
        # Both sources answer, both are about someone else: never a silent match.
        with self.assertRaises(ExternalUnavailable):
            client(routes, sources=("semanticscholar", "openalex")).lookup(doi=DOI)

    def test_doi_mismatch_on_one_source_still_lets_another_answer(self) -> None:
        routes = [
            ("api.semanticscholar.org", (200, s2_ok(doi="10.9999/other.1"))),
            ("api.openalex.org", (200, openalex_ok())),
        ]
        record = client(routes).lookup(doi=DOI)
        assert record is not None
        self.assertEqual(record.source, "openalex")


class FailureSemanticsTests(unittest.TestCase):
    def test_record_exists_but_has_no_abstract_is_a_real_none(self) -> None:
        routes = [
            ("api.semanticscholar.org", (200, s2_ok(abstract=""))),
            ("api.openalex.org", (200, openalex_ok(index={}))),
            ("api.crossref.org", (200, crossref_ok(abstract=None))),
        ]
        self.assertIsNone(client(routes).lookup(doi=DOI))

    def test_all_sources_404_is_a_real_none(self) -> None:
        routes = [
            ("api.semanticscholar.org", (404, {"error": "not found"})),
            ("api.openalex.org", (404, {"error": "not found"})),
            ("api.crossref.org", (404, {"error": "not found"})),
        ]
        self.assertIsNone(client(routes).lookup(doi=DOI))

    def test_outage_is_not_reported_as_no_abstract(self) -> None:
        """The rule this repo lives by: 'could not look' must never read as 'nothing there'."""
        routes = [
            ("api.semanticscholar.org", ExternalUnavailable("boom")),
            ("api.openalex.org", ExternalUnavailable("boom")),
            ("api.crossref.org", ExternalUnavailable("boom")),
        ]
        with self.assertRaises(ExternalUnavailable):
            client(routes).lookup(doi=DOI)

    def test_one_source_down_means_no_verdict_even_if_another_saw_no_abstract(self) -> None:
        """A source that failed could have been the one holding the abstract.

        So "OpenAlex looked and found no abstract, Semantic Scholar is down" is
        **not** enough to conclude "no abstract" — this is the conservative half
        of the repo-wide rule.
        """
        routes = [
            ("api.semanticscholar.org", ExternalUnavailable("down")),
            ("api.openalex.org", (200, openalex_ok(index={}))),
        ]
        with self.assertRaises(ExternalUnavailable):
            client(routes, sources=("semanticscholar", "openalex")).lookup(doi=DOI)

    def test_one_source_down_and_the_rest_simply_absent_is_not_a_none(self) -> None:
        routes = [
            ("api.semanticscholar.org", ExternalUnavailable("down")),
            ("api.openalex.org", (404, {"error": "nope"})),
        ]
        with self.assertRaises(ExternalUnavailable):
            client(routes, sources=("semanticscholar", "openalex")).lookup(doi=DOI)

    def test_arxiv_only_lookup_skips_doi_only_sources_instead_of_calling_them_empty(self) -> None:
        """Regression (measured 2026-10-10): a throttled S2 was reported as 'no abstract'.

        OpenAlex and Crossref take a DOI only, so an arXiv lookup never asked
        them anything — and a source that was never asked must not be counted as
        "it had no abstract".
        """
        routes = [("api.semanticscholar.org", (404, {"error": "not found"}))]
        # S2 says absent, the other two are not applicable → a genuine "no abstract".
        self.assertIsNone(client(routes).lookup(arxiv_id=ARXIV))

        routes_down = [("api.semanticscholar.org", ExternalUnavailable("429 Too Many Requests"))]
        with self.assertRaises(ExternalUnavailable):
            client(routes_down).lookup(arxiv_id=ARXIV)

    def test_arxiv_record_without_a_doi_is_still_keyed_by_something_stable(self) -> None:
        payload = {
            "paperId": "x",
            "title": "Attention Is All You Need",
            "abstract": ABSTRACT,
            "year": 2017,
            "venue": "Neural Information Processing Systems",
            "externalIds": {"ArXiv": ARXIV},  # deliberately no DOI
        }
        record = client([("api.semanticscholar.org", (200, payload))], sources=("semanticscholar",)).lookup(
            arxiv_id=ARXIV
        )
        assert record is not None
        self.assertEqual(record.doi, f"10.48550/arxiv.{ARXIV}")
        self.assertEqual(record.evidence_ref()["sourceId"], f"doi:10.48550/arxiv.{ARXIV}")

    def test_throttling_maps_to_unavailable(self) -> None:
        with self.assertRaises(ExternalUnavailable):
            client([("api.semanticscholar.org", (429, {}))], sources=("semanticscholar",)).lookup(doi=DOI)

    def test_server_error_maps_to_unavailable(self) -> None:
        with self.assertRaises(ExternalUnavailable):
            client([("api.semanticscholar.org", (503, {}))], sources=("semanticscholar",)).lookup(doi=DOI)

    def test_non_json_body_is_not_trusted(self) -> None:
        routes = [("api.semanticscholar.org", (200, b"<html>maintenance</html>"))]
        with self.assertRaises(ExternalUnavailable):
            client(routes, sources=("semanticscholar",)).lookup(doi=DOI)

    def test_shape_mismatch_is_not_trusted(self) -> None:
        routes = [("api.semanticscholar.org", (200, {"paperId": "x"}))]  # no title
        with self.assertRaises(ExternalUnavailable):
            client(routes, sources=("semanticscholar",)).lookup(doi=DOI)

    def test_semanticscholar_error_body_means_this_source_does_not_have_it(self) -> None:
        """S2 answers 200 with an error body; that is 'absent here', not 'unreachable'."""
        routes = [("api.semanticscholar.org", (200, {"error": "paper not found"}))]
        self.assertIsNone(client(routes, sources=("semanticscholar",)).lookup(doi=DOI))

    def test_crossref_missing_message_is_not_trusted(self) -> None:
        routes = [("api.crossref.org", (200, {"status": "ok"}))]
        with self.assertRaises(ExternalUnavailable):
            client(routes, sources=("crossref",)).lookup(doi=DOI)


class CacheTests(unittest.TestCase):
    def test_a_hit_is_served_from_cache_without_calling_the_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = FileCache(tmp, ttl_seconds=3600)
            first = FakeTransport([("api.semanticscholar.org", (200, s2_ok()))])
            client_one = ExternalMetadataClient(transport=first, sources=("semanticscholar",), cache=cache)
            self.assertIsNotNone(client_one.lookup(doi=DOI))
            self.assertEqual(len(first.calls), 1)

            second = FakeTransport([])  # any call would AssertionError
            client_two = ExternalMetadataClient(transport=second, sources=("semanticscholar",), cache=cache)
            record = client_two.lookup(doi=DOI)
            assert record is not None
            self.assertEqual(record.abstract, ABSTRACT)
            self.assertEqual(second.calls, [])

    def test_expired_entries_are_a_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = FileCache(tmp, ttl_seconds=0)
            cache.put("doi:x", ExternalRecord(
                source="semanticscholar", doi="x", title="t", abstract="a",
            ).to_dict())
            self.assertIsNone(cache.get("doi:x"))

    def test_corrupt_cache_entry_is_a_miss_not_a_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = FileCache(tmp, ttl_seconds=3600)
            cache.root.mkdir(parents=True, exist_ok=True)
            cache._path("doi:x").write_text("{not json", encoding="utf-8")
            self.assertIsNone(cache.get("doi:x"))

    def test_failed_lookups_are_not_cached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = FileCache(tmp, ttl_seconds=3600)
            routes = [("api.semanticscholar.org", ExternalUnavailable("down"))]
            c = ExternalMetadataClient(
                transport=FakeTransport(routes), sources=("semanticscholar",), cache=cache
            )
            for _ in range(2):
                with self.assertRaises(ExternalUnavailable):
                    c.lookup(doi=DOI)
            self.assertEqual(list(cache.root.glob("*.json")), [])


class RecordContractTests(unittest.TestCase):
    def test_a_record_without_an_abstract_is_refused(self) -> None:
        with self.assertRaises(ExternalRejected):
            ExternalRecord(source="openalex", doi=DOI, title="t", abstract="   ")

    def test_unknown_source_is_refused(self) -> None:
        with self.assertRaises(ExternalRejected):
            ExternalRecord(source="scihub", doi=DOI, title="t", abstract="a")

    def test_abstract_for_model_caps_and_marks_truncation(self) -> None:
        record = ExternalRecord(source="openalex", doi=DOI, title="t", abstract="x " * 50)
        capped = record.abstract_for_model(limit=20)
        self.assertTrue(capped.endswith("…（摘要过长，已截断）"))
        self.assertLessEqual(len(capped), 20 + len(" …（摘要过长，已截断）"))

    def test_round_trips_through_mapping(self) -> None:
        record = ExternalRecord(
            source="openalex", doi=DOI, title="t", abstract="a", year=2016, venue="CVPR",
            source_url="https://openalex.org/W1", fetched_at="2026-10-10T00:00:00+00:00",
        )
        self.assertEqual(ExternalRecord.from_mapping(record.to_dict()), record)


class ConfigTests(unittest.TestCase):
    def test_cache_dir_precedence(self) -> None:
        self.assertEqual(resolve_cache_dir("/tmp/x"), Path("/tmp/x"))
        os.environ["EXTERNAL_CACHE_DIR"] = "/tmp/from-env"
        try:
            self.assertEqual(resolve_cache_dir(), Path("/tmp/from-env"))
        finally:
            os.environ.pop("EXTERNAL_CACHE_DIR", None)
        self.assertEqual(resolve_cache_dir(), Path(".data/external"))

    def test_timeout_falls_back_and_rejects_junk(self) -> None:
        os.environ["EXTERNAL_TIMEOUT"] = "not-a-number"
        try:
            self.assertEqual(resolve_timeout(), 12.0)
        finally:
            os.environ.pop("EXTERNAL_TIMEOUT", None)
        self.assertEqual(resolve_timeout(5), 5.0)

    def test_sources_drop_unknown_names_and_keep_order(self) -> None:
        self.assertEqual(resolve_sources(["openalex", "nope", "crossref"]), ("openalex", "crossref"))
        self.assertEqual(resolve_sources(None), ("semanticscholar", "openalex", "crossref"))

    def test_explicit_empty_sources_means_disabled_not_default(self) -> None:
        """Disabling must be expressible; otherwise the caller can only lie."""
        self.assertEqual(resolve_sources([]), ())
        os.environ["EXTERNAL_SOURCES"] = "nope,also-nope"
        try:
            self.assertEqual(resolve_sources(), ())
        finally:
            os.environ.pop("EXTERNAL_SOURCES", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)

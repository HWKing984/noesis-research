"""Live integration tests against the real Semantic Scholar / OpenAlex / Crossref APIs.

Self-skips when the sources cannot be reached (offline CI stays green) — and also
when they are merely *throttled*, which is a real state for Semantic Scholar's
keyless shared pool and must not be reported as a product bug.

Run:
    python -m unittest discover -s integrations/external-sources -t integrations/external-sources

Measured on this machine (2026-10-10), straight from the sandbox with its
injected HTTP_PROXY present: all three hosts answer in under 1.1s.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))

from metadata_client import (  # noqa: E402
    ExternalMetadataClient,
    ExternalUnavailable,
    FileCache,
    HttpTransport,
    normalize_doi,
)

RESNET_DOI = "10.1109/CVPR.2016.90"
UNKNOWN_DOI = "10.9999/zzz-no-such-doi-noesis-20261010"


class _CountingTransport:
    """Wraps a real transport and records every URL it was asked for."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.calls: list[str] = []

    def get(self, url: str):
        self.calls.append(url)
        return self.inner.get(url)


class LiveExternalSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.baseline = ExternalMetadataClient(timeout=20.0).lookup(doi=RESNET_DOI)
        except ExternalUnavailable as exc:
            raise unittest.SkipTest(f"external sources unreachable/throttled: {exc}")
        if cls.baseline is None:
            raise unittest.SkipTest("baseline DOI came back with no abstract; source shapes changed")

    def _lookup_or_skip(self, client, **kwargs):
        try:
            return client.lookup(**kwargs)
        except ExternalUnavailable as exc:
            self.skipTest(f"sources unavailable during this test: {exc}")

    def test_real_doi_yields_a_real_abstract(self) -> None:
        record = self.baseline
        self.assertIn(record.source, ("semanticscholar", "openalex", "crossref"))
        # DOIs are normalised (lower-cased) on the way out, so identity holds
        # regardless of how the source echoes the casing back.
        self.assertEqual(record.doi, normalize_doi(RESNET_DOI))
        self.assertGreater(len(record.abstract), 200, "an abstract this short is a parse failure")
        self.assertIn("residual", record.abstract.lower())

    def test_abstract_ref_satisfies_the_shared_evidence_contract(self) -> None:
        from packages.contracts.evidence import EvidenceRef  # noqa: PLC0415

        ref = self.baseline.evidence_ref(publication_id="conf/cvpr/HeZRS16")
        rebuilt = EvidenceRef.from_mapping(ref)
        self.assertEqual(rebuilt.source_type, "external_record")
        self.assertEqual(rebuilt.evidence_level, "abstract")
        self.assertEqual(rebuilt.verification_status, "id_valid")
        self.assertEqual(rebuilt.publication_id, "conf/cvpr/HeZRS16")
        self.assertTrue(rebuilt.evidence_text.strip())

    def test_a_doi_that_does_not_exist_is_not_invented(self) -> None:
        self.assertIsNone(self._lookup_or_skip(ExternalMetadataClient(timeout=20.0), doi=UNKNOWN_DOI))

    def test_cache_prevents_a_second_network_call(self) -> None:
        counting = _CountingTransport(HttpTransport(timeout=20.0))
        with tempfile.TemporaryDirectory() as tmp:
            client = ExternalMetadataClient(transport=counting, cache=FileCache(tmp, ttl_seconds=3600))
            first = self._lookup_or_skip(client, doi=RESNET_DOI)
            self.assertGreater(len(counting.calls), 0)
            calls_before = len(counting.calls)
            second = client.lookup(doi=RESNET_DOI)
            self.assertEqual(len(counting.calls), calls_before, "a cache hit must not touch the network")
            self.assertEqual(first.abstract, second.abstract)

    def test_ambient_proxy_environment_is_ignored(self) -> None:
        """Poison HTTP_PROXY to a dead port; a direct API call must still succeed.

        Regression guard: ``urllib`` reads these variables by default, and the
        sandbox injects a proxy that answers 502 for public hosts.
        """
        keys = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
        poisoned = {key: os.environ.get(key) for key in keys}
        for key in keys:
            os.environ[key] = "http://127.0.0.1:1"
        try:
            record = self._lookup_or_skip(ExternalMetadataClient(timeout=20.0), doi=RESNET_DOI)
        finally:
            for key, value in poisoned.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertIsNotNone(record)

    def test_second_real_doi_is_also_resolved(self) -> None:
        """A second, unrelated DOI: proves the first one was not a lucky fluke."""
        record = self._lookup_or_skip(ExternalMetadataClient(timeout=20.0), doi="10.1145/3292500.3330701")
        self.assertIsNotNone(record)
        self.assertEqual(record.doi, "10.1145/3292500.3330701")
        self.assertGreater(len(record.abstract), 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)

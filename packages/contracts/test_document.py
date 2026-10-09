"""Offline tests for the document availability contract.

Run (from the repository root):
    python -m unittest discover -s packages/contracts -t packages/contracts -v
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.contracts.document import (  # noqa: E402
    DOCUMENT_STATUSES,
    TRANSITIONS,
    DocumentError,
    DocumentRef,
    PassageLocator,
    QuoteNotFoundError,
    for_paper_passage,
    locate_quote,
)
from packages.contracts.evidence import EvidenceRef  # noqa: E402

_SHA = "a" * 64


def _available(**overrides) -> DocumentRef:
    values = dict(
        document_id="doc-1",
        status="available",
        publication_id="conf/nips/VaswaniSPUJGKP17",
        source_kind="arxiv",
        sha256=_SHA,
        size_bytes=2_214_004,
        detail="",
    )
    values.update(overrides)
    return DocumentRef(**values)


def _no_oa(**overrides) -> DocumentRef:
    values = dict(
        document_id="doc-2",
        status="no_oa_found",
        publication_id="conf/nips/VaswaniSPUJGKP17",
        detail="searched arXiv, OpenAlex best_oa_location, Semantic Scholar openAccessPdf: no OA copy",
    )
    values.update(overrides)
    return DocumentRef(**values)


def _failed(**overrides) -> DocumentRef:
    values = dict(
        document_id="doc-3",
        status="fetch_failed",
        publication_id="conf/nips/VaswaniSPUJGKP17",
        detail="download timeout after 3 attempts",
    )
    values.update(overrides)
    return DocumentRef(**values)


class StatusMachineTests(unittest.TestCase):
    def test_five_statuses_are_the_contract(self) -> None:
        self.assertEqual(
            DOCUMENT_STATUSES,
            ("available", "publisher_link_only", "no_oa_found", "fetch_failed", "restricted"),
        )

    def test_available_requires_hash_source_and_size(self) -> None:
        with self.assertRaises(DocumentError):
            DocumentRef(document_id="d", status="available", source_kind="arxiv", size_bytes=10)
        with self.assertRaises(DocumentError):
            _available(sha256="zz")  # not 64-hex
        with self.assertRaises(DocumentError):
            _available(source_kind=None)
        with self.assertRaises(DocumentError):
            _available(size_bytes=0)

    def test_non_available_must_not_look_hosted(self) -> None:
        with self.assertRaises(DocumentError):
            _no_oa(sha256=_SHA, size_bytes=100)
        with self.assertRaises(DocumentError):
            _failed(sha256=_SHA, size_bytes=100)

    def test_publisher_link_only_requires_landing_page(self) -> None:
        with self.assertRaises(DocumentError):
            DocumentRef(document_id="d", status="publisher_link_only", detail="")
        DocumentRef(
            document_id="d",
            status="publisher_link_only",
            source_url="https://doi.org/10.1016/j.datak.2023.100XXX",
            detail="no OA copy; landing page only",
        )

    def test_no_oa_found_must_not_carry_transport_failure_detail(self) -> None:
        with self.assertRaises(DocumentError):
            _no_oa(detail="download timeout after 3 attempts")
        # A genuine search-exhausted explanation is fine.
        _no_oa()

    def test_fetch_failed_requires_retryable_detail(self) -> None:
        with self.assertRaises(DocumentError):
            DocumentRef(document_id="d", status="fetch_failed")
        _failed()

    def test_wire_round_trip(self) -> None:
        raw = _available().to_dict()
        self.assertEqual(
            set(raw),
            {"documentId", "status", "detail", "publicationId", "sourceKind", "sha256", "sizeBytes"},
        )
        self.assertEqual(DocumentRef.from_mapping(raw), _available())


class TransitionTests(unittest.TestCase):
    def test_initial_fetch_may_land_on_any_state(self) -> None:
        for status in DOCUMENT_STATUSES:
            self.assertIn(status, TRANSITIONS["none"])

    def test_fetch_failed_may_retry_into_available(self) -> None:
        ref = _failed().transition(
            "available", source_kind="arxiv", sha256=_SHA, size_bytes=1024
        )
        self.assertEqual(ref.status, "available")
        self.assertTrue(ref.is_readable)
        self.assertFalse(ref.is_retryable)

    def test_fetch_failed_may_be_corrected_to_no_oa_found(self) -> None:
        ref = _failed().transition("no_oa_found", detail="re-searched: no OA copy exists")
        self.assertEqual(ref.status, "no_oa_found")

    def test_no_oa_found_can_never_become_fetch_failed(self) -> None:
        # "we searched and it is not there" must never decay into "we failed":
        # that flip is how a system hides investigation results behind retries.
        with self.assertRaises(DocumentError):
            _no_oa().transition("fetch_failed", detail="timeout")

    def test_available_is_terminal(self) -> None:
        with self.assertRaises(DocumentError):
            _available().transition("fetch_failed", detail="storage lost")
        with self.assertRaises(DocumentError):
            _available().transition("no_oa_found")

    def test_upload_recovers_publisher_and_restricted_states(self) -> None:
        publisher = DocumentRef(
            document_id="d1",
            status="publisher_link_only",
            source_url="https://example.com/paper",
            detail="",
        )
        self.assertEqual(
            publisher.transition("available", source_kind="upload", sha256=_SHA, size_bytes=5).status,
            "available",
        )
        restricted = DocumentRef(document_id="d2", status="restricted", detail="publisher blocks bots")
        self.assertEqual(
            restricted.transition("available", source_kind="upload", sha256=_SHA, size_bytes=5).status,
            "available",
        )

    def test_no_oa_found_to_restricted_is_not_a_thought(self) -> None:
        with self.assertRaises(DocumentError):
            _no_oa().transition("restricted")

    def test_transition_clears_stale_hash_on_non_available_target(self) -> None:
        failed = DocumentRef(document_id="d", status="fetch_failed", detail="t/o")
        moved = failed.transition("fetch_failed", detail="t/o again")
        self.assertIsNone(moved.sha256)
        self.assertIsNone(moved.size_bytes)


class PassageLocatorTests(unittest.TestCase):
    def test_camel_case_wire(self) -> None:
        loc = PassageLocator(page=4, start_offset=120, end_offset=260)
        self.assertEqual(loc.to_dict(), {"page": 4, "startOffset": 120, "endOffset": 260})

    def test_bounds_are_enforced(self) -> None:
        with self.assertRaises(DocumentError):
            PassageLocator(page=0, start_offset=0, end_offset=5)
        with self.assertRaises(DocumentError):
            PassageLocator(page=1, start_offset=5, end_offset=5)
        with self.assertRaises(DocumentError):
            PassageLocator(page=1, start_offset=-1, end_offset=5)


class LocateQuoteTests(unittest.TestCase):
    PAGE = (
        "3.2.1 Scaled Dot-Product Attention\n"
        "We call our particular attention Scaled Dot-Product Attention. The\n"
        "input consists of queries and keys of dimension dk. We compute the\n"
        "dot products of the query with all keys.\n"
    )

    def test_exact_match_returns_original_offsets(self) -> None:
        quote = "dot products of the query with all keys."
        loc = locate_quote(self.PAGE, quote)
        self.assertEqual(self.PAGE[loc.start_offset : loc.end_offset], quote)

    def test_line_broken_quote_is_fuzzy_matched_and_maps_back(self) -> None:
        # The PDF pipeline broke the sentence across lines; the quote from the
        # answer carries single spaces instead. Offsets must still point at the
        # original characters.
        quote = "particular attention Scaled Dot-Product Attention. The input consists"
        loc = locate_quote(self.PAGE, quote)
        self.assertGreaterEqual(loc.start_offset, 0)
        self.assertLess(loc.end_offset, len(self.PAGE) + 1)
        self.assertIn("particular attention", self.PAGE[loc.start_offset : loc.end_offset])

    def test_whitespace_runs_map_back_to_original_spans(self) -> None:
        page = "alpha    beta\ngamma"
        loc = locate_quote(page, "alpha beta gamma")
        self.assertEqual(page[loc.start_offset : loc.end_offset], "alpha    beta\ngamma")

    def test_missing_quote_raises_not_guesses(self) -> None:
        with self.assertRaises(QuoteNotFoundError):
            locate_quote(self.PAGE, "this sentence is nowhere in the page at all")

    def test_quote_longer_than_page_raises(self) -> None:
        with self.assertRaises(QuoteNotFoundError):
            locate_quote("short page", "x" * 500)

    def test_bounded_window_rejects_pathological_quote(self) -> None:
        with self.assertRaises(QuoteNotFoundError):
            locate_quote(self.PAGE * 50, "y" * 3000, max_fuzzy_window=2000)

    def test_empty_inputs_raise(self) -> None:
        with self.assertRaises(QuoteNotFoundError):
            locate_quote(self.PAGE, "   ")
        with self.assertRaises(QuoteNotFoundError):
            locate_quote("", "anything")


class ForPaperPassageTests(unittest.TestCase):
    def test_builds_fulltext_ref_starting_at_id_valid(self) -> None:
        doc = _available()
        loc = PassageLocator(page=4, start_offset=120, end_offset=260)
        ref = for_paper_passage(
            document=doc, chunk_id="chunk_001", locator=loc, quote="We scale the dot products."
        )
        self.assertIsInstance(ref, EvidenceRef)
        self.assertEqual(ref.source_type, "paper_passage")
        self.assertEqual(ref.evidence_level, "fulltext")
        self.assertEqual(ref.verification_status, "id_valid")
        self.assertEqual(ref.document_id, "doc-1")
        self.assertEqual(ref.publication_id, "conf/nips/VaswaniSPUJGKP17")
        self.assertEqual(ref.locator, {"page": 4, "startOffset": 120, "endOffset": 260})
        self.assertEqual(ref.evidence_text, "We scale the dot products.")

    def test_ref_can_climb_the_verification_ladder(self) -> None:
        doc = _available()
        loc = PassageLocator(page=4, start_offset=0, end_offset=10)
        ref = for_paper_passage(document=doc, chunk_id="c1", locator=loc, quote="0123456789")
        self.assertEqual(ref.advance("evidence_supports").verification_status, "evidence_supports")
        # semantic_verified requires abstract/fulltext depth — fulltext qualifies.
        self.assertEqual(ref.advance("semantic_verified").verification_status, "semantic_verified")

    def test_rejects_non_available_document(self) -> None:
        loc = PassageLocator(page=1, start_offset=0, end_offset=5)
        for doc in (_no_oa(), _failed()):
            with self.assertRaises(DocumentError):
                for_paper_passage(document=doc, chunk_id="c1", locator=loc, quote="hello")

    def test_rejects_empty_quote_and_chunk(self) -> None:
        doc = _available()
        loc = PassageLocator(page=1, start_offset=0, end_offset=5)
        with self.assertRaises(DocumentError):
            for_paper_passage(document=doc, chunk_id="c1", locator=loc, quote="   ")
        with self.assertRaises(DocumentError):
            for_paper_passage(document=doc, chunk_id="  ", locator=loc, quote="hello")

    def test_wire_payload_is_camel_case_and_complete(self) -> None:
        doc = _available()
        loc = PassageLocator(page=4, start_offset=0, end_offset=8)
        payload = for_paper_passage(document=doc, chunk_id="c1", locator=loc, quote="01234567").to_dict()
        self.assertEqual(payload["locator"], {"page": 4, "startOffset": 0, "endOffset": 8})
        self.assertEqual(payload["evidenceLevel"], "fulltext")
        self.assertEqual(payload["documentId"], "doc-1")


if __name__ == "__main__":
    unittest.main()

"""Offline tests for the unified evidence contract.

Run (from the repository root):
    python -m unittest discover -s packages/contracts -t packages/contracts -v
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.contracts.evidence import (  # noqa: E402
    ASSERTION_STATUSES,
    EVIDENCE_LEVELS,
    SOURCE_TYPES,
    VERIFICATION_STAGES,
    EvidenceError,
    EvidenceRef,
)


def _kg_bib(**overrides) -> EvidenceRef:
    values = dict(
        source_type="kg_bibliography",
        source_id="pub-1",
        publication_id="pub-1",
        graph_id="g31",
        evidence_level="title",
        evidence_text="Attention Is All You Need",
    )
    values.update(overrides)
    return EvidenceRef(**values)


class ConstructionTests(unittest.TestCase):
    def test_minimal_bibliography_ref_is_valid_and_citable(self) -> None:
        ref = _kg_bib()
        self.assertTrue(ref.is_citable)
        self.assertEqual(ref.verification_status, "unverified")
        self.assertEqual(ref.verification_rank, 0)

    def test_wire_format_uses_camel_case(self) -> None:
        payload = _kg_bib().to_dict()
        self.assertEqual(
            set(payload),
            {
                "sourceType",
                "sourceId",
                "evidenceLevel",
                "assertionStatus",
                "verificationStatus",
                "publicationId",
                "graphId",
                "evidenceText",
            },
        )
        self.assertEqual(payload["sourceType"], "kg_bibliography")
        self.assertEqual(payload["graphId"], "g31")
        # Absent optional fields must not be emitted as empty strings.
        self.assertNotIn("documentId", payload)
        self.assertNotIn("locator", payload)

    def test_enum_vocabularies_are_the_documented_ones(self) -> None:
        self.assertEqual(
            SOURCE_TYPES,
            ("kg_bibliography", "kg_assertion", "paper_passage", "external_record"),
        )
        self.assertEqual(EVIDENCE_LEVELS, ("title", "abstract", "fulltext"))
        self.assertEqual(ASSERTION_STATUSES, ("none", "candidate", "verified"))
        self.assertEqual(
            VERIFICATION_STAGES,
            ("unverified", "id_valid", "evidence_supports", "semantic_verified"),
        )

    def test_source_id_is_mandatory(self) -> None:
        for bad in ("", "   ", None):
            with self.subTest(source_id=bad):
                with self.assertRaises(EvidenceError) as ctx:
                    _kg_bib(source_id=bad)
                self.assertIn("sourceId", str(ctx.exception))

    def test_unknown_enum_values_are_rejected(self) -> None:
        cases = (
            {"source_type": "wikipedia"},
            {"evidence_level": "vibes"},
            {"verification_status": "trust me"},
            {"assertion_status": "probably"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(EvidenceError):
                    _kg_bib(**overrides)


class SourceTypeRuleTests(unittest.TestCase):
    def test_kg_sources_require_a_publication(self) -> None:
        for source_type in ("kg_bibliography", "kg_assertion"):
            with self.subTest(source_type=source_type):
                with self.assertRaises(EvidenceError) as ctx:
                    EvidenceRef(
                        source_type=source_type,
                        source_id="x-1",
                        evidence_level="title",
                        assertion_status="candidate",
                    )
                self.assertIn("publicationId", str(ctx.exception))

    def test_kg_assertion_must_declare_a_real_status(self) -> None:
        with self.assertRaises(EvidenceError) as ctx:
            EvidenceRef(
                source_type="kg_assertion",
                source_id="a-1",
                publication_id="p-1",
                evidence_level="title",
                assertion_status="none",
            )
        self.assertIn("assertionStatus", str(ctx.exception))

    def test_paper_passage_requires_a_document(self) -> None:
        with self.assertRaises(EvidenceError) as ctx:
            EvidenceRef(
                source_type="paper_passage",
                source_id="passage-7",
                evidence_level="fulltext",
            )
        self.assertIn("documentId", str(ctx.exception))

    def test_paper_passage_with_document_and_locator_is_valid(self) -> None:
        ref = EvidenceRef(
            source_type="paper_passage",
            source_id="passage-7",
            document_id="doc-3",
            evidence_level="fulltext",
            evidence_text="We evaluate on ImageNet.",
            locator={"page": 5, "paragraph": 2},
        )
        payload = ref.to_dict()
        self.assertEqual(payload["documentId"], "doc-3")
        self.assertEqual(payload["locator"], {"page": 5, "paragraph": 2})

    def test_locator_must_be_an_object(self) -> None:
        with self.assertRaises(EvidenceError):
            EvidenceRef(
                source_type="paper_passage",
                source_id="passage-7",
                document_id="doc-3",
                evidence_level="fulltext",
                locator="page 5",
            )

    def test_external_record_has_no_extra_requirements(self) -> None:
        ref = EvidenceRef(
            source_type="external_record",
            source_id="https://doi.org/10.1/example",
            evidence_level="abstract",
            evidence_text="Abstract text",
        )
        self.assertTrue(ref.is_citable)


class VerificationLadderTests(unittest.TestCase):
    def test_evidence_supports_requires_quoted_text(self) -> None:
        with self.assertRaises(EvidenceError) as ctx:
            _kg_bib(verification_status="evidence_supports", evidence_text="")
        self.assertIn("evidenceText", str(ctx.exception))

    def test_evidence_supports_is_allowed_once_text_is_quoted(self) -> None:
        ref = _kg_bib(
            verification_status="evidence_supports", evidence_text="Attention Is All You Need"
        )
        self.assertEqual(ref.verification_rank, 2)

    def test_semantic_verification_requires_depth_beyond_title(self) -> None:
        with self.assertRaises(EvidenceError) as ctx:
            _kg_bib(
                verification_status="semantic_verified",
                evidence_text="quoted",
                evidence_level="title",
            )
        self.assertIn("evidenceLevel", str(ctx.exception))

    def test_semantic_verification_is_allowed_on_an_abstract(self) -> None:
        ref = _kg_bib(
            evidence_level="abstract",
            verification_status="semantic_verified",
            evidence_text="quoted",
        )
        self.assertEqual(ref.verification_rank, 3)

    def test_advance_moves_forward_only(self) -> None:
        ref = _kg_bib()
        ref = ref.advance("id_valid")
        self.assertEqual(ref.verification_status, "id_valid")
        ref = ref.advance("id_valid")  # idempotent
        self.assertEqual(ref.verification_status, "id_valid")
        with self.assertRaises(EvidenceError) as ctx:
            ref.advance("unverified")
        self.assertIn("downgrade", str(ctx.exception))

    def test_advance_inherits_validation_rules(self) -> None:
        ref = _kg_bib()  # has evidenceText, but level is title
        with self.assertRaises(EvidenceError):
            ref.advance("semantic_verified")

    def test_with_text_can_raise_the_level(self) -> None:
        ref = _kg_bib().with_text("full abstract text", level="abstract")
        self.assertEqual(ref.evidence_level, "abstract")
        self.assertEqual(ref.evidence_text, "full abstract text")
        self.assertEqual(ref.verification_status, "unverified")


class RoundTripTests(unittest.TestCase):
    def test_from_mapping_round_trips(self) -> None:
        original = EvidenceRef(
            source_type="paper_passage",
            source_id="passage-7",
            document_id="doc-3",
            evidence_level="fulltext",
            evidence_text="We evaluate on ImageNet.",
            locator={"page": 5},
            verification_status="evidence_supports",
        )
        restored = EvidenceRef.from_mapping(original.to_dict())
        self.assertEqual(restored, original)

    def test_from_mapping_reports_missing_fields(self) -> None:
        with self.assertRaises(EvidenceError) as ctx:
            EvidenceRef.from_mapping({"sourceType": "kg_bibliography"})
        message = str(ctx.exception)
        self.assertIn("sourceId", message)
        self.assertIn("evidenceLevel", message)

    def test_from_mapping_rejects_non_objects(self) -> None:
        with self.assertRaises(EvidenceError):
            EvidenceRef.from_mapping(["not", "an", "object"])  # type: ignore[arg-type]


class AdapterFactoryTests(unittest.TestCase):
    def test_for_kg_publication_reads_publication_id(self) -> None:
        ref = EvidenceRef.for_kg_publication(
            {"publicationId": "p-9", "graphId": "g31", "title": "A Title", "year": 2021}
        )
        self.assertEqual(ref.source_type, "kg_bibliography")
        self.assertEqual(ref.source_id, "p-9")
        self.assertEqual(ref.publication_id, "p-9")
        self.assertEqual(ref.graph_id, "g31")
        self.assertEqual(ref.evidence_level, "title")
        self.assertEqual(ref.evidence_text, "A Title")

    def test_for_kg_publication_falls_back_to_id(self) -> None:
        ref = EvidenceRef.for_kg_publication({"id": "p-10", "title": "T"}, graph_id="g31")
        self.assertEqual(ref.source_id, "p-10")
        self.assertEqual(ref.graph_id, "g31")

    def test_for_kg_publication_requires_an_id(self) -> None:
        with self.assertRaises(EvidenceError):
            EvidenceRef.for_kg_publication({"title": "T"})

    def test_for_kg_assertion_keeps_candidate_status(self) -> None:
        ref = EvidenceRef.for_kg_assertion(
            {"assertionId": "a-1", "status": "candidate", "predicate": "USED_FOR"},
            publication_id="p-1",
            graph_id="g31",
            evidence_text="Title mentions BERT",
        )
        self.assertEqual(ref.source_type, "kg_assertion")
        self.assertEqual(ref.assertion_status, "candidate")
        self.assertEqual(ref.verification_status, "unverified")

    def test_for_kg_assertion_reads_the_real_kg_shape(self) -> None:
        """Matches /api/publication -> data.assertions[i].assertion verbatim."""
        live_props = {
            "id": "ai-literature-ed16399925fac2a599ed:Assertion:780c1091c566b981",
            "pairId": "pair-a8c5fbcc59113d8ac4df0ba2",
            "predicate": "USED_FOR",
            "status": "candidate",
            "confidence": 0.9990502,
            "confidenceCalibrated": False,
            "source": "model_prediction",
            "evidence": "Infer the Whole from a Glimpse of a Part.",
        }
        ref = EvidenceRef.for_kg_assertion(live_props, publication_id="conf/aaai/0002LCWHL25")
        self.assertEqual(ref.source_type, "kg_assertion")
        self.assertEqual(ref.source_id, live_props["id"])
        self.assertEqual(ref.publication_id, "conf/aaai/0002LCWHL25")
        self.assertEqual(ref.assertion_status, "candidate")
        self.assertEqual(ref.evidence_text, live_props["evidence"])
        self.assertEqual(ref.verification_status, "unverified")

    def test_for_kg_assertion_falls_back_to_pair_id(self) -> None:
        ref = EvidenceRef.for_kg_assertion(
            {"pairId": "pair-1", "status": "candidate"}, publication_id="p-1"
        )
        self.assertEqual(ref.source_id, "pair-1")

    def test_for_kg_assertion_never_invents_a_promotion(self) -> None:
        ref = EvidenceRef.for_kg_assertion(
            {"assertionId": "a-1", "status": "definitely-true"}, publication_id="p-1"
        )
        self.assertEqual(ref.assertion_status, "candidate")

    def test_for_kg_assertion_requires_an_id(self) -> None:
        with self.assertRaises(EvidenceError):
            EvidenceRef.for_kg_assertion({"status": "candidate"}, publication_id="p-1")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Unified evidence contract shared by every research source.

Why a single contract
---------------------
The knowledge graph is only the *first* source of research evidence. Later
sources are OpenAlex / Crossref / Semantic Scholar records, PaperQA2 passages
read out of a user-uploaded PDF, and the user's own notes. If each of them
invented its own shape, the citation gate could not be written once and the
UI could not render "where does this sentence come from" uniformly.

So every factual claim in a research answer points at an :class:`EvidenceRef`,
and the ref says three separable things that are routinely conflated:

1. ``source_type`` / ``source_id`` — **which record** the evidence came from.
2. ``evidence_level`` — **how deep** the evidence goes (title / abstract / full
   text). A title-level match proves the paper exists; it does not prove the
   paper did what the sentence says.
3. ``verification_status`` — **how far verification has actually got**:
   ``unverified`` → ``id_valid`` (the id resolves to a real record) →
   ``evidence_supports`` (the quoted text supports the sentence) →
   ``semantic_verified`` (a judge confirmed the entailment).

Keeping these three separate is the point: a citation whose id resolves is not
the same thing as a claim that is supported, and neither is a claim that has
been semantically verified. Reporting them as one boolean is what makes
"引用可溯率 100%" meaningless.

JSON shape (camelCase, stable — this is the wire format the API returns)::

    {
      "sourceType": "kg_assertion",
      "sourceId": "example-assertion-id",
      "publicationId": "example-paper-id",
      "graphId": "example-graph-version",
      "evidenceLevel": "title",
      "assertionStatus": "candidate",
      "evidenceText": "Original source passage",
      "verificationStatus": "unverified"
    }

Validation is a pure function of the fields (no clocks, no I/O), so the rules
below are unit-testable and the same input always produces the same verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = [
    "SOURCE_TYPES",
    "EVIDENCE_LEVELS",
    "ASSERTION_STATUSES",
    "VERIFICATION_STAGES",
    "EvidenceError",
    "EvidenceRef",
]

#: Where a piece of evidence physically comes from.
SOURCE_TYPES = (
    "kg_bibliography",  # a DBLP/Neo4j bibliography record (title-level only)
    "kg_assertion",  # a model-extracted relation, status: candidate
    "paper_passage",  # text read out of an authorised document (PaperQA2)
    "external_record",  # OpenAlex / Crossref / Semantic Scholar metadata
)

#: How deep the evidence goes. ``title`` < ``abstract`` < ``fulltext``.
EVIDENCE_LEVELS = ("title", "abstract", "fulltext")

#: The KG's own notion of a relation's standing (never upgraded silently).
ASSERTION_STATUSES = ("none", "candidate", "verified")

#: Verification ladder. Ordered: a ref may only move forward.
VERIFICATION_STAGES = ("unverified", "id_valid", "evidence_supports", "semantic_verified")

_STAGE_INDEX = {stage: index for index, stage in enumerate(VERIFICATION_STAGES)}

#: Stages that require quoted source text to be present.
_STAGES_REQUIRING_TEXT = ("evidence_supports", "semantic_verified")

#: Stages that require more than a title.
_STAGES_REQUIRING_DEPTH = ("semantic_verified",)

#: Levels deep enough for :data:`_STAGES_REQUIRING_DEPTH`.
_DEEP_ENOUGH = ("abstract", "fulltext")

#: Source types that must name a publication.
_TYPES_REQUIRING_PUBLICATION = ("kg_bibliography", "kg_assertion")


class EvidenceError(ValueError):
    """Raised when an evidence reference violates the contract."""


@dataclass(frozen=True)
class EvidenceRef:
    """One pointer from a claim to its source. See the module docstring."""

    source_type: str
    source_id: str
    evidence_level: str
    verification_status: str = "unverified"
    publication_id: str | None = None
    graph_id: str | None = None
    assertion_status: str = "none"
    evidence_text: str = ""
    document_id: str | None = None
    locator: Mapping[str, Any] | None = field(default=None)

    def __post_init__(self) -> None:
        self._require_choice("sourceType", self.source_type, SOURCE_TYPES)
        self._require_choice("evidenceLevel", self.evidence_level, EVIDENCE_LEVELS)
        self._require_choice("verificationStatus", self.verification_status, VERIFICATION_STAGES)
        self._require_choice("assertionStatus", self.assertion_status, ASSERTION_STATUSES)

        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise EvidenceError("sourceId is required: a claim with no source id is not citable")

        if self.source_type in _TYPES_REQUIRING_PUBLICATION and not self.publication_id:
            raise EvidenceError(f"publicationId is required for sourceType {self.source_type!r}")

        if self.source_type == "kg_assertion" and self.assertion_status == "none":
            raise EvidenceError(
                "assertionStatus must be 'candidate' or 'verified' for sourceType 'kg_assertion'"
            )

        if self.source_type == "paper_passage" and not self.document_id:
            raise EvidenceError("documentId is required for sourceType 'paper_passage'")

        if self.verification_status in _STAGES_REQUIRING_TEXT and not self.evidence_text.strip():
            raise EvidenceError(
                f"verificationStatus {self.verification_status!r} requires non-empty evidenceText"
            )

        if self.verification_status in _STAGES_REQUIRING_DEPTH and self.evidence_level not in _DEEP_ENOUGH:
            raise EvidenceError(
                f"verificationStatus {self.verification_status!r} requires evidenceLevel "
                f"in {_DEEP_ENOUGH}, got {self.evidence_level!r}"
            )

        if self.locator is not None and not isinstance(self.locator, Mapping):
            raise EvidenceError("locator must be an object (e.g. {'page': 3, 'paragraph': 2})")

    # -- derived -------------------------------------------------------------
    @property
    def is_citable(self) -> bool:
        """Whether this ref may appear next to a factual sentence."""
        return bool(self.source_id.strip())

    @property
    def verification_rank(self) -> int:
        """Position on the ladder; higher means further verified."""
        return _STAGE_INDEX[self.verification_status]

    def advance(self, stage: str) -> "EvidenceRef":
        """Return a copy verified one step further. Never moves backwards."""
        self._require_choice("verificationStatus", stage, VERIFICATION_STAGES)
        if _STAGE_INDEX[stage] < self.verification_rank:
            raise EvidenceError(
                f"cannot downgrade verification from {self.verification_status!r} to {stage!r}"
            )
        return self._replace(verification_status=stage)

    def with_text(self, evidence_text: str, *, level: str | None = None) -> "EvidenceRef":
        """Attach quoted source text (and optionally raise the evidence level)."""
        return self._replace(evidence_text=evidence_text, evidence_level=level or self.evidence_level)

    def _replace(self, **changes: Any) -> "EvidenceRef":
        values = {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "evidence_level": self.evidence_level,
            "verification_status": self.verification_status,
            "publication_id": self.publication_id,
            "graph_id": self.graph_id,
            "assertion_status": self.assertion_status,
            "evidence_text": self.evidence_text,
            "document_id": self.document_id,
            "locator": self.locator,
        }
        values.update(changes)
        return EvidenceRef(**values)

    # -- wire format ---------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """camelCase JSON — the shape the API and the UI both consume."""
        payload: dict[str, Any] = {
            "sourceType": self.source_type,
            "sourceId": self.source_id,
            "evidenceLevel": self.evidence_level,
            "assertionStatus": self.assertion_status,
            "verificationStatus": self.verification_status,
        }
        if self.publication_id:
            payload["publicationId"] = self.publication_id
        if self.graph_id:
            payload["graphId"] = self.graph_id
        if self.evidence_text:
            payload["evidenceText"] = self.evidence_text
        if self.document_id:
            payload["documentId"] = self.document_id
        if self.locator is not None:
            payload["locator"] = dict(self.locator)
        return payload

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EvidenceRef":
        """Rebuild a ref from its wire form (round-trips with :meth:`to_dict`)."""
        if not isinstance(raw, Mapping):
            raise EvidenceError(f"expected an object, got {type(raw).__name__}")
        missing = [key for key in ("sourceType", "sourceId", "evidenceLevel") if not raw.get(key)]
        if missing:
            raise EvidenceError(f"missing required field(s): {', '.join(missing)}")
        return cls(
            source_type=str(raw["sourceType"]),
            source_id=str(raw["sourceId"]),
            evidence_level=str(raw["evidenceLevel"]),
            verification_status=str(raw.get("verificationStatus", "unverified")),
            publication_id=raw.get("publicationId"),
            graph_id=raw.get("graphId"),
            assertion_status=str(raw.get("assertionStatus", "none")),
            evidence_text=str(raw.get("evidenceText", "")),
            document_id=raw.get("documentId"),
            locator=raw.get("locator"),
        )

    # -- adapters from concrete sources -------------------------------------
    @classmethod
    def for_kg_publication(
        cls, publication: Mapping[str, Any], *, graph_id: str | None = None
    ) -> "EvidenceRef":
        """Bibliography-level ref for one record returned by the KG search API.

        The graph stores **titles only**, so the level is ``title`` — which is
        exactly why a citation built from it cannot claim more than "this paper
        exists and its title mentions these terms".
        """
        publication_id = publication.get("publicationId") or publication.get("id")
        if not publication_id:
            raise EvidenceError("publication record has neither 'publicationId' nor 'id'")
        return cls(
            source_type="kg_bibliography",
            source_id=str(publication_id),
            publication_id=str(publication_id),
            graph_id=graph_id or publication.get("graphId"),
            evidence_level="title",
            assertion_status="none",
            evidence_text=str(publication.get("title") or ""),
        )

    @classmethod
    def for_kg_assertion(
        cls,
        assertion: Mapping[str, Any],
        *,
        publication_id: str,
        graph_id: str | None = None,
        evidence_text: str = "",
    ) -> "EvidenceRef":
        """Candidate-assertion ref. The KG never promotes these to facts.

        ``assertion`` is the assertion's own properties object — i.e.
        ``/api/publication`` -> ``data.assertions[i].assertion``, not the
        ``{assertion, head, tail}`` wrapper and not the head/tail mentions. The
        graph identifies it by ``id`` (a composite ``graph:Assertion:<sha>``)
        with ``pairId`` as the stable model-side key.
        """
        assertion_id = assertion.get("id") or assertion.get("pairId") or assertion.get("assertionId")
        if not assertion_id:
            raise EvidenceError("assertion record has no 'id' / 'pairId' / 'assertionId'")
        status = str(assertion.get("status") or "candidate")
        if status not in ASSERTION_STATUSES or status == "none":
            status = "candidate"
        return cls(
            source_type="kg_assertion",
            source_id=str(assertion_id),
            publication_id=str(publication_id),
            graph_id=graph_id,
            evidence_level="title",
            assertion_status=status,
            evidence_text=evidence_text or str(assertion.get("evidence") or ""),
        )

    @staticmethod
    def _require_choice(name: str, value: str, allowed: tuple[str, ...]) -> None:
        if value not in allowed:
            raise EvidenceError(f"{name} must be one of {allowed}, got {value!r}")

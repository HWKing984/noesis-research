"""Wire models for the research API.

Two rules shape this module:

1. **Nothing is invented.** Every field here was observed on the live service
   (see ``docs/01_source_audit.md`` §7.3). Where the upstream shape is *not*
   part of the documented contract — most notably ``urls`` — the field is
   normalised by a pure helper instead of being guessed.
2. **Evidence travels with the data.** Every paper and every candidate
   assertion carries an :class:`EvidenceRefModel`, so the UI can render a
   clickable source for each claim and the citation gate has something to
   verify. A research answer that cannot point at a source is not allowed to
   exist.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


def as_link_list(value: Any) -> list[str]:
    """Normalise the KG's ``urls`` field to a list of strings.

    ``/api/publications`` returns ``properties(p)`` verbatim, so ``urls`` is not
    covered by the service's documented contract. Accept the shapes actually
    possible (a list, a bare string, or a mapping of label -> string/list) and
    drop anything else — inventing a link would be worse than omitting one.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, dict):
        flattened: list[str] = []
        for item in value.values():
            flattened.extend(as_link_list(item))
        return flattened
    return []


def as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


class EvidenceRefModel(BaseModel):
    """Wire form of ``packages.contracts.evidence.EvidenceRef`` (camelCase)."""

    sourceType: str
    sourceId: str
    evidenceLevel: str
    assertionStatus: str = "none"
    verificationStatus: str = "unverified"
    publicationId: str | None = None
    graphId: str | None = None
    evidenceText: str | None = None
    documentId: str | None = None
    locator: dict[str, Any] | None = None


class PaperSummary(BaseModel):
    publicationId: str
    title: str
    year: int | None = None
    type: str | None = None
    doi: str | None = None
    dblpUrl: str | None = None
    urls: list[str] = Field(default_factory=list)
    graphId: str | None = None
    modelApplied: bool = False
    modelApplicationStatus: str | None = None
    evidence: EvidenceRefModel


class AuthorModel(BaseModel):
    name: str
    signatureName: str | None = None
    position: int | None = None
    identityStatus: str | None = None
    personId: str | None = None
    dblpPid: str | None = None
    dblpUrl: str | None = None


class VenueModel(BaseModel):
    name: str
    type: str | None = None


class MentionModel(BaseModel):
    """One entity mention. ``start`` / ``end`` are character offsets."""

    text: str
    label: str | None = None
    start: int | None = None
    end: int | None = None
    status: str | None = None
    offsetUnit: str | None = None


class AssertionModel(BaseModel):
    """A candidate relation. ``status`` stays ``candidate``; nothing promotes it."""

    id: str
    pairId: str | None = None
    predicate: str
    status: str
    confidence: float | None = None
    confidenceCalibrated: bool = False
    source: str | None = None
    evidenceText: str | None = None
    head: MentionModel | None = None
    tail: MentionModel | None = None
    evidence: EvidenceRefModel


class PublicationDetailModel(BaseModel):
    publication: PaperSummary
    authors: list[AuthorModel] = Field(default_factory=list)
    venues: list[VenueModel] = Field(default_factory=list)
    mentions: list[MentionModel] = Field(default_factory=list)
    assertions: list[AssertionModel] = Field(default_factory=list)
    citationDraft: str = ""
    notice: str = ""


class SearchMeta(BaseModel):
    """Query echo: what the API actually searched, and what it expanded.

    ``applied`` mirrors the graph rule that a user must be able to see which
    parameters were used — the agent is never allowed to hide its own query.
    """

    offset: int
    limit: int
    hasNext: bool
    source: str
    aliasVersion: str | None = None
    expandedTerms: dict[str, list[str]] = Field(default_factory=dict)
    applied: dict[str, str] = Field(default_factory=dict)
    graphId: str | None = None


class SearchResponse(BaseModel):
    data: list[PaperSummary]
    meta: SearchMeta


class GraphNodeModel(BaseModel):
    id: str
    kind: str
    props: dict[str, Any]


class GraphEdgeModel(BaseModel):
    id: str
    kind: str
    source: str
    target: str


class GraphSliceModel(BaseModel):
    nodes: list[GraphNodeModel]
    edges: list[GraphEdgeModel]
    paths: list[dict[str, Any]]
    rootId: str
    mode: str
    graphId: str
    hasMorePaths: bool
    notice: str


class HealthModel(BaseModel):
    status: str
    graphId: str
    source: str
    scope: dict[str, int]
    aliasVersion: str | None = None
    pinnedGraphId: str | None = None


class ErrorModel(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorModel

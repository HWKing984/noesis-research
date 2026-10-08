"""Pure functions turning adapter dataclasses into wire models.

Nothing here touches the network or the clock, so every rule is unit-testable
and the same upstream payload always produces the same response — which is what
makes the "parameter echo" and "candidate status透传" guarantees checkable
rather than aspirational.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from packages.contracts.evidence import EvidenceRef

from kg_client import Assertion, GraphSlice, KGError, PublicationDetail

from .models import (
    AssertionModel,
    AuthorModel,
    EvidenceRefModel,
    GraphEdgeModel,
    GraphNodeModel,
    GraphSliceModel,
    MentionModel,
    PaperSummary,
    PublicationDetailModel,
    VenueModel,
    as_link_list,
    as_optional_str,
)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def evidence_model(ref: EvidenceRef) -> EvidenceRefModel:
    return EvidenceRefModel(**ref.to_dict())


def paper_summary(publication: Mapping[str, Any], *, graph_id: str | None = None) -> PaperSummary:
    """One bibliography record + its (title-level) evidence ref."""
    publication_id = publication.get("publicationId") or publication.get("id")
    if not publication_id:
        # An upstream record we cannot identify is an upstream fault, not a
        # client error: surface it as KGError so the API answers 502.
        raise KGError("publication record carries neither 'publicationId' nor 'id'")
    year = publication.get("year")
    ref = EvidenceRef.for_kg_publication(dict(publication), graph_id=graph_id)
    return PaperSummary(
        publicationId=str(publication_id),
        title=_text(publication.get("title")),
        year=int(year) if isinstance(year, int) and not isinstance(year, bool) else None,
        type=as_optional_str(publication.get("type")),
        doi=as_optional_str(publication.get("doi")),
        dblpUrl=as_optional_str(publication.get("dblpUrl")),
        urls=as_link_list(publication.get("urls")),
        graphId=as_optional_str(publication.get("graphId")) or graph_id,
        modelApplied=bool(publication.get("modelApplied", False)),
        modelApplicationStatus=as_optional_str(publication.get("modelApplicationStatus")),
        evidence=evidence_model(ref),
    )


def author_models(authors: Sequence[Mapping[str, Any]]) -> list[AuthorModel]:
    models: list[AuthorModel] = []
    for author in authors:
        name = author.get("name")
        if not name:
            continue
        position = author.get("position")
        models.append(
            AuthorModel(
                name=_text(name),
                signatureName=as_optional_str(author.get("signatureName")),
                position=int(position) if isinstance(position, int) and not isinstance(position, bool) else None,
                identityStatus=as_optional_str(author.get("identityStatus")),
                personId=as_optional_str(author.get("personId")),
                dblpPid=as_optional_str(author.get("dblpPid")),
                dblpUrl=as_optional_str(author.get("dblpUrl")),
            )
        )
    return models


def venue_models(venues: Sequence[Mapping[str, Any]]) -> list[VenueModel]:
    return [
        VenueModel(name=_text(venue.get("name")), type=as_optional_str(venue.get("type")))
        for venue in venues
        if venue.get("name")
    ]


def _mention_model(mention: Mapping[str, Any] | None) -> MentionModel | None:
    if not mention:
        return None
    start = mention.get("start")
    end = mention.get("end")
    return MentionModel(
        text=_text(mention.get("text")),
        label=as_optional_str(mention.get("label")),
        start=int(start) if isinstance(start, int) and not isinstance(start, bool) else None,
        end=int(end) if isinstance(end, int) and not isinstance(end, bool) else None,
        status=as_optional_str(mention.get("status")),
        offsetUnit=as_optional_str(mention.get("offsetUnit")),
    )


def mention_models(mentions: Sequence[Mapping[str, Any]]) -> list[MentionModel]:
    models = [_mention_model(mention) for mention in mentions]
    return [model for model in models if model is not None]


def assertion_model(assertion: Assertion, *, publication_id: str, graph_id: str | None) -> AssertionModel:
    props = assertion.assertion
    assertion_id = props.get("id") or props.get("pairId")
    if not assertion_id:
        raise KGError("assertion record carries neither 'id' nor 'pairId'")
    confidence = props.get("confidence")
    ref = EvidenceRef.for_kg_assertion(
        dict(props), publication_id=publication_id, graph_id=graph_id or props.get("graphId")
    )
    return AssertionModel(
        id=str(assertion_id),
        pairId=as_optional_str(props.get("pairId")),
        predicate=assertion.predicate,
        status=assertion.status,
        confidence=float(confidence) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else None,
        confidenceCalibrated=bool(props.get("confidenceCalibrated", False)),
        source=as_optional_str(props.get("source")),
        evidenceText=as_optional_str(props.get("evidence")),
        head=_mention_model(assertion.head),
        tail=_mention_model(assertion.tail),
        evidence=evidence_model(ref),
    )


def assertion_models(
    assertions: Sequence[Assertion], *, publication_id: str, graph_id: str | None
) -> list[AssertionModel]:
    return [
        assertion_model(item, publication_id=publication_id, graph_id=graph_id)
        for item in assertions
    ]


def publication_detail(detail: PublicationDetail, *, graph_id: str | None) -> PublicationDetailModel:
    publication = detail.publication
    publication_id = str(publication.get("publicationId") or publication.get("id") or "")
    return PublicationDetailModel(
        publication=paper_summary(publication, graph_id=graph_id),
        authors=author_models(detail.authors),
        venues=venue_models(detail.venues),
        mentions=mention_models(detail.mentions),
        assertions=assertion_models(
            detail.assertions, publication_id=publication_id, graph_id=graph_id
        ),
        citationDraft=detail.citation_draft,
        notice=detail.notice,
    )


def graph_slice(slice_: GraphSlice) -> GraphSliceModel:
    return GraphSliceModel(
        nodes=[
            GraphNodeModel(id=node.id, kind=node.kind, props=dict(node.props))
            for node in slice_.nodes
        ],
        edges=[
            GraphEdgeModel(id=edge.id, kind=edge.kind, source=edge.source, target=edge.target)
            for edge in slice_.edges
        ],
        paths=[dict(path) for path in slice_.paths],
        rootId=slice_.root_id,
        mode=slice_.mode,
        graphId=slice_.graph_id,
        hasMorePaths=slice_.has_more_paths,
        notice=slice_.notice,
    )

"""Document availability contract — a five-state machine, never a boolean.

Why a state machine
-------------------
"Can I read this paper?" is not a yes/no question. The honest answer is one of
five distinct states, and collapsing them into "found / not found" is exactly
how a system ends up claiming to host a full text it does not have:

1. ``available``            — a lawful full text is cached (fetched or uploaded).
2. ``publisher_link_only``  — no OA copy exists anywhere we looked, but the
                              publisher landing page is known.
3. ``no_oa_found``          — we *searched* and there is genuinely no open
                              copy. This is a fact about the world.
4. ``fetch_failed``         — an OA copy almost certainly exists but the
                              download failed. This is a fact about *this run*
                              and is retryable.
5. ``restricted``           — the publisher blocks lawful automated access;
                              the user may upload a copy they have rights to.

``no_oa_found`` and ``fetch_failed`` must never be conflated: one says "stop
retrying, there is nothing there", the other says "try again later". The UI
renders all five verbatim and never upgrades a non-``available`` state into a
reader.

Every state change goes through :data:`TRANSITIONS`; illegal jumps (e.g.
``no_oa_found → fetch_failed``) raise :class:`DocumentError`, so a bug cannot
quietly relabel "we failed" as "it does not exist".

Passage anchoring
-----------------
A ``locator`` produced by one PDF pipeline is *not* stable across parsers or
parser versions — offsets drift, and a citation that points at the wrong
paragraph is worse than no citation. So every locator is stored together with
a ``quote`` (verbatim source text), and :func:`locate_quote` is the pure
re-anchoring rule: exact match first, then a *bounded* fuzzy pass. If neither
finds the quote, it raises :class:`QuoteNotFoundError` — the UI must show
"anchor lost", never a wrong highlight.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = [
    "DOCUMENT_STATUSES",
    "SOURCE_KINDS",
    "TRANSITIONS",
    "DocumentError",
    "QuoteNotFoundError",
    "DocumentRef",
    "PassageLocator",
    "locate_quote",
    "for_paper_passage",
]

#: The five availability states, rendered verbatim in the UI.
DOCUMENT_STATUSES = (
    "available",
    "publisher_link_only",
    "no_oa_found",
    "fetch_failed",
    "restricted",
)

#: Where a cached full text lawfully came from. ``None`` is only legal while
#: the document is not ``available``.
SOURCE_KINDS = (
    "arxiv",
    "openreview",
    "openalex",
    "semantic_scholar",
    "publisher",
    "upload",
)

#: Legal status transitions. Keys are the *current* status (``"none"`` = the
#: document has not been fetched yet); values are the statuses it may move to.
#: ``available`` is terminal: replacing the file (a new upload) keeps the
#: status, so nothing ever transitions *out* of it.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "none": ("available", "publisher_link_only", "no_oa_found", "fetch_failed", "restricted"),
    "available": ("available",),
    "publisher_link_only": ("available", "publisher_link_only", "restricted"),
    "no_oa_found": ("available", "no_oa_found"),
    "fetch_failed": ("available", "fetch_failed", "no_oa_found"),
    "restricted": ("available", "restricted"),
}

#: Fetch outcomes that mean "the investigation itself failed" and may be
#: re-labelled ``no_oa_found`` once the investigation is redone.
_INVESTIGATION_STATES = ("fetch_failed",)


class DocumentError(ValueError):
    """Raised when a document record or a status transition is invalid."""


@dataclass(frozen=True)
class DocumentRef:
    """One paper's full-text availability, verbatim and auditable.

    Invariants enforced here (so every caller, including the UI, can trust
    them without re-checking):

    * ``available`` ⇒ ``sha256`` (64 hex chars), ``source_kind``, and a
      positive ``size_bytes`` are present. A cached file without its hash is
      not version-citable; a hash without bytes is a lie.
    * not ``available`` ⇒ **no** ``sha256`` and no ``size_bytes``. Pretending
      otherwise is how "we only have the title" becomes "we host the PDF".
    * ``publisher_link_only`` ⇒ ``source_url`` present (the landing page).
    * ``no_oa_found`` ⇒ ``detail`` must say the search found nothing — it may
      not carry a failure reason, because it is not a failure state.
    * ``fetch_failed`` ⇒ ``detail`` must carry a retryable reason.
    """

    document_id: str
    status: str
    publication_id: str | None = None
    source_kind: str | None = None
    source_url: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    detail: str = ""
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in DOCUMENT_STATUSES:
            raise DocumentError(f"status must be one of {DOCUMENT_STATUSES}, got {self.status!r}")
        if not isinstance(self.document_id, str) or not self.document_id.strip():
            raise DocumentError("documentId is required")

        if self.source_kind is not None and self.source_kind not in SOURCE_KINDS:
            raise DocumentError(f"sourceKind must be one of {SOURCE_KINDS}, got {self.source_kind!r}")

        if self.status == "available":
            if not self.sha256:
                raise DocumentError("an available document must record its sha256")
            if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256.lower()):
                raise DocumentError("sha256 must be a 64-char lowercase hex digest")
            if not self.source_kind:
                raise DocumentError("an available document must record where the file came from")
            if not isinstance(self.size_bytes, int) or self.size_bytes <= 0:
                raise DocumentError("an available document must record a positive sizeBytes")
        else:
            if self.sha256 is not None or self.size_bytes is not None:
                raise DocumentError(
                    f"status {self.status!r} must not carry sha256/sizeBytes: "
                    "a document we do not host must never look hosted"
                )

        if self.status == "publisher_link_only" and not (self.source_url or "").strip():
            raise DocumentError("publisher_link_only requires the publisher landing page in sourceUrl")

        if self.status == "no_oa_found" and self.detail.strip().lower().startswith(
            ("timeout", "connection", "http ", "download")
        ):
            raise DocumentError(
                "no_oa_found must not carry a transport-failure detail: "
                "search-exhausted and fetch-failed are different states"
            )

        if self.status == "fetch_failed" and not self.detail.strip():
            raise DocumentError("fetch_failed must record the retryable failure reason in detail")

    # -- transitions ---------------------------------------------------------
    def transition(
        self,
        new_status: str,
        *,
        source_kind: str | None = None,
        source_url: str | None = None,
        sha256: str | None = None,
        size_bytes: int | None = None,
        detail: str = "",
    ) -> "DocumentRef":
        """Move to ``new_status`` through :data:`TRANSITIONS` or raise."""
        allowed = TRANSITIONS.get(self.status, ())
        if new_status not in allowed:
            raise DocumentError(
                f"illegal transition {self.status!r} -> {new_status!r}; "
                f"allowed: {allowed}"
            )
        return DocumentRef(
            document_id=self.document_id,
            status=new_status,
            publication_id=self.publication_id,
            source_kind=source_kind or (self.source_kind if new_status == self.status else None),
            source_url=source_url or self.source_url,
            sha256=sha256,
            size_bytes=size_bytes,
            detail=detail,
            meta=self.meta,
        )

    # -- derived -------------------------------------------------------------
    @property
    def is_readable(self) -> bool:
        """The only state the reader view may open a PDF for."""
        return self.status == "available"

    @property
    def is_retryable(self) -> bool:
        return self.status == "fetch_failed"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "documentId": self.document_id,
            "status": self.status,
            "detail": self.detail,
        }
        if self.publication_id:
            payload["publicationId"] = self.publication_id
        if self.source_kind:
            payload["sourceKind"] = self.source_kind
        if self.source_url:
            payload["sourceUrl"] = self.source_url
        if self.sha256:
            payload["sha256"] = self.sha256
        if self.size_bytes is not None:
            payload["sizeBytes"] = self.size_bytes
        if self.meta:
            payload["meta"] = dict(self.meta)
        return payload

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DocumentRef":
        if not isinstance(raw, Mapping):
            raise DocumentError(f"expected an object, got {type(raw).__name__}")
        if not raw.get("documentId") or not raw.get("status"):
            raise DocumentError("documentId and status are required")
        return cls(
            document_id=str(raw["documentId"]),
            status=str(raw["status"]),
            publication_id=raw.get("publicationId"),
            source_kind=raw.get("sourceKind"),
            source_url=raw.get("sourceUrl"),
            sha256=raw.get("sha256"),
            size_bytes=raw.get("sizeBytes"),
            detail=str(raw.get("detail", "")),
            meta=raw.get("meta") or {},
        )


@dataclass(frozen=True)
class PassageLocator:
    """Where a passage sits inside one document page.

    Offsets are 0-based character offsets into that page's extracted text.
    They are only meaningful together with a :data:`quote` snapshot — parsers
    drift, quotes do not. Re-anchor with :func:`locate_quote`.
    """

    page: int
    start_offset: int
    end_offset: int

    def __post_init__(self) -> None:
        if not isinstance(self.page, int) or self.page < 1:
            raise DocumentError(f"page must be a 1-based int, got {self.page!r}")
        if not isinstance(self.start_offset, int) or not isinstance(self.end_offset, int):
            raise DocumentError("offsets must be ints")
        if self.start_offset < 0 or self.end_offset <= self.start_offset:
            raise DocumentError(
                f"offsets must satisfy 0 <= start < end, got {self.start_offset}..{self.end_offset}"
            )

    def to_dict(self) -> dict[str, int]:
        return {"page": self.page, "startOffset": self.start_offset, "endOffset": self.end_offset}


class QuoteNotFoundError(DocumentError):
    """The quote could not be re-anchored in the page text (exact or bounded fuzzy).

    Callers must surface this as "anchor lost" — never fall back to a guessed
    position, because a wrong highlight is worse than none.
    """


def _normalize(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to single spaces (order-preserving).

    Returns the normalized text plus, for each normalized character, the index
    of the character it came from — so fuzzy match positions map back onto the
    original text and the locator stays valid against the real page.
    """
    chars: list[str] = []
    index_map: list[int] = []
    previous_was_space = True  # also trims the leading run
    for index, ch in enumerate(text):
        if ch.isspace():
            if not previous_was_space:
                chars.append(" ")
                index_map.append(index)
                previous_was_space = True
            continue
        chars.append(ch)
        index_map.append(index)
        previous_was_space = False
    while chars and chars[-1] == " ":
        chars.pop()
        index_map.pop()
    return "".join(chars), index_map


def locate_quote(
    page_text: str,
    quote: str,
    *,
    fuzzy_threshold: float = 0.82,
    max_fuzzy_window: int = 2000,
) -> PassageLocator:
    """Re-anchor ``quote`` inside ``page_text``; two tiers, no guessing.

    Tier 1 — exact: the quote appears verbatim in the page text.
    Tier 2 — bounded fuzzy: whitespace-collapsed comparison, sliding a window
    of the quote's normalized length over the normalized page, accepted only
    at ``difflib`` ratio >= ``fuzzy_threshold``. The window is capped at
    ``max_fuzzy_window`` chars so a pathological page cannot turn this into an
    O(n²) scan, and the best window above the threshold wins.

    Raises :class:`QuoteNotFoundError` when both tiers miss — the caller then
    renders "anchor lost" instead of a fabricated position.
    """
    if not page_text or not quote.strip():
        raise QuoteNotFoundError("quote and page_text must be non-empty")

    start = page_text.find(quote)
    if start >= 0:
        return PassageLocator(page=1, start_offset=start, end_offset=start + len(quote))

    # Tier 2: normalized sliding window. Page is 1-based in locators, but the
    # page number is supplied by the caller's context — keep 1 as the neutral
    # default here and let for_paper_passage override it.
    normalized_page, index_map = _normalize(page_text)
    normalized_quote, _ = _normalize(quote)
    if not normalized_quote:
        raise QuoteNotFoundError("quote normalizes to whitespace")
    qlen = len(normalized_quote)
    if qlen > len(normalized_page):
        raise QuoteNotFoundError("quote is longer than the (normalized) page text")
    if qlen > max_fuzzy_window:
        raise QuoteNotFoundError("quote exceeds the bounded fuzzy window; refusing to guess")

    step = max(1, qlen // 10)
    best_ratio = 0.0
    best_start = -1
    matcher = difflib.SequenceMatcher(None, normalized_quote, "")
    for pos in range(0, len(normalized_page) - qlen + 1, step):
        window = normalized_page[pos : pos + qlen]
        matcher.set_seq2(window)
        ratio = matcher.ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = pos
            if ratio == 1.0:
                break
    if best_start < 0 or best_ratio < fuzzy_threshold:
        raise QuoteNotFoundError(
            f"quote not found (best fuzzy ratio {best_ratio:.2f} < threshold {fuzzy_threshold:.2f})"
        )

    # Re-scan tightly around the best coarse window to trim the boundary, then
    # map normalized offsets back to original-text offsets.
    fine_from = max(0, best_start - step)
    fine_to = min(len(normalized_page) - qlen, best_start + step)
    matcher.set_seq1(normalized_quote)
    best_fine_start = best_start
    best_fine_ratio = -1.0
    for pos in range(fine_from, fine_to + 1):
        window = normalized_page[pos : pos + qlen]
        matcher.set_seq2(window)
        ratio = matcher.ratio()
        if ratio > best_fine_ratio:
            best_fine_ratio = ratio
            best_fine_start = pos
    if best_fine_ratio < fuzzy_threshold:
        raise QuoteNotFoundError("quote not found in the refined window")

    orig_start = index_map[best_fine_start]
    orig_end_exclusive = index_map[best_fine_start + qlen - 1] + 1
    return PassageLocator(page=1, start_offset=orig_start, end_offset=orig_end_exclusive)


def for_paper_passage(
    *,
    document: DocumentRef,
    chunk_id: str,
    locator: PassageLocator,
    quote: str,
) -> "object":
    """Build a full-text :class:`~packages.contracts.evidence.EvidenceRef`.

    This is the bridge from the document domain into the evidence contract:
    once a full text is ``available``, passages read out of it become
    ``paper_passage`` refs with ``evidenceLevel='fulltext'`` — which is what
    finally lets ``verificationStatus`` climb past ``unverified``.

    Rules:

    * the document must be ``available`` — no passage can be cited from a
      state that never hosted a file;
    * ``quote`` must be the verbatim source text; the evidence contract
      requires non-empty ``evidenceText`` for any verified stage anyway;
    * the ref starts at ``id_valid``: constructing it proves the passage
      exists in a real document, but *supporting a sentence* is a separate
      verification step nobody may skip silently.
    """
    from packages.contracts.evidence import EvidenceError, EvidenceRef

    if not document.is_readable:
        raise DocumentError(
            f"cannot cite a passage from status {document.status!r}: "
            "only an available (cached, hashed) document yields full-text evidence"
        )
    if not isinstance(chunk_id, str) or not chunk_id.strip():
        raise DocumentError("chunkId is required")
    if not isinstance(quote, str) or not quote.strip():
        raise DocumentError("quote must be the verbatim passage text")
    try:
        return EvidenceRef(
            source_type="paper_passage",
            source_id=chunk_id,
            publication_id=document.publication_id,
            document_id=document.document_id,
            evidence_level="fulltext",
            evidence_text=quote,
            verification_status="id_valid",
            locator=locator.to_dict(),
        )
    except EvidenceError as exc:  # pragma: no cover - re-wrap for a unified domain error
        raise DocumentError(f"evidence contract rejected the passage ref: {exc}") from exc

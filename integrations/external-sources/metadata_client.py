"""External metadata sources that can supply **abstract-level** evidence.

Why this exists
---------------
The knowledge graph stores titles only. Every answer built on it can therefore
claim no more than "this paper exists and its title contains these words" — the
agent has literally nothing else to read. That ceiling is not a prompt problem
and cannot be fixed by prompt engineering: it is a *material* problem. This
module supplies the material.

Three public sources, tried in a fixed order, each keyed by a **strong
identifier**:

===============  ==========================================  ===================
source           lookup key                                  abstract shape
===============  ==========================================  ===================
semanticscholar  ``DOI:<doi>`` / ``ARXIV:<id>``              plain ``abstract``
openalex         ``https://doi.org/<doi>``                   ``abstract_inverted_index``
crossref         ``/<doi>``                                  ``message.abstract`` (JATS)
===============  ==========================================  ===================

Measured on this machine (2026-10-10): Semantic Scholar returns a plain-text
abstract for both sampled DOIs (1293 / 1117 chars) plus a venue string; OpenAlex
returns a rebuildable inverted index for both; Crossref returned **no abstract
for either** sampled DOI. Hence the order above.

Identity discipline (hard rule, from the phase-1 plan §T8)
---------------------------------------------------------
Matching order is **DOI → exact arXiv id → explicit source identifier**. Title
similarity is never used to *claim* a record: this client exposes no
title-based lookup at all, and every response is rejected unless the record's
DOI equals the DOI we asked for. A wrong abstract attached to a real paper is
worse than no abstract, because it reads as verified evidence.

Failure semantics (mirrors the repo-wide rule)
----------------------------------------------
* source unreachable / throttled (429, 5xx, timeout) → :class:`ExternalUnavailable`
  — callers MUST surface this rather than reporting "no abstract";
* record genuinely absent (404) → :class:`ExternalNotFound`;
* 200 whose body does not match the documented shape, or a DOI mismatch →
  :class:`ExternalRejected`;
* record exists but carries no abstract → ``None`` (a real answer, not an error).

When no source yields an abstract, the verdict is only "no abstract" if at least
one source gave a **definite** answer (404, or a record that carries no
abstract) — and even then only if that answer was not contradicted by a source
that failed. If every source was unreachable, or every answer was in a shape we
refuse to trust, this raises :class:`ExternalUnavailable`: "I could not look"
must never be dressed up as "I looked and there is nothing".

Standard library only, on purpose: this sits on the agent's tool seam, next to
``kg_client``, which is dependency-free for the same reason.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

__all__ = [
    "ALLOWED_HOSTS",
    "DEFAULT_SOURCES",
    "SOURCE_LABELS",
    "USER_AGENT",
    "ExternalError",
    "ExternalUnavailable",
    "ExternalNotFound",
    "ExternalRejected",
    "ExternalNoIdentifier",
    "ExternalNotApplicable",
    "ExternalRecord",
    "MetadataTransport",
    "HttpTransport",
    "FileCache",
    "ExternalMetadataClient",
    "normalize_doi",
    "resolve_cache_dir",
    "resolve_sources",
    "resolve_timeout",
    "resolve_s2_api_key",
    "MAX_ABSTRACT_CHARS",
]

#: Hosts this client will talk to. Checked on the initial request; the client
#: never follows redirects to another host (see :class:`_AllowListRedirect`).
ALLOWED_HOSTS = frozenset(
    {
        "api.semanticscholar.org",
        "api.openalex.org",
        "api.crossref.org",
    }
)

#: Fallback chain, measured rather than assumed (see module docstring).
DEFAULT_SOURCES = ("semanticscholar", "openalex", "crossref")

#: Human-facing names. The answer must say *where* the abstract came from.
SOURCE_LABELS = {
    "semanticscholar": "Semantic Scholar",
    "openalex": "OpenAlex",
    "crossref": "Crossref",
}

USER_AGENT = "noesis-research-external-sources/0.1"

#: Hard cap on a metadata response body: these endpoints answer in kilobytes.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024

#: Hard cap on the abstract handed to a model. Abstracts run 800–2500 chars;
#: 4000 keeps a whole one without letting a chatty source flood the context.
MAX_ABSTRACT_CHARS = 4000

DEFAULT_TIMEOUT = 12.0
DEFAULT_CACHE_DIR = ".data/external"
DEFAULT_CACHE_TTL_SECONDS = 30 * 24 * 3600

ENV_CACHE_DIR = "EXTERNAL_CACHE_DIR"
ENV_CACHE_TTL = "EXTERNAL_CACHE_TTL"
ENV_TIMEOUT = "EXTERNAL_TIMEOUT"
ENV_SOURCES = "EXTERNAL_SOURCES"
ENV_MAILTO = "EXTERNAL_CONTACT_MAIL"
ENV_S2_API_KEY = "EXTERNAL_S2_API_KEY"

_STATUS_NOT_FOUND = 404
_STATUS_THROTTLED = 429

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:")
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_ARXIV_RE = re.compile(r"^(?:arxiv:)?(\d{4}\.\d{4,5})(v\d+)?$", re.IGNORECASE)
_JATS_RE = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------
class ExternalError(Exception):
    """Base class for every failure this client can raise."""


class ExternalUnavailable(ExternalError):
    """A source could not be reached or answered 429/5xx.

    Callers MUST surface this. Reporting it as "no abstract" would turn
    "the source is down" into "this paper has no abstract".
    """


class ExternalNotFound(ExternalError):
    """The source answered 404 — the record is genuinely absent there."""


class ExternalRejected(ExternalError):
    """The answer is unusable: bad host, bad shape, or a DOI mismatch."""


class ExternalNoIdentifier(ExternalError):
    """No usable strong identifier (DOI / arXiv id) was supplied."""


class ExternalNotApplicable(ExternalError):
    """This source cannot answer for this kind of identifier at all.

    Distinct from "no abstract": OpenAlex and Crossref are only ever queried by
    DOI here, so an arXiv-only lookup never asked them anything. Counting an
    unasked source as "it had no abstract" would let a single throttled source
    masquerade as "this paper has no abstract" — measured on 2026-10-10, when
    Semantic Scholar answered 429 and the other two were silently marked empty.
    """


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------
def resolve_cache_dir(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Cache root: argument > ``EXTERNAL_CACHE_DIR`` > ``.data/external``."""
    candidate = explicit or os.environ.get(ENV_CACHE_DIR) or DEFAULT_CACHE_DIR
    return Path(candidate)


def resolve_timeout(explicit: float | None = None) -> float:
    """Per-request timeout: argument > ``EXTERNAL_TIMEOUT`` > 12s."""
    if explicit is not None:
        return float(explicit)
    raw = os.environ.get(ENV_TIMEOUT, "").strip()
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


def resolve_sources(explicit: Sequence[str] | None = None) -> tuple[str, ...]:
    """Enabled sources **in fallback order**: argument > ``EXTERNAL_SOURCES`` > default.

    Unknown names are dropped rather than silently ending up in a URL path.

    An explicitly empty sequence — or an ``EXTERNAL_SOURCES`` that names nothing
    valid — means **disabled**. The caller then reports the feature as
    unavailable, instead of the far worse outcome of quietly reporting every
    paper as having no abstract.
    """
    if explicit is not None:
        return tuple(name for name in explicit if name in SOURCE_LABELS)
    text = os.environ.get(ENV_SOURCES, "").strip()
    if not text:
        return DEFAULT_SOURCES
    return tuple(part.strip() for part in text.split(",") if part.strip() in SOURCE_LABELS)


def resolve_mailto(explicit: str | None = None) -> str | None:
    """Contact address for the OpenAlex/Crossref polite pools, if configured."""
    value = (explicit or os.environ.get(ENV_MAILTO) or "").strip()
    return value or None


def resolve_s2_api_key(explicit: str | None = None) -> str | None:
    """Optional Semantic Scholar API key.

    Without one, S2 serves from a small shared pool and answers **429** as soon
    as a few lookups run back to back (measured on this machine, 2026-10-10).
    The key is free and lifts that limit; without it, an arXiv-only lookup — for
    which S2 is the only applicable source — will honestly report itself as
    unavailable rather than claim the paper has no abstract.
    """
    value = (explicit or os.environ.get(ENV_S2_API_KEY) or "").strip()
    return value or None


def resolve_api_keys(s2_api_key: str | None = None) -> dict[str, str] | None:
    """Per-host API keys for the transport, or ``None`` when nothing is set."""
    key = resolve_s2_api_key(s2_api_key)
    return {"api.semanticscholar.org": key} if key else None


# ---------------------------------------------------------------------------
# identifiers
# ---------------------------------------------------------------------------
def normalize_doi(raw: str | None) -> str | None:
    """Lower-case a DOI and strip any resolver prefix. ``None`` if unusable.

    Normalising matters for the identity check: APIs echo DOIs in their own
    casing, and a case difference must not be mistaken for a different paper.
    """
    if not raw:
        return None
    text = str(raw).strip()
    lowered = text.lower()
    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    text = text.strip().strip("/").strip()
    text = urllib.parse.unquote(text)
    if not text or not _DOI_RE.match(text.lower()):
        return None
    return text.lower()


def normalize_arxiv(raw: str | None) -> str | None:
    """Return the bare arXiv id (``1706.03762``) or ``None``."""
    if not raw:
        return None
    match = _ARXIV_RE.match(str(raw).strip())
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ExternalRecord:
    """One abstract-bearing record from an external source.

    ``abstract`` is the source's own text, cleaned but **not summarised** — the
    point of this record is to hand the agent material it can actually read.
    """

    source: str
    doi: str
    title: str
    abstract: str
    year: int | None = None
    venue: str | None = None
    source_url: str | None = None
    fetched_at: str = ""

    def __post_init__(self) -> None:
        if self.source not in SOURCE_LABELS:
            raise ExternalRejected(f"unknown source {self.source!r}")
        if not self.abstract.strip():
            raise ExternalRejected("an ExternalRecord without an abstract is not a record")
        if not self.doi.strip():
            raise ExternalRejected("an ExternalRecord must carry the DOI it was matched by")

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS.get(self.source, self.source)

    @property
    def evidence_level(self) -> str:
        """Always ``abstract``: that is the whole reason this record exists."""
        return "abstract"

    def abstract_for_model(self, *, limit: int = MAX_ABSTRACT_CHARS) -> str:
        """The abstract as handed to a model: capped, with an explicit marker."""
        text = " ".join(self.abstract.split())
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + " …（摘要过长，已截断）"

    def evidence_ref(self, *, publication_id: str | None = None) -> dict[str, Any]:
        """Wire-shaped ``EvidenceRef`` (see ``packages/contracts/evidence.py``).

        ``verificationStatus`` is ``id_valid`` and not higher: the DOI resolved
        to a real record, which is all that can be asserted *before* someone
        checks whether the abstract supports a particular sentence.
        """
        payload: dict[str, Any] = {
            "sourceType": "external_record",
            "sourceId": f"doi:{self.doi}",
            "evidenceLevel": "abstract",
            "assertionStatus": "none",
            "verificationStatus": "id_valid",
            "evidenceText": self.abstract_for_model(),
            "locator": {"source": self.source, "url": self.source_url} if self.source_url else {"source": self.source},
        }
        if publication_id:
            payload["publicationId"] = publication_id
        return payload

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "doi": self.doi,
            "title": self.title,
            "abstract": self.abstract,
            "year": self.year,
            "venue": self.venue,
            "sourceUrl": self.source_url,
            "fetchedAt": self.fetched_at,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ExternalRecord":
        return cls(
            source=str(raw["source"]),
            doi=str(raw["doi"]),
            title=str(raw.get("title") or ""),
            abstract=str(raw.get("abstract") or ""),
            year=raw.get("year") if isinstance(raw.get("year"), int) else None,
            venue=raw.get("venue") or None,
            source_url=raw.get("sourceUrl") or None,
            fetched_at=str(raw.get("fetchedAt") or ""),
        )


# ---------------------------------------------------------------------------
# transport seam (injectable so tests run with no network)
# ---------------------------------------------------------------------------
class MetadataTransport(Protocol):
    """Minimal absolute-URL GET seam. Returns ``(status_code, raw_body_bytes)``."""

    def get(self, url: str) -> "tuple[int, bytes]":  # pragma: no cover
        ...


class _AllowListRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse any redirect that leaves :data:`ALLOWED_HOSTS`."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        host = (urllib.parse.urlsplit(newurl).hostname or "").lower()
        if host not in ALLOWED_HOSTS:
            raise ExternalRejected(f"redirect target not allowed: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpTransport:
    """``urllib`` transport with the ambient proxy explicitly disabled.

    ``urllib`` honours ``HTTP_PROXY``/``http_proxy`` from the environment, so a
    request to a public API would be routed through whatever proxy the host
    happens to export — non-deterministic, and on this machine the sandbox proxy
    answers 502. ``ProxyHandler({})`` (an *empty dict*, not ``None``: ``None``
    reads the environment) pins every request to a direct connection.
    """

    def __init__(
        self,
        *,
        timeout: float | None = None,
        user_agent: str = USER_AGENT,
        allowed_hosts: frozenset[str] = ALLOWED_HOSTS,
        opener: urllib.request.OpenerDirector | None = None,
        api_keys: Mapping[str, str] | None = None,
    ) -> None:
        self.timeout = resolve_timeout(timeout)
        self.user_agent = user_agent
        self.allowed_hosts = allowed_hosts
        # Keys are attached per host inside ``get`` so the transport seam stays
        # ``get(url) -> (status, body)`` for every stub in the test suite.
        self.api_keys = {str(host).lower(): str(key) for host, key in (api_keys or {}).items()}
        self._opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}),  # empty dict, NOT None
            _AllowListRedirect(),
        )

    def get(self, url: str) -> tuple[int, bytes]:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        if host not in self.allowed_hosts:
            raise ExternalRejected(f"host not allowed: {host or url!r}")
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        api_key = self.api_keys.get(host)
        if api_key:
            headers["x-api-key"] = api_key
        request = urllib.request.Request(url, headers=headers)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return int(response.status), response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:  # subclass of URLError — must come first
            # A 404 body is still a body; the client decides, not the transport.
            return int(exc.code), exc.read(MAX_RESPONSE_BYTES + 1) if hasattr(exc, "read") else b""
        except urllib.error.URLError as exc:
            raise ExternalUnavailable(f"cannot reach {host}: {exc.reason}") from exc
        except TimeoutError as exc:  # read-phase timeouts are bare TimeoutError
            raise ExternalUnavailable(f"timed out reading from {host}") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise ExternalUnavailable(f"transport error from {host}: {exc}") from exc


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------
class FileCache:
    """One JSON file per lookup key, with a TTL. Atomic writes, never fatal.

    The cache exists to keep a chatty agent off public rate limits, not as a
    source of truth: a corrupt or expired entry is simply a miss.
    """

    def __init__(self, root: str | os.PathLike[str], *, ttl_seconds: int | None = None) -> None:
        self.root = Path(root)
        self.ttl_seconds = DEFAULT_CACHE_TTL_SECONDS if ttl_seconds is None else int(ttl_seconds)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.root / f"{digest}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        stored_at = payload.get("storedAt")
        if not isinstance(stored_at, (int, float)) or time.time() - stored_at > self.ttl_seconds:
            return None
        record = payload.get("record")
        return record if isinstance(record, dict) else None

    def put(self, key: str, record: Mapping[str, Any]) -> None:
        path = self._path(key)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps({"storedAt": time.time(), "key": key, "record": dict(record)}, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(tmp, path)
        except OSError:
            # A cache that cannot be written is a slow cache, not a broken one.
            pass


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------
def _inverted_index_to_text(index: Mapping[str, Any] | None) -> str:
    """Rebuild OpenAlex ``abstract_inverted_index`` into readable text."""
    if not isinstance(index, Mapping) or not index:
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in index.items():
        if not isinstance(positions, (list, tuple)):
            continue
        for position in positions:
            if isinstance(position, int):
                positioned.append((position, str(word)))
    if not positioned:
        return ""
    positioned.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positioned)


def _strip_markup(text: str) -> str:
    """Crossref abstracts are JATS XML fragments; the reader wants plain text."""
    plain = _JATS_RE.sub(" ", str(text or ""))
    return " ".join(plain.split())


def _clean_abstract(text: str) -> str:
    return " ".join(str(text or "").split())


def _first_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and value and isinstance(value[0], str):
        return value[0]
    return ""


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------
class ExternalMetadataClient:
    """Look a paper up by DOI / arXiv id and return its abstract, if any."""

    def __init__(
        self,
        *,
        transport: MetadataTransport | None = None,
        sources: Sequence[str] | None = None,
        cache: FileCache | None = None,
        mailto: str | None = None,
        timeout: float | None = None,
        s2_api_key: str | None = None,
    ) -> None:
        self.transport = transport or HttpTransport(timeout=timeout, api_keys=resolve_api_keys(s2_api_key))
        self.sources = resolve_sources(sources)
        self.cache = cache
        self.mailto = resolve_mailto(mailto)

    # -- public --------------------------------------------------------------
    def lookup(self, *, doi: str | None = None, arxiv_id: str | None = None) -> ExternalRecord | None:
        """Return an abstract-bearing record, or ``None`` when none exists.

        Raises :class:`ExternalUnavailable` when a source was unreachable and no
        other source produced a definite answer — see the module docstring.
        """
        clean_doi = normalize_doi(doi)
        clean_arxiv = normalize_arxiv(arxiv_id)
        if not clean_doi and not clean_arxiv:
            raise ExternalNoIdentifier(
                "need a DOI or an exact arXiv id; title similarity must never be used to claim a record"
            )
        key = f"doi:{clean_doi}" if clean_doi else f"arxiv:{clean_arxiv}"

        if self.cache is not None:
            cached = self.cache.get(key)
            if cached:
                try:
                    return ExternalRecord.from_mapping(cached)
                except (KeyError, ExternalRejected):
                    pass  # a malformed entry is a miss

        indefinite: list[str] = []  # no trustworthy answer: unreachable, or a shape we reject
        no_abstract: list[str] = []  # the record exists there and carries no abstract
        absent: list[str] = []  # that particular source simply does not have it
        skipped: list[str] = []  # never asked: wrong identifier kind for that source
        for source in self.sources:
            try:
                record = self._try_source(source, doi=clean_doi, arxiv_id=clean_arxiv)
            except ExternalNotApplicable as exc:
                skipped.append(f"{source}:{exc}")
                continue
            except ExternalNotFound:
                absent.append(source)
                continue
            except ExternalUnavailable as exc:
                indefinite.append(f"{source}:unreachable({exc})")
                continue
            except ExternalRejected as exc:
                # The source answered, but not in a shape we trust (bad JSON, a
                # different DOI). That is **not** evidence that this paper has no
                # abstract — our parser may simply be wrong.
                indefinite.append(f"{source}:unusable({exc})")
                continue
            if record is not None:
                if self.cache is not None:
                    self.cache.put(key, record.to_dict())
                return record
            no_abstract.append(source)

        # "No abstract" is only verdictable when **nothing failed**: every
        # applicable source was asked and each reported the record either absent
        # or abstract-less. If any source was unreachable or answered in a shape
        # we refuse to trust, it could have been the one holding the abstract —
        # and "I could not look" must never be dressed up as "there is nothing".
        if not indefinite:
            return None
        raise ExternalUnavailable(
            "no source gave a trustworthy answer, so 'no abstract' cannot be concluded: "
            + "; ".join(indefinite)
            + (f" (asked: {', '.join(absent)} absent; {', '.join(no_abstract)} present-but-empty"
               f"; {', '.join(skipped)} skipped)" if (absent or no_abstract or skipped) else "")
        )

    def lookup_publication(self, *, doi: str | None = None, urls: Sequence[str] | None = None) -> ExternalRecord | None:
        """Convenience for KG records: try the DOI first, then any arXiv URL."""
        if normalize_doi(doi):
            return self.lookup(doi=doi)
        for candidate in urls or ():
            arxiv = normalize_arxiv(_arxiv_from_url(candidate))
            if arxiv:
                return self.lookup(arxiv_id=arxiv)
        raise ExternalNoIdentifier("record carries neither a DOI nor an arXiv id")

    # -- per source ----------------------------------------------------------
    def _try_source(self, source: str, *, doi: str | None, arxiv_id: str | None) -> ExternalRecord | None:
        if source == "semanticscholar":
            if not doi and not arxiv_id:
                raise ExternalNotApplicable("no DOI or arXiv id to look up")
            identifier = f"DOI:{doi}" if doi else f"ARXIV:{arxiv_id}"
            url = (
                "https://api.semanticscholar.org/graph/v1/paper/"
                f"{urllib.parse.quote(identifier, safe=":/")}"
                "?fields=title,abstract,year,venue,externalIds"
            )
            payload = self._fetch_json(url, source)
            return self._parse_semanticscholar(payload, doi=doi, arxiv_id=arxiv_id)
        if source == "openalex":
            if not doi:
                raise ExternalNotApplicable("openalex is queried by DOI only")
            target = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(doi, safe="/")}"
            payload = self._fetch_json(self._with_mailto(target), source)
            return self._parse_openalex(payload, doi)
        if source == "crossref":
            if not doi:
                raise ExternalNotApplicable("crossref is queried by DOI only")
            target = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe="/")}"
            payload = self._fetch_json(self._with_mailto(target), source)
            return self._parse_crossref(payload, doi)
        return None

    # -- plumbing ------------------------------------------------------------
    def _with_mailto(self, url: str) -> str:
        if not self.mailto:
            return url
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}mailto={urllib.parse.quote(self.mailto)}"

    def _fetch_json(self, url: str, source: str) -> Any:
        status, body = self.transport.get(url)
        if status == _STATUS_NOT_FOUND:
            raise ExternalNotFound(f"{source} has no record for this identifier")
        if status == _STATUS_THROTTLED:
            hint = (
                " (Semantic Scholar's shared pool is tiny without a key; set EXTERNAL_S2_API_KEY)"
                if source == "semanticscholar"
                else ""
            )
            raise ExternalUnavailable(f"{source} answered HTTP 429 (rate limited){hint}")
        if status >= 500:
            raise ExternalUnavailable(f"{source} answered HTTP {status}")
        if status != 200:
            raise ExternalRejected(f"{source} answered HTTP {status}")
        if len(body) > MAX_RESPONSE_BYTES:
            raise ExternalRejected(f"{source} response exceeds {MAX_RESPONSE_BYTES} bytes")
        try:
            return json.loads(body.decode("utf-8", "replace"))
        except ValueError as exc:
            raise ExternalRejected(f"{source} did not return JSON: {exc}") from exc

    def _finish(
        self,
        source: str,
        *,
        doi: str | None,
        title: str,
        abstract: str,
        year: Any,
        venue: Any,
        url: str | None,
    ) -> ExternalRecord | None:
        text = _clean_abstract(abstract)
        if not text:
            return None
        if not title:
            raise ExternalRejected(f"{source} returned an abstract with no title to anchor it")
        return ExternalRecord(
            source=source,
            doi=doi or "",
            title=title,
            abstract=text,
            year=year if isinstance(year, int) and 1800 < year < 2100 else None,
            venue=str(venue).strip() if venue else None,
            source_url=url,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    def _parse_semanticscholar(self, payload: Any, *, doi: str | None, arxiv_id: str | None) -> ExternalRecord | None:
        if not isinstance(payload, Mapping):
            raise ExternalRejected("semanticscholar returned a non-object payload")
        if payload.get("error"):
            raise ExternalNotFound(f"semanticscholar error: {payload.get('error')}")
        title = str(payload.get("title") or "")
        if not title:
            raise ExternalRejected("semanticscholar record has no title (shape mismatch)")
        externals = payload.get("externalIds") if isinstance(payload.get("externalIds"), Mapping) else {}
        # Identity check: the DOI we get back must be the DOI we asked for.
        returned_doi = normalize_doi(externals.get("DOI")) or normalize_doi(externals.get("doi"))
        if doi and returned_doi and returned_doi != doi:
            raise ExternalRejected(f"semanticscholar returned DOI {returned_doi} for a lookup of {doi}")
        if arxiv_id:
            returned_arxiv = normalize_arxiv(externals.get("ArXiv") or externals.get("arxiv"))
            if returned_arxiv and returned_arxiv != arxiv_id:
                raise ExternalRejected(f"semanticscholar returned arXiv {returned_arxiv} for a lookup of {arxiv_id}")
        # An arXiv record often carries no DOI, and a record must never be keyed
        # by "nothing". 10.48550/arXiv.<id> is the canonical arXiv DOI, so the
        # evidence ref stays a stable, checkable identifier either way.
        fallback_doi = f"10.48550/arxiv.{arxiv_id}" if arxiv_id else ""
        return self._finish(
            "semanticscholar",
            doi=doi or returned_doi or fallback_doi,
            title=title,
            abstract=str(payload.get("abstract") or ""),
            year=payload.get("year"),
            venue=payload.get("venue"),
            url=f"https://www.semanticscholar.org/paper/{payload.get('paperId')}" if payload.get("paperId") else None,
        )

    def _parse_openalex(self, payload: Any, doi: str) -> ExternalRecord | None:
        if not isinstance(payload, Mapping):
            raise ExternalRejected("openalex returned a non-object payload")
        if payload.get("error"):
            raise ExternalNotFound(f"openalex error: {payload.get('error')}")
        returned_doi = normalize_doi(payload.get("doi"))
        if returned_doi and returned_doi != doi:
            raise ExternalRejected(f"openalex returned DOI {returned_doi} for a lookup of {doi}")
        title = str(payload.get("title") or payload.get("display_name") or "")
        venue = None
        location = payload.get("primary_location")
        if isinstance(location, Mapping):
            source_info = location.get("source")
            if isinstance(source_info, Mapping):
                venue = source_info.get("display_name")
        return self._finish(
            "openalex",
            doi=doi,
            title=title,
            abstract=_inverted_index_to_text(payload.get("abstract_inverted_index")),
            year=payload.get("publication_year"),
            venue=venue,
            url=payload.get("id") if isinstance(payload.get("id"), str) else None,
        )

    def _parse_crossref(self, payload: Any, doi: str) -> ExternalRecord | None:
        if not isinstance(payload, Mapping):
            raise ExternalRejected("crossref returned a non-object payload")
        message = payload.get("message")
        if not isinstance(message, Mapping):
            raise ExternalRejected("crossref payload has no 'message' object (shape mismatch)")
        returned_doi = normalize_doi(message.get("DOI"))
        if returned_doi and returned_doi != doi:
            raise ExternalRejected(f"crossref returned DOI {returned_doi} for a lookup of {doi}")
        container = _first_str(message.get("container-title"))
        return self._finish(
            "crossref",
            doi=doi,
            title=_first_str(message.get("title")),
            abstract=_strip_markup(str(message.get("abstract") or "")),
            year=_crossref_year(message),
            venue=container or None,
            url=str(message.get("URL") or "") or None,
        )


def _crossref_year(message: Mapping[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        block = message.get(key)
        if isinstance(block, Mapping):
            parts = block.get("date-parts")
            if isinstance(parts, (list, tuple)) and parts and isinstance(parts[0], (list, tuple)) and parts[0]:
                year = parts[0][0]
                if isinstance(year, int):
                    return year
    return None


def _arxiv_from_url(url: str) -> str | None:
    """Extract an arXiv id from an ``arxiv.org/abs/<id>`` style URL."""
    if not url:
        return None
    host = (urllib.parse.urlsplit(str(url)).hostname or "").lower()
    if host not in ("arxiv.org", "www.arxiv.org"):
        return None
    path = urllib.parse.urlsplit(str(url)).path
    for marker in ("/abs/", "/pdf/"):
        if marker in path:
            tail = path.split(marker, 1)[1]
            if tail.endswith(".pdf"):
                tail = tail[:-4]
            # Strip a version suffix: an id lookup wants the bare identifier,
            # and ``ARXIV:1706.03762v2`` is not the shape Semantic Scholar wants.
            return normalize_arxiv(tail)
    return None

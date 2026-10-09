"""Hardened full-text fetcher: allow-list hosts, no ambient proxy, PDF magic.

The rules exist because the fetcher runs on untrusted input (URLs that come
from metadata APIs) inside a machine that may carry ambient proxy settings:

* **proxy**: :func:`build_opener` installs ``ProxyHandler({})`` — an explicitly
  *empty* proxy map. The ambient ``HTTP_PROXY``/``HTTPS_PROXY`` of the host
  must not route an intranet-bound fetch through some unrelated proxy
  (regression-tested with a poisoned environment).
* **host allow-list**: both the initial URL and every redirect target must be
  on :data:`ALLOWED_HOSTS`; anything else is :class:`FetchRejected`.
* **magic + cap**: the response must start with ``%PDF-`` and fit in
  ``max_bytes``; both violations are :class:`FetchRejected` (the fetch itself
  worked, the answer is unusable).
* **transport errors** map to :class:`FetchFailed` (retryable) — note the
  exception order: ``HTTPError`` is a subclass of ``URLError``, and read-phase
  timeouts surface as bare ``TimeoutError``, not ``URLError``.
"""
from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from urllib.parse import urlsplit

__all__ = [
    "ALLOWED_HOSTS",
    "USER_AGENT",
    "build_opener",
    "fetch_pdf",
    "FetchFailed",
    "FetchRejected",
]

#: Hosts whose PDFs we are willing to fetch. The OpenAlex / Semantic Scholar
#: *metadata* APIs belong to the discovery step (they hand back landing pages
#: and arXiv ids); the bytes themselves come from these hosts.
ALLOWED_HOSTS = {
    "arxiv.org",
    "www.arxiv.org",
    "export.arxiv.org",
}

USER_AGENT = "noesis-research-paper-reader/0.1"

_MAX_REDIRECTS = 3


class FetchRejected(ValueError):
    """The answer is unusable (bad host, wrong type, bad magic, over cap)."""


class FetchFailed(Exception):
    """The transport failed (timeout, reset, HTTP error). Retryable."""


def _host_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.rstrip(".")


class _AllowListRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that re-checks the allow-list on every hop."""

    def __init__(self, max_redirects: int = _MAX_REDIRECTS) -> None:
        super().__init__()
        self._max = max_redirects

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        if _host_of(newurl) not in ALLOWED_HOSTS:
            raise FetchRejected(f"redirect target not allowed: {newurl}")
        count = getattr(req, "_noesis_redirects", 0) + 1
        if count > self._max:
            raise FetchRejected(f"more than {self._max} redirects")
        req._noesis_redirects = count  # type: ignore[attr-defined]
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener() -> urllib.request.OpenerDirector:
    """An opener with the ambient proxy explicitly disabled and capped redirects."""
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),  # empty dict, NOT None — None reads the environment
        _AllowListRedirectHandler(),
    )


def fetch_pdf(
    url: str,
    *,
    opener: urllib.request.OpenerDirector | None = None,
    timeout: float = 20.0,
    max_bytes: int = 100 * 1024 * 1024,
) -> bytes:
    """Download one PDF, enforcing allow-list host, type, magic, and size cap."""
    if _host_of(url) not in ALLOWED_HOSTS:
        raise FetchRejected(f"host not allowed: {_host_of(url)}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    active = opener or build_opener()
    try:
        with active.open(request, timeout=timeout) as response:
            content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if content_type not in ("application/pdf", "application/octet-stream", ""):
                raise FetchRejected(f"unexpected content-type {content_type!r}")
            data = response.read(max_bytes + 1)
    except FetchRejected:
        raise
    except urllib.error.HTTPError as exc:  # subclass of URLError — must come first
        raise FetchFailed(f"HTTP {exc.code} from {_host_of(url)}") from exc
    except urllib.error.URLError as exc:
        raise FetchFailed(f"cannot reach {_host_of(url)}: {exc.reason}") from exc
    except TimeoutError as exc:  # read-phase timeouts are bare TimeoutError
        raise FetchFailed(f"timed out reading from {_host_of(url)}") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise FetchFailed(f"transport error from {_host_of(url)}: {exc}") from exc

    if len(data) > max_bytes:
        raise FetchRejected(f"file exceeds the {max_bytes} byte cap")
    if not data.startswith(b"%PDF-"):
        raise FetchRejected("not a PDF: missing %PDF- magic")
    return data

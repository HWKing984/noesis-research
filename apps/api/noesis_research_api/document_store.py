"""Local full-text store: one JSON record per publication + content-addressed blobs.

Layout under the store root (``.data/documents/`` by default, git-ignored)::

    records/<stable-hash>.json     a DocumentRef wire payload
    blobs/<sha256>.pdf             the cached file itself

Rules the store enforces (beyond :mod:`packages.contracts.document`):

* uploads and fetches must both pass the ``%PDF-`` magic check and the size
  cap *before* any state is written — a rejected file leaves no trace;
* state changes go through the contract's transition table, so "we failed"
  can never be silently relabelled "it does not exist";
* blobs are content-addressed by SHA-256, which is also what makes a citation
  to this document version-stable.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from packages.contracts.document import TRANSITIONS, DocumentError, DocumentRef

_PDF_MAGIC = b"%PDF-"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class DocumentRejected(ValueError):
    """The bytes are not a lawful PDF (bad magic, or over the size cap)."""


def document_id_for(publication_id: str) -> str:
    """A stable, filesystem-safe document id derived from the DBLP key."""
    digest = hashlib.sha256(publication_id.encode("utf-8")).hexdigest()
    return f"doc-{digest[:16]}"


def _safe_part(value: str) -> str:
    part = re.sub(r"[^A-Za-z0-9._-]", "_", value)
    if not part or part in {".", ".."}:
        raise DocumentError(f"unsafe path fragment: {value!r}")
    return part


class DocumentStore:
    def __init__(self, root: Path, *, max_bytes: int = 100 * 1024 * 1024) -> None:
        self.root = Path(root)
        self.records = self.root / "records"
        self.blobs = self.root / "blobs"
        self.max_bytes = max_bytes
        self.records.mkdir(parents=True, exist_ok=True)
        self.blobs.mkdir(parents=True, exist_ok=True)

    # -- records -------------------------------------------------------------
    def _record_path(self, publication_id: str) -> Path:
        return self.records / (_safe_part(document_id_for(publication_id)) + ".json")

    def load(self, publication_id: str) -> DocumentRef | None:
        path = self._record_path(publication_id)
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return DocumentRef.from_mapping(raw)

    def save(self, ref: DocumentRef) -> DocumentRef:
        path = self._record_path(_publication_of(ref))
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(ref.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
        return ref

    # -- status helpers ------------------------------------------------------
    def status_of(self, publication_id: str) -> DocumentRef | None:
        return self.load(publication_id)

    def _transition(self, current: DocumentRef | None, publication_id: str, new_status: str, **kwargs) -> DocumentRef:
        allowed = TRANSITIONS.get(current.status if current else "none", ())
        if new_status not in allowed:
            raise DocumentError(
                f"illegal transition {(current.status if current else 'none')!r} -> {new_status!r}; "
                f"allowed: {allowed}"
            )
        base = {
            "document_id": document_id_for(publication_id),
            "publication_id": publication_id,
        }
        if current is not None:
            return current.transition(new_status, **kwargs)
        return DocumentRef(status=new_status, **base, **kwargs)

    # -- ingest --------------------------------------------------------------
    def ingest(
        self,
        publication_id: str,
        data: bytes,
        *,
        source_kind: str,
        source_url: str | None = None,
    ) -> DocumentRef:
        """Validate bytes, cache the blob, and move the record to ``available``."""
        if not isinstance(data, bytes) or not data:
            raise DocumentRejected("empty upload")
        if len(data) > self.max_bytes:
            raise DocumentRejected(f"file exceeds the {self.max_bytes} byte cap")
        if not data.startswith(_PDF_MAGIC):
            raise DocumentRejected("not a PDF: missing %PDF- magic")
        sha256 = hashlib.sha256(data).hexdigest()
        blob = self.blobs / f"{sha256}.pdf"
        if not blob.is_file():
            tmp = blob.with_suffix(".pdf.tmp")
            tmp.write_bytes(data)
            os.replace(tmp, blob)
        current = self.load(publication_id)
        ref = self._transition(
            current,
            publication_id,
            "available",
            source_kind=source_kind,
            sha256=sha256,
            size_bytes=len(data),
            detail="",
        )
        ref = DocumentRef(
            document_id=ref.document_id,
            status=ref.status,
            publication_id=ref.publication_id,
            source_kind=ref.source_kind,
            source_url=source_url or ref.source_url,
            sha256=ref.sha256,
            size_bytes=ref.size_bytes,
            detail="",
            meta=ref.meta,
        )
        return self.save(ref)

    def mark_failed(self, publication_id: str, *, detail: str, source_url: str | None = None) -> DocumentRef:
        current = self.load(publication_id)
        ref = self._transition(current, publication_id, "fetch_failed", detail=detail)
        if source_url and not ref.source_url:
            ref = DocumentRef(**{**ref.__dict__, "source_url": source_url})
        return self.save(ref)

    def mark_no_oa(self, publication_id: str, *, detail: str, source_url: str | None = None) -> DocumentRef:
        current = self.load(publication_id)
        ref = self._transition(current, publication_id, "no_oa_found", detail=detail)
        if source_url and not ref.source_url:
            ref = DocumentRef(**{**ref.__dict__, "source_url": source_url})
        return self.save(ref)

    def mark_publisher_only(self, publication_id: str, *, source_url: str) -> DocumentRef:
        current = self.load(publication_id)
        ref = self._transition(
            current,
            publication_id,
            "publisher_link_only",
            source_url=source_url,
            detail="no OA copy; publisher landing page only",
        )
        return self.save(ref)

    # -- blobs ---------------------------------------------------------------
    def blob_path(self, sha256: str) -> Path:
        if not _HEX64.match(sha256):
            raise DocumentError("sha256 must be 64 hex chars")
        return self.blobs / f"{sha256}.pdf"

    def open_blob(self, sha256: str) -> bytes:
        path = self.blob_path(sha256)
        if not path.is_file():
            raise FileNotFoundError(sha256)
        return path.read_bytes()


def _publication_of(ref: DocumentRef) -> str:
    if not ref.publication_id:
        raise DocumentError("stored records must name their publication")
    return ref.publication_id

"""Document endpoints: status / fetch / upload / file (with Range).

The state machine lives in :mod:`packages.contracts.document`; this module is
the HTTP surface over it. One behaviour matters more than the rest: **a failed
fetch is still a completed investigation** — the endpoint answers 200 with the
``fetch_failed`` ref (or the corrected ``no_oa_found``), never 5xx-without-
state. The caller always sees the machine's honest current state.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from fastapi import APIRouter, File, Request, Response
from pydantic import BaseModel

from packages.contracts.document import DocumentError, DocumentRef

from .document_store import DocumentRejected, DocumentStore
from .fulltext_fetch import FetchFailed, FetchRejected, fetch_pdf

router = APIRouter(prefix="/api", tags=["documents"])

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


class FetchBody(BaseModel):
    sourceUrl: str


def _store(request: Request) -> DocumentStore:
    return request.app.state.documents


def _fetcher(request: Request) -> Callable[..., bytes]:
    return getattr(request.app.state, "fetch_pdf", fetch_pdf)


def _none_payload(publication_id: str) -> dict[str, Any]:
    from .document_store import document_id_for

    return {
        "documentId": document_id_for(publication_id),
        "publicationId": publication_id,
        "status": "none",
        "detail": "full-text availability has not been investigated yet",
    }


@router.get("/documents/{publication_id:path}/status")
def document_status(request: Request, publication_id: str) -> dict[str, Any]:
    ref = _store(request).load(publication_id)
    return ref.to_dict() if ref is not None else _none_payload(publication_id)


@router.post("/documents/{publication_id:path}/fetch")
def fetch_document(request: Request, publication_id: str, body: FetchBody) -> dict[str, Any]:
    store = _store(request)
    # 幂等：已有缓存就直接返回当前 ref，不重复下载。
    # （`available` 是状态机终态，重复 fetch 若走下载→失败分支会撞非法转移。）
    current = store.load(publication_id)
    if current is not None and current.status == "available":
        return {**current.to_dict(), "fetched": False, "detail": "already cached; fetch skipped"}
    try:
        data = _fetcher(request)(body.sourceUrl)
    except FetchRejected as exc:
        # The source answered but the answer is unusable: this is a completed
        # investigation with a retryable failure, not a client error.
        return {**store.mark_failed(publication_id, detail=str(exc), source_url=body.sourceUrl).to_dict(), "fetched": False}
    except FetchFailed as exc:
        return {**store.mark_failed(publication_id, detail=str(exc), source_url=body.sourceUrl).to_dict(), "fetched": False}
    ref = store.ingest(publication_id, data, source_kind="arxiv", source_url=body.sourceUrl)
    return {**ref.to_dict(), "fetched": True}


@router.post("/documents/{publication_id:path}/upload", status_code=201, response_model=None)
def upload_document(request: Request, publication_id: str, file: bytes = File(...)) -> dict[str, Any] | Response:
    try:
        ref = _store(request).ingest(publication_id, file, source_kind="upload")
    except DocumentRejected as exc:
        return Response(
            status_code=422,
            content='{"error":{"code":"invalid_document","message":"' + str(exc).replace('"', "'") + '"}}',
            media_type="application/json",
        )
    return ref.to_dict()


@router.get("/documents/{publication_id:path}/file")
def document_file(request: Request, publication_id: str) -> Response:
    store = _store(request)
    ref = store.load(publication_id)
    if ref is None:
        return _json_error(404, "not_found", "no document record for this publication")
    if ref.status != "available" or not ref.sha256:
        return _json_error_with_document(
            409, "document_not_available", "full text is not cached for this publication", ref
        )
    try:
        data = store.open_blob(ref.sha256)
    except FileNotFoundError:
        return _json_error(404, "not_found", "blob missing despite available record; refetch required")
    return _with_range(data, request.headers.get("range") or "")


def _json_error_with_document(status_code: int, code: str, message: str, ref: DocumentRef) -> Response:
    import json as _json

    return Response(
        status_code=status_code,
        content=_json.dumps({"error": {"code": code, "message": message, "document": ref.to_dict()}}),
        media_type="application/json",
    )


def _json_error(status_code: int, code: str, message: str) -> Response:
    import json as _json

    return Response(
        status_code=status_code,
        content=_json.dumps({"error": {"code": code, "message": message}}),
        media_type="application/json",
    )


def _with_range(data: bytes, range_header: str) -> Response:
    headers = {"Accept-Ranges": "bytes"}
    if range_header:
        match = _RANGE.match(range_header.strip())
        if match:
            start_raw, end_raw = match.groups()
            size = len(data)
            if start_raw == "" and end_raw != "":
                # suffix range: last N bytes
                count = min(int(end_raw), size)
                start, end = size - count, size - 1
            else:
                start = int(start_raw)
                end = min(int(end_raw), size - 1) if end_raw else size - 1
            if start >= size or start > end:
                return Response(
                    status_code=416,
                    headers={**headers, "Content-Range": f"bytes */{size}"},
                )
            chunk = data[start : end + 1]
            return Response(
                status_code=206,
                content=chunk,
                media_type="application/pdf",
                headers={**headers, "Content-Range": f"bytes {start}-{end}/{size}"},
            )
    return Response(content=data, media_type="application/pdf", headers=headers)

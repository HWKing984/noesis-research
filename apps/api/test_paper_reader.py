"""HTTP-level tests for the paper-reader endpoints (status / fetch / upload / file).

Same discipline as ``test_api.py``: the real app, the real store, the real
state machine — only the network socket under the fetcher is replaced, and the
fetcher itself additionally gets a real-socket regression against a poisoned
proxy environment.

Run (needs fastapi + httpx):
    python -m unittest discover -s apps/api -t apps/api -v
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_IMPORT_ERROR: str | None = None
try:
    from fastapi.testclient import TestClient

    from noesis_research_api import create_app
    from noesis_research_api.app import Settings
    from noesis_research_api.document_store import DocumentStore
    from noesis_research_api.fulltext_fetch import FetchFailed, FetchRejected, fetch_pdf
except Exception as exc:  # pragma: no cover - exercised by the core CI job
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

if _IMPORT_ERROR is not None:
    raise unittest.SkipTest(
        f"fastapi/httpx not installed ({_IMPORT_ERROR}); install with: pip install -r apps/api/requirements.txt"
    )

PINNED_GRAPH = "ai-literature-ed16399925fac2a599ed"
PUB = "conf/nips/VaswaniSPUJGKP17"
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class FakeTransport:
    def __init__(self, routes: dict[str, list[tuple[int, bytes]]]) -> None:
        self._routes = {path: list(responses) for path, responses in routes.items()}

    def get(self, path: str, params):  # noqa: ANN001
        queue = self._routes.get(path)
        if not queue:
            raise AssertionError(f"no stubbed response for {path}")
        return queue.pop(0) if len(queue) > 1 else queue[0]


def build_client(
    fetcher=None,
    *,
    store: DocumentStore | None = None,
    max_store_bytes: int | None = None,
):
    from kg_client import KGClient

    root = Path(tempfile.mkdtemp(prefix="paper-reader-test-"))
    effective_store = store or (
        DocumentStore(root, max_bytes=max_store_bytes) if max_store_bytes else DocumentStore(root)
    )
    transport = FakeTransport({
        "/api/health": [(200, body({
            "data": {"status": "ready", "graphId": PINNED_GRAPH, "source": "live_neo4j",
                     "scope": {"bibliographyTitles": 1, "modelTitles": 1, "rejectedNERTitles": 0,
                               "candidateAssertions": 0},
                     "aliasVersion": "v4"},
            "meta": {"graphId": PINNED_GRAPH},
        }))],
    })
    client_obj = KGClient("http://stub", transport=transport, expected_graph_id=PINNED_GRAPH)
    app = create_app(
        settings=Settings(base_url="http://stub", expected_graph_id=PINNED_GRAPH, timeout=5.0),
        kg_client=client_obj,
        document_store=effective_store,
    )
    if fetcher is not None:
        app.state.fetch_pdf = fetcher
    return TestClient(app), effective_store


class StatusTests(unittest.TestCase):
    def test_uninvestigated_publication_reports_none(self) -> None:
        client, _ = build_client()
        response = client.get(f"/api/documents/{PUB}/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "none")
        self.assertEqual(payload["publicationId"], PUB)
        self.assertNotIn("sha256", payload)


class UploadTests(unittest.TestCase):
    def test_upload_valid_pdf_becomes_available_and_persists(self) -> None:
        client, store = build_client()
        response = client.post(f"/api/documents/{PUB}/upload", files={"file": ("a.pdf", PDF_BYTES, "application/pdf")})
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["status"], "available")
        self.assertEqual(payload["sourceKind"], "upload")
        self.assertEqual(payload["sha256"], hashlib.sha256(PDF_BYTES).hexdigest())
        self.assertEqual(payload["sizeBytes"], len(PDF_BYTES))
        # persisted
        again = client.get(f"/api/documents/{PUB}/status")
        self.assertEqual(again.json()["status"], "available")

    def test_upload_rejects_non_pdf_without_leaving_a_state(self) -> None:
        client, store = build_client()
        response = client.post(f"/api/documents/{PUB}/upload", files={"file": ("a.pdf", b"<html>not a pdf</html>", "application/pdf")})
        self.assertEqual(response.status_code, 422)
        self.assertIn("invalid_document", response.text)
        self.assertIsNone(store.load(PUB))

    def test_upload_over_cap_is_rejected(self) -> None:
        client, _ = build_client(max_store_bytes=16)
        response = client.post(f"/api/documents/{PUB}/upload", files={"file": ("a.pdf", PDF_BYTES, "application/pdf")})
        self.assertEqual(response.status_code, 422)


class FileTests(unittest.TestCase):
    def _seed(self) -> tuple[TestClient, DocumentStore]:
        client, store = build_client()
        client.post(f"/api/documents/{PUB}/upload", files={"file": ("a.pdf", PDF_BYTES, "application/pdf")})
        return client, store

    def test_file_serves_cached_pdf(self) -> None:
        client, _ = self._seed()
        response = client.get(f"/api/documents/{PUB}/file")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertEqual(response.headers["accept-ranges"], "bytes")

    def test_range_request_returns_206_slice(self) -> None:
        client, _ = self._seed()
        response = client.get(f"/api/documents/{PUB}/file", headers={"Range": "bytes=0-4"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, PDF_BYTES[0:5])
        self.assertTrue(response.headers["content-range"].startswith("bytes 0-4/"))
        # suffix range
        tail = client.get(f"/api/documents/{PUB}/file", headers={"Range": "bytes=-5"})
        self.assertEqual(tail.status_code, 206)
        self.assertEqual(tail.content, PDF_BYTES[-5:])

    def test_out_of_range_is_416(self) -> None:
        client, _ = self._seed()
        response = client.get(f"/api/documents/{PUB}/file", headers={"Range": f"bytes={len(PDF_BYTES) + 10}-"})
        self.assertEqual(response.status_code, 416)

    def test_file_without_record_is_404(self) -> None:
        client, _ = build_client()
        response = client.get(f"/api/documents/{PUB}/file")
        self.assertEqual(response.status_code, 404)

    def test_file_on_non_available_record_is_409_with_state(self) -> None:
        client, store = build_client()
        store.mark_no_oa(PUB, detail="searched: no OA copy")
        response = client.get(f"/api/documents/{PUB}/file")
        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "document_not_available")
        self.assertEqual(payload["error"]["document"]["status"], "no_oa_found")


class FetchTests(unittest.TestCase):
    def test_successful_fetch_is_200_available(self) -> None:
        client, _ = build_client(fetcher=lambda url: PDF_BYTES)
        response = client.post(f"/api/documents/{PUB}/fetch", json={"sourceUrl": "https://arxiv.org/pdf/1706.03762"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["fetched"])
        self.assertEqual(payload["status"], "available")
        self.assertEqual(payload["sha256"], hashlib.sha256(PDF_BYTES).hexdigest())

    def test_rejected_fetch_lands_on_fetch_failed_not_error(self) -> None:
        # The investigation completed; its conclusion is "this source gave us
        # nothing usable". That is a state, not a 5xx.
        def bad_fetch(url: str) -> bytes:
            raise FetchRejected("not a PDF: missing %PDF- magic")

        client, _ = build_client(fetcher=bad_fetch)
        response = client.post(f"/api/documents/{PUB}/fetch", json={"sourceUrl": "https://arxiv.org/pdf/1706.03762"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["fetched"])
        self.assertEqual(payload["status"], "fetch_failed")
        self.assertIn("%PDF-", payload["detail"])

    def test_transport_failure_lands_on_fetch_failed(self) -> None:
        def dead_fetch(url: str) -> bytes:
            raise FetchFailed("timed out reading from arxiv.org")

        client, _ = build_client(fetcher=dead_fetch)
        response = client.post(f"/api/documents/{PUB}/fetch", json={"sourceUrl": "https://arxiv.org/pdf/x"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "fetch_failed")

    def test_retry_after_failure_can_become_available(self) -> None:
        attempts = {"n": 0}

        def flaky(url: str) -> bytes:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise FetchFailed("timeout")
            return PDF_BYTES

        client, _ = build_client(fetcher=flaky)
        first = client.post(f"/api/documents/{PUB}/fetch", json={"sourceUrl": "https://arxiv.org/pdf/x"})
        self.assertEqual(first.json()["status"], "fetch_failed")
        second = client.post(f"/api/documents/{PUB}/fetch", json={"sourceUrl": "https://arxiv.org/pdf/x"})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "available")

    def test_no_oa_found_can_still_recover_via_fetch_or_upload(self) -> None:
        client, store = build_client(fetcher=lambda url: PDF_BYTES)
        store.mark_no_oa(PUB, detail="searched: no OA copy")
        response = client.post(f"/api/documents/{PUB}/fetch", json={"sourceUrl": "https://arxiv.org/pdf/x"})
        self.assertEqual(response.json()["status"], "available")

    def test_fetch_on_available_is_idempotent_and_never_5xx(self) -> None:
        # available 是状态机终态：重复 fetch（含白名单外来源）必须幂等返回，
        # 不能走下载→失败分支撞非法转移。
        calls = {"n": 0}

        def counting(url: str) -> bytes:
            calls["n"] += 1
            return PDF_BYTES

        client, store = build_client(fetcher=counting)
        first = client.post(f"/api/documents/{PUB}/fetch", json={"sourceUrl": "https://arxiv.org/pdf/x"})
        self.assertEqual(first.json()["status"], "available")
        again = client.post(f"/api/documents/{PUB}/fetch", json={"sourceUrl": "https://arxiv.org/pdf/x"})
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["status"], "available")
        self.assertFalse(again.json()["fetched"])
        self.assertEqual(calls["n"], 1, "已缓存的文档不应再触发下载")
        blocked = client.post(f"/api/documents/{PUB}/fetch", json={"sourceUrl": "https://evil.example.com/x.pdf"})
        self.assertEqual(blocked.status_code, 200)
        self.assertEqual(blocked.json()["status"], "available")


class FetcherUnitTests(unittest.TestCase):
    """Real-socket tests for the fetcher itself (allow-list + poisoned proxy)."""

    def _serve(self, payload: bytes, content_type: str = "application/pdf") -> HTTPServer:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args) -> None:  # noqa: ANN002
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def test_poisoned_proxy_does_not_hijack_the_fetch(self) -> None:
        # kg_client regression, replayed here: a poisoned ambient HTTP_PROXY
        # must not route an intranet-bound fetch into a dead proxy.
        from unittest.mock import patch

        server = self._serve(PDF_BYTES)
        try:
            url = f"http://127.0.0.1:{server.server_port}/paper.pdf"
            poisoned = dict(os.environ)
            os.environ["HTTP_PROXY"] = "http://127.0.0.1:1"
            os.environ["HTTPS_PROXY"] = "http://127.0.0.1:1"
            os.environ["http_proxy"] = "http://127.0.0.1:1"
            os.environ["https_proxy"] = "http://127.0.0.1:1"
            try:
                with patch("noesis_research_api.fulltext_fetch.ALLOWED_HOSTS", {"127.0.0.1"}):
                    data = fetch_pdf(url, timeout=5.0)
            finally:
                os.environ.clear()
                os.environ.update(poisoned)
            self.assertTrue(data.startswith(b"%PDF-"))
        finally:
            server.shutdown()

    def test_allow_list_rejects_other_hosts(self) -> None:
        server = self._serve(PDF_BYTES)
        try:
            url = f"http://127.0.0.1:{server.server_port}/paper.pdf"
            with self.assertRaises(FetchRejected):
                fetch_pdf(url, timeout=5.0)
        finally:
            server.shutdown()

    def test_non_pdf_magic_is_rejected_even_with_pdf_content_type(self) -> None:
        server = self._serve(b"<html>landing page</html>")
        try:
            from unittest.mock import patch

            with patch(
                "noesis_research_api.fulltext_fetch.ALLOWED_HOSTS",
                {"127.0.0.1"},
            ):
                url = f"http://127.0.0.1:{server.server_port}/paper.pdf"
                with self.assertRaises(FetchRejected):
                    fetch_pdf(url, timeout=5.0)
        finally:
            server.shutdown()

    def test_transport_failure_maps_to_fetch_failed_not_urLError(self) -> None:
        # Dead port + allow-listed host is impossible with the real allow-list,
        # so simulate the resolver side: point at a closed port on an allowed
        # host by patching the allow-list — the point is the exception mapping.
        from unittest.mock import patch

        with patch("noesis_research_api.fulltext_fetch.ALLOWED_HOSTS", {"127.0.0.1"}):
            url = "http://127.0.0.1:1/paper.pdf"
            with self.assertRaises(FetchFailed):
                fetch_pdf(url, timeout=2.0)


if __name__ == "__main__":
    unittest.main()

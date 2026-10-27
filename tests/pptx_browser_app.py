"""Explicit browser QA harness. Only synthetic Confluence responses."""
from pathlib import Path
import httpx
from backend.app.main import create_app
from backend.app.confluence.client import ConfluenceClient
from tests.test_confluence_jobs import TestSecrets, handler
from tests.test_pptx import presentation_bytes

QA_DIR = Path(__file__).resolve().parents[1] / "output" / "pptx-browser"


def response(request):
    if request.headers.get("authorization") != "Bearer qa-only-token": return httpx.Response(401)
    if request.url.path.endswith("/child/attachment"):
        return httpx.Response(200, json={"results": [{"id": "att77", "type": "attachment", "title": "decision.pptx", "version": {"number": 3}, "container": {"id": "1"}, "_links": {"download": "/download/attachments/1/decision.pptx?version=3"}}]})
    if request.url.path.startswith("/download/attachments/"): return httpx.Response(200, content=presentation_bytes())
    return handler(request)


def create():
    return create_app(QA_DIR, secret_store=TestSecrets(), confluence_client_factory=lambda url, token: ConfluenceClient(url, token, transport=httpx.MockTransport(response), sleep=lambda _: None))

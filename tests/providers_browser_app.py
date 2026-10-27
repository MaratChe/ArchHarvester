"""Synthetic QA registry; compatible API uses only the local Ollama /v1 endpoint."""
from pathlib import Path
from backend.app.main import create_app
from tests.test_providers import Secrets


def create():
    root=Path(__file__).resolve().parents[1]
    return create_app(root/'output'/'providers-browser',frontend_dir=root/'output'/'providers-dist',provider_secret_store=Secrets(),start_worker=False)

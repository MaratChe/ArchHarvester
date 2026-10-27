"""Explicit live-Ollama QA, isolated registry containing only synthetic fixtures."""
from pathlib import Path
from backend.app.main import create_app


def create():
    root=Path(__file__).resolve().parents[1]
    return create_app(root/'output'/'ollama-browser',frontend_dir=root/'output'/'ollama-dist')

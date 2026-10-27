import pytest
from fastapi.testclient import TestClient
from backend.app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as c:
        c.headers["X-Local-Token"] = c.get("/api/session").json()["token"]
        yield c


@pytest.fixture
def type_id(client):
    return client.get("/api/types").json()[0]["id"]


def upload(client, type_id, html, **kwargs):
    return client.post("/api/uploads", files={"file": ("decision.html", html.encode(), "text/html")},
                       data={"type_id": type_id, **kwargs})

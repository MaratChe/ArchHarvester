from fastapi.testclient import TestClient
from backend.app.main import create_app


def test_manual_draft_publication_revisions_and_restart(client, type_id, tmp_path):
    draft = client.post("/api/artifacts", json={"type_id": type_id, "fields": {}, "status": "draft"})
    assert draft.status_code == 201
    item = draft.json()
    assert item["sources"] == []
    invalid = client.put(f"/api/artifacts/{item['id']}", json={"expected_revision": 1, "fields": {}, "status": "published"})
    assert invalid.status_code == 422
    saved = client.put(f"/api/artifacts/{item['id']}", json={"expected_revision": 1, "fields": {"title": "Надёжная доставка"}, "status": "published"})
    assert saved.json()["revision"] == 2
    assert saved.json()["provenance"]["title"]["method"] == "manual"
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as reopened:
        assert reopened.get(f"/api/artifacts/{item['id']}").json()["fields"]["title"] == "Надёжная доставка"
        assert len(reopened.get(f"/api/artifacts/{item['id']}/revisions").json()) == 2


def test_stale_edit_and_invalid_field_types(client, type_id):
    item = client.post("/api/artifacts", json={"type_id": type_id, "fields": {"title": "A"}}).json()
    route = f"/api/artifacts/{item['id']}"
    assert client.put(route, json={"expected_revision": 1, "fields": {"title": "B"}}).status_code == 200
    assert client.put(route, json={"expected_revision": 1, "fields": {"title": "C"}}).status_code == 409
    assert client.post("/api/artifacts", json={"type_id": type_id, "fields": {"title": 42}}).status_code == 422
    assert client.get(route).json()["fields"]["title"] == "B"


def test_type_version_is_immutable_and_bad_schema_rejected(client, type_id):
    old = client.get("/api/types").json()[0]
    new_schema = {**old["schema"], "required": ["title", "owner"]}
    new = client.post("/api/types", json={"type_key": old["type_key"], "name": old["name"], "schema": new_schema})
    assert new.status_code == 201
    assert new.json()["version"] == 2
    assert client.post("/api/artifacts", json={"type_id": type_id, "fields": {"title": "A"}, "status": "published"}).status_code == 201
    assert client.post("/api/artifacts", json={"type_id": new.json()["id"], "fields": {"title": "A"}, "status": "published"}).status_code == 422
    assert client.post("/api/types", json={"type_key": "bad", "name": "Bad", "schema": {"$ref": "https://example.org/schema"}}).status_code == 422


def test_local_request_protection(client, type_id):
    assert client.post("/api/artifacts", headers={"X-Local-Token": "wrong"}, json={"type_id": type_id}).status_code == 403
    assert client.get("/api/session", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/types", headers={"Host": "evil.example"}).status_code == 400


def test_search_and_export(client, type_id):
    client.post("/api/artifacts", json={"type_id": type_id, "fields": {"title": "Доставка сообщений"}, "status": "published"})
    client.post("/api/artifacts", json={"type_id": type_id, "fields": {"title": "Черновик"}})
    assert len(client.get("/api/artifacts", params={"q": "сообщений"}).json()) == 1
    assert client.get("/api/artifacts", params={"q": "' OR 1=1 --"}).json() == []
    export = client.get("/api/export").json()
    assert export["export_format_version"] == 1
    assert len(export["artifacts"]) == 1
    assert export["artifacts"][0]["fields"]["title"] == "Доставка сообщений"

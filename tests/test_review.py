from tests.conftest import upload


HTML = '<table><tr><td>Название</td><td>Очередь</td></tr><tr><td>Проблематика</td><td>Потери</td></tr></table>'


def accept(client, candidate, **overrides):
    return client.post(f"/api/candidates/{candidate['id']}/review", json={"expected_revision": candidate["base_revision"], "fields": {k: p["value"] for k, p in candidate["proposals"].items()}, "status": "published", **overrides})


def test_retry_and_repeat_import_preserve_manual_changes(client, type_id):
    c = upload(client, type_id, HTML).json()
    assert upload(client, type_id, HTML).json()["id"] == c["id"]
    result = accept(client, c)
    assert result.status_code == 200
    a = result.json()
    assert accept(client, c).json()["revision"] == 1
    assert a["provenance"]["problem"]["method"] == "table"
    client.put(f"/api/artifacts/{a['id']}", json={"expected_revision": 1, "fields": {"title": "Очередь", "problem": "Ручное уточнение"}, "status": "published"})
    c2 = upload(client, type_id, HTML.replace("Потери", "Новые потери"), resource_id=c["resource_id"]).json()
    assert c2["target_id"] == a["id"]
    assert c2["baseline"]["problem"] == "Потери"
    assert c2["current_fields"]["problem"] == "Ручное уточнение"
    assert client.get(f"/api/artifacts/{a['id']}").json()["fields"]["problem"] == "Ручное уточнение"
    reviewed = accept(client, c2, fields={"title": "Очередь", "problem": "Ручное уточнение"}).json()
    assert reviewed["provenance"]["problem"]["method"] == "manual"
    assert len(client.get("/api/artifacts").json()) == 1


def test_stale_review_and_superseded_candidate(client, type_id):
    a = client.post("/api/artifacts", json={"type_id": type_id, "fields": {"title": "Ручной"}}).json()
    c = upload(client, type_id, HTML, target_id=a["id"]).json()
    client.put(f"/api/artifacts/{a['id']}", json={"expected_revision": 1, "fields": {"title": "Из другой вкладки"}})
    assert accept(client, c).status_code == 409
    c2 = upload(client, type_id, HTML.replace("Потери", "Ещё"), resource_id=c["resource_id"]).json()
    assert accept(client, c).status_code == 409
    assert accept(client, c2).status_code == 200


def test_link_existing_manual_and_reject_candidate(client, type_id):
    a = client.post("/api/artifacts", json={"type_id": type_id, "fields": {"title": "Ручной"}}).json()
    c = upload(client, type_id, HTML, target_id=a["id"]).json()
    assert c["target_id"] == a["id"]
    assert client.get(f"/api/artifacts/{a['id']}").json()["fields"] == {"title": "Ручной"}
    assert client.post(f"/api/candidates/{c['id']}/reject").status_code == 200
    assert accept(client, c).status_code == 409


def test_bind_after_unbound_upload_retargets_pending_candidate(client, type_id):
    c = upload(client, type_id, HTML).json()
    a = client.post("/api/artifacts", json={"type_id": type_id, "fields": {"title": "Ручной"}}).json()
    bound = upload(client, type_id, HTML, target_id=a["id"]).json()
    assert bound["target_id"] == a["id"]
    assert bound["base_revision"] == 1
    assert accept(client, bound).json()["id"] == a["id"]
    assert len(client.get("/api/artifacts").json()) == 1


def test_reprocess_rejected_and_reverted_source(client, type_id):
    first = upload(client, type_id, HTML).json()
    client.post(f"/api/candidates/{first['id']}/reject")
    retry = upload(client, type_id, HTML).json()
    assert retry["id"] != first["id"]
    assert accept(client, retry).status_code == 200
    second = upload(client, type_id, HTML.replace("Потери", "Новые потери"), resource_id=first["resource_id"]).json()
    assert accept(client, second).status_code == 200
    reverted = upload(client, type_id, HTML, resource_id=first["resource_id"]).json()
    assert reverted["status"] == "pending"
    assert reverted["baseline"]["problem"] == "Новые потери"
    assert accept(client, reverted).json()["fields"]["problem"] == "Потери"

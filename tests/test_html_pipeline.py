from tests.conftest import upload


def test_table_selection_and_evidence(client, type_id):
    html = '<h1>ADR</h1><table><tr><td>Не то</td><td>Мимо</td></tr></table><table><tr><th>Поле</th><th>Значение</th></tr><tr><td>Название</td><td>Очередь</td></tr><tr><td>Владелец</td><td>Команда А</td></tr></table>'
    response = upload(client, type_id, html, table_index="1")
    assert response.status_code == 201
    c = response.json()
    assert c["proposals"]["title"]["value"] == "Очередь"
    ev = c["proposals"]["owner"]["evidence"][0]
    assert ev["quote"] == "Команда А"
    snapshot = client.get(f"/api/snapshots/{ev['snapshot_id']}").json()
    assert any(b["id"] == ev["block_id"] and "Команда А" in b["text"] for b in snapshot["document"]["blocks"])
    assert client.get(f"/api/snapshots/{ev['snapshot_id']}/download").content.decode() == html


def test_headings_not_inline_markers_and_missing_end(client, type_id):
    h = '<h1>Решение</h1><h2>Проблематика</h2><p>Фраза Задачи проекта внутри текста.</p><p>Потери.</p><h2>Задачи проекта</h2><p>Исправить</p>'
    c = upload(client, type_id, h, mode="sections").json()
    assert c["proposals"]["problem"]["value"] == "Фраза Задачи проекта внутри текста.\nПотери."
    missing = upload(client, type_id, '<h2>Проблематика</h2><p>Текст</p>', mode="sections").json()
    assert "problem" not in missing["proposals"]
    assert missing["warnings"]


def test_ambiguity_merged_cells_and_nested_tables_are_not_silent(client, type_id):
    c = upload(client, type_id, '<table><tr><td>Название</td><td>A</td></tr><tr><td>Название</td><td>B</td></tr></table>').json()
    assert "title" not in c["proposals"]
    assert c["warnings"]
    merged = upload(client, type_id, '<table><tr><td colspan="2">Название</td></tr><tr><td>Владелец</td><td><table><tr><td>Вложено</td></tr></table></td></tr></table>').json()
    assert not merged["proposals"]
    assert merged["warnings"]


def test_hostile_markup_and_invalid_file(client, type_id):
    c = upload(client, type_id, '<h1>Безопасно</h1><script>alert(1)</script><iframe src="https://evil.example"></iframe>').json()
    snap = client.get(f"/api/snapshots/{c['snapshot_id']}").json()
    assert "alert(1)" not in str(snap["document"])
    assert client.post("/api/uploads", files={"file": ("x.exe", b"MZ", "application/octet-stream")}, data={"type_id": type_id}).status_code == 422
    assert upload(client, type_id, " ").status_code == 422


def test_section_preserves_div_text_and_does_not_duplicate_nested_paragraph(client, type_id):
    html = '<h1>Решение</h1><h2>Проблематика</h2><div>Потери сообщений</div><ul><li><p>Вложенный текст</p></li></ul><h2>Задачи проекта</h2><p>Исправить</p>'
    c = upload(client, type_id, html, mode="sections").json()
    assert c["proposals"]["problem"]["value"] == "Потери сообщений\nВложенный текст"

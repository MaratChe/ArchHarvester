from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
import re
from fastapi import HTTPException
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import select
from .db import artifacts, revisions, types, links, resources, find


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


def require(connection, table, id):
    row = find(connection, table, id)
    if row is None:
        raise HTTPException(404, "Запись не найдена")
    return deepcopy(row["data"])


DEFAULT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["title"],
    "properties": {key: {"type": "string", "title": label, **({"minLength": 1} if key == "title" else {})} for key, label in [
        ("title", "Название"), ("description", "Описание"), ("problem", "Проблематика"),
        ("tasks", "Задачи проекта"), ("solution", "Решение"), ("owner", "Владелец")
    ]},
}


def check_schema(schema):
    allowed_top = {"type", "properties", "required", "additionalProperties", "title", "description", "$schema"}
    allowed_field = {"type", "title", "description", "enum", "format", "minLength", "maxLength", "minimum", "maximum", "items"}
    try:
        Draft202012Validator.check_schema(schema)
        assert schema.get("type") == "object" and schema.get("additionalProperties") is False
        assert not (set(schema) - allowed_top)
        props = schema["properties"]
        assert 1 <= len(props) <= 40
        assert set(schema.get("required", [])) <= set(props)
        for key, value in props.items():
            assert re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key)
            assert not (set(value) - allowed_field)
            assert value.get("type") in {"string", "number", "integer", "boolean", "array"}
            if "format" in value:
                assert value["type"] == "string" and value["format"] == "date"
            if value["type"] == "array":
                assert value.get("items") == {"type": "string"}
    except Exception:
        raise HTTPException(422, "Схема: объект с 1–40 простыми полями, additionalProperties=false; вложенные схемы и $ref не поддерживаются")


def create_type(connection, type_key, name, schema):
    check_schema(schema)
    versions = connection.execute(select(types.c.version).where(types.c.type_key == type_key)).scalars().all()
    data = {"id": uid(), "type_key": type_key, "version": max(versions, default=0) + 1, "name": name, "schema": schema}
    connection.execute(types.insert().values(id=data["id"], type_key=type_key, version=data["version"], data=data))
    return data


def validate_fields(connection, type_id, fields, status):
    schema = require(connection, types, type_id)["schema"]
    if status == "draft":
        schema.pop("required", None)
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(fields), key=lambda e: str(e.path))
    if errors:
        raise HTTPException(422, [{"field": ".".join(map(str, e.path)), "message": e.message} for e in errors])
    if status == "published":
        for key in schema.get("required", []):
            if isinstance(fields.get(key), str) and not fields[key].strip():
                raise HTTPException(422, f"Заполните обязательное поле: {key}")


def artifact_view(connection, id):
    result = require(connection, artifacts, id)
    result["sources"] = [{"role": "primary", **require(connection, resources, row.resource_id)}
                         for row in connection.execute(select(links).where(links.c.artifact_id == id))]
    return result


def save_artifact(connection, type_id, fields, status, *, id=None, expected_revision=0, provenance=None, review=None):
    validate_fields(connection, type_id, fields, status)
    old = require(connection, artifacts, id) if id else None
    if old and old["revision"] != expected_revision:
        raise HTTPException(409, "Объект изменён. Откройте актуальную ревизию и повторите проверку.")
    id = id or uid()
    origins = {}
    for key, value in fields.items():
        if provenance and key in provenance:
            origins[key] = provenance[key]
        elif old and key in old["fields"] and old["fields"][key] == value:
            origins[key] = old["provenance"].get(key, {"method": "manual"})
        else:
            origins[key] = {"method": "manual", "at": now()}
    data = {"id": id, "type_id": type_id, "revision": old["revision"] + 1 if old else 1,
            "fields": fields, "status": status, "provenance": origins, "updated_at": now(),
            "created_at": old["created_at"] if old else now()}
    if old:
        connection.execute(artifacts.update().where(artifacts.c.id == id).values(data=data))
    else:
        connection.execute(artifacts.insert().values(id=id, type_id=type_id, data=data))
    connection.execute(revisions.insert().values(artifact_id=id, revision=data["revision"], data={**data, "review": review}))
    connection.exec_driver_sql("DELETE FROM artifact_fts WHERE id = ?", (id,))
    text = " ".join(str(v) for v in fields.values())
    connection.exec_driver_sql("INSERT INTO artifact_fts(id, content) VALUES (?, ?)", (id, text))
    return artifact_view(connection, id)


def list_artifacts(connection, q="", status="", type_id=""):
    query = select(artifacts.c.data)
    if type_id:
        query = query.where(artifacts.c.type_id == type_id)
    items = list(connection.execute(query).scalars())
    if q.strip():
        tokens = re.findall(r"\w+", q, re.UNICODE)
        if not tokens:
            return []
        match = " AND ".join('"' + token + '"*' for token in tokens)
        ids = {row[0] for row in connection.exec_driver_sql("SELECT id FROM artifact_fts WHERE artifact_fts MATCH ?", (match,))}
        items = [a for a in items if a["id"] in ids or a["id"] == q.strip()]
    return sorted([a for a in items if not status or a["status"] == status], key=lambda a: a["updated_at"], reverse=True)

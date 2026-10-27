from hashlib import sha256
import json
import os
from fastapi import HTTPException
from sqlalchemy import select
from .db import resources, snapshots, candidates, links, artifacts, types
from .registry import require, uid, now, save_artifact, artifact_view
from .html_parser import parse_html, extract


PIPELINE_VERSION = "html-v1"


def check_binding_schema(connection, resource_id, type_id):
    requested = require(connection, types, type_id)
    for linked_type_id in connection.execute(select(links.c.type_id).where(links.c.resource_id == resource_id)).scalars():
        if linked_type_id == type_id: continue
        existing_type = require(connection, types, linked_type_id)
        if existing_type["type_key"] == requested["type_key"]:
            raise HTTPException(409, f"Источник уже связан с объектом этого типа по схеме версии {existing_type['version']}. Выберите эту версию схемы; автоматическая миграция не выполняется.")


def persist_blob(directory, digest, content):
    path = directory / "blobs" / digest
    if path.exists() and sha256(path.read_bytes()).hexdigest() == digest:
        return
    temporary = directory / "blobs" / (digest + "." + uid() + ".tmp")
    try:
        with temporary.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def bind_source(connection, resource_id, type_id, artifact_id):
    check_binding_schema(connection, resource_id, type_id)
    artifact = require(connection, artifacts, artifact_id)
    if artifact["type_id"] != type_id:
        raise HTTPException(422, "Версия типа источника и объекта должна совпадать")
    binding = connection.execute(select(links).where(links.c.resource_id == resource_id, links.c.type_id == type_id)).mappings().first()
    if binding and binding["artifact_id"] != artifact_id:
        raise HTTPException(409, "Этот источник уже связан с другим объектом")
    if not binding:
        connection.execute(links.insert().values(resource_id=resource_id, type_id=type_id, artifact_id=artifact_id))


def import_html(db, connection, content, filename, type_id, mode, table_index, resource_id=None, target_id=None, *, source_metadata=None, parser=parse_html, source_kind="html", prepared_result=None, pipeline_config=None):
    artifact_type = require(connection, types, type_id)
    digest = sha256(content).hexdigest()
    source_version = source_metadata.get("page_version", source_metadata.get("version")) if source_metadata else None
    snapshot_key = sha256((digest + ":" + str(source_version)).encode()).hexdigest() if source_metadata else digest
    if resource_id:
        resource = require(connection, resources, resource_id)
    else:
        # Exact duplicate uploads reuse a resource; filenames alone never identify a source.
        existing = next((row for row in connection.execute(select(snapshots.c.resource_id).where(snapshots.c.digest == digest))
                         if require(connection, resources, row[0]).get("kind") == source_kind), None)
        resource = require(connection, resources, existing[0]) if existing else {"id": uid(), "name": filename, "kind": source_kind, "created_at": now()}
        if not existing:
            connection.execute(resources.insert().values(id=resource["id"], data=resource))
    resource_id = resource["id"]
    check_binding_schema(connection, resource_id, type_id)
    if target_id:
        bind_source(connection, resource_id, type_id, target_id)
    binding = connection.execute(select(links.c.artifact_id).where(links.c.resource_id == resource_id, links.c.type_id == type_id)).first()
    target_id = binding[0] if binding else None
    previous = connection.execute(select(snapshots.c.data).where(snapshots.c.resource_id == resource_id, snapshots.c.digest == snapshot_key)).scalar_one_or_none()
    persist_blob(db.directory, digest, content)
    if previous:
        snapshot = previous
    else:
        snapshot_id = uid()
        document = parser(content, snapshot_id)
        snapshot = {"id": snapshot_id, "resource_id": resource_id, "sha256": digest, "filename": filename,
                    "document": document, "created_at": now(), "size": len(content)}
        if source_metadata:
            snapshot["source_metadata"] = source_metadata
        connection.execute(snapshots.insert().values(id=snapshot_id, resource_id=resource_id, digest=snapshot_key, data=snapshot))
    config = {"mode": mode, "table_index": table_index, "pipeline_version": "pptx-v1" if source_kind == "pptx" else "confluence-storage-v1" if source_metadata else PIPELINE_VERSION}
    if pipeline_config: config.update(pipeline_config)
    if prepared_result and prepared_result.get('llm_runs'):
        from .llm_history import record
        for run in prepared_result['llm_runs']:run['snapshot_id']=snapshot['id']
        config['llm_runs']=prepared_result['llm_runs']
        record(connection,prepared_result)
    result_key = sha256(json.dumps([snapshot["id"], type_id, config], sort_keys=True).encode()).hexdigest()
    history = sorted([item for item in connection.execute(select(candidates.c.data)).scalars()
                      if item["resource_id"] == resource_id and item["type_id"] == type_id], key=lambda item: item["created_at"])
    latest = history[-1] if history else None
    if (latest and latest["snapshot_id"] == snapshot["id"] and latest["config"] == config
            and latest["target_id"] == target_id and latest["status"] in {"pending", "accepted"}):
        return candidate_view(connection, latest["id"])
    # A user re-import after rejection, a source revert, or a new binding is a new evaluation.
    if connection.execute(select(candidates.c.id).where(candidates.c.result_key == result_key)).first():
        result_key += ":" + uid()
    if prepared_result is None:
        proposals, warnings = extract(snapshot["document"], artifact_type["schema"], mode, table_index)
    else:
        from copy import deepcopy
        proposals, warnings = deepcopy(prepared_result["proposals"]), list(prepared_result["warnings"])
        for proposal in proposals.values():
            for evidence in proposal["evidence"]: evidence["snapshot_id"] = snapshot["id"]
    baseline = {}
    for item in history:
        if item["status"] == "accepted":
            baseline = {k: p["value"] for k, p in item["proposals"].items()}
        elif item["status"] == "pending":
            item = {**item, "status": "superseded"}
            connection.execute(candidates.update().where(candidates.c.id == item["id"]).values(data=item))
    current = require(connection, artifacts, target_id) if target_id else None
    data = {"id": uid(), "resource_id": resource_id, "source_name": resource["name"], "snapshot_id": snapshot["id"],
            "type_id": type_id, "target_id": target_id, "base_revision": current["revision"] if current else 0,
            "current_fields": current["fields"] if current else {}, "baseline": baseline, "proposals": proposals,
            "warnings": warnings, "config": config, "status": "pending", "created_at": now()}
    if source_metadata:
        data["source_metadata"] = source_metadata
    if prepared_result is not None:
        data["step_results"] = prepared_result.get("steps", [])
    connection.execute(candidates.insert().values(id=data["id"], result_key=result_key, data=data))
    return data


def candidate_view(connection, id):
    data = require(connection, candidates, id)
    if data["target_id"]:
        current = require(connection, artifacts, data["target_id"])
        data["latest_revision"] = current["revision"]
        data["latest_fields"] = current["fields"]
    return data


def review_candidate(connection, id, request):
    candidate = require(connection, candidates, id)
    if candidate["status"] == "accepted":
        # Retried submission returns the committed revision, even after later manual edits.
        return candidate["committed_result"]
    if candidate["status"] != "pending":
        raise HTTPException(409, "Предложение отклонено или заменено более новым")
    if request.expected_revision != candidate["base_revision"]:
        raise HTTPException(409, "Ревизия не соответствует предложению")
    current = require(connection, artifacts, candidate["target_id"]) if candidate["target_id"] else None
    origins, decisions = {}, {}
    for key, proposal in candidate["proposals"].items():
        if key not in request.fields:
            decisions[key] = "rejected"
        elif current and key in current["fields"] and current["fields"][key] == request.fields[key]:
            decisions[key] = "kept"
        elif request.fields[key] == proposal["value"]:
            origins[key] = {"method": proposal["method"], "evidence": proposal["evidence"], "candidate_id": id,
                            "pipeline_version": candidate["config"]["pipeline_version"],
                            **{k: candidate["config"][k] for k in ("pipeline_id", "pipeline_hash", "runtime_image_id") if k in candidate["config"]},
                            **({"step": proposal["step"]} if "step" in proposal else {})}
            if proposal.get('model_metadata'):origins[key]['model_metadata']=proposal['model_metadata']
            decisions[key] = "accepted"
        else:
            decisions[key] = "edited"
    result = save_artifact(connection, candidate["type_id"], request.fields, request.status,
                           id=candidate["target_id"], expected_revision=request.expected_revision,
                           provenance=origins, review={"candidate_id": id, "decisions": decisions, "at": now()})
    bind_source(connection, candidate["resource_id"], candidate["type_id"], result["id"])
    result = artifact_view(connection, result["id"])
    candidate.update(status="accepted", target_id=result["id"], committed_result=result, reviewed_at=now())
    connection.execute(candidates.update().where(candidates.c.id == id).values(data=candidate))
    return result


def rebase_candidate(connection, id):
    candidate = require(connection, candidates, id)
    if candidate["status"] != "pending" or not candidate["target_id"]:
        raise HTTPException(409, "Обновить сравнение можно только для ожидающего изменения объекта")
    current = require(connection, artifacts, candidate["target_id"])
    candidate.update(base_revision=current["revision"], current_fields=current["fields"])
    connection.execute(candidates.update().where(candidates.c.id == id).values(data=candidate))
    return candidate

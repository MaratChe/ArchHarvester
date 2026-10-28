from .providers import client_for
from hashlib import sha256
import json
from fastapi import APIRouter, HTTPException
from pydantic import Field
from sqlalchemy import select
from .contracts import StrictModel
from .db import pipelines, pipeline_tests, types, snapshots, resources
from .registry import require, uid, now
from .pipeline_engine import run_pipeline, validate_steps
from .imports import import_html
from .python_runner import runtime_status


class PipelineCreate(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    type_id: str
    steps: list[dict] = Field(min_length=1, max_length=20)


class TestRequest(StrictModel):
    snapshot_ids: list[str] = Field(min_length=1, max_length=10)


class ProposeRequest(StrictModel):
    snapshot_id: str


def load_pipeline(c, id, type_id):
    if not id: return None
    pipeline = require(c, pipelines, id)
    if pipeline["status"] != "published" or pipeline["type_id"] != type_id:
        raise HTTPException(422, "Выберите опубликованный пайплайн для этой версии типа")
    return pipeline


def script_document(document, db, steps):
    if 'html' in document or document.get('format') == 'pptx' or not any(s['kind'] == 'javascript' for s in steps):
        return document
    # Older snapshots retain their block IDs and provenance; hydrate only HTML.
    with db.engine.connect() as c:
        snapshot = require(c, snapshots, document['snapshot_id'])
    from .html_parser import parse_html
    from .confluence.storage import parse_storage
    parser = parse_storage if document.get('format') == 'confluence_storage' else parse_html
    html = parser((db.directory / 'blobs' / snapshot['sha256']).read_bytes(), snapshot['id'])['html']
    return {**document, 'html': html}


def evaluate(document, schema, pipeline, *, db=None):
    if pipeline is None: return None, None
    from .providers import client_for
    if db: document = script_document(document, db, pipeline["steps"])
    result = run_pipeline(document, schema, pipeline["steps"], expected_runtime=pipeline.get("runtime_image_id"),expected_js_runtime=pipeline.get("javascript_runtime_image_id"),client_factory=(lambda id:client_for(db,id)) if db else None)
    return result, {"pipeline_id": pipeline["id"], "pipeline_version": f"{pipeline['key']}:{pipeline['version']}", "pipeline_hash": pipeline["hash"], "runtime_image_id": pipeline.get("runtime_image_id")}


def build_pipeline_router(db):
    router = APIRouter(prefix="/api")

    @router.get("/pipelines")
    def listing():
        with db.engine.connect() as c: return list(c.execute(select(pipelines.c.data).order_by(pipelines.c.pipeline_key, pipelines.c.version.desc())).scalars())

    @router.get("/javascript-runtime")
    def javascript_runtime():
        from .javascript_runner import runtime_status
        return runtime_status()

    @router.get("/python-runtime")
    def runtime(): return runtime_status()

    @router.get("/snapshots")
    def snapshot_list():
        with db.engine.connect() as c:
            return sorted([{"id": s["id"], "filename": s["filename"], "created_at": s["created_at"], "resource_id": s["resource_id"]} for s in c.execute(select(snapshots.c.data)).scalars()], key=lambda s:s["created_at"], reverse=True)

    @router.post("/pipelines", status_code=201)
    def create(body: PipelineCreate):
        with db.transaction() as c:
            schema = require(c, types, body.type_id)["schema"]
            validate_steps(body.steps, schema)
            versions = list(c.execute(select(pipelines.c.version).where(pipelines.c.pipeline_key == body.key)).scalars())
            data = {"id": uid(), "key": body.key, "name": body.name, "type_id": body.type_id, "version": max(versions, default=0) + 1,
                    "steps": body.steps, "status": "draft", "created_at": now(),
                    "hash": sha256(json.dumps([body.type_id, body.steps], sort_keys=True, ensure_ascii=False).encode()).hexdigest()}
            c.execute(pipelines.insert().values(id=data["id"], pipeline_key=body.key, version=data["version"], data=data))
        return data

    @router.get("/pipelines/{id}/tests")
    def tests(id: str):
        with db.engine.connect() as c:
            require(c, pipelines, id)
            return sorted([t for t in c.execute(select(pipeline_tests.c.data)).scalars() if t["pipeline_id"] == id], key=lambda t:t["created_at"], reverse=True)

    @router.post("/pipelines/{id}/tests")
    def test(id: str, body: TestRequest):
        with db.engine.connect() as c:
            pipeline = require(c, pipelines, id)
            schema = require(c, types, pipeline["type_id"])["schema"]
            inputs = [require(c, snapshots, s) for s in dict.fromkeys(body.snapshot_ids)]
            previous = sorted([p for p in c.execute(select(pipelines.c.data)).scalars() if p["key"] == pipeline["key"] and p["version"] < pipeline["version"] and p["status"] == "published" and p["type_id"] == pipeline["type_id"]], key=lambda p:p["version"])
        report = {"id": uid(), "pipeline_id": id, "hash": pipeline["hash"], "created_at": now(), "results": [], "ok": True,
                  "baseline_id": previous[-1]["id"] if previous else None}
        for snapshot in inputs:
            row = {"snapshot_id": snapshot["id"], "filename": snapshot["filename"]}
            try:
                row["result"] = run_pipeline(script_document(snapshot["document"], db, pipeline["steps"]), schema, pipeline["steps"], expected_runtime=pipeline.get("runtime_image_id"),expected_js_runtime=pipeline.get("javascript_runtime_image_id"),client_factory=lambda id:client_for(db,id))
                from .llm_history import record
                with db.transaction() as c:record(c,row['result'])
                old = {}
                if previous:
                    try:
                        baseline_result = run_pipeline(script_document(snapshot["document"], db, previous[-1]["steps"]), schema, previous[-1]["steps"], expected_runtime=previous[-1].get("runtime_image_id"),expected_js_runtime=previous[-1].get("javascript_runtime_image_id"),client_factory=lambda id:client_for(db,id))
                        with db.transaction() as c:record(c,baseline_result)
                        old=baseline_result['proposals']
                        row['baseline_llm_runs']=baseline_result.get('llm_runs',[])
                    except HTTPException as e:
                        from .llm_history import record_failure
                        with db.transaction() as c:row['baseline_error_run_id']=record_failure(c,e)
                        row['baseline_completed_llm_runs']=getattr(e,'llm_completed',{}).get('llm_runs',[])
                        row["baseline_error"] = "Сравнение недоступно: предыдущая версия завершилась ошибкой. " + str(e.detail)
                new = row["result"]["proposals"]
                row["diff"] = [{"field": key, "before": old.get(key, {}).get("value"), "after": new.get(key, {}).get("value")} for key in sorted(set(old) | set(new)) if old.get(key) != new.get(key)]
            except HTTPException as e:
                from .llm_history import record_failure
                with db.transaction() as c:row['error_run_id']=record_failure(c,e)
                row['completed_llm_runs']=getattr(e,'llm_completed',{}).get('llm_runs',[])
                row["error"] = str(e.detail); report["ok"] = False
            report["results"].append(row)
        with db.transaction() as c: c.execute(pipeline_tests.insert().values(id=report["id"], data=report))
        return report

    @router.post("/pipelines/{id}/publish")
    def publish(id: str):
        with db.transaction() as c:
            pipeline = require(c, pipelines, id)
            if pipeline["status"] == "published": return pipeline
            runs = sorted([t for t in c.execute(select(pipeline_tests.c.data)).scalars() if t["pipeline_id"] == id and t["hash"] == pipeline["hash"]], key=lambda t:t["created_at"])
            if not runs or not runs[-1]["ok"]: raise HTTPException(409, "Сначала выполните успешный тест этой версии на сохранённом снимке")
            image_ids = {s["runtime_image_id"] for row in runs[-1]["results"] for s in row["result"]["steps"] if s.get("runtime_image_id")}
            if len(image_ids) > 1: raise HTTPException(409, "Образ исполнителя изменился во время теста; повторите тест")
            js_ids = {s['javascript_runtime_image_id'] for row in runs[-1]['results'] for s in row['result']['steps'] if s.get('javascript_runtime_image_id')}
            if len(js_ids) > 1: raise HTTPException(409, 'Образ JavaScript изменился во время теста; повторите тест')
            pipeline['javascript_runtime_image_id'] = next(iter(js_ids), None)
            pipeline.update(status="published", published_at=now(), test_id=runs[-1]["id"], runtime_image_id=next(iter(image_ids), None))
            c.execute(pipelines.update().where(pipelines.c.id == id).values(data=pipeline))
            return pipeline

    @router.post("/pipelines/{id}/propose", status_code=201)
    def propose(id: str, body: ProposeRequest):
        with db.engine.connect() as c:
            p = require(c, pipelines, id)
            pipeline = load_pipeline(c, id, p["type_id"])
            schema = require(c, types, p["type_id"])["schema"]
            snapshot = require(c, snapshots, body.snapshot_id)
            resource = require(c, resources, snapshot["resource_id"])
        result, config = evaluate(snapshot["document"], schema, pipeline, db=db)
        content = (db.directory / "blobs" / snapshot["sha256"]).read_bytes()
        with db.transaction() as c:
            return import_html(db, c, content, snapshot["filename"], p["type_id"], "table", None, resource["id"],
                               source_metadata=snapshot.get("source_metadata"), source_kind="pptx" if snapshot["document"].get("format") == "pptx" else "html",
                               parser=lambda _, sid: {**snapshot["document"], "snapshot_id": sid}, prepared_result=result, pipeline_config=config)

    return router

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select
from .contracts import ArtifactCreate, ArtifactEdit, ReviewRequest, TypeCreate
from .db import Database, artifacts, candidates, revisions, snapshots, types
from .registry import DEFAULT_SCHEMA, artifact_view, create_type, list_artifacts, now, require, save_artifact
from .imports import candidate_view, import_html, rebase_candidate, review_candidate
from .confluence.client import ConfluenceClient
from .confluence.credentials import WindowsCredentials
from .confluence.jobs import ImportWorker
from .confluence.router import build_router
from .pipelines import build_pipeline_router, load_pipeline, evaluate
from .pptx_router import build_pptx_router
from .html_parser import parse_html
from .llm_router import build_llm_router

MAX_UPLOAD = 5 * 1024 * 1024
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def create_app(data_dir: Path | None = None, *, secret_store=None, confluence_client_factory=None, start_worker=True, frontend_dir: Path | None = None, provider_secret_store=None, provider_transport=None):
    from .tls import client_ssl_context
    client_ssl_context()  # Fail early on invalid corporate trust configuration.
    directory = data_dir or Path(os.environ.get("ARCH_REGISTRY_DATA", str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ArchitectureRegistryStudio")))
    db = Database(Path(directory))
    from .providers import ProviderRegistry
    from .provider_router import build_provider_router
    db.provider_registry=ProviderRegistry(db,provider_secret_store,provider_transport)
    with db.transaction() as connection:
        if not connection.execute(select(types.c.id)).first():
            create_type(connection, "architecture_decision", "Архитектурное решение", DEFAULT_SCHEMA)
    token = secrets.token_urlsafe(32)
    credential_store = secret_store if secret_store is not None else WindowsCredentials()
    client_factory = confluence_client_factory or ConfluenceClient
    worker = ImportWorker(db, credential_store, client_factory)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker: worker.start()
        yield
        worker.stop()
        db.engine.dispose()

    app = FastAPI(title="Architecture Registry Studio", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db = db
    app.state.confluence_worker = worker
    app.include_router(build_router(db, credential_store, client_factory, worker))
    app.include_router(build_pipeline_router(db))
    app.include_router(build_pptx_router(db, credential_store, client_factory))
    app.include_router(build_llm_router(db))
    app.include_router(build_provider_router(db))
    from .llm_history import cleanup
    with db.transaction() as c:cleanup(c)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        from .llm_history import record_failure
        if getattr(exc,'llm_output',None):
            with db.transaction() as c:run_id=record_failure(c,exc)
            return JSONResponse({'detail':{'message':str(exc.detail),'run_id':run_id}},status_code=exc.status_code)
        return JSONResponse({'detail':exc.detail},status_code=exc.status_code,headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic errors can include raw input; never reflect a submitted PAT.
        return JSONResponse({"detail":[{"field":".".join(map(str,e["loc"])),"message":e["msg"]} for e in exc.errors()]},status_code=422)

    @app.middleware("http")
    async def local_only(request, call_next):
        host = request.headers.get("host", "")
        if urlsplit("http://" + host).hostname not in {"127.0.0.1", "localhost", "::1"}:
            return JSONResponse({"detail": "Разрешён только локальный адрес"}, status_code=400)
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{host}":
            return JSONResponse({"detail": "Запрос с другого сайта запрещён"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Запрос с другого сайта запрещён"}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not secrets.compare_digest(request.headers.get("x-local-token", ""), token):
            return JSONResponse({"detail": "Обновите страницу: локальная сессия не подтверждена"}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            try:
                limit = 25 * 1024 * 1024 if request.url.path == "/api/pptx/uploads" else MAX_UPLOAD
                if int(request.headers.get("content-length", "0")) > limit + 65536:
                    return JSONResponse({"detail": "Превышен максимальный размер запроса"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Неверная длина запроса"}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/session")
    def session():
        return {"token": token, "data_dir": str(directory), "version": "0.8.0"}

    @app.get("/api/types")
    def get_types():
        with db.engine.connect() as c:
            return list(c.execute(select(types.c.data).order_by(types.c.type_key, types.c.version.desc())).scalars())

    @app.post("/api/types", status_code=201)
    def add_type(body: TypeCreate):
        with db.transaction() as c:
            if body.create_new and c.execute(select(types.c.id).where(types.c.type_key==body.type_key)).first():
                raise HTTPException(409,'Тип с таким ключом уже существует. Выберите другой ключ или создайте следующую версию существующего типа.')
            if body.create_new:
                from .registry import check_schema
                check_schema(body.schema_)
                if body.schema_['properties'].get('title',{}).get('type')!='string' or 'title' not in body.schema_.get('required',[]):
                    raise HTTPException(422,'Для нового типа добавьте обязательный строковый реквизит title — название объекта.')
            return create_type(c, body.type_key, body.name, body.schema_)

    @app.get("/api/artifacts")
    def listing(q: str = "", status: str = "", type_id: str = ""):
        with db.engine.connect() as c:
            return list_artifacts(c, q, status, type_id)

    @app.post("/api/artifacts", status_code=201)
    def create(body: ArtifactCreate):
        with db.transaction() as c:
            return save_artifact(c, body.type_id, body.fields, body.status)

    @app.get("/api/artifacts/{id}")
    def get_artifact(id: str):
        with db.engine.connect() as c:
            return artifact_view(c, id)

    @app.put("/api/artifacts/{id}")
    def edit(id: str, body: ArtifactEdit):
        with db.transaction() as c:
            old = require(c, artifacts, id)
            return save_artifact(c, old["type_id"], body.fields, body.status, id=id, expected_revision=body.expected_revision)

    @app.get("/api/artifacts/{id}/revisions")
    def history(id: str):
        with db.engine.connect() as c:
            require(c, artifacts, id)
            return list(c.execute(select(revisions.c.data).where(revisions.c.artifact_id == id).order_by(revisions.c.revision.desc())).scalars())

    @app.post("/api/uploads", status_code=201)
    def upload(file: UploadFile = File(...), type_id: str = Form(...), mode: str = Form("table"),
               table_index: int | None = Form(None), resource_id: str | None = Form(None), target_id: str | None = Form(None), pipeline_id: str | None = Form(None)):
        filename = Path((file.filename or "document.html").replace("\\", "/")).name
        if Path(filename).suffix.lower() not in {".html", ".htm"}:
            raise HTTPException(422, "Выберите HTML-файл (.html или .htm)")
        if mode not in {"table", "sections"}:
            raise HTTPException(422, "Неизвестный способ извлечения")
        content = file.file.read(MAX_UPLOAD + 1)
        if len(content) > MAX_UPLOAD:
            raise HTTPException(413, "Максимальный размер HTML — 5 MiB")
        document = parse_html(content, "pending")
        with db.engine.connect() as c:
            pipeline = load_pipeline(c, pipeline_id, type_id)
            schema = require(c, types, type_id)["schema"]
        result, config = evaluate(document, schema, pipeline, db=db)
        with db.transaction() as c:
            return import_html(db, c, content, filename, type_id, mode, table_index, resource_id or None, target_id or None,
                               parser=lambda _, sid: {**document, "snapshot_id": sid}, prepared_result=result, pipeline_config=config)

    @app.get("/api/candidates")
    def candidate_list():
        with db.engine.connect() as c:
            items = list(c.execute(select(candidates.c.data)).scalars())
            return sorted(items, key=lambda x: x["created_at"], reverse=True)

    @app.get("/api/candidates/{id}")
    def get_candidate(id: str):
        with db.engine.connect() as c:
            return candidate_view(c, id)

    @app.post("/api/candidates/{id}/review")
    def review(id: str, body: ReviewRequest):
        with db.transaction() as c:
            return review_candidate(c, id, body)

    @app.post("/api/candidates/{id}/rebase")
    def rebase(id: str):
        with db.transaction() as c:
            return rebase_candidate(c, id)

    @app.post("/api/candidates/{id}/reject")
    def reject(id: str):
        with db.transaction() as c:
            item = require(c, candidates, id)
            if item["status"] != "pending":
                raise HTTPException(409, "Предложение уже обработано")
            item.update(status="rejected", reviewed_at=now())
            c.execute(candidates.update().where(candidates.c.id == id).values(data=item))
            return item

    @app.get("/api/snapshots/{id}")
    def snapshot(id: str):
        with db.engine.connect() as c:
            return require(c, snapshots, id)

    @app.get("/api/snapshots/{id}/download")
    def download(id: str):
        with db.engine.connect() as c:
            item = require(c, snapshots, id)
        return FileResponse(db.directory / "blobs" / item["sha256"], filename=item["filename"], media_type="application/octet-stream")

    @app.get("/api/export")
    def export(include_drafts: bool = False):
        with db.engine.connect() as c:
            items = list_artifacts(c, status="" if include_drafts else "published")
            return JSONResponse({"export_format_version": 1, "exported_at": now(),
                                 "types": list(c.execute(select(types.c.data)).scalars()),
                                 "artifacts": [artifact_view(c, a["id"]) for a in items]},
                                headers={"Content-Disposition": 'attachment; filename="architecture-registry.json"'})

    dist = frontend_dir or PROJECT_ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        @app.get("/")
        def not_built():
            return JSONResponse({"detail": "Соберите интерфейс: npm --prefix frontend run build"}, status_code=503)
    return app

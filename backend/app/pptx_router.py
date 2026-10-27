from uuid import uuid5, UUID
from typing import Literal
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import Field
from sqlalchemy import select
from .contracts import StrictModel
from .db import types, resources, connections, links, find
from .registry import require
from .pptx_parser import parse_pptx, MAX_PPTX
from .pipelines import evaluate, load_pipeline
from .imports import import_html
from .confluence.attachments import resolve_attachment, fetch_attachment
from .confluence.client import ConfluenceError


class ResolveRequest(StrictModel):
    connection_id: str
    link: str = Field(min_length=1, max_length=4096)


class AttachmentImport(ResolveRequest):
    type_id: str
    mode: Literal["table", "sections"] = "table"
    table_index: int | None = Field(default=None, ge=0)
    pipeline_id: str | None = None
    target_id: str | None = None
    standalone: bool = False
    expected_version: int = Field(ge=1)


def build_pptx_router(db, secrets, factory):
    router = APIRouter(prefix="/api/pptx")

    @router.post("/uploads", status_code=201)
    def upload(file: UploadFile = File(...), type_id: str = Form(...), mode: str = Form("table"), table_index: int | None = Form(None),
               pipeline_id: str | None = Form(None), target_id: str | None = Form(None), resource_id: str | None = Form(None)):
        if not file.filename or not file.filename.lower().endswith(".pptx"): raise HTTPException(422, "Выберите PPTX-файл")
        if mode not in {"table", "sections"}: raise HTTPException(422, "Неизвестный способ извлечения")
        content = file.file.read(MAX_PPTX + 1)
        if len(content) > MAX_PPTX: raise HTTPException(413, "PPTX превышает 25 MiB")
        document = parse_pptx(content, "pending")
        with db.engine.connect() as c:
            schema = require(c, types, type_id)["schema"]
            pipeline = load_pipeline(c, pipeline_id, type_id)
            if resource_id and require(c, resources, resource_id)["kind"] != "pptx": raise HTTPException(422, "Выбранный источник не является локальным PPTX")
        result, config = evaluate(document, schema, pipeline, db=db)
        with db.transaction() as c:
            return import_html(db, c, content, file.filename, type_id, mode, table_index, resource_id, target_id,
                               source_kind="pptx", parser=lambda _, sid: {**document, "snapshot_id": sid}, prepared_result=result, pipeline_config=config)

    def remote(body):
        with db.engine.connect() as c: connection = require(c, connections, body.connection_id)
        try: token = secrets.get(body.connection_id)
        except RuntimeError as e: raise HTTPException(503, str(e)) from None
        if not token: raise HTTPException(422, "Введите PAT подключения Confluence")
        return factory(connection["base_url"], token)

    @router.post("/resolve")
    def resolve(body: ResolveRequest):
        try:
            with remote(body) as client: return resolve_attachment(client, body.link)
        except ConfluenceError as e: raise HTTPException(502, str(e)) from None

    @router.post("/attachments", status_code=201)
    def attachment(body: AttachmentImport):
        try:
            with remote(body) as client:
                metadata = resolve_attachment(client, body.link)
                if metadata["version"] != body.expected_version: raise HTTPException(409, "Версия вложения изменилась. Проверьте ссылку ещё раз")
                resource_id = str(uuid5(UUID(body.connection_id), "attachment:" + metadata["attachment_id"]))
                parent_id = str(uuid5(UUID(body.connection_id), metadata["parent_page_id"]))
                with db.engine.connect() as c:
                    schema = require(c, types, body.type_id)["schema"]
                    pipeline = load_pipeline(c, body.pipeline_id, body.type_id)
                    target_id = body.target_id
                    if not target_id and not body.standalone:
                        for rid in (resource_id, parent_id):
                            target_id = c.execute(select(links.c.artifact_id).where(links.c.resource_id == rid, links.c.type_id == body.type_id)).scalar_one_or_none()
                            if target_id: break
                        if not target_id: raise HTTPException(409, "У страницы пока нет объекта этой версии типа. Сначала примите импорт страницы, выберите существующий объект или явно включите отдельный объект")
                content = fetch_attachment(client, metadata)
        except ConfluenceError as e: raise HTTPException(502, str(e)) from None
        document = parse_pptx(content, "pending")
        result, config = evaluate(document, schema, pipeline, db=db)
        metadata.update(kind="confluence_attachment", connection_id=body.connection_id)
        with db.transaction() as c:
            previous = find(c, resources, resource_id)
            resource = {"id": resource_id, "kind": "confluence_attachment", "name": metadata["title"], **metadata,
                        "role": previous["data"].get("role", "primary") if previous else "supplementary" if target_id else "primary"}
            if find(c, resources, resource_id): c.execute(resources.update().where(resources.c.id == resource_id).values(data=resource))
            else: c.execute(resources.insert().values(id=resource_id, data=resource))
            return import_html(db, c, content, metadata["title"], body.type_id, body.mode, body.table_index, resource_id, target_id,
                               source_kind="pptx", source_metadata=metadata, parser=lambda _, sid: {**document, "snapshot_id": sid},
                               prepared_result=result, pipeline_config=config)
    return router

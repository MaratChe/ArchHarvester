from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import Field, SecretStr, field_validator
from sqlalchemy import select
from ..contracts import StrictModel
from ..db import connections, previews, jobs
from ..registry import now, require, uid
from .client import ConfluenceError, normalize_url
from .jobs import create_job


class ConnectionCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(max_length=2048)
    token: SecretStr

    @field_validator("base_url")
    @classmethod
    def url(cls, value): return normalize_url(value)

    @field_validator("token")
    @classmethod
    def pat(cls, value):
        raw = value.get_secret_value()
        if not raw or len(raw) > 1280 or not raw.isascii() or any(ch.isspace() for ch in raw):
            raise ValueError("PAT должен быть непустой ASCII-строкой без пробелов (до 1280 символов)")
        return value


class TokenUpdate(StrictModel):
    token: SecretStr
    _pat = field_validator("token")(ConnectionCreate.pat.__func__)


class PreviewCreate(StrictModel):
    connection_id: str
    cql: str = Field(min_length=1, max_length=8000)
    max_pages: int = Field(default=500, ge=1, le=500)


class JobCreate(StrictModel):
    preview_id: str
    page_ids: list[str] = Field(min_length=1, max_length=500)
    type_id: str
    pipeline_id: str | None = None
    mode: Literal["table", "sections"] = "table"
    table_index: int | None = Field(default=None, ge=0, le=1000)


def build_router(db, secrets, client_factory, worker):
    router = APIRouter(prefix="/api/confluence")

    def credential(key):
        try: return secrets.get(key)
        except RuntimeError as e: raise HTTPException(503, str(e)) from None

    @router.get("/connections")
    def listing():
        with db.engine.connect() as c:
            configs = list(c.execute(select(connections.c.data)).scalars())
        return [{**config, "has_token": bool(credential(config["id"]))} for config in configs]

    @router.post("/connections", status_code=201)
    def create(body: ConnectionCreate):
        with db.transaction() as c:
            if c.execute(select(connections.c.id).where(connections.c.base_url == body.base_url)).first():
                raise HTTPException(409, "Такое подключение уже существует. При необходимости обновите его PAT.")
            data = {"id":uid(), "name":body.name, "base_url":body.base_url, "edition":"data_center", "created_at":now()}
            try: secrets.set(data["id"], body.token.get_secret_value())
            except RuntimeError as e: raise HTTPException(503, str(e)) from None
            try: c.execute(connections.insert().values(id=data["id"],base_url=data["base_url"],data=data))
            except Exception:
                secrets.delete(data["id"])
                raise
        return {**data,"has_token":True}

    @router.put("/connections/{id}/token")
    def token_update(id: str, body: TokenUpdate):
        with db.engine.connect() as c: require(c, connections, id)
        try: secrets.set(id, body.token.get_secret_value())
        except RuntimeError as e: raise HTTPException(503, str(e)) from None
        return {"has_token":True}

    @router.delete("/connections/{id}/token")
    def token_delete(id: str):
        with db.engine.connect() as c: require(c, connections, id)
        try: secrets.delete(id)
        except RuntimeError as e: raise HTTPException(503, str(e)) from None
        return {"has_token":False}

    def discover(id, cql, max_pages):
        with db.engine.connect() as c: config = require(c, connections, id)
        token = credential(id)
        if not token: raise HTTPException(422, "Введите PAT для подключения")
        try:
            with client_factory(config["base_url"], token) as client:
                return client.discover(cql, max_pages)
        except ConfluenceError as e:
            raise HTTPException(502, {"code":e.code,"message":str(e)}) from None

    @router.post("/connections/{id}/test")
    def test_connection(id: str):
        result = discover(id,"type = page",1)
        return {"ok":True,"visible_pages":len(result["pages"])}

    @router.post("/previews", status_code=201)
    def preview(body: PreviewCreate):
        result = discover(body.connection_id,body.cql,body.max_pages)
        data = {"id":uid(),"connection_id":body.connection_id,"cql":body.cql,"created_at":now(),**result}
        with db.transaction() as c: c.execute(previews.insert().values(id=data["id"],data=data))
        return data

    @router.post("/jobs", status_code=201)
    def enqueue(body: JobCreate):
        with db.transaction() as c:
            result = create_job(c,body.preview_id,body.page_ids,body.type_id,body.mode,body.table_index,pipeline_id=body.pipeline_id)
        worker.wake.set()
        return result

    @router.get("/jobs")
    def list_jobs():
        with db.engine.connect() as c:
            return sorted(c.execute(select(jobs.c.data)).scalars(),key=lambda x:x["created_at"],reverse=True)

    @router.get("/jobs/{id}")
    def get_job(id: str):
        with db.engine.connect() as c: return require(c,jobs,id)

    @router.post("/jobs/{id}/cancel")
    def cancel(id: str):
        with db.transaction() as c:
            data = require(c,jobs,id)
            if data["status"] not in {"queued","running"}: raise HTTPException(409,"Загрузка уже завершена")
            data["cancel_requested"] = True
            c.execute(jobs.update().where(jobs.c.id==id).values(data=data))
        worker.wake.set()
        return data

    @router.post("/jobs/{id}/retry", status_code=201)
    def retry(id: str):
        with db.transaction() as c:
            old = require(c,jobs,id)
            if old["status"] in {"queued","running"}: raise HTTPException(409,"Дождитесь окончания текущей загрузки")
            page_ids = [item["page_id"] for item in old["items"] if item["status"] == "failed"]
            if not page_ids: raise HTTPException(409,"Нет неуспешных страниц для повтора")
            data = create_job(c,old["preview_id"],page_ids,old["type_id"],old["mode"],old["table_index"],retry_of=id,pipeline_id=old.get("pipeline_id"))
        worker.wake.set()
        return data

    return router

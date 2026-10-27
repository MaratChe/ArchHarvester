from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import Field,SecretStr,field_validator
from sqlalchemy import select
from .contracts import StrictModel
from .db import providers
from .registry import uid,now,require
from .providers import normalize_base_url


class ProviderCreate(StrictModel):
    name:str=Field(min_length=1,max_length=100)
    base_url:str=Field(min_length=1,max_length=1000)
    response_format:Literal['json_object','json_schema','text']='json_object'
    token_parameter:Literal['max_tokens','max_completion_tokens']='max_tokens'
    send_temperature:bool=True
    deployment_revision:str=Field(default='1',min_length=1,max_length=100)
    auth_required:bool=True
    api_key:SecretStr|None=None

    @field_validator('base_url')
    @classmethod
    def url(cls,value):return normalize_base_url(value)


class KeyChange(StrictModel):
    api_key:SecretStr


class Enabled(StrictModel):
    enabled:bool


def valid_key(secret):
    value=secret.get_secret_value() if secret else None
    if value is not None and (not value or len(value)>1280 or not value.isascii() or any(ord(c)<33 or ord(c)>126 for c in value)):
        raise HTTPException(422,'API-ключ: 1–1280 печатных ASCII-символов без пробелов')
    return value


def build_provider_router(db):
    router=APIRouter(prefix='/api/providers');store=db.provider_registry.secrets

    def view(row):
        try:return {**row,'has_key':bool(store.get(row['id']))}
        except RuntimeError:raise HTTPException(503,'Не удалось прочитать состояние API-ключа') from None

    @router.get('')
    def listing():
        with db.engine.connect() as c:return [view(row) for row in c.execute(select(providers.c.data)).scalars()]

    @router.post('',status_code=201)
    def create(body:ProviderCreate):
        key=valid_key(body.api_key)
        if body.auth_required and not key:raise HTTPException(422,'Введите API-ключ или выберите подключение без авторизации')
        row={**body.model_dump(exclude={'api_key'}),'id':uid(),'enabled':True,'credential_revision':1,'created_at':now()}
        written=False
        try:
            with db.transaction() as c:
                c.execute(providers.insert().values(id=row['id'],data=row))
                if key:store.set(row['id'],key);written=True
        except Exception as exc:
            if written:store.delete(row['id'])
            if isinstance(exc,RuntimeError):raise HTTPException(503,'Не удалось сохранить API-ключ в Windows Credential Manager') from None
            raise
        return view(row)

    def change_key(id,key):
        # Serialize credential changes with their DB revision; restore old secret on commit failure.
        old=None;written=False
        try:
            with db.transaction() as c:
                row=require(c,providers,id);old=store.get(id)
                if key is None:store.delete(id)
                else:store.set(id,key)
                written=True;row['credential_revision']+=1
                c.execute(providers.update().where(providers.c.id==id).values(data=row))
        except Exception as exc:
            if written:
                if old is None:store.delete(id)
                else:store.set(id,old)
            if isinstance(exc,RuntimeError):raise HTTPException(503,'Не удалось изменить API-ключ в Windows Credential Manager') from None
            raise
        return view(row)

    @router.put('/{id}/key')
    def rotate(id:str,body:KeyChange):return change_key(id,valid_key(body.api_key))

    @router.delete('/{id}/key')
    def delete_key(id:str):return change_key(id,None)

    @router.put('/{id}/enabled')
    def enabled(id:str,body:Enabled):
        with db.transaction() as c:
            row=require(c,providers,id);row['enabled']=body.enabled
            c.execute(providers.update().where(providers.c.id==id).values(data=row))
        return view(row)

    return router

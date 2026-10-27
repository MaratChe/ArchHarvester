import time
from fastapi import APIRouter,HTTPException
from pydantic import Field
from sqlalchemy import select
from .contracts import StrictModel
from .db import types,snapshots,llm_outputs
from .registry import require
from .ollama import Ollama,extract_fields,BASE_URL,SYSTEM
from .evidence import evidence_for
from .imports import import_html
from .semantic import build_index,index_status,search
from .llm_history import cleanup
from .providers import client_for


class ExtractionRequest(StrictModel):
    provider_id:str=Field(default='ollama',min_length=1,max_length=100)
    snapshot_id:str
    type_id:str
    model:str=Field(default='ornith-1.5:9b',min_length=1,max_length=150)
    block_ids:list[str]|None=Field(default=None,max_length=200)


class IndexRequest(StrictModel):
    provider_id:str=Field(default='ollama',min_length=1,max_length=100)
    model:str=Field(default='bge-m3:latest',min_length=1,max_length=150)


def build_llm_router(db):
    router=APIRouter(prefix='/api')

    @router.get('/llm/default-prompt')
    def default_prompt():return {'prompt':SYSTEM}

    @router.get('/llm/models')
    def models(provider_id:str='ollama'):
        with db.transaction() as c:cleanup(c)
        if provider_id!='ollama':
            client=client_for(db,provider_id)
            return {'endpoint':client.base_url,'models':[{**m,'capabilities':[]} for m in client.models()]}
        client=Ollama(); models=[]
        for item in client.models():
            info=client.request('POST','/api/show',{'model':item['name']})
            if not info.get('remote_host') and not info.get('remote_model') and 'cloud' not in item['name'].lower():
                models.append({'name':item['name'],'size':item.get('size'),'digest':item['digest'],'capabilities':info.get('capabilities',[])})
        return {'endpoint':BASE_URL,'models':models,'default_generation':'ornith-1.5:9b','default_embedding':'bge-m3:latest'}

    @router.post('/llm/propose',status_code=201)
    def propose(body:ExtractionRequest):
        with db.engine.connect() as c:
            snapshot=require(c,snapshots,body.snapshot_id)
            schema=require(c,types,body.type_id)['schema']
        result=extract_fields(snapshot['document'],schema,body.model,block_ids=body.block_ids,client=client_for(db,body.provider_id))
        blocks={b['id']:b for b in snapshot['document']['blocks']}
        prepared={'proposals':{},'warnings':result['warnings'],'llm_runs':[result['metadata']],
                  '_llm_raw':[{'id':result['metadata']['run_id'],**result['trace']}]}
        for p in result['proposals']:
            prepared['proposals'][p['field']]={'value':p['value'],'method':'llm_extract' if p['mode']=='extracted' else 'llm_transform','model_metadata':result['metadata'],
                'evidence':[{**evidence_for(snapshot['document'],blocks[e['block_id']]),'quote':e['quote']} for e in p['evidence']]}
        content=(db.directory/'blobs'/snapshot['sha256']).read_bytes()
        with db.transaction() as c:
            return import_html(db,c,content,snapshot['filename'],body.type_id,'table',None,snapshot['resource_id'],
                source_metadata=snapshot.get('source_metadata'),source_kind='pptx' if snapshot['document'].get('format')=='pptx' else 'html',
                parser=lambda _,sid:{**snapshot['document'],'snapshot_id':sid},prepared_result=prepared,pipeline_config={'pipeline_version':'llm-v2','provider_id':body.provider_id})

    @router.get('/llm/runs/{id}/raw')
    def raw(id:str):
        with db.transaction() as c:
            cleanup(c)
            row=c.execute(select(llm_outputs).where(llm_outputs.c.id==id)).mappings().first()
            if not row:raise HTTPException(404,'Сырой ответ отсутствует или срок хранения истёк')
            return row['data']

    @router.get('/search/index')
    def status():return index_status(db)

    @router.post('/search/index')
    def index(body:IndexRequest):return build_index(db,body.model,provider_id=body.provider_id)

    @router.get('/search')
    def lookup(q:str='',status:str='',type_id:str='',limit:int=50):
        if len(q)>2000 or not 1<=limit<=100:raise HTTPException(422,'Запрос до 2000 символов, limit от 1 до 100')
        return search(db,q,status=status,type_id=type_id,limit=limit)

    return router

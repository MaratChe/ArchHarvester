import math
import threading
import re
from fastapi import HTTPException
from sqlalchemy import select
from .db import artifacts,types,search_indexes,search_vectors
from .registry import uid,now,list_artifacts
from .ollama import Ollama
from .providers import client_for

BUILD_LOCK=threading.Lock()


def chunks(artifact,labels=None):
    labels=labels or {}
    text='\n'.join(f'{labels.get(k,k)}: {v}' for k,v in artifact['fields'].items())
    return [text[i:i+1500] for i in range(0,len(text),1300)] or ['(empty)']


def normalize(vector):
    norm=math.sqrt(sum(v*v for v in vector))
    if not vector or not math.isfinite(norm) or norm<=0:raise HTTPException(502,'Некорректный вектор embeddings')
    return [v/norm for v in vector]


def active_index(c):
    return next((i for i in c.execute(select(search_indexes.c.data)).scalars() if i.get('active')),None)


def index_status(db):
    with db.engine.connect() as c:
        index=active_index(c)
        current={a['id']:a['revision'] for a in c.execute(select(artifacts.c.data)).scalars()}
        ready=set()
        if index:
            for v in c.execute(select(search_vectors.c.data).where(search_vectors.c.index_id==index['id'])).scalars():
                if current.get(v['artifact_id'])==v['revision']:ready.add(v['artifact_id'])
        return {'index':index,'total':len(current),'indexed':len(ready),'stale':len(current)-len(ready),'building':BUILD_LOCK.locked()}


def build_index(db,model,*,client=None,provider_id='ollama'):
    if not BUILD_LOCK.acquire(blocking=False):raise HTTPException(409,'Индекс уже строится')
    try:
        client=client or client_for(db,provider_id); identity=client.identity(model,'embedding')
        with db.engine.connect() as c:
            items=list(c.execute(select(artifacts.c.data)).scalars())
            labels={t['id']:{k:p.get('title',k) for k,p in t['schema']['properties'].items()} for t in c.execute(select(types.c.data)).scalars()}
        if len(items)>5000:raise HTTPException(422,'Пилотный индекс ограничен 5000 объектами')
        rows=[]; dimension=None; index_id=uid()
        vector_values=0
        for item in items:
            texts=chunks(item,labels.get(item['type_id']))
            if len(texts)>100:raise HTTPException(422,'Объект слишком велик для пилотного индекса (100 чанков)')
            for start in range(0,len(texts),8):
                batch=texts[start:start+8];vectors=client.embed(batch,model)
                if len(vectors)!=len(batch):raise HTTPException(502,'Неверное число embeddings')
                for text,vector in zip(batch,vectors):
                    if dimension is not None and len(vector)!=dimension:raise HTTPException(502,'Размерность модели изменилась; индекс не опубликован')
                    dimension=len(vector)
                    vector_values+=dimension
                    if vector_values>5_000_000:raise HTTPException(422,'Пилотный индекс превышает 5 млн компонент векторов; уменьшите объём реестра')
                    rows.append({'id':uid(),'index_id':index_id,'data':{'artifact_id':item['id'],'revision':item['revision'],'vector':normalize(vector),'text':text}})
        if client.identity(model,'embedding')!=identity:raise HTTPException(409,'Модель изменилась во время построения индекса')
        index={'id':index_id,'model':model,'digest':identity['digest'],'dimension':dimension,'active':True,'created_at':now(),'objects':len(items),'chunks':len(rows),'chunk_version':'labels-1500-200-v1'}
        index.update(provider_id=provider_id,identity_kind=identity.get('identity_kind','weights'),resolved_model=getattr(client,'embedding_model',None))
        if hasattr(client,'config'):index.update(provider_name=client.config['name'],base_url=client.base_url,deployment_revision=client.config.get('deployment_revision','1'))
        with db.transaction() as c:
            # Validate every revision before publishing; no network while holding a write lock.
            current={a['id']:a['revision'] for a in c.execute(select(artifacts.c.data)).scalars()}
            if current!={a['id']:a['revision'] for a in items}:raise HTTPException(409,'Реестр изменился во время индексации. Повторите обновление индекса.')
            for old in c.execute(select(search_indexes.c.data)).scalars():
                old={**old,'active':False};c.execute(search_indexes.update().where(search_indexes.c.id==old['id']).values(data=old))
            c.execute(search_indexes.insert().values(id=index_id,data=index))
            if rows:c.execute(search_vectors.insert(),rows)
            # Only the active generation needs vectors; generation metadata remains auditable.
            c.execute(search_vectors.delete().where(search_vectors.c.index_id!=index_id))
    finally:BUILD_LOCK.release()
    return index_status(db)


def search(db,q,*,status='',type_id='',limit=50,client=None):
    with db.engine.connect() as c:
        lexical=list_artifacts(c,q,status,type_id)
        tokens=re.findall(r'\w+',q,re.UNICODE)
        if tokens:
            match=' AND '.join('"'+t+'"*' for t in tokens)
            lexical_ranks={row[0]:rank for rank,row in enumerate(c.exec_driver_sql('SELECT id FROM artifact_fts WHERE artifact_fts MATCH ? ORDER BY bm25(artifact_fts)',(match,)))}
            lexical.sort(key=lambda a:lexical_ranks.get(a['id'],-1))
        index=active_index(c)
        candidates={a['id']:a for a in list_artifacts(c,'',status,type_id)}
        vectors=list(c.execute(select(search_vectors.c.data).where(search_vectors.c.index_id==index['id'])).scalars()) if index else []
    if not q.strip():return {'items':list(candidates.values())[:limit],'warning':None,'mode':'all'}
    warning=None; semantic=[]; details={}
    try:
        if not index or not index['dimension']:raise HTTPException(409,'Семантический индекс ещё не построен')
        client=client or client_for(db,index.get('provider_id','ollama'))
        identity=client.identity(index['model'],'embedding')
        if identity['digest']!=index['digest']:raise HTTPException(409,'Embedding-модель изменилась: перестройте индекс')
        query=normalize(client.embed([q],index['model'])[0])
        if index.get('resolved_model')!=getattr(client,'embedding_model',None):raise HTTPException(409,'API сменил embedding-модель: перестройте индекс')
        if len(query)!=index['dimension']:raise HTTPException(409,'Размерность модели изменилась: перестройте индекс')
        if client.identity(index['model'],'embedding')!=identity:raise HTTPException(409,'Модель изменилась во время поиска')
        scores={}
        for row in vectors:
            item=candidates.get(row['artifact_id'])
            if not item or item['revision']!=row['revision']:continue
            if len(row['vector'])!=len(query):raise HTTPException(409,'Размерность индекса нарушена: перестройте индекс')
            score=sum(a*b for a,b in zip(query,row['vector']))
            if score>scores.get(item['id'],-2):scores[item['id']]=score;details[item['id']]=row['text']
        semantic=sorted(scores,key=lambda id:(-scores[id],id))[:limit]
    except HTTPException as e:warning=str(e.detail)+'. Показан поиск по словам.'
    ranks={}
    for channel in ([a['id'] for a in lexical],semantic):
        for rank,id in enumerate(channel,1):ranks[id]=ranks.get(id,0)+1/(60+rank)
    ids=sorted(ranks,key=lambda id:(-ranks[id],id))[:limit]
    # A concurrent manual edit must not return an older revision from the in-memory snapshot.
    with db.engine.connect() as c:
        fresh={a['id']:a for a in list_artifacts(c,'',status,type_id)}
    items=[{**fresh[id],'search_match':details.get(id),'search_method':'hybrid' if id in semantic else 'keyword'} for id in ids if id in fresh and fresh[id]['revision']==candidates[id]['revision']]
    return {'items':items,'warning':warning,'mode':'keyword' if warning else 'hybrid'}

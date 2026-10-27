from backend.app.semantic import build_index, search
from tests.conftest import upload


class Embedder:
    def identity(self,model,capability):return {'name':model,'digest':'digest1'}
    def embed(self,texts,model):return [[1.,0.] if 'delivery' in t.lower() or 'transport' in t.lower() else [0.,1.] for t in texts]


def test_semantic_revision_filter_and_keyword_fallback(client,type_id):
    a=client.post('/api/artifacts',json={'type_id':type_id,'fields':{'title':'Delivery queue'},'status':'published'}).json()
    db=client.app.state.db
    build_index(db,'embed:1',client=Embedder())
    result=search(db,'transport',client=Embedder())
    assert result['items'][0]['id']==a['id']
    client.put('/api/artifacts/'+a['id'],json={'expected_revision':1,'fields':{'title':'Unrelated'},'status':'published'})
    assert search(db,'transport',client=Embedder())['items']==[]
    class Offline(Embedder):
        def identity(self,*a):
            from fastapi import HTTPException
            raise HTTPException(503,'offline')
    result=search(db,'Unrelated',client=Offline())
    assert result['items'][0]['id']==a['id'] and result['warning']


def test_model_change_dimension_failure_and_filters(client,type_id):
    from backend.app.semantic import index_status
    from fastapi import HTTPException
    import pytest
    for status in ['draft','published']:client.post('/api/artifacts',json={'type_id':type_id,'fields':{'title':'Delivery '+status},'status':status})
    build_index(client.app.state.db,'embed:1',client=Embedder())
    original=index_status(client.app.state.db)['index']['id']
    class Changed(Embedder):
        def identity(self,*a):return {'name':'embed:1','digest':'changed'}
    r=search(client.app.state.db,'Delivery',status='published',client=Changed())
    assert len(r['items'])==1 and r['items'][0]['status']=='published' and r['warning']
    class Broken(Embedder):
        def __init__(self):self.calls=0
        def embed(self,texts,model):
            self.calls+=1
            return [[1.,0.] if self.calls==1 else [1.,0.,0.] for t in texts]
    with pytest.raises(HTTPException):build_index(client.app.state.db,'embed:1',client=Broken())
    assert index_status(client.app.state.db)['index']['id']==original


def test_index_rejects_concurrent_registry_edit(client,type_id):
    import pytest
    from fastapi import HTTPException
    a=client.post('/api/artifacts',json={'type_id':type_id,'fields':{'title':'Delivery'},'status':'draft'}).json()
    class Editing(Embedder):
        def embed(self,texts,model):
            client.put('/api/artifacts/'+a['id'],json={'expected_revision':1,'fields':{'title':'Changed'},'status':'draft'})
            return super().embed(texts,model)
    with pytest.raises(HTTPException,match='изменился'):build_index(client.app.state.db,'embed:1',client=Editing())

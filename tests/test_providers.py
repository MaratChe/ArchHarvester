import json
import httpx
import pytest
from fastapi import HTTPException
from backend.app.providers import OpenAICompatible, normalize_base_url
from backend.app.ollama import extract_fields
from backend.app.html_parser import parse_html
from backend.app.registry import DEFAULT_SCHEMA

CONFIG={'id':'p1','name':'Proxy','base_url':'https://proxy.example/api/v1','response_format':'json_object','token_parameter':'max_tokens','deployment_revision':'1','credential_revision':1,'enabled':True,'auth_required':True}


def test_openai_protocol_and_no_ollama_options():
    seen=[]
    def handler(r):
        seen.append(r)
        assert str(r.url)=='https://proxy.example/api/v1/chat/completions'
        assert r.headers['authorization']=='Bearer secret-test'
        body=json.loads(r.content)
        assert body['response_format']=={'type':'json_object'} and body['max_tokens']==2048
        assert not {'think','keep_alive','options','format'} & set(body)
        assert 'proposals' in body['messages'][0]['content']
        return httpx.Response(200,json={'model':'vendor/model-1','choices':[{'finish_reason':'stop','message':{'content':json.dumps({'proposals':[{'field':'title','value':'Delivery','mode':'extracted','evidence':[{'block_id':'b0','quote':'Delivery'}]}]})}}]})
    client=OpenAICompatible(CONFIG,'secret-test',transport=httpx.MockTransport(handler))
    result=extract_fields(parse_html(b'<p>Delivery</p>','s'),DEFAULT_SCHEMA,'deployment',client=client)
    assert result['metadata']['provider_id']=='p1'
    assert result['metadata']['identity_kind']=='configuration'
    assert result['metadata']['resolved_model']=='vendor/model-1'
    assert len(seen)==1 and 'secret-test' not in json.dumps(result)


def test_embeddings_order_and_validation():
    def handler(r):
        assert r.url.path=='/api/v1/embeddings'
        return httpx.Response(200,json={'model':'embed-1','data':[{'index':1,'embedding':[0,1]},{'index':0,'embedding':[1,0]}]})
    client=OpenAICompatible(CONFIG,'key',transport=httpx.MockTransport(handler))
    assert client.embed(['one','two'],'alias')==[[1,0],[0,1]]
    assert client.embedding_model=='embed-1'


@pytest.mark.parametrize('status',[301,401,403,429,500])
def test_errors_never_echo_keys_or_follow_redirects(status):
    seen=[]
    def handler(r):seen.append(r);return httpx.Response(status,text='secret-test',headers={'location':'https://evil.example'})
    cli=OpenAICompatible(CONFIG,'secret-test',transport=httpx.MockTransport(handler))
    with pytest.raises(HTTPException) as e:cli.models()
    assert 'secret-test' not in str(e.value.detail) and len(seen)==1


def test_url_validation():
    assert normalize_base_url('http://localhost:4000/v1/')=='http://localhost:4000/v1'
    assert normalize_base_url('https://openrouter.ai/api/v1')=='https://openrouter.ai/api/v1'
    for url in ['http://remote.example/v1','https://user:pass@host/v1','https://host/v1?q=secret','https://host/a/../b']:
        with pytest.raises(ValueError):normalize_base_url(url)


class Secrets:
    def __init__(self):self.values={}
    def get(self,id):return self.values.get(id)
    def set(self,id,value):self.values[id]=value
    def delete(self,id):self.values.pop(id,None)


def test_profile_review_pipeline_index_and_rotation(tmp_path):
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    from backend.app.pipeline_engine import run_pipeline
    from backend.app.providers import client_for
    from backend.app.db import providers
    from sqlalchemy import select
    calls=[]
    def handler(r):
        calls.append(r.url.path)
        if r.url.path.endswith('/models'):return httpx.Response(404)
        if r.url.path.endswith('/embeddings'):
            body=json.loads(r.content)
            return httpx.Response(200,json={'model':'embedding-real','data':[{'index':i,'embedding':[1,0]} for i in range(len(body['input']))]})
        return httpx.Response(200,json={'model':'chat-real','choices':[{'finish_reason':'stop','message':{'content':json.dumps({'proposals':[{'field':'title','value':'Delivery','mode':'extracted','evidence':[{'block_id':'b0','quote':'Delivery'}]}]})}}]})
    secrets=Secrets();app=create_app(tmp_path,provider_secret_store=secrets,provider_transport=httpx.MockTransport(handler),start_worker=False)
    with TestClient(app,base_url='http://127.0.0.1') as c:
        c.headers['X-Local-Token']=c.get('/api/session').json()['token']
        profile=c.post('/api/providers',json={'name':'Gateway','base_url':CONFIG['base_url'],'api_key':'private-key-123'});assert profile.status_code==201,profile.text
        id=profile.json()['id'];assert profile.json()['has_key']
        assert 'private-key' not in profile.text+c.get('/api/providers').text
        with app.state.db.engine.connect() as conn:assert 'private-key' not in json.dumps(list(conn.execute(select(providers.c.data)).scalars()))
        type_id=c.get('/api/types').json()[0]['id']
        uploaded=c.post('/api/uploads',files={'file':('test.html',b'<p>Delivery</p>','text/html')},data={'type_id':type_id}).json()
        # Models endpoint is optional; manual model alias still generates only a pending candidate.
        assert c.get('/api/llm/models',params={'provider_id':id}).status_code==502
        response=c.post('/api/llm/propose',json={'snapshot_id':uploaded['snapshot_id'],'type_id':type_id,'model':'alias','provider_id':id})
        assert response.status_code==201,response.text
        assert response.json()['status']=='pending' and c.get('/api/artifacts').json()==[]
        assert response.json()['proposals']['title']['model_metadata']['provider_id']==id
        pipeline=run_pipeline(parse_html(b'<p>Delivery</p>','s'),DEFAULT_SCHEMA,[{'kind':'llm','model':'alias','provider_id':id}],client_factory=lambda id:client_for(app.state.db,id))
        assert pipeline['proposals']['title']['model_metadata']['provider_id']==id
        created=c.post('/api/artifacts',json={'type_id':type_id,'fields':{'title':'Delivery'},'status':'draft'})
        assert created.status_code==201,created.text
        indexed=c.post('/api/search/index',json={'model':'embed-alias','provider_id':id});assert indexed.status_code==200,indexed.text
        assert indexed.json()['building'] is False
        assert indexed.json()['index']['provider_id']==id
        assert c.get('/api/search',params={'q':'Delivery'}).json()['mode']=='hybrid'
        old=client_for(app.state.db,id)
        assert c.put(f'/api/providers/{id}/key',json={'api_key':'replacement'}).status_code==200
        with pytest.raises(HTTPException):old.identity('alias','embedding')
        before=len(calls);result=c.get('/api/search',params={'q':'Delivery'}).json()
        assert result['mode']=='keyword' and result['items'] and len(calls)==before
        assert c.delete(f'/api/providers/{id}/key').json()['has_key'] is False
        assert c.post('/api/search/index',json={'model':'embed','provider_id':id}).status_code==422


@pytest.mark.parametrize('data',[
    [{'index':0,'embedding':[1,0]},{'index':0,'embedding':[0,1]}],
    [{'index':0,'embedding':[0,0]},{'index':1,'embedding':[0,1]}],
    [{'index':0,'embedding':[True,1]},{'index':1,'embedding':[0,1]}],
    [{'index':0,'embedding':[1]},{'index':1,'embedding':[0,1]}],
    [{'index':0,'embedding':[10**400,1]},{'index':1,'embedding':[0,1]}],
])
def test_invalid_embeddings_rejected(data):
    cli=OpenAICompatible(CONFIG,'key',transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'data':data})))
    with pytest.raises(HTTPException):cli.embed(['a','b'],'alias')


def test_embedding_identity_cannot_appear_mid_build():
    responses=iter([{'data':[{'index':0,'embedding':[1,0]}]},{'model':'new-model','data':[{'index':0,'embedding':[1,0]}]}])
    cli=OpenAICompatible(CONFIG,transport=httpx.MockTransport(lambda r:httpx.Response(200,json=next(responses))))
    cli.embed(['a'],'alias')
    with pytest.raises(HTTPException):cli.embed(['b'],'alias')


@pytest.mark.parametrize('fmt',['text','json_schema'])
def test_alternate_protocol_formats(fmt):
    def handler(r):
        body=json.loads(r.content)
        assert 'max_completion_tokens' in body and 'temperature' not in body
        if fmt=='text':assert 'response_format' not in body
        else:assert body['response_format']['json_schema']['strict'] is False
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"proposals":[]}'}}]})
    cli=OpenAICompatible({**CONFIG,'response_format':fmt,'token_parameter':'max_completion_tokens','send_temperature':False},transport=httpx.MockTransport(handler))
    assert extract_fields(parse_html(b'<p>text</p>','s'),DEFAULT_SCHEMA,'alias',client=cli)['proposals']==[]

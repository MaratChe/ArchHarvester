from backend.app.registry import DEFAULT_SCHEMA
import pytest

@pytest.mark.parametrize('title,required',[(None,[]),({'type':'integer'},['title']),({'type':'string'},[])])
def test_new_type_requires_display_title(client,title,required):
    schema={'type':'object','additionalProperties':False,'required':required,'properties':{'description':{'type':'string'}}}
    if title:schema['properties']['title']=title
    response=client.post('/api/types',json={'type_key':'unnamed','name':'Unnamed','schema':schema,'create_new':True})
    assert response.status_code==422

def test_new_type_intent_cannot_create_another_version(client,type_id):
    body={'type_key':'system','name':'System','schema':DEFAULT_SCHEMA,'create_new':True}
    first=client.post('/api/types',json=body)
    assert first.status_code==201,first.text
    assert first.json()['version']==1
    assert client.post('/api/types',json=body).status_code==409
    body['create_new']=False
    second=client.post('/api/types',json=body)
    assert second.status_code==201 and second.json()['version']==2
    versions=[t for t in client.get('/api/types').json() if t['type_key']=='system']
    assert len(versions)==2

def test_new_schema_and_versions_leave_existing_object_unchanged(client):
    schema={'type':'object','additionalProperties':False,'description':'System registry','required':['title'],
            'properties':{'title':{'type':'string','title':'Name','minLength':1},'phase':{'type':'string','enum':['planned','live']},'tags':{'type':'array','items':{'type':'string'}},'active':{'type':'boolean'},'date':{'type':'string','format':'date'}}}
    first=client.post('/api/types',json={'type_key':'system','name':'System','schema':schema,'create_new':True}).json()
    item=client.post('/api/artifacts',json={'type_id':first['id'],'status':'published','fields':{'title':'Billing','phase':'live','tags':['core'],'active':True,'date':'2026-10-27'}})
    assert item.status_code==201,item.text
    schema['properties']['title']['title']='System name'
    newer=client.post('/api/types',json={'type_key':'system','name':'System','schema':schema}).json()
    assert newer['version']==2
    saved=client.get('/api/artifacts/'+item.json()['id']).json()
    assert saved['type_id']==first['id'] and saved['revision']==1

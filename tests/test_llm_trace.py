import json
import httpx
import pytest
from fastapi import HTTPException
from backend.app.ollama import extract_fields,SYSTEM
from backend.app.providers import OpenAICompatible
from tests.test_providers import CONFIG
from tests.test_llm_context import Model,DOC,RULE
from backend.app.registry import DEFAULT_SCHEMA

def test_trace_has_input_and_raw_response():
    model=Model()
    result=extract_fields(DOC,DEFAULT_SCHEMA,'test',client=model,prompt='My task',previous_results={'fields':{}})
    trace=result['trace']
    assert trace['request']['body']==model.requests[0]
    user=json.loads(trace['request']['body']['messages'][1]['content'])
    assert user['task_instruction']=='My task' and user['previous_results']=={'fields':{}}
    assert trace['raw']==result['raw']

@pytest.mark.parametrize('finish',['stop','length'])
def test_openai_actual_wire_request_and_failure_response(finish):
    seen=[]
    def handler(r):
        seen.append(json.loads(r.content))
        return httpx.Response(200,json={'model':'test','choices':[{'finish_reason':finish,'message':{'content':'{"proposals":[]}'}}]})
    cli=OpenAICompatible(CONFIG,'secret-key',transport=httpx.MockTransport(handler))
    if finish=='stop':trace=extract_fields(DOC,DEFAULT_SCHEMA,'test',client=cli)['trace']
    else:
        with pytest.raises(HTTPException) as error:extract_fields(DOC,DEFAULT_SCHEMA,'test',client=cli)
        trace=error.value.llm_output
    assert trace['request']['body']==seen[0]
    assert 'Required output JSON contract:' in trace['request']['body']['messages'][0]['content']
    assert trace['response']['choices'][0]['finish_reason']==finish
    assert 'secret-key' not in json.dumps(trace)

def test_test_report_retains_completed_call_before_later_failure(client,type_id,monkeypatch):
    class FailSecond(Model):
        def request(self,*args):
            result=super().request(*args)
            if len(self.requests)==2:result['message']['content']='invalid JSON'
            return result
    model=FailSecond()
    monkeypatch.setattr('backend.app.pipelines.client_for',lambda *args:model)
    uploaded=client.post('/api/uploads',files={'file':('test.html',b'<h2>Start</h2><p>Delivery fails</p><h2>End</h2>','text/html')},data={'type_id':type_id}).json()
    pipeline=client.post('/api/pipelines',json={'key':'trace','name':'Trace','type_id':type_id,'steps':[RULE,{'kind':'llm','model':'test','prompt':'My task','include_previous':True},{'kind':'llm','model':'test'}]}).json()
    report=client.post(f"/api/pipelines/{pipeline['id']}/tests",json={'snapshot_ids':[uploaded['snapshot_id']]}).json()
    row=report['results'][0]
    assert report['ok'] is False and len(row['completed_llm_runs'])==1
    first=client.get('/api/llm/runs/'+row['completed_llm_runs'][0]['run_id']+'/raw').json()
    failed=client.get('/api/llm/runs/'+row['error_run_id']+'/raw').json()
    assert first['metadata']['step']==2 and failed['metadata']['step']==3
    assert failed['raw']=='invalid JSON' and first['request']['body']['messages']
    assert client.get('/api/llm/default-prompt').json()['prompt']==SYSTEM

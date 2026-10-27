import pytest
from fastapi import HTTPException
from backend.app.pipeline_engine import run_pipeline
from backend.app.html_parser import parse_html
from backend.app.registry import DEFAULT_SCHEMA
from tests.conftest import upload

DOC='<h2>Проблематика</h2><p>Потери</p><h2>Задачи проекта</h2><p>Доставка</p>'


def test_between_rule_and_evidence():
    doc=parse_html(DOC.encode(),"snap")
    result=run_pipeline(doc,DEFAULT_SCHEMA,[{"kind":"between","field":"problem","start":"Проблематика","end":"Задачи проекта"}])
    assert result["proposals"]["problem"]["value"]=="Потери"
    assert result["proposals"]["problem"]["evidence"][0]["quote"]=="Потери"


def test_rule_conflicts_do_not_silently_overwrite():
    doc=parse_html(DOC.encode(),"s")
    rule={"kind":"between","field":"problem","start":"Проблематика","end":"Задачи проекта"}
    result=run_pipeline(doc,DEFAULT_SCHEMA,[rule,rule])
    assert "problem" not in result["proposals"] and result["warnings"]


def test_pipeline_version_requires_test_before_publish(client,type_id):
    candidate=upload(client,type_id,DOC,mode="sections").json()
    body={"key":"adr","name":"ADR","type_id":type_id,"steps":[{"kind":"between","field":"problem","start":"Проблематика","end":"Задачи проекта"}]}
    draft=client.post("/api/pipelines",json=body)
    assert draft.status_code==201,draft.text
    id=draft.json()["id"]
    assert client.post(f"/api/pipelines/{id}/publish").status_code==409
    run=client.post(f"/api/pipelines/{id}/tests",json={"snapshot_ids":[candidate["snapshot_id"]]})
    assert run.status_code==200,run.text
    assert run.json()["results"][0]["result"]["proposals"]["problem"]["value"]=="Потери"
    assert client.post(f"/api/pipelines/{id}/publish").json()["status"]=="published"
    second=client.post("/api/pipelines",json={**body,"steps":[{"kind":"sections"}]}).json()
    assert second["version"]==2
    proposed=client.post(f"/api/pipelines/{id}/propose",json={"snapshot_id":candidate["snapshot_id"]}).json()
    assert proposed["config"]["pipeline_id"]==id
    assert client.get("/api/artifacts").json()==[]


def test_html_import_uses_published_pipeline_and_keeps_provenance(client,type_id):
    source=upload(client,type_id,DOC,mode='sections').json()
    draft=client.post('/api/pipelines',json={"key":"between","name":"Between","type_id":type_id,"steps":[{"kind":"between","field":"problem","start":"Проблематика","end":"Задачи проекта"}]}).json()
    client.post(f"/api/pipelines/{draft['id']}/tests",json={"snapshot_ids":[source['snapshot_id']]})
    client.post(f"/api/pipelines/{draft['id']}/publish")
    candidate=upload(client,type_id,DOC,pipeline_id=draft['id']).json()
    assert candidate['proposals']['problem']['value']=='Потери'
    artifact=client.post(f"/api/candidates/{candidate['id']}/review",json={"expected_revision":0,"fields":{"title":"Manual","problem":"Потери"},"status":"published"}).json()
    assert artifact['provenance']['problem']['pipeline_id']==draft['id']
    assert artifact['provenance']['problem']['step']==1


def test_broken_baseline_does_not_block_corrected_version(client,type_id):
    two=upload(client,type_id,'<table><tr><td>x</td><td>y</td></tr></table><table><tr><td>Название</td><td>Title</td></tr></table>',table_index=1).json()
    original={"key":"fixable","name":"Fixable","type_id":type_id,"steps":[{"kind":"table","table_index":1}]}
    old=client.post('/api/pipelines',json=original).json()
    client.post(f"/api/pipelines/{old['id']}/tests",json={"snapshot_ids":[two['snapshot_id']]})
    assert client.post(f"/api/pipelines/{old['id']}/publish").status_code==200
    source=upload(client,type_id,DOC,mode='sections').json()
    new=client.post('/api/pipelines',json={**original,'steps':[{'kind':'sections'}]}).json()
    report=client.post(f"/api/pipelines/{new['id']}/tests",json={"snapshot_ids":[source['snapshot_id']]}).json()
    assert report['ok'] is True
    assert report['results'][0]['baseline_error']
    assert client.post(f"/api/pipelines/{new['id']}/publish").status_code==200


def test_confluence_job_uses_selected_pipeline(tmp_path):
    from tests.test_confluence_jobs import setup_client,config,handler,enqueue
    app,client,_=setup_client(tmp_path,handler)
    with client:
        connection_id,type_id=config(client)
        sample=upload(client,type_id,'<table><tr><td>Название</td><td>Title</td></tr></table>').json()
        draft=client.post('/api/pipelines',json={"key":"wiki","name":"Wiki","type_id":type_id,"steps":[{"kind":"table"}]}).json()
        client.post(f"/api/pipelines/{draft['id']}/tests",json={"snapshot_ids":[sample['snapshot_id']]})
        client.post(f"/api/pipelines/{draft['id']}/publish")
        job=enqueue(client,connection_id,type_id,pipeline_id=draft['id']).json()
        app.state.confluence_worker.run_once()
        completed=client.get('/api/confluence/jobs/'+job['id']).json()
        assert completed['status']=='succeeded'
        candidate=client.get('/api/candidates/'+completed['items'][0]['candidate_id']).json()
        assert candidate['config']['pipeline_id']==draft['id']
        assert candidate['proposals']['title']['value']=='Same content'

import time
from hashlib import sha256
import httpx
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.confluence.client import ConfluenceClient
from backend.app.db import jobs, snapshots
from sqlalchemy import select


class TestSecrets:
    __test__ = False
    def __init__(self): self.values = {}
    def set(self, key, value): self.values[key] = value
    def get(self, key): return self.values.get(key)
    def delete(self, key): self.values.pop(key, None)


def setup_client(tmp_path, handler):
    secrets=TestSecrets()
    app=create_app(tmp_path, secret_store=secrets, confluence_client_factory=lambda url, token: ConfluenceClient(url,token,transport=httpx.MockTransport(handler),sleep=lambda _:None), start_worker=False)
    client=TestClient(app,base_url="http://127.0.0.1")
    client.headers["X-Local-Token"]=client.get("/api/session").json()["token"]
    return app,client,secrets


def config(client):
    r=client.post("/api/confluence/connections",json={"name":"Wiki", "base_url":"https://wiki.example", "token":"private-test-token"})
    assert r.status_code == 201, r.text
    assert "private-test-token" not in r.text
    return r.json()["id"],client.get("/api/types").json()[0]["id"]


def handler(req):
    if req.url.path.endswith("/search"):
        return httpx.Response(200,json={"results":[{"id":"1","title":"One","type":"page"},{"id":"2","title":"Two","type":"page"}],"_links":{}})
    page_id=req.url.path.rsplit("/",1)[-1]
    return httpx.Response(200,json={"id":page_id,"type":"page","title":"Page "+page_id,"version":{"number":1},"body":{"storage":{"value":"<table><tr><td>Название</td><td>Same content</td></tr></table>"}}})


def enqueue(client,connection_id,type_id, **options):
    preview=client.post("/api/confluence/previews",json={"connection_id":connection_id,"cql":"type=page"}).json()
    return client.post("/api/confluence/jobs",json={"preview_id":preview["id"],"page_ids":["1","2"],"type_id":type_id,**options})


def test_preview_import_identity_review_and_retry(tmp_path):
    app,client,secrets=setup_client(tmp_path,handler)
    with client:
        connection_id,type_id=config(client)
        job=enqueue(client,connection_id,type_id).json()
        assert client.get("/api/artifacts").json()==[]
        app.state.confluence_worker.run_once()
        complete=client.get("/api/confluence/jobs/"+job["id"]).json()
        assert complete["status"]=="succeeded"
        assert len({i["candidate_id"] for i in complete["items"]})==2
        assert client.get("/api/artifacts").json()==[]
        for item in complete["items"]:
            c=client.get("/api/candidates/"+item["candidate_id"]).json()
            snap=client.get("/api/snapshots/"+c["snapshot_id"]).json()
            assert snap["source_metadata"]["page_version"]==1
            assert snap["source_metadata"]["page_id"]==item["page_id"]
            assert client.post("/api/candidates/"+c["id"]+"/review",json={"expected_revision":0,"fields":{"title":"Same content"},"status":"published"}).status_code==200
        again=enqueue(client,connection_id,type_id).json()
        app.state.confluence_worker.run_once()
        assert client.get("/api/confluence/jobs/"+again["id"]).json()["status"]=="succeeded"
        assert len(client.get("/api/candidates").json())==2
        assert len(client.get("/api/artifacts").json())==2
        assert "private-test-token" not in client.get("/api/export").text
        assert "private-test-token" not in (tmp_path/"registry.db").read_bytes().decode(errors="ignore")


def test_partial_retry_cancel_and_selection_validation(tmp_path):
    blocked={"value":True}
    def partly(req):
        if req.url.path.endswith("/2") and blocked["value"]: return httpx.Response(403,text="private-test-token")
        return handler(req)
    app,client,_=setup_client(tmp_path,partly)
    with client:
        connection_id,type_id=config(client)
        job=enqueue(client,connection_id,type_id).json()
        app.state.confluence_worker.run_once()
        result=client.get("/api/confluence/jobs/"+job["id"]).json()
        assert result["status"]=="partial"
        assert result["items"][1]["error"]["code"]=="forbidden"
        assert "private-test-token" not in str(result)
        blocked["value"]=False
        retry=client.post("/api/confluence/jobs/"+job["id"]+"/retry").json()
        assert [i["page_id"] for i in retry["items"]]==["2"]
        app.state.confluence_worker.run_once()
        assert len(client.get("/api/candidates").json())==2
        cancelled=enqueue(client,connection_id,type_id).json()
        client.post("/api/confluence/jobs/"+cancelled["id"]+"/cancel")
        app.state.confluence_worker.run_once()
        assert client.get("/api/confluence/jobs/"+cancelled["id"]).json()["status"]=="cancelled"
        invalid=client.post("/api/confluence/jobs",json={"preview_id":job["preview_id"],"page_ids":["999"],"type_id":type_id})
        assert invalid.status_code==422


def test_expired_lease_recovery_preserves_committed_candidate(tmp_path):
    app,client,_=setup_client(tmp_path,handler)
    with client:
        connection_id,type_id=config(client)
        job=enqueue(client,connection_id,type_id).json()
        app.state.confluence_worker.run_once()
        complete=client.get("/api/confluence/jobs/"+job["id"]).json()
        original=[i["candidate_id"] for i in complete["items"]]
        complete["status"]="running"
        complete["items"][1]["status"]="running"
        with app.state.db.transaction() as c:
            c.execute(jobs.update().where(jobs.c.id==job["id"]).values(data=complete,owner="dead-worker",lease_until=time.time()-1))
        app.state.confluence_worker.run_once()
        recovered=client.get("/api/confluence/jobs/"+job["id"]).json()
        assert recovered["status"]=="succeeded"
        assert [i["candidate_id"] for i in recovered["items"]]==original
        assert recovered["items"][0]["attempts"]==1
        assert recovered["items"][1]["attempts"]==2
        assert len(client.get("/api/candidates").json())==2


def test_page_rename_new_version_preserves_binding_and_manual_values(tmp_path):
    revision={"number":1}
    def versioned(req):
        result=handler(req)
        if not req.url.path.endswith("/search"):
            data=result.json()
            data["version"]["number"]=revision["number"]
            data["title"]="Новое название" if revision["number"]==2 else "Старое название"
            return httpx.Response(200,json=data)
        return result
    app,client,_=setup_client(tmp_path,versioned)
    with client:
        connection_id,type_id=config(client)
        first=enqueue(client,connection_id,type_id).json()
        app.state.confluence_worker.run_once()
        candidate=client.get("/api/candidates/"+client.get("/api/confluence/jobs/"+first["id"]).json()["items"][0]["candidate_id"]).json()
        artifact=client.post("/api/candidates/"+candidate["id"]+"/review",json={"expected_revision":0,"fields":{"title":"Ручное название"},"status":"published"}).json()
        revision["number"]=2
        second=enqueue(client,connection_id,type_id).json()
        app.state.confluence_worker.run_once()
        new=client.get("/api/candidates/"+client.get("/api/confluence/jobs/"+second["id"]).json()["items"][0]["candidate_id"]).json()
        assert new["resource_id"]==candidate["resource_id"]
        assert new["snapshot_id"]!=candidate["snapshot_id"]
        assert new["target_id"]==artifact["id"]
        assert new["source_name"]=="Новое название"
        assert new["current_fields"]=={"title":"Ручное название"}
        assert client.get("/api/artifacts/"+artifact["id"]).json()["revision"]==1


def test_validation_and_token_rotation_never_echo_secret(tmp_path):
    app,client,secrets=setup_client(tmp_path,handler)
    with client:
        connection_id,_=config(client)
        invalid=client.put("/api/confluence/connections/"+connection_id+"/token",json={"token":"private-test-token\n"})
        assert invalid.status_code==422
        assert "private-test-token" not in invalid.text
        assert client.put("/api/confluence/connections/"+connection_id+"/token",json={"token":"replacement"}).status_code==200
        assert secrets.get(connection_id)=="replacement"
        assert client.delete("/api/confluence/connections/"+connection_id+"/token").status_code==200
        assert client.get("/api/confluence/connections").json()[0]["has_token"] is False


def test_cancel_during_download_does_not_create_candidate(tmp_path):
    context={}
    def cancelling(req):
        if not req.url.path.endswith("/search"):
            context["client"].post("/api/confluence/jobs/"+context["job_id"]+"/cancel")
        return handler(req)
    app,client,_=setup_client(tmp_path,cancelling)
    with client:
        connection_id,type_id=config(client)
        job=enqueue(client,connection_id,type_id).json()
        context.update(client=client,job_id=job["id"])
        app.state.confluence_worker.run_once()
        assert client.get("/api/confluence/jobs/"+job["id"]).json()["status"]=="cancelled"
        assert client.get("/api/candidates").json()==[]


def test_retry_repairs_interrupted_blob_before_committing_snapshot(tmp_path):
    app,client,_=setup_client(tmp_path,handler)
    content=b"<table><tr><td>\xd0\x9d\xd0\xb0\xd0\xb7\xd0\xb2\xd0\xb0\xd0\xbd\xd0\xb8\xd0\xb5</td><td>Same content</td></tr></table>"
    digest=sha256(content).hexdigest()
    (tmp_path/"blobs"/digest).write_bytes(content[:10])
    with client:
        connection_id,type_id=config(client)
        job=enqueue(client,connection_id,type_id).json()
        app.state.confluence_worker.run_once()
        result=client.get("/api/confluence/jobs/"+job["id"]).json()
        assert result["status"]=="succeeded"
        candidate=client.get("/api/candidates/"+result["items"][0]["candidate_id"]).json()
        assert client.get("/api/snapshots/"+candidate["snapshot_id"]+"/download").content==content


def test_new_schema_version_does_not_duplicate_existing_page_artifact(tmp_path):
    app,client,_=setup_client(tmp_path,handler)
    with client:
        connection_id,type_id=config(client)
        first=enqueue(client,connection_id,type_id).json()
        app.state.confluence_worker.run_once()
        candidate_id=client.get("/api/confluence/jobs/"+first["id"]).json()["items"][0]["candidate_id"]
        assert client.post("/api/candidates/"+candidate_id+"/review",json={"expected_revision":0,"fields":{"title":"A"},"status":"published"}).status_code==200
        old=client.get("/api/types").json()[0]
        new=client.post("/api/types",json={"type_key":old["type_key"],"name":old["name"],"schema":old["schema"]}).json()
        second=enqueue(client,connection_id,new["id"]).json()
        app.state.confluence_worker.run_once()
        result=client.get("/api/confluence/jobs/"+second["id"]).json()
        assert result["items"][0]["status"]=="failed"
        assert "схем" in result["items"][0]["error"]["message"]
        assert len(client.get("/api/artifacts").json())==1

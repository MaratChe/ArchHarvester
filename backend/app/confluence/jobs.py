"""Durable per-page jobs. Network requests never hold SQLite write transactions."""
from copy import deepcopy
import threading
import time
from uuid import UUID, uuid5
from fastapi import HTTPException
from sqlalchemy import select
from ..db import connections, previews, jobs, resources, types, find
from ..registry import require, uid, now
from ..imports import import_html
from .client import ConfluenceError
from ..html_parser import parse_html
from ..pptx_parser import parse_pptx
from .attachments import list_presentations, current_presentation, fetch_attachment
from ..pipelines import load_pipeline, evaluate

LEASE_SECONDS = 60


def create_job(connection, preview_id, page_ids, type_id, mode, table_index, retry_of=None, pipeline_id=None, source_mode="pages"):
    preview = require(connection, previews, preview_id)
    require(connection, types, type_id)
    load_pipeline(connection, pipeline_id, type_id)
    available = {p["id"]: p for p in preview["pages"]}
    if not page_ids or any(id not in available for id in page_ids):
        raise HTTPException(422, "Выберите страницы из сохранённой CQL-выборки")
    items = [{"page_id": id, "title": available[id]["title"], "status": "queued", "attempts": 0,
              "candidate_id": None, "error": None} for id in dict.fromkeys(page_ids)]
    data = {"id": uid(), "preview_id": preview_id, "connection_id": preview["connection_id"], "cql": preview["cql"],
            "type_id": type_id, "mode": mode, "table_index": table_index, "items": items, "pipeline_id": pipeline_id,
            "source_mode": source_mode, "status": "queued", "cancel_requested": False, "created_at": now(), "retry_of": retry_of}
    connection.execute(jobs.insert().values(id=data["id"], data=data, owner=None, lease_until=0))
    return data


class ImportWorker:
    def __init__(self, db, secrets, client_factory):
        self.db, self.secrets, self.client_factory = db, secrets, client_factory
        self.owner = uid()
        self.stopping = threading.Event()
        self.wake = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._loop, name="confluence-import", daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        self.wake.set()
        if self.thread: self.thread.join(timeout=3)

    def _loop(self):
        while not self.stopping.is_set():
            try:
                worked = self.run_once()
            except Exception:
                # Never log remote exception text: it may contain headers or sensitive source content.
                worked = False
            if not worked:
                self.wake.wait(1)
                self.wake.clear()

    def _claim(self):
        with self.db.transaction() as c:
            for row in c.execute(select(jobs).order_by(jobs.c.id)).mappings():
                job = deepcopy(row["data"])
                if job["status"] not in {"queued", "running"}: continue
                if row["lease_until"] > time.time(): continue
                if job["cancel_requested"]:
                    for item in job["items"]:
                        if item["status"] in {"queued", "running"}: item["status"] = "cancelled"
                    job["status"] = "cancelled"
                    c.execute(jobs.update().where(jobs.c.id == job["id"]).values(data=job, owner=None, lease_until=0))
                    continue
                for item in job["items"]:
                    if item["status"] == "running": item["status"] = "queued"
                job["status"] = "running"
                c.execute(jobs.update().where(jobs.c.id == job["id"]).values(data=job, owner=self.owner, lease_until=time.time()+LEASE_SECONDS))
                return job["id"]

    def _heartbeat(self, id, finished):
        while not finished.wait(5):
            try:
                with self.db.transaction() as c:
                    c.execute(jobs.update().where(jobs.c.id == id, jobs.c.owner == self.owner).values(lease_until=time.time()+LEASE_SECONDS))
            except Exception:
                # Commit path verifies ownership before writing any imported data.
                return

    def run_once(self):
        id = self._claim()
        if not id: return False
        finished = threading.Event()
        heartbeat = threading.Thread(target=self._heartbeat, args=(id, finished), daemon=True)
        heartbeat.start()
        try:
            self._process(id)
        finally:
            finished.set()
            heartbeat.join(timeout=2)
            with self.db.transaction() as c:
                row = find(c, jobs, id)
                if row and row["owner"] == self.owner:
                    job = deepcopy(row["data"])
                    if job["status"] == "running":
                        job["status"] = "queued"
                        for item in job["items"]:
                            if item["status"] == "running": item["status"] = "queued"
                    c.execute(jobs.update().where(jobs.c.id == id).values(data=job, owner=None, lease_until=0))
        return True

    def _process(self, id):
        while not self.stopping.is_set():
            with self.db.transaction() as c:
                row = find(c, jobs, id)
                if row["owner"] != self.owner: return
                job = deepcopy(row["data"])
                if job["cancel_requested"]:
                    for item in job["items"]:
                        if item["status"] in {"queued", "running"}: item["status"] = "cancelled"
                index = next((i for i, item in enumerate(job["items"]) if item["status"] == "queued"), None)
                if index is None:
                    states = {item["status"] for item in job["items"]}
                    job["status"] = "cancelled" if "cancelled" in states else "partial" if "failed" in states and "succeeded" in states else "failed" if "failed" in states else "succeeded"
                    job["finished_at"] = now()
                    c.execute(jobs.update().where(jobs.c.id == id).values(data=job))
                    return
                job["items"][index].update(status="running", attempts=job["items"][index]["attempts"]+1)
                c.execute(jobs.update().where(jobs.c.id == id).values(data=job))
                config = require(c, connections, job["connection_id"])
                page_id = job["items"][index]["page_id"]
            attachment_id = job['items'][index].get('attachment_id')
            scanning = job.get('source_mode') == 'attachments' and not attachment_id
            error, page, discovered = None, None, None
            try:
                token = self.secrets.get(config["id"])
                if not token: raise ConfluenceError("missing_token", "Введите PAT для этого подключения.")
                with self.client_factory(config["base_url"], token) as client:
                    if scanning:
                        discovered = list_presentations(client, page_id)
                    elif attachment_id:
                        metadata = current_presentation(client, page_id, attachment_id)
                        page = {**metadata, 'content': fetch_attachment(client, metadata)}
                    else:
                        page = client.fetch_page(page_id)
                # Parse before taking a write transaction; the resulting document is reused on persistence.
                if not scanning:
                    document = parse_pptx(page['content'], 'pending') if attachment_id else parse_html(page['content'], 'pending')
                    if not attachment_id: document['format'] = 'confluence_html'
                    with self.db.engine.connect() as read:
                        pipeline = load_pipeline(read, job.get('pipeline_id'), job['type_id'])
                        schema = require(read, types, job['type_id'])['schema']
                    prepared_result, pipeline_config = evaluate(document, schema, pipeline, db=self.db)
            except ConfluenceError as e:
                error = {"code": e.code, "message": str(e)}
            except HTTPException as e:
                from ..llm_history import record_failure
                with self.db.transaction() as c:record_failure(c,e)
                error = {"code": "parse_error", "message": str(e.detail)}
            except Exception:
                error = {"code": "processing_error", "message": "Не удалось обработать страницу или прочитать PAT. Проверьте подключение и повторите элемент."}
            with self.db.transaction() as c:
                row = find(c, jobs, id)
                if row["owner"] != self.owner: return
                latest = deepcopy(row["data"])
                item = latest["items"][index]
                if latest["cancel_requested"]:
                    item["status"] = "cancelled"
                elif error:
                    item.update(status="failed", error=error)
                elif scanning:
                    known = {i.get('attachment_id') for i in latest['items']}
                    additions = [a for a in discovered if a['attachment_id'] not in known]
                    if len(latest['items']) + len(additions) > 2500:
                        item.update(status='failed', error={'code': 'too_large', 'message': 'Лимит задания: 2500 страниц и вложений. Сузьте CQL.'})
                    else:
                        item.update(status='succeeded', scan=True, attachment_count=len(discovered))
                        latest['items'].extend({'page_id': page_id, 'parent_title': item['title'], 'attachment_id': a['attachment_id'],
                                              'title': a['title'], 'status': 'queued', 'attempts': 0, 'candidate_id': None, 'error': None} for a in additions)
                else:
                    try:
                        # A savepoint prevents a failed import from leaving partial resources/snapshots.
                        with c.begin_nested():
                            resource_id = str(uuid5(UUID(config["id"]), "attachment:" + attachment_id if attachment_id else page_id))
                            resource = {"id": resource_id, "kind": "confluence_page", "name": page["title"],
                                        "connection_id": config["id"], "page_id": page_id, "url": page["url"], "page_version": page["version"]}
                            if attachment_id:
                                previous = find(c, resources, resource_id)
                                resource = {'id': resource_id, 'kind': 'confluence_attachment', 'name': page['title'],
                                            **metadata, 'connection_id': config['id'],
                                            'role': previous['data'].get('role', 'primary') if previous else 'primary'}
                            if find(c, resources, resource_id):
                                c.execute(resources.update().where(resources.c.id == resource_id).values(data=resource))
                            else: c.execute(resources.insert().values(id=resource_id, data=resource))
                            def parsed(_content, snapshot_id):
                                return {**document, "snapshot_id": snapshot_id}
                            candidate = import_html(self.db, c, page["content"], page["title"] if attachment_id else f"confluence-{page_id}-v{page['version']}.html",
                                                    job["type_id"], job["mode"], job["table_index"], resource_id,
                                                    source_kind="pptx" if attachment_id else "html",
                                                    source_metadata={**metadata, "kind":"confluence_attachment", "connection_id":config["id"]} if attachment_id else {"kind":"confluence_page", "connection_id":config["id"], "page_id":page_id,
                                                                     "page_version":page["version"], "title":page["title"], "url":page["url"], "format":"html"}, parser=parsed,
                                                    prepared_result=prepared_result, pipeline_config=pipeline_config)
                            item.update(status="succeeded", candidate_id=candidate["id"], error=None, title=page["title"], page_version=page["version"])
                    except HTTPException as e:
                        item.update(status="failed", error={"code":"validation_error", "message":str(e.detail)})
                    except Exception:
                        item.update(status="failed", error={"code":"processing_error", "message":"Не удалось сохранить предложение страницы. Повторите элемент."})
                c.execute(jobs.update().where(jobs.c.id == id).values(data=latest))

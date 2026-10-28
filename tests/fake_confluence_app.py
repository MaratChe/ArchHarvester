"""Browser QA harness. No live Confluence calls or persistent credentials.

Run explicitly: uvicorn tests.fake_confluence_app:create --factory --port 8767
"""
from pathlib import Path
import httpx
from backend.app.main import create_app
from backend.app.confluence.client import ConfluenceClient
from tests.test_confluence_jobs import TestSecrets

QA_DIR = Path(__file__).resolve().parents[1] / "output" / "confluence-browser"


def fake_response(request):
    if request.headers.get("authorization") != "Bearer qa-only-token":
        return httpx.Response(401)
    if request.url.path.endswith("/search"):
        if "start" not in request.url.params:
            return httpx.Response(200,json={"results":[{"id":"101","type":"page","title":"Гарантированная доставка"},{"id":"102","type":"page","title":"Резервирование канала"}],"_links":{"next":"/confluence/rest/api/content/search?start=2"}})
        return httpx.Response(200,json={"results":[{"id":"103","type":"page","title":"Закрытая страница"}],"_links":{}})
    id=request.url.path.rsplit("/",1)[-1]
    if id=="103" and not (QA_DIR/"allow-103").exists(): return httpx.Response(403)
    title={"101":"Гарантированная доставка","102":"Резервирование канала","103":"Закрытая страница"}.get(id,"Страница")
    storage=f'<ac:structured-macro ac:name="details"><ac:rich-text-body><table><tr><td>Название</td><td>{title}</td></tr><tr><td>Проблематика</td><td>Потери&nbsp;сообщений при сбоях.</td></tr><tr><td>Владелец</td><td>Команда интеграции</td></tr></table></ac:rich-text-body></ac:structured-macro>'
    return httpx.Response(200,json={"id":id,"type":"page","title":title,"version":{"number":3},"body":{"view":{"value":storage}}})


def create():
    return create_app(QA_DIR,secret_store=TestSecrets(),confluence_client_factory=lambda url,token:ConfluenceClient(url,token,transport=httpx.MockTransport(fake_response),sleep=lambda _:None))

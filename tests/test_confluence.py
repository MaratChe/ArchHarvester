import httpx
import pytest
from backend.app.confluence.client import ConfluenceClient, ConfluenceError
from backend.app.confluence.storage import parse_storage


def test_cql_pagination_dedup_and_bearer():
    requests = []
    def handler(req):
        requests.append(req)
        assert req.headers["authorization"] == "Bearer test-secret"
        assert "expand" not in req.url.params
        if "start" not in req.url.params:
            assert req.url.params["cql"] == 'space = ARCH AND type = page'
            return httpx.Response(200, json={"results": [{"id":"1","type":"page","title":"Первое"}], "_links":{"next":"/confluence/rest/api/content/search?start=1&cql=space%20%3D%20ARCH%20AND%20type%20%3D%20page"}})
        return httpx.Response(200, json={"results":[{"id":"1","type":"page","title":"Первое"},{"id":"2","type":"page","title":"Второе"},{"id":"3","type":"attachment","title":"Файл"}],"_links":{}})
    with ConfluenceClient("https://wiki.example/confluence", "test-secret", transport=httpx.MockTransport(handler)) as client:
        result = client.discover('space = ARCH AND type = page', 100)
    assert [p["id"] for p in result["pages"]] == ["1", "2"]
    assert len(requests) == 2
    assert not result["truncated"]


@pytest.mark.parametrize("status,code", [(401,"unauthorized"),(403,"forbidden"),(404,"not_found"),(429,"rate_limited"),(500,"server_error"),(302,"redirect")])
def test_safe_remote_errors(status, code):
    seen=[]
    def handler(req):
        seen.append(req)
        return httpx.Response(status, text="secret response test-secret", headers={"Location":"https://evil.example", "Retry-After":"0"})
    with ConfluenceClient("https://wiki.example", "test-secret", transport=httpx.MockTransport(handler), sleep=lambda _:None) as client:
        with pytest.raises(ConfluenceError) as err:
            client.fetch_page("1")
    assert err.value.code == code
    assert "secret" not in str(err.value)
    assert all(r.url.host == "wiki.example" for r in seen)
    assert len(seen) == (3 if status in (429,500) else 1)


def test_untrusted_next_url_and_timeout():
    with ConfluenceClient("https://wiki.example", "x", transport=httpx.MockTransport(lambda r: httpx.Response(200,json={"results":[],"_links":{"next":"https://evil.example/rest/api/content/search?start=1"}}))) as client:
        with pytest.raises(ConfluenceError, match="пагинации"):
            client.discover("type=page", 10)
    def timeout(req):
        raise httpx.ReadTimeout("test-secret", request=req)
    with ConfluenceClient("https://wiki.example", "test-secret", transport=httpx.MockTransport(timeout), sleep=lambda _:None) as client:
        with pytest.raises(ConfluenceError) as err:
            client.fetch_page("1")
    assert err.value.code == "timeout"
    assert "test-secret" not in str(err.value)


def test_fetch_page_validates_identity_version_and_storage():
    def handler(req):
        assert req.url.path == "/rest/api/content/42"
        assert req.url.params["expand"] == "body.storage,version"
        return httpx.Response(200,json={"id":"42","type":"page","title":"Решение", "version":{"number":7}, "body":{"storage":{"value":"<p>Текст</p>","representation":"storage"}}})
    with ConfluenceClient("https://wiki.example", "x", transport=httpx.MockTransport(handler)) as client:
        page=client.fetch_page("42")
    assert page["version"] == 7
    assert page["content"] == b"<p>\xd0\xa2\xd0\xb5\xd0\xba\xd1\x81\xd1\x82</p>"


def test_storage_macros_do_not_become_field_values():
    content = '<ac:structured-macro ac:name="details"><ac:parameter ac:name="id">not-a-field</ac:parameter><ac:rich-text-body><table><tr><td>Название</td><td>ADR</td></tr></table></ac:rich-text-body></ac:structured-macro><ac:structured-macro ac:name="include"><ac:parameter ac:name="">secret-page</ac:parameter></ac:structured-macro>'
    document = parse_storage(content.encode(), "snapshot-1")
    assert document["tables"][0]["rows"][0][1]["text"] == "ADR"
    assert "secret-page" not in str(document["blocks"])
    assert "not-a-field" not in str(document["blocks"])
    assert any("include" in w for w in document["warnings"])
    assert document["blocks"][0]["html_path"].startswith("/storage/")


def test_storage_xhtml_entities_and_layout():
    data = '<ac:layout><ac:layout-section ac:type="single"><ac:layout-cell><h2>Описание</h2><p>Система&nbsp;А &mdash; обмен &amp; доставка.</p></ac:layout-cell></ac:layout-section></ac:layout>'
    document = parse_storage(data.encode(), "s")
    assert any(b["text"] == "Система А — обмен & доставка." for b in document["blocks"])


def test_truncated_preview_and_invalid_page_payload():
    with ConfluenceClient("https://wiki.example", "x", transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"results":[{"id":"1","type":"page","title":"A"},{"id":"2","type":"page","title":"B"}],"_links":{}}))) as client:
        result=client.discover("type=page",1)
        assert result["truncated"] and len(result["pages"])==1
    with ConfluenceClient("https://wiki.example", "x", transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"id":"99","type":"page"}))) as client:
        with pytest.raises(ConfluenceError) as err: client.fetch_page("1")
        assert err.value.code=="invalid_response"

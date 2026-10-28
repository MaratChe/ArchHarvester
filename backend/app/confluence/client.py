"""Read-only REST adapter for Confluence Data Center 7.13 (PAT)."""
import json
import re
import time
from html import escape
from urllib.parse import parse_qsl, urlencode, urlsplit
import httpx
from ..tls import client_ssl_context


class ConfluenceError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def normalize_url(value):
    parsed = urlsplit(value.strip())
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or any(ch.isspace() for ch in value)
            or "\\" in value or "%" in parsed.path or any(p in {".", ".."} for p in parsed.path.split("/"))):
        raise ValueError("Нужен HTTPS-адрес Confluence без логина, параметров и фрагмента; например https://wiki.company.ru/confluence")
    try:
        parsed.port
    except ValueError:
        raise ValueError("Некорректный порт Confluence")
    return parsed._replace(netloc=parsed.netloc.lower(), path=parsed.path.rstrip("/")).geturl()


class ConfluenceClient:
    def __init__(self, base_url, token, *, transport=None, sleep=time.sleep):
        self.base_url = normalize_url(base_url)
        self.sleep = sleep
        self.client = httpx.Client(headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                                   timeout=httpx.Timeout(20, connect=10), follow_redirects=False, transport=transport,
                                   verify=client_ssl_context())

    def __enter__(self): return self
    def __exit__(self, *args): self.client.close()

    def _json(self, url, params=None):
        for attempt in range(3):
            try:
                with self.client.stream("GET", url, params=params) as response:
                    status = response.status_code
                    if status == 429 or status >= 500:
                        if attempt < 2:
                            delay = min(5, max(0, float(response.headers.get("Retry-After", 2 ** attempt)))) if response.headers.get("Retry-After", "").isdigit() else 2 ** attempt
                            self.sleep(delay)
                            continue
                    messages = {401:("unauthorized", "Токен не принят. Проверьте PAT и срок его действия."),
                                403:("forbidden", "Нет доступа к странице или поиску Confluence."),
                                404:("not_found", "Страница или REST endpoint не найдены."),
                                429:("rate_limited", "Confluence ограничил частоту запросов. Повторите позже.")}
                    if status in messages: raise ConfluenceError(*messages[status])
                    if 300 <= status < 400: raise ConfluenceError("redirect", "Confluence перенаправляет запрос. Укажите конечный HTTPS-адрес без SSO-переадресации.")
                    if status >= 500: raise ConfluenceError("server_error", "Временная ошибка сервера Confluence.")
                    if status != 200: raise ConfluenceError("request_error", f"Confluence отклонил запрос (HTTP {status}). Проверьте CQL и адрес.")
                    chunks, size, started = [], 0, time.monotonic()
                    for part in response.iter_bytes():
                        size += len(part)
                        if size > 8 * 1024 * 1024: raise ConfluenceError("too_large", "Ответ Confluence превышает 8 MiB.")
                        if time.monotonic() - started > 45: raise ConfluenceError("timeout", "Превышено время загрузки ответа Confluence.")
                        chunks.append(part)
                    try:
                        data = json.loads(b"".join(chunks))
                        if not isinstance(data, dict): raise ValueError()
                        return data
                    except (ValueError, UnicodeDecodeError):
                        raise ConfluenceError("invalid_response", "Confluence вернул не JSON. Проверьте адрес REST API и настройки SSO.") from None
            except httpx.TimeoutException:
                if attempt < 2:
                    self.sleep(2 ** attempt)
                    continue
                raise ConfluenceError("timeout", "Превышено время ожидания Confluence.") from None
            except httpx.HTTPError:
                if attempt < 2:
                    self.sleep(2 ** attempt)
                    continue
                raise ConfluenceError("connection_error", "Не удалось соединиться с Confluence. Проверьте сеть, VPN и доверие сертификату.") from None

    def page_url(self, page_id):
        return self.base_url + "/pages/viewpage.action?" + urlencode({"pageId": page_id})

    def discover(self, cql, max_pages=500):
        endpoint = self.base_url + "/rest/api/content/search"
        params = {"cql": cql, "limit": "50"}
        pages, seen, cursors, skipped = [], set(), set(), 0
        for _ in range(200):
            cursor = urlencode(sorted(params.items()))
            if cursor in cursors: raise ConfluenceError("pagination", "Confluence повторил ссылку пагинации; уточните CQL.")
            cursors.add(cursor)
            data = self._json(endpoint, params)
            results = data.get("results")
            if not isinstance(results, list): raise ConfluenceError("invalid_response", "В ответе CQL нет списка results.")
            for result in results:
                if not isinstance(result, dict): raise ConfluenceError("invalid_response", "Некорректный элемент выдачи CQL.")
                if result.get("type") != "page":
                    skipped += 1
                    continue
                id = str(result.get("id", ""))
                if not re.fullmatch(r"[0-9]+", id): raise ConfluenceError("invalid_response", "Некорректный page ID в выдаче CQL.")
                if id in seen: continue
                seen.add(id)
                if len(pages) == max_pages:
                    return {"pages": pages, "truncated": True, "skipped": skipped}
                pages.append({"id": id, "title": str(result.get("title", id)), "url": self.page_url(id)})
            next_url = data.get("_links", {}).get("next")
            if not next_url: return {"pages": pages, "truncated": False, "skipped": skipped}
            if len(pages) >= max_pages: return {"pages": pages, "truncated": True, "skipped": skipped}
            parsed = urlsplit(next_url)
            base = urlsplit(self.base_url)
            allowed_path = base.path + "/rest/api/content/search"
            if (parsed.netloc and (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc)) or parsed.path not in {allowed_path, "/rest/api/content/search"} or parsed.fragment:
                raise ConfluenceError("pagination", "Недоверенная ссылка пагинации Confluence.")
            params = dict(parse_qsl(parsed.query))
            # Keep the original query and response size; only continuation state can change.
            params = {k: v for k, v in params.items() if k in {"start", "cursor"}}
            if not params: raise ConfluenceError("pagination", "В ссылке пагинации нет start/cursor.")
            params.update(cql=cql, limit="50")
        raise ConfluenceError("pagination", "Слишком много страниц пагинации. Сузьте CQL.")

    def fetch_page(self, page_id):
        if not re.fullmatch(r"[0-9]+", page_id): raise ConfluenceError("invalid_id", "Некорректный ID страницы.")
        data = self._json(self.base_url + "/rest/api/content/" + page_id, {"expand": "body.view,version"})
        try:
            if str(data["id"]) != page_id or data["type"] != "page": raise ValueError()
            version = data["version"]["number"]
            rendered = data["body"]["view"]["value"]
            if type(version) is not int or version < 1 or not isinstance(rendered, str): raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise ConfluenceError("invalid_response", "Страница не содержит ожидаемые ID, version и HTML body.view.") from None
        title = str(data.get('title', page_id))
        content = ('<!doctype html>\n<html><head><meta charset="utf-8">'
                   f'<title>{escape(title)}</title><base href="{escape(self.page_url(page_id), quote=True)}">'
                   f'</head><body>{rendered}</body></html>').encode('utf-8')
        if len(content) > 5 * 1024 * 1024: raise ConfluenceError("too_large", "Содержимое страницы превышает 5 MiB.")
        return {"id": page_id, "title": str(data.get("title", page_id)), "url": self.page_url(page_id), "version": version, "content": content}

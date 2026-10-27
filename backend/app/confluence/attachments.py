"""Resolve only authenticated Confluence attachment links, never arbitrary URLs."""
import re
import time
from urllib.parse import urlsplit, unquote, parse_qs, urlencode
import httpx
from .client import ConfluenceError
from ..pptx_parser import MAX_PPTX


def trusted_url(client, url, *, download=False):
    base = urlsplit(client.base_url)
    if url.startswith("/") and not url.startswith("//"):
        if not url.startswith(base.path + "/"):
            url = base.path + url
        url = base.scheme + "://" + base.netloc + url
    parsed = urlsplit(url)
    decoded = unquote(parsed.path)
    if (parsed.scheme != base.scheme or parsed.netloc.lower() != base.netloc.lower() or parsed.username or parsed.password
            or "\\" in decoded or any(p in {".", ".."} for p in decoded.split("/")) or "%" in decoded
            or any(ord(ch) < 32 for ch in url) or not decoded.startswith(base.path + "/")):
        raise ConfluenceError("attachment_url", "Нужна ссылка на вложение выбранного Confluence.")
    path = decoded[len(base.path):]
    if download and not re.fullmatch(r"/download/attachments/\d+/[^/]+", path):
        raise ConfluenceError("attachment_url", "Недопустимый путь загрузки вложения.")
    return parsed._replace(fragment="").geturl(), path


def resolve_attachment(client, link):
    url, path = trusted_url(client, link)
    params = parse_qs(urlsplit(url).query)
    match = re.fullmatch(r"/download/attachments/(\d+)/([^/]+)", path)
    attachment_id = None
    if match:
        page_id, filename = match.groups()
        data = client._json(client.base_url + f"/rest/api/content/{page_id}/child/attachment",
                            {"filename": filename, "expand": "version,container", "limit": "2"})
        items = data.get("results", [])
        if len(items) != 1: raise ConfluenceError("attachment_missing", "Не найдено единственное вложение с таким именем.")
        item = items[0]
    elif params.get("preview"):
        preview = params["preview"][0].strip("/").split("/")
        if len(preview) != 3 or not preview[0].isdigit() or not re.fullmatch(r"(?:att)?\d+", preview[1]):
            raise ConfluenceError("attachment_url", "Не распознана preview-ссылка вложения.")
        page_id, attachment_id, filename = preview
        attachment_id = attachment_id if attachment_id.startswith("att") else "att" + attachment_id
        item = client._json(client.base_url + "/rest/api/content/" + attachment_id, {"expand": "version,container"})
    else:
        raise ConfluenceError("attachment_url", "Используйте ссылку download/attachments или ссылку с параметром preview.")
    try:
        assert item["type"] == "attachment" and str(item["container"]["id"]) == page_id
        assert re.fullmatch(r"(?:att)?\d+", str(item["id"]))
        assert attachment_id is None or str(item["id"]) == attachment_id
        assert item["title"].lower().endswith(".pptx") and "/" not in item["title"] and "\\" not in item["title"]
        version = item["version"]["number"]
        assert type(version) is int and version > 0
        download_url, download_path = trusted_url(client, item["_links"]["download"], download=True)
        assert download_path.startswith(f"/download/attachments/{page_id}/")
        # Pin the downloaded bytes to the version returned by REST.
        query = parse_qs(urlsplit(download_url).query)
        query["version"] = [str(version)]
        download_url = urlsplit(download_url)._replace(query=urlencode(query, doseq=True)).geturl()
        return {"attachment_id": str(item["id"]), "parent_page_id": page_id, "version": version,
                "title": item["title"], "url": client.page_url(page_id), "download_url": download_url, "format": "pptx"}
    except (KeyError, TypeError, AssertionError, AttributeError):
        raise ConfluenceError("attachment_response", "Confluence вернул некорректные сведения о вложении.") from None


def fetch_attachment(client, metadata):
    url, _ = trusted_url(client, metadata["download_url"], download=True)
    try:
        with client.client.stream("GET", url, headers={"Accept": "application/octet-stream"}) as response:
            if response.status_code != 200:
                raise ConfluenceError("attachment_download", f"Загрузка вложения отклонена (HTTP {response.status_code}); перенаправления запрещены.")
            chunks, size, start = [], 0, time.monotonic()
            for part in response.iter_bytes(chunk_size=65536):
                size += len(part)
                if size > MAX_PPTX: raise ConfluenceError("too_large", "PPTX превышает 25 MiB.")
                if time.monotonic() - start > 60: raise ConfluenceError("timeout", "Загрузка PPTX превысила 60 секунд.")
                chunks.append(part)
            return b"".join(chunks)
    except httpx.HTTPError:
        raise ConfluenceError("connection_error", "Не удалось скачать вложение; проверьте сеть, PAT и доступ.") from None

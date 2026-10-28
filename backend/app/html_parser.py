"""HTML is parsed into text blocks; original markup is never rendered in the UI."""
from lxml import html, etree
from fastapi import HTTPException


def clean_text(element):
    return " ".join(element.text_content().split())


def parse_html(content: bytes, snapshot_id: str, *, anchor_paths=None):
    if not content.strip():
        raise HTTPException(422, "HTML-файл пуст")
    try:
        # Decode explicitly when UTF-8 is valid; lxml otherwise respects HTML encoding metadata.
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content
        root = html.document_fromstring(text, parser=html.HTMLParser(no_network=True, huge_tree=False))
    except (ValueError, etree.ParserError):
        raise HTTPException(422, "Не удалось прочитать HTML")
    for node in root.xpath("//script|//style|//iframe|//object|//embed|//noscript|//template|//svg"):
        node.drop_tree()
    tree = root.getroottree()
    blocks, tables, warnings = [], [], []
    block_by_element = {}
    heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}
    block_tags = heading_tags | {"p", "li", "ul", "ol", "div", "section", "article", "main", "header", "footer",
                                "td", "th", "tr", "table", "thead", "tbody", "tfoot", "pre", "blockquote", "br"}

    def emit(el, text):
        text = " ".join(text.split())
        if text:
            block = {"id": f"b{len(blocks)}", "kind": "heading" if el.tag in heading_tags else "text",
                     "level": int(el.tag[1]) if el.tag in heading_tags else None,
                     "text": text, "html_path": (anchor_paths or {}).get(el.get("data-storage-anchor"), tree.getpath(el))}
            blocks.append(block)
            block_by_element[el] = block

    def walk(el):
        if not isinstance(el.tag, str) or el.tag == "head":
            return
        if el.tag in heading_tags or (el.tag in {"td", "th"} and not el.xpath(".//table")):
            emit(el, clean_text(el))
            return
        buffer = el.text or ""
        for child in el:
            is_block = child.tag in block_tags or any(node.tag in block_tags for node in child.iterdescendants())
            if is_block:
                emit(el, buffer)
                buffer = ""
                walk(child)
            elif isinstance(child.tag, str):
                buffer += child.text_content()
            buffer += child.tail or ""
        emit(el, buffer)

    walk(root)
    for table in root.xpath("//table[not(ancestor::table)]"):
        rows = []
        for row in table.xpath("./tr|./thead/tr|./tbody/tr|./tfoot/tr"):
            cells = row.xpath("./td|./th")
            if any(c.get("colspan", "1") != "1" or c.get("rowspan", "1") != "1" or c.xpath(".//table") for c in cells):
                warnings.append("Строка с объединёнными ячейками или вложенной таблицей пропущена: " + tree.getpath(row))
                continue
            rows.append([block_by_element.get(c) for c in cells])
        tables.append({"index": len(tables), "rows": rows, "caption": " ".join(table.xpath("./caption//text()"))})
    if not blocks:
        body = root.find("body")
        text = clean_text(body if body is not None else root)
        if text:
            blocks.append({"id": "b0", "kind": "text", "level": None, "text": text, "html_path": "/html/body"})
    return {"contract_version": 1, "snapshot_id": snapshot_id, "blocks": blocks, "tables": tables, "warnings": warnings,
            "html": etree.tostring(root, encoding='unicode', method='html')}


def extract(document, schema, mode="table", table_index=None):
    proposals, warnings = {}, list(document["warnings"])
    fields = schema["properties"]
    labels = {str(v.get("title", key)).strip().casefold(): key for key, v in fields.items()}
    labels.update({key.casefold(): key for key in fields})
    found = {}

    def add(key, value, blocks, method):
        if not value:
            return
        spec = fields[key]
        try:
            if spec["type"] == "integer":
                value = int(value)
            elif spec["type"] == "number":
                value = float(value.replace(",", "."))
                import math
                if not math.isfinite(value):
                    raise ValueError()
            elif spec["type"] == "boolean":
                lookup = {"true": True, "false": False, "да": True, "нет": False}
                value = lookup[value.casefold()]
            elif spec["type"] == "array":
                value = [v.strip() for v in value.split(";") if v.strip()]
        except (ValueError, KeyError):
            warnings.append(f"Не удалось преобразовать значение поля {key}")
            return
        from .evidence import evidence_for
        evidence = [evidence_for(document, b) for b in blocks]
        found.setdefault(key, []).append({"value": value, "method": method, "evidence": evidence})

    if mode == "table":
        tables = document["tables"]
        if table_index is None:
            matches = [t for t in tables if any(row and row[0] and row[0]["text"].casefold() in labels for row in t["rows"])]
            if len(matches) != 1:
                warnings.append("Не найдена единственная таблица с реквизитами. Укажите номер таблицы (с 0).")
                matches = []
        else:
            if table_index < 0 or table_index >= len(tables):
                raise HTTPException(422, "Таблица с таким номером не найдена")
            matches = [tables[table_index]]
        for table in matches:
            for row in table["rows"]:
                if len(row) == 2 and all(row):
                    key = labels.get(row[0]["text"].casefold())
                    if key:
                        add(key, row[1]["text"], [row[1]], "table")
    else:
        blocks = document["blocks"]
        headings = [(i, b) for i, b in enumerate(blocks) if b["kind"] == "heading"]
        for i, b in headings:
            key = labels.get(b["text"].casefold())
            if not key:
                continue
            end = next((j for j, h in headings if j > i and h["level"] <= b["level"]), len(blocks))
            # The explicit problem → tasks contract requires both boundary headings.
            if key == "problem":
                ends = [j for j, h in headings if j > i and h["text"].casefold() == "задачи проекта"]
                if not ends or ends[0] != end:
                    warnings.append("Для «Проблематики» не найдена граница «Задачи проекта»")
                    continue
            selected = blocks[i + 1:end]
            add(key, "\n".join(x["text"] for x in selected), selected, "section")
        title = [b for b in blocks if b["kind"] == "heading" and b["level"] == 1]
        if "title" in fields and "title" not in found and len(title) == 1:
            add("title", title[0]["text"], title, "heading")
    for key, values in found.items():
        if len(values) == 1:
            proposals[key] = values[0]
        else:
            warnings.append(f"Несколько значений для поля {key}; предложение не сформировано")
    if not proposals:
        warnings.append("Поля не извлечены. Измените способ извлечения или заполните объект вручную.")
    return proposals, warnings

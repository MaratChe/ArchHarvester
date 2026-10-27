from lxml import etree
from fastapi import HTTPException
from html.entities import name2codepoint
import re
from ..html_parser import parse_html

AC = "http://atlassian.com/content"
RI = "http://atlassian.com/resource/identifier"


def parse_storage(content, snapshot_id):
    try:
        # Confluence XHTML can contain named HTML entities without a DTD.
        # Map known names outside CDATA only; never fetch or enable external entities.
        parts = re.split(r'(<!\[CDATA\[.*?\]\]>)', content.decode("utf-8"), flags=re.DOTALL)
        def numeric(match):
            name = match.group(1)
            return f"&#{name2codepoint[name]};" if name in name2codepoint and name not in {"amp","lt","gt","quot","apos"} else match.group(0)
        normalized = ''.join(part if part.startswith('<![CDATA[') else re.sub(r'&([A-Za-z][A-Za-z0-9]+);', numeric, part) for part in parts).encode("utf-8")
        root = etree.fromstring(b'<storage xmlns:ac="http://atlassian.com/content" xmlns:ri="http://atlassian.com/resource/identifier">' + normalized + b'</storage>',
                                parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False))
    except (etree.XMLSyntaxError, UnicodeDecodeError):
        raise HTTPException(422, "Некорректный Confluence Storage XML; содержимое не интерпретировано") from None
    tree = root.getroottree()
    paths = {str(i): tree.getpath(el) for i, el in enumerate(root.iter()) if isinstance(el.tag, str)}
    for i, el in enumerate(root.iter()):
        if isinstance(el.tag, str): el.set("data-storage-anchor", str(i))
    warnings = []
    wrappers = {"details", "panel", "info", "note", "warning", "tip", "expand", "section", "column"}
    for macro in list(root.iter("{" + AC + "}structured-macro")):
        name = macro.get("{" + AC + "}name", "unknown")
        if name not in wrappers:
            warnings.append(f"Макрос «{name}» не выполняется; его содержимое не извлечено.")
            parent = macro.getparent()
            if parent is not None:
                placeholder = etree.Element("p")
                placeholder.text = f"[Макрос {name}: содержимое не извлечено]"
                placeholder.set("data-storage-anchor", macro.get("data-storage-anchor", ""))
                placeholder.tail = macro.tail
                parent.replace(macro, placeholder)
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            if el.getparent() is not None: el.getparent().remove(el)
            continue
        if el.tag == "{" + AC + "}parameter":
            el.getparent().remove(el)
        elif el.tag.startswith("{" + AC + "}"):
            el.tag = "div"
        elif el.tag.startswith("{" + RI + "}"):
            el.tag = "span"
            warnings.append("Ссылка на ресурс Confluence сохранена в исходнике; содержимое ресурса не загружено.")
    root.tag = "div"
    document = parse_html(etree.tostring(root, encoding="utf-8", method="html"), snapshot_id, anchor_paths=paths)
    document["format"] = "confluence_storage"
    document["warnings"].extend(dict.fromkeys(warnings))
    return document

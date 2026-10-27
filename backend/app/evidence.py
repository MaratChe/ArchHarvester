def evidence_for(document, block):
    return {"snapshot_id": document["snapshot_id"], "block_id": block["id"], "quote": block["text"],
            **{k: block[k] for k in ("html_path", "slide_index", "shape_id", "cell") if k in block}}

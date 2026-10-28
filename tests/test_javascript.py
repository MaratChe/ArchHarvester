import pytest
from fastapi import HTTPException
from backend.app.pipeline_engine import run_pipeline, validate_steps
from backend.app.html_parser import parse_html
from backend.app.registry import DEFAULT_SCHEMA


def test_js_step_contract_and_evidence(monkeypatch):
    from backend.app import javascript_runner
    doc = parse_html(b'<p>Owner: Alice</p>', 's')
    def run(code, document, params, **kwargs):
        assert '<p>Owner: Alice</p>' in document['html']
        return {'proposals': [{'field': 'owner', 'value': 'Alice', 'block_ids': ['b0']}],
                'warnings': [], 'files': [{'name': 'page.md', 'content': 'Owner: Alice'}], 'runtime_image_id': 'sha256:js'}
    monkeypatch.setattr(javascript_runner, 'run_javascript', run)
    result = run_pipeline(doc, DEFAULT_SCHEMA, [{'kind': 'javascript', 'code': 'emit(...)', 'params': {}}])
    assert result['proposals']['owner']['evidence'][0]['quote'] == 'Owner: Alice'
    assert result['steps'][0]['files'][0]['name'] == 'page.md'
    assert result['steps'][0]['javascript_runtime_image_id'] == 'sha256:js'


@pytest.mark.parametrize('step', [
    {'kind': 'javascript', 'code': ''},
    {'kind': 'javascript', 'code': 'x', 'params': []},
])
def test_invalid_javascript_settings(step):
    with pytest.raises(HTTPException):
        validate_steps([step], DEFAULT_SCHEMA)


def test_old_snapshot_html_is_hydrated_without_changing_blocks(client, type_id):
    from tests.conftest import upload
    from backend.app.pipelines import script_document
    from backend.app.db import snapshots
    from backend.app.registry import require
    candidate = upload(client, type_id, '<p>Owner: Alice</p>').json()
    db = client.app.state.db
    with db.transaction() as connection:
        snapshot = require(connection, snapshots, candidate['snapshot_id'])
        snapshot['document'].pop('html')
        connection.execute(snapshots.update().where(snapshots.c.id == snapshot['id']).values(data=snapshot))
    old = snapshot['document']
    hydrated = script_document(old, db, [{'kind': 'javascript'}])
    assert '<p>Owner: Alice</p>' in hydrated['html']
    assert hydrated['blocks'] == old['blocks']
    assert 'html' not in old


def test_confluence_exposes_normalized_html():
    from backend.app.confluence.storage import parse_storage
    doc = parse_storage(b'<h1>Decision</h1><p>Owner: Alice</p>', 's')
    assert '<h1' in doc['html'] and 'Owner: Alice' in doc['html']
    assert doc['format'] == 'confluence_storage'

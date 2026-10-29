import pytest
from fastapi import HTTPException
from backend.app.pipeline_engine import run_pipeline
from backend.app.html_parser import parse_html
from backend.app.registry import DEFAULT_SCHEMA

DOC = parse_html(b'<p>Owner: Alice</p>', 's')


def test_cross_language_outputs_and_trace_are_independent(monkeypatch):
    def js(code, document, params, **kwargs):
        assert kwargs['previous_results']['steps'] == []
        return {'proposals': [], 'warnings': [], 'output': {'text': 'Alice', 'ids': ['b0']},
                'files': [{'name': 'page.md', 'content': 'Owner: Alice'}], 'runtime_image_id': 'js'}
    def py(code, document, params, **kwargs):
        previous = kwargs['previous_results']
        data = previous['steps'][-1]['output']
        assert previous['steps'][-1]['files'][0]['name'] == 'page.md'
        previous['steps'][0]['output']['text'] = 'mutated'
        return {'proposals': [{'field': 'owner', 'value': 'Alice', 'block_ids': data['ids']}],
                'warnings': [], 'output': {'done': True}, 'runtime_image_id': 'py'}
    monkeypatch.setattr('backend.app.javascript_runner.run_javascript', js)
    monkeypatch.setattr('backend.app.python_runner.run_python', py)
    result = run_pipeline(DOC, DEFAULT_SCHEMA, [{'kind': 'javascript', 'code': 'x'}, {'kind': 'python', 'code': 'x'}], capture_io=True)
    assert result['proposals']['owner']['value'] == 'Alice'
    assert result['steps'][0]['output'] == {'text': 'Alice', 'ids': ['b0']}
    assert result['steps'][1]['input']['previous_results']['steps'][0]['output']['text'] == 'Alice'
    assert result['steps'][1]['input']['document'] == DOC
    assert result['steps'][1]['result']['output'] == {'done': True}


@pytest.mark.parametrize('value', [float('nan'), {'bad': object()}, 'x' * (256 * 1024 + 1)], ids=['nan', 'non_json', 'oversize'])
def test_invalid_step_output_is_rejected(monkeypatch, value):
    monkeypatch.setattr('backend.app.python_runner.run_python', lambda *a, **k: {'proposals': [], 'warnings': [], 'output': value, 'runtime_image_id': 'py'})
    with pytest.raises(HTTPException, match='JSON|256'):
        run_pipeline(DOC, DEFAULT_SCHEMA, [{'kind': 'python', 'code': 'x'}])


def test_failed_test_retains_completed_and_failed_step_inputs(client, type_id):
    from tests.conftest import upload
    snapshot = upload(client, type_id, '<p>Alice</p>').json()['snapshot_id']
    steps = [{'kind': 'sections'}, {'kind': 'table', 'table_index': 99}]
    pipeline = client.post('/api/pipelines', json={'key': 'trace', 'name': 'Trace', 'type_id': type_id, 'steps': steps}).json()
    report = client.post(f"/api/pipelines/{pipeline['id']}/tests", json={'snapshot_ids': [snapshot]}).json()
    assert not report['ok']
    trace = report['results'][0]['steps']
    assert len(trace) == 2 and 'result' in trace[0]
    assert 'error' in trace[1] and trace[1]['input']['document']['snapshot_id'] == snapshot


def test_normal_run_does_not_store_full_inputs():
    result = run_pipeline(DOC, DEFAULT_SCHEMA, [{'kind': 'sections'}])
    assert 'input' not in result['steps'][0]


def test_invalid_proposal_is_still_a_validation_error_with_trace(monkeypatch):
    monkeypatch.setattr('backend.app.python_runner.run_python', lambda *a, **k: {
        'proposals': [{'field': 'owner', 'value': float('nan'), 'block_ids': ['b0']}],
        'warnings': [], 'runtime_image_id': 'py'})
    with pytest.raises(HTTPException) as error:
        run_pipeline(DOC, DEFAULT_SCHEMA, [{'kind': 'python', 'code': 'x'}], capture_io=True)
    assert error.value.status_code == 422
    assert error.value.step_results[0]['result']['invalid_json']


def test_large_trace_is_explicitly_truncated_without_changing_document():
    doc = {**DOC, 'html': 'x' * (600 * 1024)}
    result = run_pipeline(doc, DEFAULT_SCHEMA, [{'kind': 'sections'}], capture_io=True)
    assert result['steps'][0]['input']['truncated'] is True
    assert len(doc['html']) == 600 * 1024

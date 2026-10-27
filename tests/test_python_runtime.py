"""Opt-in integration tests run the real disposable Docker container."""
import os
import pytest
from fastapi import HTTPException
from backend.app.python_runner import run_python
from backend.app.pipeline_engine import run_pipeline
from backend.app.html_parser import parse_html
from backend.app.registry import DEFAULT_SCHEMA

pytestmark = pytest.mark.skipif(os.environ.get("RUN_DOCKER_TESTS") != "1", reason="Set RUN_DOCKER_TESTS=1 for real Docker isolation tests")
DOC = parse_html(b"<p>Delivery</p>", "test")


def test_sdk_and_isolation():
    code = '''import os, socket
assert os.getuid() == 65534
assert not os.path.exists('/var/run/docker.sock')
assert not os.path.exists('registry.db')
assert open('/sys/fs/cgroup/memory.max').read().strip() == '536870912'
assert open('/sys/fs/cgroup/pids.max').read().strip() == '64'
assert open('/sys/fs/cgroup/cpu.max').read().strip() == '100000 100000'
try:
    open('/probe', 'w')
    raise AssertionError('root filesystem is writable')
except OSError:
    pass
try:
    socket.create_connection(('1.1.1.1', 443), timeout=.5)
    raise AssertionError('network access is enabled')
except OSError:
    pass
emit('title', document['blocks'][0]['text'], [document['blocks'][0]['id']])
'''
    result = run_pipeline(DOC, DEFAULT_SCHEMA, [{"kind": "python", "code": code}])
    assert result["proposals"]["title"]["value"] == "Delivery"
    assert result["steps"][0]["runtime_image_id"].startswith("sha256:")


def test_timeout_and_output_bound(monkeypatch):
    monkeypatch.setattr("backend.app.python_runner.TIMEOUT", 3)
    with pytest.raises(HTTPException, match="времени"):
        run_python("while True: pass", DOC, {})
    with pytest.raises(HTTPException, match="вывода"):
        run_python("print('x' * 3000000)", DOC, {})


def test_bad_evidence_and_schema():
    with pytest.raises(HTTPException, match="источник"):
        run_pipeline(DOC, DEFAULT_SCHEMA, [{"kind": "python", "code": "emit('title','invented',['missing'])"}])
    with pytest.raises(HTTPException, match="схеме"):
        run_pipeline(DOC, DEFAULT_SCHEMA, [{"kind": "python", "code": "emit('title',42,['b0'])"}])


def test_runtime_missing_fails_closed(monkeypatch):
    monkeypatch.setattr("backend.app.python_runner.shutil.which", lambda name: None)
    with pytest.raises(HTTPException) as exc: run_python("raise Exception()", DOC, {})
    assert exc.value.status_code == 503


def test_memory_limit_and_invalid_json():
    with pytest.raises(HTTPException, match="ошибкой"):
        run_python("large = bytearray(768 * 1024 * 1024)", DOC, {})
    with pytest.raises(HTTPException, match="StepResult JSON"):
        run_python("print('not json')", DOC, {})


def test_python_between_headings():
    doc=parse_html('<h2>Проблематика</h2><p>Потери</p><h2>Задачи проекта</h2>'.encode(),'s')
    result=run_pipeline(doc,DEFAULT_SCHEMA,[{"kind":"python","code":'''blocks = document['blocks']
start = next(i for i,b in enumerate(blocks) if b['text'] == 'Проблематика')
end = next(i for i,b in enumerate(blocks) if b['text'] == 'Задачи проекта')
selected = blocks[start+1:end]
emit('problem', '\\n'.join(b['text'] for b in selected), [b['id'] for b in selected])
'''}])
    assert result['proposals']['problem']['value']=='Потери'

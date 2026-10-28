"""Real Node Worker + Docker checks, opt in with RUN_DOCKER_TESTS=1."""
import os
import pytest
from fastapi import HTTPException
from backend.app.javascript_runner import run_javascript
from backend.app.html_parser import parse_html
from backend.app.pipeline_engine import run_pipeline
from backend.app.registry import DEFAULT_SCHEMA
from tests.conftest import upload

pytestmark = pytest.mark.skipif(os.environ.get('RUN_DOCKER_TESTS') != '1', reason='Set RUN_DOCKER_TESTS=1 for Node Worker isolation tests')
CODE = """
const md = toMarkdown(document.html);
saveMarkdown('page.md', md);
const block = document.blocks.find(b => b.text.startsWith(params.prefix));
emit('owner', block.text.slice(params.prefix.length).trim(), [block.id]);
"""


def test_markdown_and_proposals():
    doc = parse_html('<h1>Проект</h1><p>Владелец: Алиса</p><script>evil()</script>'.encode(), 's')
    result = run_pipeline(doc, DEFAULT_SCHEMA, [{'kind': 'javascript', 'code': CODE, 'params': {'prefix': 'Владелец:'}}])
    assert result['proposals']['owner']['value'] == 'Алиса'
    assert result['proposals']['owner']['evidence'][0]['quote'] == 'Владелец: Алиса'
    md = result['steps'][0]['files'][0]['content']
    assert '# Проект' in md and 'evil' not in md


def test_container_files_network_and_environment_are_isolated():
    code = """
const fs = await import('node:fs/promises');
let denied = false;
try { await fs.writeFile('/runner/leak', 'x'); } catch { denied = true; }
if (!denied) throw Error('root writable');
try { await fs.access('/var/run/docker.sock'); throw Error('socket exposed'); }
catch (e) { if (e.code !== 'ENOENT') throw e; }
if (process.env.ARCH_REGISTRY_CA_BUNDLE || process.env.LOCALAPPDATA) throw Error('host environment');
try { await fetch('https://example.com', {signal: AbortSignal.timeout(1000)}); throw Error('network available'); }
catch (e) { if (e.message === 'network available') throw e; }
warnings.push('isolation checked');
"""
    assert run_javascript(code, {}, {})['warnings'] == ['isolation checked']


@pytest.mark.parametrize('code', ["throw Error('broken')", 'while (true) {}', "saveMarkdown('../escape.md', 'x')", "saveMarkdown('large.md', 'x'.repeat(262145))"])
def test_failures_are_bounded(code):
    with pytest.raises(HTTPException):
        run_javascript(code, {}, {})


@pytest.mark.parametrize('code', ["emit('owner', 42, ['b0'])", "emit('owner', 'Alice', ['missing'])"])
def test_schema_and_source_validation(code):
    with pytest.raises(HTTPException):
        run_pipeline(parse_html(b'<p>Alice</p>', 's'), DEFAULT_SCHEMA, [{'kind': 'javascript', 'code': code}])


def test_publish_and_review_keep_markdown_and_pin_runtime(client, type_id):
    sample = upload(client, type_id, '<p>Owner: Alice</p>').json()
    draft = client.post('/api/pipelines', json={'key': 'js', 'name': 'JS', 'type_id': type_id,
                        'steps': [{'kind': 'javascript', 'code': CODE, 'params': {'prefix': 'Owner:'}}]}).json()
    run = client.post(f"/api/pipelines/{draft['id']}/tests", json={'snapshot_ids': [sample['snapshot_id']]}).json()
    assert run['ok'], run
    published = client.post(f"/api/pipelines/{draft['id']}/publish").json()
    assert published['javascript_runtime_image_id'].startswith('sha256:')
    candidate = client.post(f"/api/pipelines/{draft['id']}/propose", json={'snapshot_id': sample['snapshot_id']}).json()
    assert candidate['step_results'][0]['files'][0]['content'] == 'Owner: Alice'
    assert candidate['proposals']['owner']['value'] == 'Alice'
    assert client.get('/api/artifacts').json() == []

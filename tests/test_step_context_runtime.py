"""Exercise actual JSON transport across both restricted container runtimes."""
import os
import pytest
from backend.app.pipeline_engine import run_pipeline
from backend.app.html_parser import parse_html
from backend.app.registry import DEFAULT_SCHEMA

pytestmark = pytest.mark.skipif(os.environ.get('RUN_DOCKER_TESTS') != '1', reason='Requires real Docker runners')


def test_javascript_python_javascript_chain():
    doc = parse_html(b'<h1>Decision</h1><p>Owner: Alice</p>', 'chain')
    steps = [
        {'kind': 'javascript', 'code': "const md = toMarkdown(document.html); saveMarkdown('page.md', md); set_output({markdown: md, ids: document.blocks.filter(b => b.text.startsWith('Owner:')).map(b => b.id)});"},
        {'kind': 'python', 'code': "data = previous_results['steps'][-1]['output']\nowner = next(line.split(':', 1)[1].strip() for line in data['markdown'].splitlines() if line.startswith('Owner:'))\nset_output({'owner': owner, 'ids': data['ids']})\ndocument['blocks'].clear()"},
        {'kind': 'javascript', 'code': "const data = previous_results.steps.at(-1).output; emit('owner', data.owner, data.ids); set_output({count: document.blocks.length});"},
    ]
    result = run_pipeline(doc, DEFAULT_SCHEMA, steps, capture_io=True)
    assert result['proposals']['owner']['value'] == 'Alice'
    assert result['proposals']['owner']['evidence'][0]['quote'] == 'Owner: Alice'
    assert result['steps'][2]['output']['count'] == 2
    assert result['steps'][1]['input']['previous_results']['steps'][0]['files'][0]['name'] == 'page.md'
    assert result['steps'][1]['result']['output'] == {'owner': 'Alice', 'ids': ['b1']}


@pytest.mark.parametrize('kind,code', [('python', "set_output(float('nan'))"), ('javascript', 'set_output({value: undefined})'), ('javascript', 'set_output(NaN)')])
def test_non_json_outputs_fail_closed(kind, code):
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        run_pipeline(parse_html(b'<p>Alice</p>', 's'), DEFAULT_SCHEMA, [{'kind': kind, 'code': code}])

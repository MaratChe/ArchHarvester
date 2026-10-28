"""JavaScript uses a Worker inside the same restricted container boundary as Python."""
import re
from fastapi import HTTPException
from .python_runner import run_python, runtime_status as container_status

IMAGE = 'architecture-registry-javascript:1'


def runtime_status():
    state = container_status(IMAGE)
    if not state['available']:
        state['message'] = 'Script Engine недоступен. Запустите Docker и scripts/setup-javascript-runner.ps1 (или .sh)'
    return state


def run_javascript(code, document, params, *, expected_runtime=None):
    try:
        result = run_python(code, document, params, expected_runtime=expected_runtime, image=IMAGE)
    except HTTPException as exc:
        raise HTTPException(exc.status_code, str(exc.detail).replace('Python', 'JavaScript').replace('setup-python-runner', 'setup-javascript-runner')) from None
    files = result.get('files', [])
    if not isinstance(files, list) or len(files) > 5:
        raise HTTPException(422, 'JavaScript: допускается до 5 Markdown-файлов')
    for item in files:
        if (not isinstance(item, dict) or set(item) != {'name', 'content'}
                or not isinstance(item['name'], str) or not re.fullmatch(r'[\w-][\w .-]{0,95}\.md', item['name'])
                or not isinstance(item['content'], str) or len(item['content'].encode('utf-8')) > 256 * 1024):
            raise HTTPException(422, 'JavaScript: неверный Markdown-файл (имя .md, до 256 KiB)')
    return result

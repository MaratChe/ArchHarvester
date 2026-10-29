"""Deterministic rules and isolated Python share one evidence validation boundary."""
import json
from copy import deepcopy
from fastapi import HTTPException
from jsonschema import Draft202012Validator, FormatChecker
from .evidence import evidence_for
from .html_parser import extract


def validate_steps(steps, schema):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 20: raise HTTPException(422, "Нужно от 1 до 20 шагов")
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") not in {"table", "sections", "between", "python", "llm", "javascript"}:
            raise HTTPException(422, "Неизвестный вид шага")
        allowed = {"kind", "overwrite"} | {"table": {"table_index"}, "sections": set(), "between": {"field", "start", "end"}, "python": {"code", "params"}, "javascript": {"code", "params"}, "llm": {"model","provider_id","prompt","include_previous"}}[step["kind"]]
        if set(step) - allowed: raise HTTPException(422, "Неизвестные параметры шага")
        if "overwrite" in step and type(step["overwrite"]) is not bool: raise HTTPException(422, "overwrite должен быть boolean")
        if step["kind"] == "table" and step.get("table_index") is not None and (type(step["table_index"]) is not int or step["table_index"] < 0):
            raise HTTPException(422, "Номер таблицы — целое число с 0")
        if step["kind"] == "between":
            if step.get("field") not in schema["properties"]: raise HTTPException(422, "Поле правила отсутствует в схеме")
            if not all(isinstance(step.get(k), str) and 0 < len(step[k].strip()) <= 200 for k in ("start", "end")):
                raise HTTPException(422, "Укажите две границы длиной до 200 символов")
        if step["kind"] in {"python", "javascript"}:
            if not isinstance(step.get("code"), str) or not 0 < len(step["code"].strip()) <= 32000: raise HTTPException(422, "Код скрипта: от 1 до 32000 символов")
            if not isinstance(step.get("params", {}), dict): raise HTTPException(422, "params должен быть объектом")
        if step['kind']=='llm':
            if not isinstance(step.get('prompt',''),str) or len(step.get('prompt',''))>4000:raise HTTPException(422,'Инструкция LLM — строка до 4000 символов')
            if type(step.get('include_previous',False)) is not bool:raise HTTPException(422,'include_previous должен быть boolean')
            if not isinstance(step.get('model'),str) or not 1<=len(step['model'])<=150:raise HTTPException(422,'Укажите имя модели')
            if not isinstance(step.get('provider_id','ollama'),str) or not 1<=len(step.get('provider_id','ollama'))<=100:raise HTTPException(422,'Укажите провайдера')
    if len(json.dumps(steps, ensure_ascii=False)) > 100000: raise HTTPException(422, "Слишком большой пайплайн")


def run_pipeline(document, schema, steps, *, expected_runtime=None,expected_js_runtime=None,client_factory=None, capture_io=False):
    audit={'llm_runs':[],'_llm_raw':[], 'steps':[]}
    try:return _run_pipeline(document,schema,steps,expected_runtime=expected_runtime,expected_js_runtime=expected_js_runtime,client_factory=client_factory,audit=audit,capture_io=capture_io)
    except HTTPException as exc:
        exc.llm_completed=audit
        exc.step_results=audit['steps']
        if capture_io and audit['steps']:
            audit['steps'][-1]['error']=str(exc.detail)
        raise


def _run_pipeline(document,schema,steps,*,expected_runtime=None,expected_js_runtime=None,client_factory=None,audit,capture_io=False):
    validate_steps(steps, schema)
    proposals, warnings, diagnostics, conflicts = {}, list(document.get("warnings", [])), [], set()
    block_map = {b["id"]: b for b in document["blocks"]}
    llm_runs, llm_raw = audit['llm_runs'], audit['_llm_raw']
    for index, step in enumerate(steps, 1):
        previous = {'fields': deepcopy(proposals), 'conflicts': sorted(conflicts),
                    'steps': [{k: deepcopy(v) for k, v in d.items() if k not in {'input', 'result'}} for d in diagnostics]}
        diagnostic = {'index': index, 'kind': step['kind'], 'emitted_fields': [], 'warnings': []}
        if capture_io:
            diagnostic['input'] = trace_value({'document': document, 'params': step.get('params', {}),
                                               'settings': step, 'previous_results': previous if step['kind'] in {'python', 'javascript'} or step.get('include_previous') else None})
            audit['steps'].append(diagnostic)
        result = {}

        kind, emitted, step_warnings = step["kind"], [], []
        if kind in {"table", "sections"}:
            found, step_warnings = extract(document, schema, kind, step.get("table_index"))
            emitted = [{"field": key, "value": p["value"], "block_ids": [e["block_id"] for e in p["evidence"]]} for key, p in found.items()]
        elif kind == "between":
            blocks = document["blocks"]
            start = [i for i, b in enumerate(blocks) if b["text"].strip().casefold() == step["start"].strip().casefold()]
            end = [i for i, b in enumerate(blocks) if b["text"].strip().casefold() == step["end"].strip().casefold()]
            if len(start) == len(end) == 1 and start[0] < end[0] and end[0] - start[0] > 1:
                selected = blocks[start[0]+1:end[0]]
                emitted = [{"field": step["field"], "value": "\n".join(b["text"] for b in selected), "block_ids": [b["id"] for b in selected]}]
            else: step_warnings.append("Границы не найдены, неоднозначны или между ними нет текста")
        elif kind == 'llm':
            from .ollama import extract_fields
            provider_id=step.get('provider_id','ollama')
            if not client_factory and provider_id!='ollama':raise HTTPException(422,'Подключение провайдера недоступно')
            context=None
            if step.get('include_previous',False):
                context=previous
            try:
                result = extract_fields(document,schema,step['model'],client=client_factory(provider_id) if client_factory else None,
                                        prompt=step.get('prompt',''),previous_results=context)
            except HTTPException as exc:
                if getattr(exc,'llm_output',None):exc.llm_output['metadata']['step']=index
                raise
            result['metadata']['step']=index
            emitted,step_warnings=result['proposals'],result['warnings']
            llm_runs.append(result['metadata']);llm_raw.append({'id':result['metadata']['run_id'],**result['trace']})
        elif kind == 'javascript':
            from .javascript_runner import run_javascript
            result = run_javascript(step['code'], document, step.get('params', {}), expected_runtime=expected_js_runtime, previous_results=deepcopy(previous))
            emitted, step_warnings = result.get('proposals'), result.get('warnings', [])
        else:
            from .python_runner import run_python
            result = run_python(step["code"], document, step.get("params", {}), expected_runtime=expected_runtime, previous_results=deepcopy(previous))
            emitted, step_warnings = result.get("proposals"), result.get("warnings", [])
        if not isinstance(emitted, list) or len(emitted) > 200 or not isinstance(step_warnings, list) or not all(isinstance(w, str) and len(w) <= 2000 for w in step_warnings):
            raise HTTPException(422, f"Шаг {index}: неверный контракт StepResult")
        output = checked_output(result.get('output'))
        if capture_io:
            diagnostic['result'] = trace_value({'proposals': emitted, 'warnings': step_warnings,
                                                 'output': output, 'files': result.get('files', [])})
        for item in emitted:
            if not isinstance(item, dict): raise HTTPException(422, f"Шаг {index}: неверное предложение")
            key = item.get("field")
            if not isinstance(key, str) or key not in schema["properties"]: raise HTTPException(422, f"Шаг {index}: неизвестное поле")
            ids = item.get("block_ids")
            if not isinstance(ids, list) or not ids or len(ids) > 20000 or not all(isinstance(id, str) and id in block_map for id in ids):
                raise HTTPException(422, f"Шаг {index}, {key}: неверные ссылки на источник")
            value = item.get("value")
            if any(Draft202012Validator(schema["properties"][key], format_checker=FormatChecker()).iter_errors(value)):
                raise HTTPException(422, f"Шаг {index}, {key}: значение не соответствует схеме")
            # Reject NaN/infinity even for permissive number schemas.
            try: json.dumps(value, allow_nan=False)
            except ValueError: raise HTTPException(422, f"Шаг {index}: нечисловое значение") from None
            if (key in proposals or key in conflicts) and not step.get("overwrite", False):
                proposals.pop(key, None); conflicts.add(key)
                step_warnings.append(f"Конфликт поля {key}: включите overwrite в выбранном шаге или устраните повтор")
                continue
            conflicts.discard(key)
            proposals[key] = {"value": value, "method": kind, "step": index,
                              "evidence": [evidence_for(document, block_map[id]) for id in dict.fromkeys(ids)]}
            if kind=='llm':
                proposals[key]['method']='llm_extract' if item['mode']=='extracted' else 'llm_transform'
                proposals[key]['model_metadata']=result['metadata']
                proposals[key]['evidence']=[{**evidence_for(document,block_map[e['block_id']]),'quote':e['quote']} for e in item['evidence']]
        warnings.extend(f"Шаг {index}: {w}" for w in step_warnings)
        diagnostic.update(emitted_fields=[i.get('field') for i in emitted], warnings=step_warnings, output=output)
        if capture_io:
            diagnostic['result'] = trace_value({'proposals': emitted, 'warnings': step_warnings, 'output': output,
                                               'files': result.get('files', []), 'fields': proposals, 'conflicts': sorted(conflicts)})
        diagnostics.append(diagnostic)
        if kind == 'javascript':
            diagnostics[-1]['javascript_runtime_image_id'] = result['runtime_image_id']
            diagnostics[-1]['files'] = result.get('files', [])
        if kind == "python": diagnostics[-1]["runtime_image_id"] = result["runtime_image_id"]
        if kind == 'llm':diagnostics[-1]['model_metadata']=result['metadata']
    if not proposals: warnings.append("Нет предложений: проверьте правила или заполните поля вручную")
    return {"proposals": proposals, "warnings": warnings, "steps": diagnostics, "llm_runs":llm_runs, "_llm_raw":llm_raw}


def checked_output(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode('utf-8')) > 256 * 1024:
            raise HTTPException(422, 'Результат шага output превышает 256 KiB')
        return json.loads(encoded)
    except (TypeError, ValueError, RecursionError, UnicodeError):
        raise HTTPException(422, 'Результат шага output должен быть корректным JSON') from None


def trace_value(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        # Keep diagnostics from turning a rejected script response into HTTP 500.
        return {'invalid_json': True, 'preview': repr(value)[:512 * 1024]}
    raw = encoded.encode('utf-8')
    if len(raw) <= 512 * 1024:
        return json.loads(encoded)
    return {'truncated': True, 'size_bytes': len(raw),
            'preview': raw[:512 * 1024].decode('utf-8', errors='ignore')}

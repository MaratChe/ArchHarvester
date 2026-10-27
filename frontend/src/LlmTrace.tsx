import {useState} from 'react';
import {api} from './api';

export type TraceRun={run_id:string;model:string;step?:number};
type Trace={request?:{endpoint:string;body:{messages?:{role:string;content:string}[]}};response?:unknown;raw?:string|null;response_omitted?:boolean;metadata?:{error?:string}};
const pretty=(value:unknown)=>JSON.stringify(value,null,2);
export function LlmTrace({id,label}:{id:string;label:string}){
  const [trace,setTrace]=useState<Trace>(),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  const load=async()=>{setLoading(true);try{setTrace(await api<Trace>(`/llm/runs/${id}/raw`));setError('');}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setLoading(false);}};
  let input:{task_instruction?:string;previous_results?:unknown}={};
  try{input=JSON.parse(trace?.request?.body.messages?.find(m=>m.role==='user')?.content||'{}');}catch{/* Historical payload may not be structured JSON. */}
  return <details className="llm-trace" onToggle={e=>{if(e.currentTarget.open&&!trace&&!error&&!loading)void load();}}><summary>{label} · запрос и ответ LLM</summary>
    {loading&&<p role="status">Загружаем диагностику…</p>}{error&&<p className="notice">{error} <button onClick={()=>void load()}>Повторить</button></p>}
    {trace&&<><p className="muted">Хранится 7 дней. HTTP-заголовки и API-ключ не сохраняются.</p>{trace.metadata?.error&&<p className="notice">{trace.metadata.error}</p>}
      {trace.request?<><p className="provider-address">{trace.request.endpoint}</p><label className="field">Системный промпт<textarea readOnly rows={8} value={trace.request.body.messages?.filter(m=>m.role==='system').map(m=>m.content).join('\n')||''}/></label><label className="field">Моя инструкция<textarea readOnly rows={4} value={input.task_instruction||'Отдельная инструкция не передавалась.'}/></label><label className="field">Переданные результаты предыдущих шагов<textarea readOnly rows={8} value={input.previous_results===undefined?'Результаты предыдущих шагов не передавались.':pretty(input.previous_results)}/></label><details><summary>Полное тело запроса: сообщения, документ, схема и параметры</summary><pre>{pretty(trace.request.body)}</pre></details></>:<p className="notice">В этом старом запуске запрос не сохранялся. Повторите тест для полной диагностики.</p>}
      <label className="field">Сырой ответ модели<textarea readOnly rows={10} value={trace.raw??'Текстовый ответ не получен или не сохранён.'}/></label>{trace.response_omitted&&<p className="notice">Ответ превысил лимит диагностики 256 KiB и сохранён не полностью.</p>}{trace.response!=null&&<details><summary>Полный JSON ответа API</summary><pre>{pretty(trace.response)}</pre></details>}
    </>}
  </details>;
}

export function LlmTraces({runs=[],errorId,prefix='Текущая версия'}:{runs?:TraceRun[];errorId?:string|null;prefix?:string}){
  return <>{runs.map((run,i)=><LlmTrace key={run.run_id} id={run.run_id} label={`${prefix} · ${run.step?`шаг ${run.step}`:`вызов ${i+1}`} · ${run.model}`}/>)}{errorId&&<LlmTrace id={errorId} label={`${prefix} · завершившийся ошибкой вызов`}/>}</>;
}

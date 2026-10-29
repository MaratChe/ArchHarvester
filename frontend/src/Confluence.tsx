import {useEffect, useRef, useState} from 'react';
import {PipelineSelect} from './PipelineSelect';
import {api, stamp} from './api';
import type {ArtifactType} from './api';

type Connection = {id:string;name:string;base_url:string;has_token:boolean};
type Preview = {id:string;connection_id:string;cql:string;pages:{id:string;title:string;url:string}[];truncated:boolean;skipped:number};
type Item = {attachment_id?:string;parent_title?:string;scan?:boolean;attachment_count?:number;page_id:string;title:string;status:string;candidate_id:string|null;attempts:number;page_version?:number;error?:{code:string;message:string}|null};
type Job = {source_mode?:string;id:string;connection_id:string;created_at:string;cql:string;status:string;cancel_requested:boolean;items:Item[]};
const labels:Record<string,string>={queued:'В очереди',running:'Загружается',succeeded:'Готово к проверке',partial:'Есть ошибки',failed:'Ошибка',cancelled:'Отменено'};

export function Confluence({types,onReview,onError,onChanged,initialJobId}:{types:ArtifactType[];onReview:(id:string,jobId:string)=>void;initialJobId?:string;onError:(e:unknown)=>void;onChanged:()=>Promise<void>}){
  const [connections,setConnections]=useState<Connection[]>([]),[connectionId,setConnectionId]=useState('');
  const [name,setName]=useState('Confluence'),[baseUrl,setBaseUrl]=useState(''),[token,setToken]=useState('');
  const [showConnect,setShowConnect]=useState(false),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const [cql,setCql]=useState('type = page AND space = "ARCH"'),[preview,setPreview]=useState<Preview>(),[selected,setSelected]=useState<Set<string>>(new Set());
  const [typeId,setTypeId]=useState(types[0]?.id||''),[mode,setMode]=useState('table'),[tableIndex,setTableIndex]=useState('');
  const [sourceMode,setSourceMode]=useState('pages');
  const [pipelineId,setPipelineId]=useState('');
  const [jobs,setJobs]=useState<Job[]>([]),[activeJob,setActiveJob]=useState(initialJobId||'');
  const lastCandidates=useRef('');
  const changed=useRef(onChanged);
  changed.current=onChanged;
  const current=connections.find(c=>c.id===connectionId);
  const reloadConnections=async()=>{const list=await api<Connection[]>('/confluence/connections');setConnections(list);setConnectionId(id=>id||list[0]?.id||'');if(!list.length)setShowConnect(true);};
  const reloadJobs=async()=>{const list=await api<Job[]>('/confluence/jobs');setJobs(list);return list;};
  useEffect(()=>{void Promise.all([reloadConnections(),reloadJobs()]).catch(onError);},[]);
  useEffect(()=>{
    let alive=true;
    const timer=setInterval(()=>{void api<Job[]>('/confluence/jobs').then(async list=>{if(!alive)return;setJobs(list);const signature=list.flatMap(j=>j.items.map(i=>i.candidate_id||'')).join('|');if(signature!==lastCandidates.current){lastCandidates.current=signature;await changed.current();}}).catch(e=>{if(alive)onError(e);});},2000);
    return ()=>{alive=false;clearInterval(timer);};
  },[]);
  const execute=async(task:()=>Promise<void>)=>{setBusy(true);setNotice('');try{await task();}catch(e){onError(e);}finally{setBusy(false);}};
  const updateCql=(value:string)=>{setCql(value);setPreview(undefined);setSelected(new Set());};
  const job=jobs.find(j=>j.id===activeJob);
  return <>
    <div className="page-heading"><div><div className="eyebrow">Confluence Data Center · 7.13</div><h1>Страницы в реестр</h1><p>Найдите страницы по CQL, загрузите содержимое и проверьте предложения.</p></div><button onClick={()=>setShowConnect(v=>!v)}>{showConnect?'Скрыть подключение':'Настроить подключение'}</button></div>
    {notice&&<div className="success" role="status">{notice}</div>}
    {showConnect&&<section className="panel connection-panel"><h2>Подключение с Personal Access Token</h2><p className="muted">PAT хранится в Windows Credential Manager. Приложение только читает Confluence.</p>
      <form onSubmit={e=>{e.preventDefault();void execute(async()=>{const c=await api<Connection>('/confluence/connections',{method:'POST',body:JSON.stringify({name,base_url:baseUrl,token})});setToken('');await reloadConnections();setConnectionId(c.id);setPreview(undefined);setNotice('Подключение сохранено. Проверьте доступ.');setShowConnect(false);});}}>
        <div className="connection-fields"><label className="field">Название подключения<input value={name} required maxLength={120} onChange={e=>setName(e.target.value)}/></label><label className="field">Адрес Confluence<input type="url" placeholder="https://wiki.company.ru/confluence" value={baseUrl} required onChange={e=>setBaseUrl(e.target.value)}/><small>Базовый HTTPS-адрес, включая /confluence, если он есть. Без /rest/api.</small></label><label className="field">PAT<input type="password" autoComplete="off" value={token} required onChange={e=>setToken(e.target.value)}/></label></div>
        <button className="primary" disabled={busy} type="submit">Сохранить подключение</button>
      </form>
    </section>}
    <section className="panel"><div className="connection-toolbar"><label className="field">Подключение<select value={connectionId} disabled={busy} onChange={e=>{setConnectionId(e.target.value);setPreview(undefined);setSelected(new Set());setToken('');}}><option value="">Выберите подключение</option>{connections.map(c=><option key={c.id} value={c.id}>{c.name}{c.has_token?'':' · PAT не задан'}</option>)}</select></label><button disabled={!current||busy} onClick={()=>void execute(async()=>{const r=await api<{visible_pages:number}>(`/confluence/connections/${connectionId}/test`,{method:'POST'});setNotice(r.visible_pages?'Подключение работает: доступ к страницам подтверждён.':'REST API доступен, но видимых страниц не найдено.');})}>Проверить доступ</button></div>
      {current&&<details className="credential-settings"><summary>Обновить или удалить сохранённый PAT · {current.base_url}</summary><div className="connection-toolbar"><label className="field">Новый PAT<input type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)}/></label><button disabled={busy||!token} onClick={()=>void execute(async()=>{await api(`/confluence/connections/${connectionId}/token`,{method:'PUT',body:JSON.stringify({token})});setToken('');await reloadConnections();setNotice('PAT обновлён.');})}>Обновить PAT</button><button disabled={busy||!current.has_token} onClick={()=>void execute(async()=>{await api(`/confluence/connections/${connectionId}/token`,{method:'DELETE'});setToken('');await reloadConnections();setNotice('PAT удалён из Windows Credential Manager.');})}>Удалить PAT</button></div></details>}
      <form onSubmit={e=>{e.preventDefault();void execute(async()=>{const p=await api<Preview>('/confluence/previews',{method:'POST',body:JSON.stringify({connection_id:connectionId,cql,max_pages:500})});setPreview(p);setSelected(new Set(p.pages.map(p=>p.id)));});}}>
        <label className="field">CQL-запрос<textarea rows={3} value={cql} disabled={busy} onChange={e=>updateCql(e.target.value)}/><small>Например: type = page AND space = "ARCH" AND label = "adr". Запрос выбирает страницы; в режиме PPTX будут загружены их вложения.</small></label>
        <button className="primary" disabled={busy||!current?.has_token||!cql.trim()} type="submit">{busy?'Выполняется запрос…':'Найти страницы'}</button>
      </form>
    </section>
    {preview&&<section className="panel import-history"><div className="panel-heading"><h2>Найдено страниц: {preview.pages.length}</h2><span>Выбрано: {selected.size}</span></div>
      {preview.truncated&&<div className="notice">Показаны первые {preview.pages.length} страниц. Выборка неполная — сузьте CQL, чтобы обработать остальные.</div>}
      {preview.skipped>0&&<p className="muted">Пропущено результатов другого типа: {preview.skipped}.</p>}
      {preview.pages.length===0?<p>Нет доступных страниц по этому запросу. Проверьте CQL и права PAT.</p>:<>
        <div className="button-row"><button disabled={busy} onClick={()=>setSelected(new Set(preview.pages.map(p=>p.id)))}>Выбрать все</button><button disabled={busy} onClick={()=>setSelected(new Set())}>Снять выбор</button></div>
        <div className="page-selection"><table><thead><tr><th>Выбор</th><th>Страница</th><th>ID</th></tr></thead><tbody>{preview.pages.map(p=><tr key={p.id}><td><input className="page-check" type="checkbox" aria-label={'Выбрать '+p.title} checked={selected.has(p.id)} disabled={busy} onChange={e=>{const next=new Set(selected);if(e.target.checked)next.add(p.id);else next.delete(p.id);setSelected(next);}}/></td><td><a href={p.url} target="_blank" rel="noreferrer">{p.title}</a></td><td className="mono">{p.id}</td></tr>)}</tbody></table></div>
        <label className="field">Что загружать<select value={sourceMode} onChange={e=>setSourceMode(e.target.value)}><option value="pages">HTML страниц — один объект на страницу</option><option value="attachments">PPTX-вложения страниц — отдельный объект на презентацию</option></select><small>Новая версия вложения обновляет связанное решение после проверки. Привязка по ID вложения, а не по имени файла.</small></label><div className="connection-fields"><label className="field">Тип объектов<select value={typeId} onChange={e=>setTypeId(e.target.value)}>{types.map(t=><option key={t.id} value={t.id}>{t.name} · схема {t.version}</option>)}</select></label><label className="field">Способ извлечения<select value={mode} onChange={e=>setMode(e.target.value)}><option value="table">Таблица «реквизит — значение»</option><option value="sections">Разделы по заголовкам</option></select></label>{mode==='table'&&<label className="field">Номер таблицы (с 0)<input type="number" min={0} placeholder="Автоматически" value={tableIndex} onChange={e=>setTableIndex(e.target.value)}/></label>}</div>
        <PipelineSelect typeId={typeId} value={pipelineId} onChange={setPipelineId} onError={onError}/>
        <div className="save-bar"><button className="primary" disabled={busy||selected.size===0} onClick={()=>void execute(async()=>{const j=await api<Job>('/confluence/jobs',{method:'POST',body:JSON.stringify({source_mode:sourceMode,preview_id:preview.id,page_ids:[...selected],type_id:typeId,pipeline_id:pipelineId||null,mode,table_index:mode==='table'&&tableIndex!==''?Number(tableIndex):null})});setActiveJob(j.id);await reloadJobs();setNotice('Загрузка запущена. Объекты появятся в реестре только после проверки.');})}>Загрузить выбранные ({selected.size})</button><span className="muted">{sourceMode==='attachments'?'Каждый PPTX → отдельное решение; повторная загрузка → обновление':'Одна страница → одно предложение'}</span></div>
      </>}
    </section>}
    <section className="panel import-history"><div className="panel-heading"><h2>Загрузки Confluence</h2><button onClick={()=>void execute(async()=>{await reloadJobs();await onChanged();})}>Обновить</button></div>
      {!jobs.length&&<p className="muted">Здесь появятся прогресс и результат по каждой странице. Ошибка одной страницы не остановит остальные.</p>}
      {jobs.map(j=><div className="import-item" key={j.id}><div><strong>{connections.find(c=>c.id===j.connection_id)?.name||'Confluence'} · {stamp(j.created_at)}</strong><small>{j.source_mode==='attachments'?'PPTX · ':''}{j.items.filter(i=>i.status==='succeeded').length} / {j.items.length} этапов обработано · {j.cql}</small></div><span className="badge">{labels[j.status]}{j.cancel_requested&&j.status==='running'?' · отменяется':''}</span><button onClick={()=>setActiveJob(j.id)}>Результаты</button></div>)}
    </section>
    {job&&<section className="panel import-history"><div className="panel-heading"><h2>Результаты загрузки</h2><div className="button-row">{['running','queued'].includes(job.status)&&<button disabled={busy||job.cancel_requested} onClick={()=>void execute(async()=>{await api(`/confluence/jobs/${job.id}/cancel`,{method:'POST'});await reloadJobs();})}>Отменить загрузку</button>}{!['running','queued'].includes(job.status)&&job.items.some(i=>i.status==='failed')&&<button disabled={busy} onClick={()=>void execute(async()=>{const j=await api<Job>(`/confluence/jobs/${job.id}/retry`,{method:'POST'});setActiveJob(j.id);await reloadJobs();})}>Повторить ошибки</button>}</div></div>
      <p className="muted">«Готово к проверке» означает, что предложение сохранено. Его принятие выполняется в отдельном экране.</p>
      {job.items.map(i=><div className="import-item" key={i.attachment_id||i.page_id}><div><strong>{i.title}</strong><small>{i.attachment_id?`Вложение ${i.attachment_id} · ${i.parent_title||''} · страница `:'ID '}{i.page_id}{i.page_version?' · версия '+i.page_version:''} · {i.scan?`Страница проверена · PPTX: ${i.attachment_count}`:labels[i.status]}</small>{i.error&&<p className="item-error">{i.error.message}</p>}</div>{i.candidate_id&&<button className="primary" onClick={()=>{void onChanged().then(()=>onReview(i.candidate_id!,job.id)).catch(onError);}}>Проверить предложение</button>}</div>)}
    </section>}
  </>;
}

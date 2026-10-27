import {useEffect,useState} from 'react';
import {api} from './api';
import type {Artifact,ArtifactType,Candidate} from './api';
import {PipelineSelect} from './PipelineSelect';

type Attachment={title:string;version:number;attachment_id:string;parent_page_id:string;url:string};
export function Pptx({types,artifacts,onError,onReview,onChanged}:{types:ArtifactType[];artifacts:Artifact[];onError:(e:unknown)=>void;onReview:(id:string)=>void;onChanged:()=>Promise<void>}){
  const [connections,setConnections]=useState<{id:string;name:string}[]>([]),[connection,setConnection]=useState(''),[link,setLink]=useState('');
  const [typeId,setTypeId]=useState(types[0]?.id||''),[pipeline,setPipeline]=useState(''),[mode,setMode]=useState('table'),[table,setTable]=useState('');
  const [target,setTarget]=useState(''),[standalone,setStandalone]=useState(false),[metadata,setMetadata]=useState<Attachment>(),[busy,setBusy]=useState(false);
  useEffect(()=>{void api<{id:string;name:string}[]>('/confluence/connections').then(c=>{setConnections(c);setConnection(c[0]?.id||'');}).catch(onError);},[]);
  const execute=async(f:()=>Promise<void>)=>{setBusy(true);try{await f();}catch(e){onError(e);}finally{setBusy(false);}};
  return <><div className="page-heading"><div><div className="eyebrow">Презентация как основание решения</div><h1>PPTX из Confluence</h1><p>Вставьте ссылку на вложение. Слайды и таблицы станут предложениями с цитатами.</p></div></div><div className="import-grid"><section className="panel"><fieldset className="plain-fieldset" disabled={busy}>
    <label className="field">Подключение<select value={connection} onChange={e=>{setConnection(e.target.value);setMetadata(undefined);}}><option value="">Выберите подключение</option>{connections.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
    {!connections.length&&<p className="notice">Сначала настройте PAT в разделе Confluence.</p>}
    <label className="field">Ссылка на PPTX<input type="url" placeholder="https://wiki.company.ru/download/attachments/…" value={link} onChange={e=>{setLink(e.target.value);setMetadata(undefined);}}/><small>Поддерживаются download/attachments и ссылки с параметром preview.</small></label>
    <button disabled={!connection||!link} onClick={()=>void execute(async()=>{setMetadata(await api<Attachment>('/pptx/resolve',{method:'POST',body:JSON.stringify({connection_id:connection,link})}));})}>Проверить вложение</button>
    {metadata&&<div className="notice"><strong>{metadata.title}</strong><p>Версия {metadata.version} · вложение {metadata.attachment_id}</p><a href={metadata.url} target="_blank" rel="noreferrer">Родительская страница {metadata.parent_page_id} ↗</a></div>}
    <label className="field">Тип объекта<select value={typeId} onChange={e=>{setTypeId(e.target.value);setTarget('');}}>{types.map(t=><option key={t.id} value={t.id}>{t.name} · схема {t.version}</option>)}</select></label>
    <PipelineSelect typeId={typeId} value={pipeline} onChange={setPipeline} onError={onError}/>
    {!pipeline&&<><label className="field">Способ извлечения<select value={mode} onChange={e=>setMode(e.target.value)}><option value="table">Таблица «реквизит — значение»</option><option value="sections">Разделы по заголовкам слайдов</option></select></label>{mode==='table'&&<label className="field">Номер таблицы (с 0)<input type="number" min={0} placeholder="Автоматически" value={table} onChange={e=>setTable(e.target.value)}/></label>}</>}
    <label className="field">Объект для дополнения<select value={target} onChange={e=>{setTarget(e.target.value);setStandalone(false);}}><option value="">Автоматически: объект родительской страницы</option>{artifacts.filter(a=>a.type_id===typeId).map(a=><option key={a.id} value={a.id}>{String(a.fields.title||'Без названия')}</option>)}</select></label>
    {!target&&<label className="check-line"><input type="checkbox" checked={standalone} onChange={e=>setStandalone(e.target.checked)}/>Создать отдельный объект для вложения после проверки</label>}
    <div className="save-bar"><button className="primary" disabled={!metadata} onClick={()=>void execute(async()=>{const c=await api<Candidate>('/pptx/attachments',{method:'POST',body:JSON.stringify({connection_id:connection,link,type_id:typeId,pipeline_id:pipeline||null,mode,table_index:mode==='table'&&table!==''?Number(table):null,target_id:target||null,standalone,expected_version:metadata!.version})});await onChanged();onReview(c.id);})}>{busy?'Загружаем и разбираем…':'Загрузить и проверить предложения'}</button></div>
    </fieldset></section><section className="panel"><h2>Что будет перенесено</h2><p>Текстовые блоки, таблицы и текст внутри групп. Каждая цитата содержит номер слайда и фигуры.</p><p>По умолчанию презентация дополняет объект страницы. Текущие реквизиты сохраняются, пока вы не примените предложения в форме проверки.</p><p className="muted">До 25 MiB и 300 слайдов. Изображения и SmartArt не распознаются. Порядок текста соответствует структуре файла и может отличаться от визуального.</p><p>Локальный PPTX загрузите в разделе «Загрузка файлов».</p></section></div></>;
}

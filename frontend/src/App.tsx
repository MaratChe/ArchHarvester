import {useEffect, useState} from 'react';
import {api, init, display, stamp} from './api';
import type {Artifact, ArtifactType, Candidate, Fields, Snapshot} from './api';
import {FieldsForm} from './FieldsForm';
import {Review} from './Review';
import {Confluence} from './Confluence';
import {Pipelines} from './Pipelines';
import {PipelineSelect} from './PipelineSelect';
import {Pptx} from './Pptx';
import {Models} from './Models';
import {Types} from './Types';

type Page = 'registry'|'imports'|'types'|'confluence'|'pipelines'|'pptx'|'models';
export default function App(){
  const [ready,setReady]=useState(false),[page,setPage]=useState<Page>('registry');
  const [types,setTypes]=useState<ArtifactType[]>([]),[items,setItems]=useState<Artifact[]>([]),[candidates,setCandidates]=useState<Candidate[]>([]);
  const [allItems,setAllItems]=useState<Artifact[]>([]);
  const [pipelineId,setPipelineId]=useState('');
  const [searching,setSearching]=useState(false),[searchMode,setSearchMode]=useState('keyword'),[searchNotice,setSearchNotice]=useState('');
  const [searchEndpoint,setSearchEndpoint]=useState('');
  useEffect(()=>{if(ready&&page==='registry'&&searchMode==='hybrid')void api<{index?:{base_url?:string}|null}>('/search/index').then(s=>setSearchEndpoint(s.index?(s.index.base_url||'http://127.0.0.1:11434'):'Индекс ещё не создан')).catch(fail);},[ready,page,searchMode]);
  const [error,setError]=useState(''),[message,setMessage]=useState(''),[dataDir,setDataDir]=useState('');
  const [editing,setEditing]=useState<Artifact|null>(),[values,setValues]=useState<Fields>({}),[typeId,setTypeId]=useState('');
  const [reviewId,setReviewId]=useState(''),[query,setQuery]=useState(''),[status,setStatus]=useState(''),[busy,setBusy]=useState(false);
  const [history,setHistory]=useState<Artifact[]>([]),[evidence,setEvidence]=useState<{snapshot:Snapshot;blocks:string[]}>();
  const fail=(e:unknown)=>{setError(e instanceof Error?e.message:String(e));setMessage('');};
  const refresh=async()=>{const [t,a,c]=await Promise.all([api<ArtifactType[]>('/types'),api<Artifact[]>('/artifacts'),api<Candidate[]>('/candidates')]);setTypes(t);setItems(a);setAllItems(a);setCandidates(c);setTypeId(id=>id||t[0].id);};
  useEffect(()=>{void init().then(async s=>{setDataDir(s.data_dir);await refresh();setReady(true);}).catch(fail);},[]);
  const navigate=(p:Page)=>{setPage(p);setEditing(undefined);setReviewId('');setError('');setMessage('');setHistory([]);setItems(allItems);setQuery('');setStatus('');setSearchNotice('');};
  const open=async(id:string)=>{const a=await api<Artifact>(`/artifacts/${id}`);setEditing(a);setValues(a.fields);setTypeId(a.type_id);setHistory(await api<Artifact[]>(`/artifacts/${id}/revisions`));setError('');};
  const newObject=()=>{setEditing(null);setValues({});setHistory([]);setTypeId(types[0].id);setError('');};
  const currentType=types.find(t=>t.id===typeId);
  async function save(nextStatus:string){
    setBusy(true);setError('');
    try{const saved=await api<Artifact>(editing?`/artifacts/${editing.id}`:'/artifacts',{method:editing?'PUT':'POST',body:JSON.stringify(editing?{fields:values,status:nextStatus,expected_revision:editing.revision}:{fields:values,status:nextStatus,type_id:typeId})});await refresh();await open(saved.id);setMessage(nextStatus==='published'?'Объект опубликован':'Черновик сохранён');}catch(e){fail(e);}finally{setBusy(false);}
  }
  const [file,setFile]=useState<File>(),[mode,setMode]=useState('table'),[table,setTable]=useState(''),[target,setTarget]=useState(''),[resource,setResource]=useState('');
  async function upload(e:React.FormEvent){e.preventDefault();if(!file)return;setBusy(true);setError('');
    const f=new FormData();f.append('file',file);f.append('type_id',typeId);f.append('mode',mode);if(table!==''&&mode==='table')f.append('table_index',table);if(target)f.append('target_id',target);if(resource)f.append('resource_id',resource);
    if(pipelineId)f.append('pipeline_id',pipelineId);
    try{const c=await api<Candidate>(file.name.toLowerCase().endsWith('.pptx')?'/pptx/uploads':'/uploads',{method:'POST',body:f});await refresh();setReviewId(c.id);}catch(e){fail(e);}finally{setBusy(false);}
  }
  const pending=candidates.filter(c=>c.status==='pending').length;
  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">A<span>↗</span></span><div>Архитектурный<br/><strong>реестр</strong></div></div><div className="workspace-label">Личное рабочее пространство</div>
      <nav aria-label="Основная навигация">{([['registry','Реестр объектов','▦'],['imports','Загрузка файлов','⇥'],['confluence','Confluence','↗'],['pptx','PPTX из Confluence','▤'],['pipelines','Пайплайны','≡'],['models','Модели и API','◎'],['types','Типы объектов','◇']] as const).map(([p,label,icon])=><button className={page===p?'nav active':'nav'} key={p} onClick={()=>navigate(p)}><span>{icon}</span>{label}{p==='imports'&&pending>0&&<b>{pending}</b>}</button>)}</nav>
      <div className="sidebar-bottom"><span className="local-dot"/> Локально на компьютере<p>Реестр хранится локально.<br/>Сервер модели выбираете вы.</p><small>Версия 0.6 · конструктор типов</small></div>
    </aside>
    <main><header className="topbar"><span>Architecture Registry Studio</span><span className="muted">Объектов: {allItems.length} · на проверке: {pending}</span></header>
      <div className="content">{error&&<div className="error" role="alert"><strong>Не удалось выполнить действие</strong><pre>{error}</pre><button onClick={()=>setError('')}>Закрыть сообщение</button></div>}{message&&<div className="success" role="status">{message}</div>}
      {!ready?<p role="status">Подключаем локальный реестр…</p>:reviewId?<Review id={reviewId} types={types} onError={fail} onDone={async a=>{setReviewId('');await refresh();if(a){setPage('registry');await open(a.id);setMessage('Результат проверки сохранён');}}}/>:
      page==='models'?<Models types={types} onError={fail} onReview={setReviewId} onChanged={refresh}/>:page==='pptx'?<Pptx types={types} artifacts={allItems} onReview={setReviewId} onError={fail} onChanged={refresh}/>:page==='pipelines'?<Pipelines types={types} onReview={setReviewId} onError={fail} onChanged={refresh}/>:page==='confluence'?<Confluence types={types} onReview={setReviewId} onError={fail} onChanged={refresh}/>:page==='registry'?<>
        <div className="page-heading"><div><div className="eyebrow">Архитектурные решения</div><h1>{editing!==undefined?(editing?'Карточка объекта':'Новый объект'):'Реестр объектов'}</h1><p>{editing!==undefined?'Реквизиты, история и основания решения.':'Собирайте решения. Сохраняйте основания. Проверяйте изменения.'}</p></div><div className="button-row">{editing!==undefined?<button onClick={()=>setEditing(undefined)}>К реестру</button>:<><a className="button" href="/api/export">Экспорт JSON</a><button className="primary" onClick={newObject}>+ Создать объект</button></>}</div></div>
        {editing!==undefined&&currentType?<div className="editor-grid"><section className="panel"><div className="panel-heading"><h2>{editing?'Реквизиты':'Ручное создание'}</h2>{editing&&<span className={'badge '+editing.status}>{editing.status==='published'?'Опубликован':'Черновик'} · v{editing.revision}</span>}</div>
          <label className="field">Тип объекта<select disabled={!!editing||busy} value={typeId} onChange={e=>{setTypeId(e.target.value);setValues({});}}>{types.map(t=><option key={t.id} value={t.id}>{t.name} · схема {t.version}</option>)}</select></label>
          <FieldsForm type={currentType} values={values} onChange={setValues} disabled={busy}/><div className="save-bar"><button className="primary" disabled={busy} onClick={()=>void save('published')}>Опубликовать</button><button disabled={busy} onClick={()=>void save('draft')}>Сохранить черновик</button></div>
        </section><aside className="detail-side"><section className="panel"><h2>Основания</h2>{!editing?.sources?.length?<p className="muted">Объект можно создать полностью вручную. Файл-основание добавляется позже.</p>:editing.sources.map(s=><p key={s.id}>{s.url?<a href={s.url} target="_blank" rel="noreferrer">{s.name}</a>:s.name}<button className="link-button" onClick={()=>{if(s.kind==='confluence_page'){navigate('confluence');return;}if(s.kind==='confluence_attachment'){navigate('pptx');return;}setTarget(editing.id);setResource(s.id);setTypeId(editing.type_id);navigate('imports');}}>Загрузить новую версию</button></p>)}{editing&&<button onClick={()=>{setTarget(editing.id);setResource('');setTypeId(editing.type_id);navigate('imports');}}>Прикрепить файл</button>}
          {editing&&Object.entries(editing.provenance).map(([k,p])=><div className="origin" key={k}><span>{currentType.schema.properties[k]?.title||k}</span><small>{p.method==='manual'?'Ручной ввод':'Из источника'}</small>{p.evidence?.length&&<button className="link-button" onClick={async()=>{try{setEvidence({snapshot:await api<Snapshot>(`/snapshots/${p.evidence![0].snapshot_id}`),blocks:p.evidence!.map(e=>e.block_id)});}catch(e){fail(e);}}}>Проверить источник ↗</button>}</div>)}
        </section><section className="panel"><h2>История ревизий</h2>{history.length?history.map(a=><details key={a.revision}><summary>Ревизия {a.revision} · {stamp(a.updated_at)}</summary>{Object.entries(a.fields).map(([k,v])=><p key={k}><strong>{currentType.schema.properties[k]?.title||k}</strong><br/>{display(v)}</p>)}</details>):<p className="muted">Появится после первого сохранения.</p>}</section></aside></div>:<>
          <form className="toolbar" onSubmit={async e=>{e.preventDefault();setSearching(true);try{setSearchNotice('');if(searchMode==='hybrid'){const r=await api<{items:Artifact[];warning:string|null}>(`/search?q=${encodeURIComponent(query)}&status=${status}`);setItems(r.items);setSearchNotice(r.warning||'Результаты по смыслу и словам. Устаревшие векторы исключены; индекс обновляется в разделе «Модели и API».');}else setItems(await api<Artifact[]>(`/artifacts?q=${encodeURIComponent(query)}&status=${status}`));}catch(err){fail(err);}finally{setSearching(false);}}}><input aria-label="Поиск по реестру" placeholder="Найти по названию, реквизитам или UUID…" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="Статус" value={status} onChange={e=>setStatus(e.target.value)}><option value="">Все статусы</option><option value="published">Опубликованные</option><option value="draft">Черновики</option></select><select aria-label="Режим поиска" value={searchMode} onChange={e=>setSearchMode(e.target.value)}><option value="keyword">По словам</option><option value="hybrid">По смыслу и словам</option></select><button type="submit" disabled={searching}>{searching?'Ищем…':'Найти'}</button></form>{searchMode==='hybrid'&&<p className="muted provider-address">Поисковый запрос получает сервер активного индекса: {searchEndpoint||'проверяем…'}.</p>}{searchNotice&&<p className="notice" role="status">{searchNotice}</p>}
          {items.length?<div className="registry-table"><table><thead><tr><th>Объект / название</th><th>Тип</th><th>Статус</th><th>Изменён</th></tr></thead><tbody>{items.map(a=><tr key={a.id}><td><button className="object-link" onClick={()=>void open(a.id).catch(fail)}>{String(a.fields.title||'Без названия')}</button><small className="mono">{a.id.slice(0,8)} · ревизия {a.revision}</small>{a.search_match&&<p className="search-snippet">{a.search_match.slice(0,300)}</p>}</td><td>{types.find(t=>t.id===a.type_id)?.name}</td><td><span className={'badge '+a.status}>{a.status==='published'?'Опубликован':'Черновик'}</span></td><td>{stamp(a.updated_at)}</td></tr>)}</tbody></table></div>:<div className="empty"><div className="empty-symbol">▦</div><h2>{query?'Совпадений нет':'Первое решение начинается здесь'}</h2><p>{query?'Попробуйте другое слово или снимите фильтр.':'Создайте объект вручную или перенесите реквизиты из HTML-документа.'}</p><div className="button-row"><button className="primary" onClick={newObject}>Создать объект</button><button onClick={()=>navigate('imports')}>Загрузить HTML</button></div></div>}
        </>}
      </>:page==='imports'?<>
        <div className="page-heading"><div><div className="eyebrow">Документ → предложение → объект</div><h1>Загрузка файлов</h1><p>Проверьте извлечённые значения перед сохранением в реестр.</p></div></div>
        <div className="import-grid"><form className="panel" onSubmit={upload}><h2>Новый документ</h2><label className="upload-zone"><strong>{file?file.name:'Выберите HTML или PPTX'}</strong><span>.html, .htm · до 5 MiB / .pptx · до 25 MiB</span><input aria-label="Файл HTML или PPTX" type="file" accept=".html,.htm,.pptx" required onChange={e=>setFile(e.target.files?.[0])}/></label>
          <label className="field">Тип объекта<select value={typeId} disabled={!!target} onChange={e=>setTypeId(e.target.value)}>{types.map(t=><option key={t.id} value={t.id}>{t.name} · схема {t.version}</option>)}</select></label>
          <PipelineSelect typeId={typeId} value={pipelineId} onChange={setPipelineId} onError={fail}/>
          <label className="field">Способ извлечения<select value={mode} onChange={e=>setMode(e.target.value)}><option value="table">Таблица «реквизит — значение»</option><option value="sections">Разделы по заголовкам</option></select></label>
          {mode==='table'&&<label className="field">Номер таблицы (необязательно)<input type="number" min="0" placeholder="Автоматически по названиям реквизитов" value={table} onChange={e=>setTable(e.target.value)}/><small>Нумерация с 0. При неоднозначности приложение попросит выбрать таблицу.</small></label>}
          <label className="field">Связать с объектом<select value={target} onChange={e=>{setTarget(e.target.value);setResource('');const a=allItems.find(a=>a.id===e.target.value);if(a)setTypeId(a.type_id);}}><option value="">Создать новый после проверки</option>{allItems.map(a=><option key={a.id} value={a.id}>{String(a.fields.title||'Без названия')} · {a.id.slice(0,8)}</option>)}</select></label>
          {resource&&<div className="notice">Загрузка новой версии существующего основания. Ручные исправления сохранятся.</div>}
          <button className="primary" type="submit" disabled={busy||!file}>{busy?'Обрабатываем документ…':'Извлечь реквизиты'}</button>
        </form><section className="panel"><h2>Как подготовить документ</h2><p>Для таблицы: в левом столбце название реквизита, в правом — его значение.</p><div className="example-table"><div>Название</div><div>Гарантированная доставка</div><div>Проблематика</div><div>Сообщения теряются при сбоях</div><div>Владелец</div><div>Команда интеграции</div></div><p>Для разделов используйте заголовки HTML. Текст «Проблематики» извлекается до заголовка «Задачи проекта».</p><p className="muted">Сложные строки с объединёнными ячейками или вложенными таблицами пропускаются с предупреждением.</p></section></div>
        <section className="panel import-history"><div className="panel-heading"><h2>История загрузок</h2><span>{pending} ожидают проверки</span></div>{candidates.length?candidates.map(c=><div className="import-item" key={c.id}><div><strong>{c.source_name}</strong><small>{Object.keys(c.proposals).length} полей · {c.warnings.length} предупреждений</small></div><span className="badge">{({pending:'На проверке',accepted:'Принято',rejected:'Отклонено',superseded:'Заменено'} as Record<string,string>)[c.status]}</span><button onClick={()=>setReviewId(c.id)}>Открыть</button></div>):<p className="muted">Загруженные документы появятся здесь. Можно закрыть приложение и вернуться к проверке позже.</p>}</section>
      </>:<>
        <Types types={types} onChanged={refresh}/>
        <p className="muted data-path">Данные: {dataDir}</p>
      </>}
      </div>
    </main>
    {evidence&&<div className="modal-backdrop" onClick={()=>setEvidence(undefined)}><section className="modal panel" role="dialog" aria-modal="true" aria-label="Источник значения" onClick={e=>e.stopPropagation()}><div className="panel-heading"><h2>{evidence.snapshot.filename}</h2><button autoFocus onClick={()=>setEvidence(undefined)}>Закрыть</button></div>{evidence.snapshot.document.blocks.filter(b=>evidence.blocks.includes(b.id)).map(b=><blockquote key={b.id}>{b.text}<small>{b.slide_index?`Слайд ${b.slide_index} · фигура ${b.shape_id}`:b.html_path}</small></blockquote>)}<a href={`/api/snapshots/${evidence.snapshot.id}/download`}>Скачать исходный файл</a></section></div>}
  </div>;
}

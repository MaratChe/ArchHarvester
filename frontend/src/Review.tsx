import {useEffect, useState} from 'react';
import {api, display} from './api';
import type {Artifact, ArtifactType, Candidate, Fields, Snapshot} from './api';
import {FieldsForm} from './FieldsForm';

export function Review({id,types,onDone,onError}:{id:string;types:ArtifactType[];onDone:(artifact?:Artifact)=>void;onError:(e:unknown)=>void}) {
  const [candidate,setCandidate]=useState<Candidate>();
  const [snapshot,setSnapshot]=useState<Snapshot>();
  const [values,setValues]=useState<Fields>({});
  const [selected,setSelected]=useState<string[]>([]);
  const [busy,setBusy]=useState(false);
  const load = async () => {
    const c = await api<Candidate>(`/candidates/${id}`);
    setCandidate(c);
    // On updates, retain current values until user explicitly chooses proposals.
    setValues(c.target_id ? {...c.current_fields} : Object.fromEntries(Object.entries(c.proposals).map(([k,p])=>[k,p.value])));
    setSnapshot(await api<Snapshot>(`/snapshots/${c.snapshot_id}`));
  };
  useEffect(()=>{void load().catch(onError);},[id]);
  if (!candidate || !snapshot) return <p role="status">Загружаем предложение…</p>;
  const type = types.find(t=>t.id===candidate.type_id)!;
  const stale = candidate.latest_revision!==undefined && candidate.latest_revision!==candidate.base_revision;
  const pending = candidate.status==='pending';
  async function save(status:string) {
    setBusy(true);
    try {onDone(await api<Artifact>(`/candidates/${id}/review`,{method:'POST',body:JSON.stringify({expected_revision:candidate!.base_revision,fields:values,status})}));}
    catch(e){onError(e);} finally {setBusy(false);}
  }
  const reveal = (ids:string[]) => {setSelected(ids);document.getElementById('source-'+ids[0])?.scrollIntoView({behavior:'smooth',block:'center'});};
  return <>
    <div className="page-heading"><div><div className="eyebrow">Проверка переноса</div><h1>{candidate.target_id?'Обновление объекта':snapshot.document.format==='pptx'?'Новый объект из PPTX':snapshot.source_metadata?'Новый объект из Confluence':'Новый объект из HTML'}</h1><p>{candidate.source_name} · {type.name}</p></div><button onClick={()=>onDone()}>К списку</button></div>
    {candidate.warnings.length>0 && <div className="notice">{candidate.warnings.map((w,i)=><p key={i}>{w}</p>)}</div>}
    {!pending && <div className="notice">Предложение уже обработано: {({accepted:'принято',rejected:'отклонено',superseded:'заменено новой загрузкой'} as Record<string,string>)[candidate.status]}.</div>}
    {stale && pending && <div className="notice">Объект изменился после загрузки. <button onClick={async()=>{try{await api(`/candidates/${id}/rebase`,{method:'POST'});await load();}catch(e){onError(e);}}}>Обновить сравнение</button><p>Несохранённые правки формы будут заменены актуальными значениями.</p></div>}
    <div className="review-grid">
      <section className="panel source-panel"><div className="panel-heading"><h2>Основание</h2><a href={`/api/snapshots/${snapshot.id}/download`}>{snapshot.document.format==='pptx'?'Скачать PPTX':snapshot.source_metadata?'Скачать Storage XML':'Скачать HTML'}</a></div><p className="muted">Текст сохранённого снимка. Активное содержимое не выполняется.</p>{snapshot.source_metadata&&<p><a href={snapshot.source_metadata.url} target="_blank" rel="noreferrer">Открыть страницу Confluence ↗</a><br/><small>Снимок версии {snapshot.source_metadata.version??snapshot.source_metadata.page_version} · ID {snapshot.source_metadata.attachment_id??snapshot.source_metadata.page_id}. Ссылка открывает текущую страницу.</small></p>}
        <div className="source-document">{snapshot.document.blocks.map(b=><div id={'source-'+b.id} key={b.id} className={`source-block ${b.kind} ${selected.includes(b.id)?'highlight':''}`}><span className="anchor">{b.id}</span><div>{b.slide_index&&<small className="slide-coordinate">Слайд {b.slide_index} · фигура {b.shape_id}</small>}{b.text}</div></div>)}</div>
      </section>
      <section className="panel"><div className="panel-heading"><h2>Реквизиты объекта</h2><span className="badge">{candidate.target_id?'Ревизия '+candidate.base_revision:'Проверка перед созданием'}</span></div>
        {candidate.target_id && <p className="muted">В форме сохранены текущие значения. Применяйте новые предложения по одному.</p>}
        <div className="proposal-list">{Object.entries(candidate.proposals).map(([k,p])=><div className="proposal" key={k}>
          <div className="proposal-title"><strong>{type.schema.properties[k]?.title||k}</strong><button className="link-button" onClick={()=>reveal(p.evidence.map(e=>e.block_id))}>Показать источник ↗</button></div>
          {candidate.target_id && <><small>Прошлый импорт: {display(candidate.baseline[k])}</small><small>Сейчас: {display(candidate.current_fields[k])}</small></>}
          <p>{display(p.value)}</p>{p.method.startsWith('llm_')&&<small>{p.method==='llm_transform'?'LLM · пересказ/преобразование: проверьте смысл':'LLM · буквальное извлечение'}</small>}{p.model_metadata&&<details><summary>Модель: {p.model_metadata.model}</summary><small>Провайдер: {p.model_metadata.provider_name||'Локальная Ollama'} · {p.model_metadata.base_url}<br/>{p.model_metadata.identity_kind==='configuration'?'Конфигурация (не hash весов)':'Версия весов'}: {p.model_metadata.model_digest}<br/>Модель в ответе: {p.model_metadata.resolved_model||p.model_metadata.model}<br/>Prompt hash: {p.model_metadata.prompt_hash}<br/>Время: {p.model_metadata.duration_seconds} с</small><a href={`/api/llm/runs/${p.model_metadata.run_id}/raw`} target="_blank" rel="noreferrer">Сырой ответ модели (7 дней)</a></details>}<div className="button-row"><button disabled={!pending||busy||stale} onClick={()=>setValues({...values,[k]:p.value})}>Применить предложение</button>
          <button disabled={!pending||busy||stale} onClick={()=>{const next={...values};if(k in candidate.current_fields)next[k]=candidate.current_fields[k];else delete next[k];setValues(next);}}> {candidate.target_id?'Оставить текущее':'Не переносить'}</button></div>
        </div>)}</div>
        <FieldsForm type={type} values={values} onChange={setValues} disabled={!pending||busy||stale}/>
        {pending && <div className="save-bar"><button className="primary" disabled={busy||stale} onClick={()=>void save('published')}>Подтвердить и опубликовать</button><button disabled={busy||stale} onClick={()=>void save('draft')}>Сохранить черновик</button><button className="danger" disabled={busy} onClick={async()=>{setBusy(true);try{await api(`/candidates/${id}/reject`,{method:'POST'});onDone();}catch(e){onError(e);}finally{setBusy(false);}}}>Отклонить</button></div>}
      </section>
    </div>
  </>;
}

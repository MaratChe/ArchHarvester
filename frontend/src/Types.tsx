import {useState} from 'react';
import {api} from './api';
import type {ArtifactType,FieldSpec} from './api';
import './types.css';

type Schema=ArtifactType['schema'] & {description?:string;[key:string]:unknown};
type Spec=FieldSpec & {items?:{type:string};[key:string]:unknown};
type Row={lockedTitle?:boolean;id:string;key:string;spec:Spec;required:boolean};
const pattern=/^[a-z][a-z0-9_]{0,63}$/;
const initial:Schema={type:'object',additionalProperties:false,required:['title'],properties:{title:{type:'string',title:'Название',minLength:1} as Spec}};
const kinds=[['string','Текст'],['number','Число'],['integer','Целое число'],['boolean','Да / нет'],['date','Дата'],['array','Список строк'],['enum','Выбор из списка']];
const rowsFrom=(s:Schema):Row[]=>Object.entries(s.properties).map(([key,spec])=>({lockedTitle:key==='title',id:crypto.randomUUID(),key,spec:structuredClone(spec),required:s.required?.includes(key)||false}));
const kindOf=(s:Spec)=>s.type==='string'&&s.enum?'enum':s.format==='date'?'date':s.type;

function parseSchema(text:string):Schema{
  const s=JSON.parse(text);
  if(!s||s.type!=='object'||s.additionalProperties!==false||!s.properties||typeof s.properties!=='object'||Array.isArray(s.properties))throw Error('Нужен объект JSON Schema с properties и additionalProperties=false.');
  if(s.description!==undefined&&typeof s.description!=='string')throw Error('Описание типа должно быть строкой.');
  if(s.required!==undefined&&(!Array.isArray(s.required)||!s.required.every((k:unknown)=>typeof k==='string'&&Object.hasOwn(s.properties,k))))throw Error('required должен содержать ключи существующих реквизитов.');
  const entries=Object.entries(s.properties);
  if(entries.length<1||entries.length>40)throw Error('В типе должно быть от 1 до 40 реквизитов.');
  for(const [key,value] of entries){
    const p=value as Spec;
    if(!pattern.test(key)||!p||typeof p!=='object'||Array.isArray(p)||!['string','number','integer','boolean','array'].includes(p.type))throw Error(`Проверьте ключ и вид реквизита «${key}».`);
    if((p.title!==undefined&&typeof p.title!=='string')||(p.description!==undefined&&typeof p.description!=='string'))throw Error(`Название и описание «${key}» должны быть строками.`);
    if(p.type==='array'&&(!p.items||p.items.type!=='string'))throw Error('Поддерживаются только списки строк.');
    if(p.format!==undefined&&(p.type!=='string'||p.format!=='date'))throw Error('Поддерживается только формат даты для строки.');
    if(p.enum!==undefined&&(!Array.isArray(p.enum)||!p.enum.length||p.enum.some(v=>!['string','number','boolean'].includes(typeof v))))throw Error(`Проверьте варианты «${key}».`);
  }
  return s;
}

function TypeEditor({source,types,onCancel,onSaved}:{source:ArtifactType|null;types:ArtifactType[];onCancel:()=>void;onSaved:()=>Promise<void>}){
  const [name,setName]=useState(source?.name||''),[key,setKey]=useState(source?.type_key||'');
  const [base,setBase]=useState<Schema>(structuredClone(source?.schema||initial));
  const [rows,setRows]=useState<Row[]>(()=>rowsFrom(source?.schema||initial));
  const [description,setDescription]=useState((source?.schema as Schema)?.description||'');
  const [json,setJson]=useState(''),[mode,setMode]=useState<'builder'|'json'>('builder'),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const update=(id:string,patch:Partial<Row>)=>setRows(current=>current.map(r=>r.id===id?{...r,...patch}:r));
  const spec=(r:Row,patch:Partial<Spec>)=>update(r.id,{spec:{...r.spec,...patch}});
  const build=():Schema=>{
    if(!rows.length||rows.length>40)throw Error('Добавьте от 1 до 40 реквизитов.');
    const seen=new Set<string>();
    for(const row of rows){
      if(!pattern.test(row.key))throw Error('Ключ реквизита: латинские строчные буквы, цифры и _, начиная с буквы, до 64 символов.');
      if(seen.has(row.key))throw Error(`Повторяется ключ реквизита: ${row.key}`);
      seen.add(row.key);
      if(row.spec.enum&&(!row.spec.enum.length||new Set(row.spec.enum).size!==row.spec.enum.length||row.spec.enum.some(v=>typeof v==='string'&&!v.trim())))throw Error(`Укажите непустые уникальные варианты для «${row.spec.title||row.key}».`);
    }
    return {...base,description,properties:Object.fromEntries(rows.map(r=>[r.key,r.spec])),required:rows.filter(r=>r.required).map(r=>r.key)};
  };
  const switchMode=()=>{setError('');try{
    if(mode==='builder'){setJson(JSON.stringify(build(),null,2));setMode('json');}
    else{const s=parseSchema(json);setBase(s);setRows(rowsFrom(s));setDescription(s.description||'');setMode('builder');}
  }catch(e){setError(e instanceof Error?e.message:String(e));}};
  const save=async()=>{setError('');setBusy(true);try{
    if(!name.trim())throw Error('Введите название типа.');
    if(!pattern.test(key))throw Error('Ключ типа: латинские строчные буквы, цифры и _, начиная с буквы, до 64 символов.');
    if(!source&&types.some(t=>t.type_key===key))throw Error('Такой ключ типа уже существует. Укажите другой или создайте следующую версию.');
    const schema=mode==='builder'?build():parseSchema(json);
    if(schema.properties.title?.type!=='string'||!schema.required?.includes('title'))throw Error('Добавьте обязательный строковый реквизит title — название объекта.');
    await api('/types',{method:'POST',body:JSON.stringify({type_key:key,name:name.trim(),schema,create_new:!source})});
    await onSaved();
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}};
  return <section className="panel type-editor"><div className="panel-heading"><h2>{source?`Новая версия · ${source.name}`:'Новый тип объектов'}</h2><button disabled={busy} onClick={onCancel}>Отмена</button></div>
    {error&&<p className="error" role="alert">{error}</p>}<fieldset className="plain-fieldset" disabled={busy}>
      <div className="type-meta"><label className="field">Название типа<input value={name} maxLength={120} onChange={e=>setName(e.target.value)} placeholder="Информационная система"/></label><label className="field">Ключ типа<input value={key} disabled={!!source} maxLength={64} onChange={e=>setKey(e.target.value)} placeholder="information_system"/><small>{source?'Ключ сохраняется; существующие объекты останутся на прежней версии.':'Уникальный ключ: латинские буквы, цифры и _.'}</small></label></div>
      <div className="panel-heading"><h3>{mode==='builder'?'Реквизиты':'JSON Schema'}</h3><button onClick={switchMode}>{mode==='builder'?'Редактировать JSON Schema':'Вернуться в конструктор'}</button></div>
      {mode==='json'?<label className="field">JSON Schema<textarea className="type-json" rows={22} value={json} onChange={e=>setJson(e.target.value)}/></label>:<>
        <label className="field">Описание типа<textarea rows={2} value={description} onChange={e=>setDescription(e.target.value)} placeholder="Для каких объектов предназначен этот тип"/></label>
        {rows.map((r,i)=><article className="type-field" key={r.id}><div className="type-field-heading"><strong>Реквизит {i+1}</strong><button disabled={r.lockedTitle} onClick={()=>setRows(rows.filter(row=>row.id!==r.id))} aria-label={`Удалить реквизит ${i+1}`}>Удалить</button></div><div className="type-field-inputs"><label className="field">Название реквизита<input value={r.spec.title||''} onChange={e=>spec(r,{title:e.target.value})} placeholder="Владелец"/></label><label className="field">Ключ реквизита<input disabled={r.lockedTitle} value={r.key} maxLength={64} onChange={e=>update(r.id,{key:e.target.value})} placeholder="owner"/></label><label className="field">Вид данных<select disabled={r.lockedTitle&&r.spec.type==='string'} value={kindOf(r.spec)} onChange={e=>{const kind=e.target.value;update(r.id,{spec:{type:kind==='date'||kind==='enum'?'string':kind,title:r.spec.title,description:r.spec.description,...(kind==='date'?{format:'date'}:kind==='array'?{items:{type:'string'}}:kind==='enum'?{enum:[]}:{} )}});}}>{kinds.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label></div>
          <label className="check-line"><input type="checkbox" disabled={r.lockedTitle&&r.required} checked={r.required} onChange={e=>update(r.id,{required:e.target.checked})}/>Обязательное при публикации</label>
          <details><summary>Описание{kindOf(r.spec)==='enum'?' и варианты':''}</summary><label className="field">Описание реквизита<textarea rows={2} value={r.spec.description||''} onChange={e=>spec(r,{description:e.target.value})} placeholder="Что указывать в этом поле; подсказка пользователю и LLM"/></label>{kindOf(r.spec)==='enum'&&<label className="field">Варианты — по одному на строке<textarea rows={4} value={r.spec.enum?.join('\n')||''} onChange={e=>spec(r,{enum:e.target.value.split('\n')})}/></label>}</details>
        </article>)}
        <button disabled={rows.length>=40} onClick={()=>{let n=1;while(rows.some(r=>r.key===`field_${n}`))n++;setRows([...rows,{id:crypto.randomUUID(),key:`field_${n}`,spec:{type:'string',title:''},required:false}]);}}>+ Добавить реквизит</button><p className="muted type-help">{rows.length} из 40 реквизитов. Обязательное строковое поле title используется как название объекта и защищено от удаления. Смена вида данных сбрасывает ограничения этого поля; остальные ограничения доступны в JSON Schema.</p>
      </>}
      <div className="save-bar"><button className="primary" onClick={()=>void save()}>{busy?'Сохраняем…':source?'Сохранить новую версию':'Создать тип'}</button></div>
    </fieldset>
  </section>;
}

export function Types({types,onChanged}:{types:ArtifactType[];onChanged:()=>Promise<void>}){
  const [editing,setEditing]=useState<ArtifactType|null|undefined>(),[editorKey,setEditorKey]=useState(0),[notice,setNotice]=useState('');
  const open=(source:ArtifactType|null)=>{setNotice('');setEditing(source);setEditorKey(k=>k+1);};
  return <><div className="page-heading"><div><div className="eyebrow">Структура реестра</div><h1>Типы объектов</h1><p>Опишите реквизиты — приложение создаст форму ввода и схему для извлечения.</p></div>{editing===undefined&&<button className="primary" onClick={()=>open(null)}>+ Создать новый тип</button>}</div>
    {notice&&<p className="success" role="status">{notice}</p>}
    {editing!==undefined?<TypeEditor key={editorKey} source={editing} types={types} onCancel={()=>setEditing(undefined)} onSaved={async()=>{await onChanged();setEditing(undefined);setNotice(editing?'Новая версия сохранена. Существующие объекты сохранили прежнюю схему.':'Новый тип создан. Его можно выбрать при создании объекта, импорте и настройке пайплайна.');}}/>:<section className="panel">{types.map(t=><div className="import-item" key={t.id}><div><strong>{t.name}</strong><small>{t.type_key} · версия {t.version} · {Object.keys(t.schema.properties).length} реквизитов</small>{(t.schema as Schema).description&&<p className="muted">{(t.schema as Schema).description}</p>}</div><button onClick={()=>open(t)}>Создать следующую версию</button></div>)}</section>}
  </>;
}

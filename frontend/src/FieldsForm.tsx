import type {ArtifactType, Fields} from './api';
import {display} from './api';

export function FieldsForm({type, values, onChange, disabled = false}:{type:ArtifactType;values:Fields;onChange:(v:Fields)=>void;disabled?:boolean}) {
  const update = (key:string, value:Fields[string]|undefined) => {
    const next = {...values};
    if (value === undefined) delete next[key]; else next[key] = value;
    onChange(next);
  };
  return <div className="fields">{Object.entries(type.schema.properties).map(([key,spec]) => {
    const label = spec.title || key;
    const inputId = `field-${key}`;
    return <div className="field" key={key}><label htmlFor={inputId}>{label}{type.schema.required?.includes(key) && <span className="required"> *</span>}</label>
      {spec.enum ? <select id={inputId} disabled={disabled} value={values[key] === undefined ? '' : String(spec.enum.findIndex(v=>v===values[key]))} onChange={e=>update(key,e.target.value===''?undefined:spec.enum![Number(e.target.value)])}><option value="">Не выбрано</option>{spec.enum.map((v,i)=><option key={i} value={i}>{display(v)}</option>)}</select>
      : spec.type==='boolean' ? <select id={inputId} disabled={disabled} value={values[key]===undefined?'':String(values[key])} onChange={e=>update(key,e.target.value===''?undefined:e.target.value==='true')}><option value="">Не выбрано</option><option value="true">Да</option><option value="false">Нет</option></select>
      : spec.type==='integer'||spec.type==='number' ? <input id={inputId} type="number" step={spec.type==='integer'?1:'any'} disabled={disabled} value={values[key]===undefined?'':String(values[key])} onChange={e=>update(key,e.target.value===''?undefined:Number(e.target.value))}/>
      : spec.format==='date' ? <input id={inputId} type="date" disabled={disabled} value={String(values[key]??'')} onChange={e=>update(key,e.target.value||undefined)}/>
      : key==='title'||key==='owner' ? <input id={inputId} disabled={disabled} value={String(values[key]??'')} onChange={e=>update(key,e.target.value||undefined)}/>
      : <textarea id={inputId} rows={3} disabled={disabled} value={values[key]===undefined?'':display(values[key])} onChange={e=>update(key,e.target.value===''?undefined:spec.type==='array'?e.target.value.split(';').map(v=>v.trim()):e.target.value)}/>}
      {spec.description && <small>{spec.description}</small>}{spec.type==='array' && <small>Значения через точку с запятой</small>}
    </div>;
  })}</div>;
}

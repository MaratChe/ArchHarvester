import {useEffect,useState} from 'react';
import {api} from './api';

export type Step={kind:'table'|'sections'|'between'|'python'|'llm';model?:string;prompt?:string;include_previous?:boolean;provider_id?:string;overwrite?:boolean;table_index?:number;field?:string;start?:string;end?:string;code?:string;params?:Record<string,unknown>};
export type Pipeline={id:string;key:string;name:string;version:number;status:string;type_id:string;steps:Step[];hash:string};

export function PipelineSelect({typeId,value,onChange,onError}:{typeId:string;value:string;onChange:(id:string)=>void;onError:(e:unknown)=>void}){
  const [items,setItems]=useState<Pipeline[]|null>(null);
  useEffect(()=>{void api<Pipeline[]>('/pipelines').then(setItems).catch(onError);},[]);
  useEffect(()=>{if(items&&value&&!items.some(p=>p.id===value&&p.type_id===typeId&&p.status==='published'))onChange('');},[typeId,items,value]);
  return <label className="field">Пайплайн извлечения<select value={value} onChange={e=>onChange(e.target.value)}><option value="">Встроенный способ</option>{(items||[]).filter(p=>p.type_id===typeId&&p.status==='published').map(p=><option key={p.id} value={p.id}>{p.name} · версия {p.version}</option>)}</select><small>{value?'Применяются шаги выбранной версии пайплайна.':'Настроить и проверить свои правила можно в разделе «Пайплайны».'}</small></label>;
}

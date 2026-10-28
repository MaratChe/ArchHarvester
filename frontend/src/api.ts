import type {ScriptResult} from './ScriptResults';
export type ModelRun={provider_id?:string;provider_name?:string;base_url?:string;identity_kind?:string;resolved_model?:string;run_id:string;model:string;model_digest:string;prompt_hash:string;duration_seconds:number};
export type Fields = Record<string, string | number | boolean | string[]>;
export type FieldSpec = {type: string; title?: string; description?: string; enum?: (string | number | boolean)[]; format?: string};
export type ArtifactType = {id:string;type_key:string;version:number;name:string;schema:{type:string;properties:Record<string,FieldSpec>;required?:string[];additionalProperties:boolean}};
export type Evidence = {snapshot_id:string;block_id:string;html_path?:string;quote:string;slide_index?:number;shape_id?:number;cell?:number[]};
export type Artifact = {search_match?:string;search_method?:string;id:string;type_id:string;revision:number;fields:Fields;status:string;updated_at:string;provenance:Record<string,{method:string;evidence?:Evidence[];model_metadata?:ModelRun}>;sources?:{id:string;name:string;kind?:string;url?:string}[]};
export type Candidate = {step_results?:ScriptResult[];id:string;type_id:string;target_id:string|null;resource_id:string;snapshot_id:string;source_name:string;status:string;base_revision:number;latest_revision?:number;current_fields:Fields;baseline:Fields;warnings:string[];proposals:Record<string,{value:Fields[string];method:string;evidence:Evidence[];model_metadata?:ModelRun}>};
export type Snapshot = {id:string;filename:string;sha256:string;source_metadata?:{url:string;page_id?:string;page_version?:number;parent_page_id?:string;attachment_id?:string;version?:number;title:string;format:string};document:{format?:string;blocks:{id:string;kind:string;text:string;html_path?:string;slide_index?:number;shape_id?:number;level:number|null}[]}};
let token = '';
export async function init() { const s = await api<{token:string;data_dir:string}>('/session'); token = s.token; return s; }
export async function api<T>(path:string, options:RequestInit = {}):Promise<T> {
  const headers:Record<string,string> = {'X-Local-Token':token};
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const result = await fetch('/api' + path, {...options, headers:{...headers, ...options.headers}});
  if (!result.ok) {
    const data = await result.json().catch(() => ({detail:'Ошибка соединения'}));
    const detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail, null, 2);
    throw new Error(detail || `Ошибка ${result.status}`);
  }
  return result.json();
}
export const display = (v:unknown) => Array.isArray(v) ? v.join('; ') : v === undefined || v === null ? '—' : typeof v === 'boolean' ? (v ? 'Да' : 'Нет') : String(v);
export const stamp = (s:string) => new Date(s).toLocaleString('ru-RU', {dateStyle:'short',timeStyle:'short'});

export type ScriptResult={index:number;kind:string;emitted_fields:string[];warnings:string[];files?:{name:string;content:string}[];input?:unknown;result?:unknown;output?:unknown;error?:string};

function download(name:string,content:string){
  const url=URL.createObjectURL(new Blob([content],{type:'text/markdown;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download=name;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export function ScriptResults({steps=[],showIO=false}:{steps?:ScriptResult[];showIO?:boolean}){
  const names:Record<string,string>={javascript:'Script Engine',python:'Python',table:'Таблица',sections:'Разделы',between:'Между границами',llm:'LLM'};
  return <>{steps.filter(s=>showIO||s.kind==='javascript').map(s=><details key={s.index} className="pipeline-step step-trace"><summary>Шаг {s.index} · {names[s.kind]||s.kind} · {s.error?'ошибка':'результаты'}</summary>
    {showIO&&<>{s.input===undefined?<p className="muted">В старом отчёте вход и выход не сохранены. Повторите тестирование.</p>:<details><summary>Вход шага</summary><pre>{JSON.stringify(s.input,null,2)}</pre></details>}
      {s.result!==undefined&&<details><summary>Выход шага</summary><pre>{JSON.stringify(s.result,null,2)}</pre></details>}
      {s.error&&<p className="error">{s.error}</p>}</>}
    <p>Выданные поля: {s.emitted_fields.join(', ')||'нет'}</p>
    {s.warnings.map((w,i)=><p key={i}>{w}</p>)}
    {s.files?.map((file,i)=><div key={i}><h4>{file.name}</h4><button onClick={()=>download(file.name,file.content)}>Скачать Markdown</button><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{file.content}</pre></div>)}
  </details>)}</>;
}

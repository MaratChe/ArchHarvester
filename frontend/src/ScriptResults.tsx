export type ScriptResult={index:number;kind:string;emitted_fields:string[];warnings:string[];files?:{name:string;content:string}[]};

function download(name:string,content:string){
  const url=URL.createObjectURL(new Blob([content],{type:'text/markdown;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download=name;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export function ScriptResults({steps=[]}:{steps?:ScriptResult[]}){
  return <>{steps.filter(s=>s.kind==='javascript').map(s=><details key={s.index} className="pipeline-step"><summary>Шаг {s.index} · Script Engine · результаты</summary>
    <p>Выданные поля: {s.emitted_fields.join(', ')||'нет'}</p>
    {s.warnings.map((w,i)=><p key={i}>{w}</p>)}
    {s.files?.map((file,i)=><div key={i}><h4>{file.name}</h4><button onClick={()=>download(file.name,file.content)}>Скачать Markdown</button><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{file.content}</pre></div>)}
  </details>)}</>;
}

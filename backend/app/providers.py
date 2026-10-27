"""OpenAI-compatible transport and per-application provider registry."""
import ipaddress
import json
import math
import time
from hashlib import sha256
from urllib.parse import urlsplit
import httpx
from fastapi import HTTPException
from .ollama import Ollama
from .registry import require
from .db import providers
from .confluence.credentials import WindowsCredentials


def normalize_base_url(value):
    p=urlsplit(value.strip())
    try:
        p.port
        loopback=p.hostname=='localhost' or ipaddress.ip_address(p.hostname or '').is_loopback
    except ValueError:loopback=p.hostname=='localhost'
    try:p.port
    except ValueError:raise ValueError('Некорректный порт API') from None
    if (not p.hostname or p.username is not None or p.password is not None or p.query or p.fragment or any(ch.isspace() for ch in value)
            or '\\' in value or '%' in p.path or any(part in {'.','..'} for part in p.path.split('/'))
            or not (p.scheme=='https' or p.scheme=='http' and loopback)):
        raise ValueError('Нужен HTTPS base URL без ключа/query; HTTP разрешён только для localhost/loopback')
    return p._replace(netloc=p.netloc.lower(),path=p.path.rstrip('/')).geturl()


class ProviderCredentials(WindowsCredentials):
    label='LLM API key'
    @staticmethod
    def _key(key):return 'ArchitectureRegistryStudio/Providers/'+key


class OpenAICompatible:
    def __init__(self,config,key=None,*,transport=None,guard=None):
        self.config=dict(config);self.key=key;self.transport=transport
        self.base_url=normalize_base_url(config['base_url']);self.guard=guard
        self.embedding_model=None;self.embedding_seen=False;self.resolved_model=None;self.last_parameters={};self.wire_prompt_hash=None

    def _http(self,method,path,payload=None):
        if self.guard:self.guard()
        headers={'Accept':'application/json'}
        if self.key:headers['Authorization']='Bearer '+self.key
        try:
            with httpx.Client(transport=self.transport,trust_env=False,follow_redirects=False,timeout=httpx.Timeout(180,connect=10),headers=headers) as client:
                with client.stream(method,self.base_url+path,json=payload) as response:
                    if response.status_code!=200:
                        descriptions={401:'API-ключ не принят',403:'Нет доступа к модели/API',404:'Endpoint или модель не найдены',429:'Лимит запросов или бюджета провайдера'}
                        message=descriptions.get(response.status_code,'Провайдер отклонил запрос; проверьте формат ответа и параметры модели')
                        if 300<=response.status_code<400:message='Перенаправления запрещены; укажите конечный base URL'
                        raise HTTPException(502,f'{message} (HTTP {response.status_code})')
                    data=bytearray();start=time.monotonic()
                    for chunk in response.iter_bytes(chunk_size=16384):
                        data.extend(chunk)
                        if len(data)>(8 if path=='/models' else 2)*1024*1024 or time.monotonic()-start>180:raise HTTPException(502,'Ответ провайдера превысил лимит размера или времени')
                    parsed=json.loads(data)
                    if not isinstance(parsed,dict):raise ValueError()
                    return parsed
        except httpx.TimeoutException:raise HTTPException(503,'Провайдер не ответил за отведённое время (до180 секунд)') from None
        except httpx.HTTPError:raise HTTPException(503,'Не удалось соединиться с API; проверьте адрес, сеть и сертификат') from None
        except (ValueError,UnicodeDecodeError):raise HTTPException(502,'API вернул некорректный JSON') from None

    def identity(self,model,capability):
        if self.guard:self.guard()
        if not isinstance(model,str) or not model.strip() or len(model)>150:raise HTTPException(422,'Укажите модель или deployment alias')
        identity={k:self.config.get(k) for k in ('id','base_url','deployment_revision','credential_revision')}
        identity['model']=model
        return {'name':model,'digest':'config:'+sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),
                'provider_id':self.config['id'],'identity_kind':'configuration'}

    def models(self):
        data=self._http('GET','/models').get('data')
        if not isinstance(data,list):raise HTTPException(502,'API /models не вернул список data; модель можно указать вручную')
        return [{'name':m['id']} for m in data if isinstance(m,dict) and isinstance(m.get('id'),str)]

    def generation_metadata(self):
        return {'provider_id':self.config['id'],'provider_name':self.config['name'],'base_url':self.base_url,'identity_kind':'configuration',
                'deployment_revision':self.config.get('deployment_revision','1'),'credential_revision':self.config.get('credential_revision',1),
                'resolved_model':self.resolved_model,'options':self.last_parameters,**({'prompt_hash':self.wire_prompt_hash} if self.wire_prompt_hash else {})}

    def request(self,method,path,payload=None):
        if method!='POST' or path!='/api/chat':raise HTTPException(422,'Неподдерживаемый запрос адаптера')
        fmt=self.config.get('response_format','json_object')
        messages=[dict(m) for m in payload['messages']]
        messages[0]['content']+='\nRequired output JSON contract: '+json.dumps(payload['format'],ensure_ascii=False)
        token_parameter=self.config.get('token_parameter','max_tokens')
        body={'model':payload['model'],'messages':messages,'stream':False,token_parameter:payload['options']['num_predict']}
        if self.config.get('send_temperature',True):body['temperature']=payload['options']['temperature']
        if fmt=='json_object':body['response_format']={'type':'json_object'}
        elif fmt=='json_schema':body['response_format']={'type':'json_schema','json_schema':{'name':'architecture_proposals','strict':False,'schema':payload['format']}}
        self.last_parameters={k:v for k,v in body.items() if k not in {'model','messages','response_format'}}
        self.last_parameters['response_format']=fmt
        self.wire_prompt_hash=sha256(json.dumps({'messages':messages,'response_format':body.get('response_format')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        self.last_request={'endpoint':self.base_url+'/chat/completions','body':body}
        self.last_response=None
        response=self._http('POST','/chat/completions',body)
        self.last_response=response
        choices=response.get('choices')
        if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict):raise HTTPException(502,'Некорректный ответ chat/completions')
        choice=choices[0];message=choice.get('message')
        if not isinstance(message,dict) or message.get('tool_calls') or message.get('function_call') or choice.get('finish_reason')!='stop' or not isinstance(message.get('content'),str):
            raise HTTPException(502,'Генерация не завершена, отклонена или содержит вызов инструмента')
        resolved=response.get('model')
        if resolved is not None and (not isinstance(resolved,str) or len(resolved)>300):raise HTTPException(502,'Некорректное имя модели в ответе')
        self.resolved_model=resolved
        return {'done':True,'done_reason':'stop','message':{'content':message['content']}}

    def embed(self,texts,model):
        data=self._http('POST','/embeddings',{'model':model,'input':texts,'encoding_format':'float'})
        resolved=data.get('model')
        if resolved is not None and (not isinstance(resolved,str) or len(resolved)>300):raise HTTPException(502,'Некорректное имя embedding-модели')
        if self.embedding_seen and resolved!=self.embedding_model:raise HTTPException(409,'Embedding API сменил модель между пакетами; индекс не опубликован')
        self.embedding_model=resolved;self.embedding_seen=True
        rows=data.get('data')
        if not isinstance(rows,list) or len(rows)!=len(texts) or not all(isinstance(r,dict) and type(r.get('index')) is int for r in rows):raise HTTPException(502,'Неверное число или индексы embeddings')
        if sorted(r['index'] for r in rows)!=list(range(len(texts))):raise HTTPException(502,'Повторяющиеся или отсутствующие индексы embeddings')
        vectors=[r.get('embedding') for r in sorted(rows,key=lambda r:r['index'])];dimension=None
        for v in vectors:
            try:valid=isinstance(v,list) and 1<=len(v)<=8192 and all(type(x) in (float,int) and math.isfinite(x) for x in v)
            except OverflowError:valid=False
            if not valid:raise HTTPException(502,'Некорректный embedding')
            if dimension is not None and dimension!=len(v):raise HTTPException(502,'Размерности embeddings различаются')
            dimension=len(v);norm=math.sqrt(sum(float(x)*float(x) for x in v))
            if not math.isfinite(norm) or norm<=0:raise HTTPException(502,'Нулевой или бесконечный embedding')
        return vectors


class ProviderRegistry:
    def __init__(self,db,secrets=None,transport=None):
        self.db=db;self.secrets=secrets if secrets is not None else ProviderCredentials();self.transport=transport

    def client(self,provider_id='ollama'):
        if not provider_id or provider_id=='ollama':return Ollama()
        with self.db.engine.connect() as c:config=require(c,providers,provider_id)
        if not config['enabled']:raise HTTPException(409,'Подключение провайдера отключено')
        try:key=self.secrets.get(provider_id)
        except RuntimeError:raise HTTPException(503,'Не удалось прочитать API-ключ из Windows Credential Manager') from None
        if config['auth_required'] and not key:raise HTTPException(422,'Введите API-ключ подключения')
        def guard():
            with self.db.engine.connect() as c:current=require(c,providers,provider_id)
            if not current['enabled'] or current['credential_revision']!=config['credential_revision']:
                raise HTTPException(409,'Подключение изменилось во время запроса; повторите операцию')
        return OpenAICompatible(config,key,transport=self.transport,guard=guard)


def client_for(db,provider_id='ollama'):
    registry=getattr(db,'provider_registry',None)
    if registry:return registry.client(provider_id)
    if provider_id and provider_id!='ollama':raise HTTPException(422,'Реестр провайдеров не настроен')
    return Ollama()

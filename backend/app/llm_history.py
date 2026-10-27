import time
from .db import llm_outputs


def cleanup(c):
    c.execute(llm_outputs.delete().where(llm_outputs.c.expires<time.time()))


def record(c,result):
    cleanup(c)
    for raw in result.pop('_llm_raw',[]):
        c.execute(llm_outputs.insert().values(id=raw['id'],expires=time.time()+7*86400,data={k:v for k,v in raw.items() if k!='id'}))


def record_failure(c,exc):
    completed=getattr(exc,'llm_completed',None)
    if completed:record(c,completed)
    output=getattr(exc,'llm_output',None)
    if output:
        cleanup(c)
        c.execute(llm_outputs.insert().values(id=output['id'],expires=time.time()+7*86400,data=output))
        return output['id']

"""Opt-in phase timing. Never record prompts, source text, credentials or error bodies."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime,timezone
from functools import wraps
from inspect import signature
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import json,os,logging

_current=ContextVar('gsm_timing',default=None)
SAFE={'kb_id','release_id','source_version_id','domain_version_id','task_id','build_id','correlation_id'}

@contextmanager
def phase(operation,context=None):
    target=os.environ.get('GSM_TIMING_LOG')
    if not target:yield;return
    parent=_current.get();meta={**(parent['context'] if parent else {}),**{k:v for k,v in (context or {}).items() if k in SAFE and isinstance(v,str)}}
    row={'operation':operation,'trace_id':parent['trace_id'] if parent else str(uuid4()),'span_id':str(uuid4()),'parent_id':parent['span_id'] if parent else None,'context':meta,'started_at':datetime.now(timezone.utc).isoformat(),'status':'ok','actor':os.environ.get('GSM_TIMING_ROLE','unspecified') if os.environ.get('GSM_TIMING_ROLE') in ('developer','consumer','worker') else 'unspecified'}
    token=_current.set(row);start=perf_counter()
    try:yield
    except BaseException as error:
        row['status']='error';row['error_type']=type(error).__name__
        if hasattr(error,'code'):row['error_code']=error.code
        raise
    finally:
        row['duration_ms']=round((perf_counter()-start)*1000,3);row['ended_at']=datetime.now(timezone.utc).isoformat();_current.reset(token)
        try:
            with Path(target).open('a') as out:out.write(json.dumps(row,ensure_ascii=False)+'\n')
        except OSError:logging.getLogger('gsm.timing').warning('Timing sink unavailable; phase metrics were not captured')

def timed(operation):
    def decorate(fn):
        sig=signature(fn)
        @wraps(fn)
        def wrapper(*args,**kwargs):
            if not os.environ.get('GSM_TIMING_LOG'):return fn(*args,**kwargs)
            values=sig.bind_partial(*args,**kwargs).arguments
            with phase(operation,{k:v for k,v in values.items() if k in SAFE}):return fn(*args,**kwargs)
        return wrapper
    return decorate

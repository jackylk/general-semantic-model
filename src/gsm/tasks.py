from gsm.observability import timed
from hashlib import sha256
import json
from pathlib import Path
from psycopg.types.json import Jsonb
from .errors import ProductError

class TaskService:
    def __init__(self,store): self.store=store

    def migrate(self):
        with self.store.connect('owner') as conn:
            conn.execute('SELECT pg_advisory_xact_lock(79523489)')
            if not conn.execute("SELECT 1 FROM schema_migrations WHERE version='002'").fetchone():
                conn.execute(Path('migrations/002_tasks.sql').read_text())
                conn.execute("INSERT INTO schema_migrations(version) VALUES('002')")

    @timed('task.enqueue')
    def submit(self,principal,kb_id,kind,payload,idempotency_key):
        principal.require(kb_id,write=True)
        if not idempotency_key or len(idempotency_key)>200: raise ProductError('INVALID_KEY','幂等键不能为空且最长 200 字符')
        digest=sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.store.transaction(principal,kb_id) as conn:
            row=conn.execute('INSERT INTO tasks(kb_id,kind,payload,input_hash,idempotency_key) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(kb_id,kind,idempotency_key) DO NOTHING RETURNING id',(kb_id,kind,Jsonb(payload),digest,idempotency_key)).fetchone()
            if not row:
                previous=conn.execute('SELECT id,input_hash FROM tasks WHERE kb_id=%s AND kind=%s AND idempotency_key=%s',(kb_id,kind,idempotency_key)).fetchone()
                if previous[1]!=digest: raise ProductError('IDEMPOTENCY_CONFLICT','同一幂等键对应不同请求')
                task_id=str(previous[0])
            else: task_id=str(row[0])
        return self.get(principal,kb_id,task_id)

    def get(self,principal,kb_id,task_id):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            row=conn.execute('SELECT id,kind,status,stage,checkpoint,error,payload FROM tasks WHERE kb_id=%s AND id=%s',(kb_id,task_id)).fetchone()
            if not row: raise ProductError('NOT_FOUND','任务不存在或无权限')
            return dict(zip(('id','kind','status','stage','checkpoint','error','payload'),(str(row[0]),*row[1:])))

    def status(self,principal,kb_id,task_id):
        principal.require(kb_id,write=True)
        array_count=lambda name: "jsonb_array_length(CASE WHEN jsonb_typeof(checkpoint->'"+name+"')='array' THEN checkpoint->'"+name+"' ELSE '[]'::jsonb END)"
        query="SELECT id,kind,status,stage,CASE WHEN error IS NULL THEN NULL ELSE jsonb_build_object('code',error->'code','message',error->'message','retryable',error->'retryable') END,"+array_count('completed_batches')+",CASE WHEN jsonb_typeof(checkpoint->'coverage')='object' THEN checkpoint->'coverage'->'planned_batches' ELSE NULL END,"+array_count('candidate_ids')+",checkpoint->>'build_id' FROM tasks WHERE kb_id=%s AND id=%s"
        with self.store.transaction(principal,kb_id) as conn:row=conn.execute(query,(kb_id,task_id)).fetchone()
        if not row:raise ProductError('NOT_FOUND','任务不存在或无权限')
        return {'id':str(row[0]),'kind':row[1],'status':row[2],'stage':row[3],'error':({k:v for k,v in row[4].items() if k in ('code','message','retryable')} if row[4] else None),
            'progress':{'completed_batches':row[5],'planned_batches':row[6],'candidate_count':row[7],'build_id':row[8]}}

    def get_error(self,principal,kb_id,task_id):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            row=conn.execute('SELECT error FROM tasks WHERE kb_id=%s AND id=%s',(kb_id,task_id)).fetchone()
        if not row:raise ProductError('NOT_FOUND','任务不存在或无权限')
        return row[0]

    def checkpoint(self,principal,kb_id,task_id,stage,checkpoint):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            cursor=conn.execute("UPDATE tasks SET stage=%s,checkpoint=%s,status='running',error=NULL,updated_at=now() WHERE kb_id=%s AND id=%s",(stage,Jsonb(checkpoint),kb_id,task_id))
            if not cursor.rowcount: raise ProductError('NOT_FOUND','任务不存在或无权限')

    def fail(self,principal,kb_id,task_id,code,message,retryable=False,details=None):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            cursor=conn.execute("UPDATE tasks SET status='failed',error=%s,updated_at=now() WHERE kb_id=%s AND id=%s",(Jsonb({'code':code,'message':message,'retryable':retryable,'details':json.loads(json.dumps(details or [],default=str))}),kb_id,task_id))
            if not cursor.rowcount: raise ProductError('NOT_FOUND','任务不存在或无权限')

    def retry(self,principal,kb_id,task_id):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            row=conn.execute('SELECT status,error FROM tasks WHERE kb_id=%s AND id=%s FOR UPDATE',(kb_id,task_id)).fetchone()
            if not row or row[0]!='failed' or not (row[1] or {}).get('retryable'):
                raise ProductError('NOT_RETRYABLE','任务不是可重试的失败状态')
            conn.execute("UPDATE tasks SET status='queued',error=NULL,updated_at=now() WHERE kb_id=%s AND id=%s",(kb_id,task_id))
        return self.get(principal,kb_id,task_id)

    def cancel(self,principal,kb_id,task_id):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            if not conn.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0))',(task_id,)).fetchone()[0]:
                raise ProductError('TASK_BUSY','任务正在执行，不能取消；请稍后重试',retryable=True)
            row=conn.execute('SELECT status FROM tasks WHERE kb_id=%s AND id=%s FOR UPDATE',(kb_id,task_id)).fetchone()
            if not row:raise ProductError('NOT_FOUND','任务不存在或无权限')
            if row[0]=='succeeded':raise ProductError('NOT_CANCELLABLE','已完成任务不能取消')
            conn.execute("UPDATE tasks SET status='cancelled',updated_at=now() WHERE kb_id=%s AND id=%s",(kb_id,task_id))
        return self.get(principal,kb_id,task_id)

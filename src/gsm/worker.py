"""Persistent task execution; per-task advisory lock prevents duplicate workers."""
from psycopg.types.json import Jsonb
from .errors import ProductError

class Worker:
    def __init__(self,tasks,handlers): self.tasks=tasks;self.handlers=handlers

    def run(self,principal,kb_id,task_id):
        principal.require(kb_id,write=True)
        with self.tasks.store.transaction(principal,kb_id) as lock_conn:
            acquired=lock_conn.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0))',(task_id,)).fetchone()[0]
            if not acquired: raise ProductError('TASK_BUSY','任务正在执行',retryable=True)
            task=self.tasks.get(principal,kb_id,task_id)
            if task['status']=='succeeded': return task
            if task['kind'] not in self.handlers: raise ProductError('UNKNOWN_TASK','不支持的任务类型')
            self.tasks.checkpoint(principal,kb_id,task_id,task['stage'],task['checkpoint'])
            try:
                result=self.handlers[task['kind']](task['payload'],task['checkpoint'])
                with self.tasks.store.transaction(principal,kb_id) as conn:
                    conn.execute("UPDATE tasks SET status='succeeded',stage='complete',checkpoint=%s,updated_at=now() WHERE kb_id=%s AND id=%s",(Jsonb(result),kb_id,task_id))
            except ProductError as error:
                self.tasks.fail(principal,kb_id,task_id,error.code,str(error),error.retryable)
            except Exception:
                self.tasks.fail(principal,kb_id,task_id,'INTERNAL_ERROR','任务内部错误，请检查服务端受控诊断',False)
            return self.tasks.get(principal,kb_id,task_id)

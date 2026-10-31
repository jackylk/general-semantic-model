from uuid import uuid4
import pytest
from gsm.config import Settings
from gsm.store import Store
from gsm.auth import Principal
from gsm.tasks import TaskService
from gsm.errors import ProductError


def test_idempotency_restart_and_failure_state():
    store=Store(Settings.load());store.migrate()
    kb=str(uuid4());p=Principal('developer',frozenset([kb]));store.create_kb(p,kb,'tasks')
    service=TaskService(store);service.migrate()
    one=service.submit(p,kb,'parse',{'source':'a'},'k1')
    assert service.submit(p,kb,'parse',{'source':'a'},'k1')['id']==one['id']
    with pytest.raises(ProductError): service.submit(p,kb,'parse',{'source':'b'},'k1')
    service.checkpoint(p,kb,one['id'],'parsed',{'block_count':2})
    service=TaskService(store)
    recovered=service.get(p,kb,one['id'])
    assert recovered['stage']=='parsed'
    assert recovered['checkpoint']=={'block_count':2}
    service.fail(p,kb,one['id'],'PARSER_UNAVAILABLE','local parser missing',retryable=True)
    failed=service.get(p,kb,one['id'])
    assert failed['status']=='failed' and failed['error']['retryable']
    with pytest.raises(ProductError): service.get(Principal('consumer',frozenset()),kb,one['id'])


def test_worker_runs_persistent_task_and_does_not_repeat_completed_job():
    from gsm.worker import Worker
    store=Store(Settings.load());store.migrate()
    kb=str(uuid4());p=Principal('developer',frozenset([kb]));store.create_kb(p,kb,'worker')
    tasks=TaskService(store);tasks.migrate()
    task=tasks.submit(p,kb,'count',{'n':2},'worker-1')
    calls=[]
    def count(payload,checkpoint):
        calls.append(payload['n']);return {'answer':payload['n']+1}
    worker=Worker(tasks,{'count':count})
    assert worker.run(p,kb,task['id'])['checkpoint']=={'answer':3}
    assert worker.run(p,kb,task['id'])['status']=='succeeded'
    assert calls==[2]

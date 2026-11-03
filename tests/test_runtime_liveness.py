import asyncio,time
from types import SimpleNamespace
from urllib.error import URLError,HTTPError
from gsm.auth import Principal
from gsm.mcp.server import create_server
from gsm.shared_runtime import healthy


def test_busy_live_services_are_not_treated_as_dead(monkeypatch):
    import gsm.shared_runtime as runtime
    monkeypatch.setattr(runtime.os,'kill',lambda *args:None)
    class Opener:
        def open(self,*args,**kwargs):raise URLError(TimeoutError('synthetic busy event loop'))
    monkeypatch.setattr(runtime,'build_opener',lambda *args:Opener())
    state={'producer':{'pid':1,'url':'http://127.0.0.1:1/mcp'},'consumer':{'pid':2,'url':'http://127.0.0.1:2/mcp'},'worker':{'pid':3}}
    assert healthy(state)


def test_sync_tool_work_does_not_block_async_service_loop(monkeypatch):
    from gsm.search import QueryService
    def delayed_records(*args,**kwargs):time.sleep(.8);return []
    monkeypatch.setattr(QueryService,'records',delayed_records)
    server=create_server(SimpleNamespace(principal=Principal('consumer',frozenset(['synthetic-kb'])),store=object()))
    async def check():
        start=time.perf_counter()
        task=asyncio.create_task(server.call_tool('query_records',{'kb_id':'synthetic-kb','release_id':'synthetic-release'}))
        await asyncio.sleep(.01)
        responsive=time.perf_counter()-start
        await task
        return responsive
    assert asyncio.run(check())<.5


def test_replacing_dead_worker_keeps_live_role_endpoints(tmp_path,monkeypatch):
    import json
    import gsm.shared_runtime as runtime
    operator=tmp_path/'operator';operator.mkdir();product=tmp_path/'product';product.mkdir()
    previous={'producer':{'pid':11,'url':'http://127.0.0.1:1/mcp','token':'producer-test'},'consumer':{'pid':22,'url':'http://127.0.0.1:2/mcp','token':'consumer-test'},'worker':{'pid':33}}
    (operator/'services.json').write_text(json.dumps(previous))
    monkeypatch.setattr(runtime,'registry',lambda root:(operator,{'product':str(product)}))
    def kill(pid,sig):
        assert sig==0,'live role processes must not be stopped'
        if pid==33:raise ProcessLookupError()
    monkeypatch.setattr(runtime.os,'kill',kill)
    def forbidden_stop(*args):raise AssertionError('must not tear down live role endpoints')
    monkeypatch.setattr(runtime,'_stop',forbidden_stop)
    class Opener:
        def open(self,url,**kwargs):raise HTTPError(url,401,'Unauthorized',{},None)
    monkeypatch.setattr(runtime,'build_opener',lambda *args:Opener())
    commands=[]
    def popen(command,**kwargs):commands.append(command);return SimpleNamespace(pid=44)
    monkeypatch.setattr(runtime.subprocess,'Popen',popen)
    result=runtime.services(tmp_path/'workspace')
    assert result['producer']==previous['producer']
    assert result['consumer']==previous['consumer']
    assert result['worker']['pid']==44
    assert len(commands)==1 and 'worker' in commands[0]

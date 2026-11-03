import pytest
from test_build import build_env,candidates
from gsm.search import QueryService
from gsm.releases import ReleaseService
from gsm.auth import Principal
from gsm.errors import ProductError


def publish(env):
    store,b,review,p,kb,dv,block=env
    ingested=b.ingest(p,kb,dv,candidates(block))
    build=b.finish(p,kb,dv,[r['id'] for r in ingested['candidates']],embed=False)
    rel=ReleaseService(store).publish(p,kb,build)
    return ingested,rel


def test_graph_conditions_and_source_evidence(build_env):
    store,b,review,p,kb,dv,block=build_env
    data,rel=publish(build_env);q=QueryService(store);reader=Principal('consumer',frozenset([kb]))
    paths=q.paths(reader,kb,rel,data['objects']['a'],data['objects']['b'],max_depth=3)
    assert len(paths)==1
    assert paths[0]['records'][0]['payload']['predicate']=='connects'
    assert paths[0]['records'][0]['evidence_ids']
    records=q.records(reader,kb,rel,kind='assertion',conditions={'temperature':'20'})
    assert records[0]['payload']['value']['value']=='10.25'
    assert q.records(reader,kb,rel,kind='assertion',conditions={'temperature':'0'})==[]
    evidence=ReleaseService(store).read_evidence(reader,kb,rel,records[0]['evidence_ids'][0])
    assert '20℃时' in evidence['quote']


def test_chinese_search_and_wiki_fixed_to_release(build_env):
    store,b,review,p,kb,dv,block=build_env
    data,rel=publish(build_env);q=QueryService(store)
    results=q.search(p,kb,rel,'功率',use_vector=False)
    assert any('10.25' in str(r['payload']) for r in results)
    wiki=q.wiki(p,kb,rel)
    assert '10.25' in wiki['text'] and wiki['citations']
    with pytest.raises(ProductError): q.paths(p,kb,rel,data['objects']['a'],max_depth=100)


def test_retrieval_agent_uses_tools_and_rejects_fabricated_citations(build_env):
    from gsm.retrieval import RetrievalService
    from gsm.adapters.llm import Completion
    store,b,review,p,kb,dv,block=build_env
    data,rel=publish(build_env)
    evidence=QueryService(store).records(p,kb,rel,kind='assertion')[0]['evidence_ids'][0]
    class ScriptedModel:
        def __init__(self): self.calls=0
        def complete(self,prompt,system='',**kwargs):
            if system.startswith('证据一致性核验'):return Completion({'supported':True,'complete':True,'reasoning_valid':True,'reasons':[]},'test',{})
            self.calls+=1
            if self.calls==1:return Completion({'action':'query_records','args':{'kind':'assertion'}},'test',{'total_tokens':5})
            if self.calls==2:return Completion({'action':'read_evidence','args':{'evidence_id':evidence}},'test',{'total_tokens':5})
            return Completion({'action':'finish','answer':'20℃时为10.25 W','citations':[evidence],'status':'supported'},'test',{'total_tokens':5})
    result=RetrievalService(store,ScriptedModel()).retrieve(p,kb,rel,'20℃时功率？')
    assert result['citations']==[evidence]
    assert len(result['trace'])==3
    class BadModel:
        def complete(self,*args,**kwargs):return Completion({'action':'finish','answer':'unknown claim','citations':['invented'],'status':'supported'},'test',{})
    with pytest.raises(ProductError):RetrievalService(store,BadModel()).retrieve(p,kb,rel,'问题')


def test_multi_round_evidence_context_has_bounded_budget_for_real_documents(build_env):
    from gsm.retrieval import RetrievalService
    from gsm.adapters.llm import Completion
    store,b,review,p,kb,dv,block=build_env
    data,rel=publish(build_env);evidence=QueryService(store).records(p,kb,rel,kind='assertion')[0]['evidence_ids'][0]
    class Model:
        def __init__(self):self.n=0
        def complete(self,*args,**kwargs):
            if kwargs.get('system','').startswith('证据一致性核验'):return Completion({'supported':True,'complete':True,'reasoning_valid':True,'reasons':[]},'test',{})
            self.n+=1
            if self.n==1:return Completion({'action':'query_records','args':{'kind':'assertion'}},'test',{'total_tokens':6000})
            if self.n==2:return Completion({'action':'read_evidence','args':{'evidence_id':evidence}},'test',{'total_tokens':7000})
            return Completion({'action':'finish','status':'supported','answer':'10.25 W at 20℃','citations':[evidence]},'test',{'total_tokens':7000})
    assert RetrievalService(store,Model()).retrieve(p,kb,rel,'功率')['total_tokens']==20000
    with pytest.raises(ProductError):RetrievalService(store,Model(),max_tokens=10000).retrieve(p,kb,rel,'功率')


def test_retrieval_refuses_input_before_spending_remaining_budget(build_env):
    from gsm.retrieval import RetrievalService
    store,b,review,p,kb,dv,block=build_env
    _,rel=publish(build_env)
    class NoCall:
        def complete(self,*args,**kwargs):raise AssertionError('must stop before paid call')
    with pytest.raises(ProductError,match='预算'):RetrievalService(store,NoCall(),max_tokens=10).retrieve(p,kb,rel,'问题')


def test_search_keeps_hits_after_first_200_records(build_env):
    from gsm.sources import SourceService
    store,b,review,p,kb,dv,block=build_env
    text=' '.join(f'设备 serial{i:03d}' for i in range(205));src=SourceService(store)
    path=store.settings.source_root/'many.txt';path.write_text(text);v=src.import_file(p,kb,path.name);parsed=src.save_parse(p,kb,v['id'],'text',[{'text':text,'page':1}]);bid=parsed['blocks'][0]['id']
    data=[{'kind':'object','local_id':str(i),'type_id':'device','name':f'serial{i:03d}','identity':{'serial':f'serial{i:03d}'},'evidence':[{'block_id':bid,'quote':f'设备 serial{i:03d}'}]} for i in range(205)]
    records=b.ingest(p,kb,dv,data)['candidates'];rel=ReleaseService(store).publish(p,kb,b.finish(p,kb,dv,[r['id'] for r in records],embed=False))
    target=max(records,key=lambda r:r['id'])
    hits=QueryService(store).search(p,kb,rel,target['payload']['name'],use_vector=False)
    assert any(r['id']==target['id'] for r in hits)


def test_retrieval_uses_published_vocabulary_batches_evidence_and_rejects_bad_answer(build_env):
    import json
    from gsm.retrieval import RetrievalService
    from gsm.adapters.llm import Completion
    store,b,review,p,kb,dv,block=build_env
    _,rel=publish(build_env);eid=QueryService(store).records(p,kb,rel,kind='assertion')[0]['evidence_ids'][0]
    class Model:
        def __init__(self):self.n=0;self.reviewed=False
        def complete(self,prompt,system='',**kwargs):
            data=json.loads(prompt)
            if system.startswith('证据一致性核验'):
                self.reviewed=True
                assert data['original_blocks'][0]['source']['filename']=='a.txt'
                assert '10.25' in data['original_blocks'][0]['text']
                return Completion({'supported':False,'complete':True,'reasoning_valid':False,'reasons':['数值或主体不受所引原文支持']},'test',{})
            if 'domain' in data:assert any(x['id']=='power' for x in data['domain']['properties'])
            self.n+=1
            if self.n==1:return Completion({'action':'read_evidence_batch','args':{'evidence_ids':[eid]}},'test',{})
            return Completion({'action':'finish','status':'supported','answer':'另一个设备功率100 W','citations':[eid]},'test',{})
    model=Model();result=RetrievalService(store,model,max_rounds=2).retrieve(p,kb,rel,'设备A的功率')
    assert model.reviewed and result['status']=='insufficient'
    assert result['support_check']['supported'] is False
    assert '100 W' not in result['answer']


def test_retrieval_reserves_budget_to_finish_from_already_read_originals(build_env):
    import json
    from gsm.retrieval import RetrievalService
    from gsm.adapters.llm import Completion
    store,b,review,p,kb,dv,block=build_env
    _,rel=publish(build_env);eid=QueryService(store).records(p,kb,rel,kind='assertion')[0]['evidence_ids'][0]
    class Model:
        def __init__(self):self.n=0
        def complete(self,prompt,system='',**kwargs):
            if system.startswith('证据一致性核验'):return Completion({'supported':True,'complete':True,'reasoning_valid':True,'reasons':[]},'test',{})
            self.n+=1;data=json.loads(prompt)
            if self.n==1:return Completion({'action':'read_evidence','args':{'evidence_id':eid}},'test',{'total_tokens':1000})
            assert 'original_blocks' in data and 'history' not in data
            assert '10.25' in data['original_blocks'][0]['text']
            return Completion({'action':'finish','status':'supported','answer':'20℃时10.25 W','citations':[eid]},'test',{'total_tokens':100})
    result=RetrievalService(store,Model(),max_tokens=8000).retrieve(p,kb,rel,'功率？')
    assert result['status']=='supported' and result['trace'][-1]['grounded_finalization']


def test_retrieval_does_not_spend_finish_budget_when_required_review_cannot_fit(build_env):
    from gsm.retrieval import RetrievalService
    from gsm.adapters.llm import Completion
    store,b,review,p,kb,dv,block=build_env
    _,rel=publish(build_env);eid=QueryService(store).records(p,kb,rel,kind='assertion')[0]['evidence_ids'][0]
    class Model:
        def __init__(self):self.calls=0
        def complete(self,*args,**kwargs):
            self.calls+=1
            assert self.calls==1,'must stop before paying for an unreviewable finish'
            return Completion({'action':'read_evidence','args':{'evidence_id':eid}},'test',{'total_tokens':7000})
    model=Model();result=RetrievalService(store,model,max_tokens=10000).retrieve(p,kb,rel,'功率')
    assert result['status']=='insufficient' and result['failure_code']=='RETRIEVAL_BUDGET'
    assert result['support_check']['supported'] is False


def test_release_context_preserves_neighboring_conditions_without_crossing_scope(build_env):
    from gsm.sources import SourceService
    store,b,review,p,kb,dv,block=build_env
    src=SourceService(store);path=store.settings.source_root/'context.txt'
    first='设备 A 序号 001。设备 B 序号 002。A 连接 B。20℃时 A 功率 10.25 W。'
    path.write_text(first+'\n仅供试验，不适用于室外。\n未经核验的图表内容。')
    v=src.import_file(p,kb,path.name)
    parsed=src.save_parse(p,kb,v['id'],'synthetic-context',[
        {'text':first,'page':1},{'text':'仅供试验，不适用于室外。','page':2},
        {'text':'未经核验的图表内容。','page':2,'requires_review':True}])
    items=b.ingest(p,kb,dv,candidates(parsed['blocks'][0]['id']))['candidates']
    rel=ReleaseService(store).publish(p,kb,b.finish(p,kb,dv,[r['id'] for r in items],embed=False))
    eid=QueryService(store).records(p,kb,rel,kind='assertion')[0]['evidence_ids'][0]
    context=ReleaseService(store).read_context(p,kb,rel,eid)
    assert any('不适用于室外' in x['text'] for x in context)
    assert not any('未经核验' in x['text'] for x in context)
    assert all(x['release_id']==rel for x in context)
    with pytest.raises(ProductError):ReleaseService(store).read_context(p,kb,rel,'block:'+block)


def test_retrieval_rejects_consistent_but_incomplete_answer(build_env):
    from gsm.retrieval import RetrievalService
    from gsm.adapters.llm import Completion
    store,b,review,p,kb,dv,block=build_env
    _,rel=publish(build_env);eid=QueryService(store).records(p,kb,rel,kind='assertion')[0]['evidence_ids'][0]
    class Model:
        def __init__(self):self.n=0
        def complete(self,prompt,system='',**kwargs):
            if system.startswith('证据一致性核验'):
                return Completion({'supported':True,'complete':False,'reasoning_valid':True,'missing_aspects':['适用条件尚未覆盖'],'reasons':[]},'test',{})
            self.n+=1
            if self.n==1:return Completion({'action':'read_evidence','args':{'evidence_id':eid}},'test',{})
            return Completion({'action':'finish','status':'supported','answer':'10.25 W','citations':[eid]},'test',{})
    result=RetrievalService(store,Model(),max_rounds=2).retrieve(p,kb,rel,'功率及其适用条件？')
    assert result['status']=='insufficient'
    assert not result['support_check']['complete']


def test_published_pdf_page_preview_is_version_bound(build_env):
    import subprocess,sys
    from pathlib import Path
    from gsm.sources import SourceService
    store,b,review,p,kb,dv,block=build_env
    runtime=Path('runtime/mineru/bin/python')
    if not runtime.exists():pytest.skip('PDF runtime not installed')
    path=store.settings.source_root/'synthetic-layout.pdf'
    subprocess.run([str(runtime),'-c',"from pypdf import PdfWriter;import sys;w=PdfWriter();w.add_blank_page(width=300,height=400);w.write(sys.argv[1])",str(path)],check=True)
    source=SourceService(store);v=source.import_file(p,kb,path.name)
    parsed=source.save_parse(p,kb,v['id'],'synthetic-pdf',[{'text':'设备 A 序号 001。设备 B 序号 002。A 连接 B。20℃时 A 功率 10.25 W。','page':1}])
    items=b.ingest(p,kb,dv,candidates(parsed['blocks'][0]['id']))['candidates']
    rel=ReleaseService(store).publish(p,kb,b.finish(p,kb,dv,[r['id'] for r in items],embed=False))
    service=ReleaseService(store)
    result=service.render_source_page(p,kb,rel,v['id'],1)
    assert result['png'].startswith(b'\x89PNG\r\n\x1a\n')
    assert result['metadata']['release_id']==rel
    assert result['metadata']['source_sha256']==v['sha256']
    import asyncio
    from types import SimpleNamespace
    from gsm.mcp.server import create_server
    server=create_server(SimpleNamespace(principal=p,store=store))
    content=asyncio.run(server.call_tool('render_source_page',{'kb_id':kb,'release_id':rel,'source_version_id':v['id'],'page':1}))
    blocks=content[0] if isinstance(content,tuple) else content
    assert any(getattr(x,'type',None)=='image' for x in blocks)
    with pytest.raises(ProductError):service.render_source_page(p,kb,rel,v['id'],0)
    other=source.import_file(p,kb,'a.txt')
    with pytest.raises(ProductError):service.render_source_page(p,kb,rel,other['id'],1)


def test_retrieval_repairs_bad_tool_argument_instead_of_failing_entire_question(build_env):
    from gsm.retrieval import RetrievalService
    from gsm.adapters.llm import Completion
    store,b,_,p,kb,_,_=build_env;_,release=publish(build_env)
    class Model:
        def __init__(self):self.n=0
        def complete(self,*args,**kwargs):
            self.n+=1
            if self.n==1:return Completion({'action':'search','args':{'query':'synthetic','limit':'five'}},'test',{})
            return Completion({'action':'finish','answer':'资料不足','status':'insufficient','citations':[]},'test',{})
    result=RetrievalService(store,Model(),max_rounds=3).retrieve(p,kb,release,'合成问题')
    assert result['status']=='insufficient'
    assert result['trace'][0]['error']['code']=='INVALID_TOOL_ARGUMENT'
    assert not result['trace'][0]['executed']


@pytest.mark.parametrize('bad_plan',[
    {'action':'delete_records','args':{}},
    {'action':'search','args':{'query':'synthetic','unexpected':True}},
    {'action':['search'],'args':{}},
    {'action':'search','args':[]},
])
def test_invalid_plan_is_not_executed_and_can_be_corrected(build_env,bad_plan):
    import json
    from gsm.retrieval import RetrievalService
    from gsm.adapters.llm import Completion
    store,_,_,p,kb,_,_=build_env;_,release=publish(build_env)
    class Model:
        calls=0
        def complete(self,prompt,**kwargs):
            self.calls+=1
            if self.calls==1:return Completion(bad_plan,'test',{'total_tokens':7})
            history=json.loads(prompt)['history']
            assert history[-1]['result']['code']=='INVALID_TOOL_PLAN'
            return Completion({'action':'finish','status':'insufficient','answer':'资料不足','citations':[]},'test',{'total_tokens':3})
    result=RetrievalService(store,Model(),max_rounds=3).retrieve(p,kb,release,'合成问题')
    assert result['status']=='insufficient' and result['total_tokens']==10
    assert not result['trace'][0]['executed']
    assert result['trace'][0]['error']['code']=='INVALID_TOOL_PLAN'

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
            if system.startswith('证据一致性核验'):return Completion({'supported':True,'reasons':[]},'test',{})
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
            if kwargs.get('system','').startswith('证据一致性核验'):return Completion({'supported':True,'reasons':[]},'test',{})
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
                return Completion({'supported':False,'reasons':['数值或主体不受所引原文支持']},'test',{})
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
            if system.startswith('证据一致性核验'):return Completion({'supported':True,'reasons':[]},'test',{})
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

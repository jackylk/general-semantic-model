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
        def complete(self,prompt,system=''):
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

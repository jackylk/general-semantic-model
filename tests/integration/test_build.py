from uuid import uuid4
import pytest
from gsm.auth import Principal
from gsm.store import Store
from gsm.config import Settings
from gsm.sources import SourceService
from gsm.build import BuildService
from gsm.review import ReviewService
from gsm.releases import ReleaseService
from gsm.errors import ProductError

DOMAIN={'schema_version':'1','id':'devices','name':'设备制度','types':[{'id':'device','name':'设备','identity':['serial']}],
'properties':[{'id':'serial','name':'序号','subject_types':['device'],'value_type':'string'},
{'id':'power','name':'功率','subject_types':['device'],'value_type':'quantity','units':['W'],'required_conditions':['temperature']}],
'conditions':[{'id':'temperature','value_type':'decimal'}],
'relations':[{'id':'connects','name':'连接','subject_types':['device'],'object_types':['device']}]}

@pytest.fixture
def build_env(tmp_path):
    s=Settings.load();s.source_root=tmp_path;s.file_root=tmp_path/'blobs'
    store=Store(s);store.migrate();kb=str(uuid4());p=Principal('developer',frozenset([kb]));store.create_kb(p,kb,'build')
    src=SourceService(store);(tmp_path/'a.txt').write_text('设备 A 序号 001。设备 B 序号 002。A 连接 B。20℃时 A 功率 10.25 W。')
    v=src.import_file(p,kb,'a.txt');parsed=src.save_parse(p,kb,v['id'],'text',[{'text':(tmp_path/'a.txt').read_text(),'page':1}])
    build=BuildService(store);build.migrate();dv=build.submit_domain(p,kb,DOMAIN)
    return store,build,ReviewService(store),p,kb,dv,parsed['blocks'][0]['id']


def candidates(block):
    return [
        {'kind':'object','local_id':'a','type_id':'device','name':'设备 A','identity':{'serial':'001'},'evidence':[{'block_id':block,'quote':'设备 A 序号 001'}]},
        {'kind':'object','local_id':'b','type_id':'device','name':'设备 B','identity':{'serial':'002'},'evidence':[{'block_id':block,'quote':'设备 B 序号 002'}]},
        {'kind':'relation','subject':'a','predicate':'connects','object':'b','evidence':[{'block_id':block,'quote':'A 连接 B'}]},
        {'kind':'assertion','subject':'a','predicate':'power','value':{'value':'10.25','unit':'W'},'conditions':{'temperature':'20'},'evidence':[{'block_id':block,'quote':'20℃时 A 功率 10.25 W'}]},
    ]


def test_generic_ingestion_preserves_conditions_and_stable_identity(build_env):
    store,b,review,p,kb,dv,block=build_env
    first=b.ingest(p,kb,dv,candidates(block));second=b.ingest(p,kb,dv,candidates(block))
    assert first['objects']['a']==second['objects']['a']
    assert all(item['status']=='verified' for item in first['candidates'])
    assertion=first['candidates'][-1]
    assert assertion['payload']['value']=={'value':'10.25','unit':'W'}
    assert assertion['payload']['conditions']=={'temperature':'20'}


def test_missing_identity_or_evidence_cannot_be_confirmed_away(build_env):
    store,b,review,p,kb,dv,block=build_env
    data=candidates(block);data[0]['identity']={};data[1]['evidence']=[]
    result=b.ingest(p,kb,dv,data)
    assert result['candidates'][0]['status']=='candidate'
    assert result['candidates'][1]['status']=='candidate'
    with pytest.raises(ProductError): review.decide(p,kb,[result['candidates'][0]['id']],'confirm','looks right')


def test_invalid_unit_and_missing_condition_are_blocked(build_env):
    store,b,review,p,kb,dv,block=build_env
    data=candidates(block);data[-1]['value']['unit']='kW';data[-1]['conditions']={}
    result=b.ingest(p,kb,dv,data)
    assert result['candidates'][-1]['status']=='candidate'
    assert {'UNIT_NOT_ALLOWED','MISSING_CONDITION'} <= {i['code'] for i in result['candidates'][-1]['issues']}


def test_conflicts_require_review_but_different_conditions_do_not(build_env):
    store,b,review,p,kb,dv,block=build_env
    b.ingest(p,kb,dv,candidates(block))
    changed=candidates(block);changed[-1]['value']['value']='11.25'
    result=b.ingest(p,kb,dv,changed)
    assert 'CONFLICT' in {i['code'] for i in result['candidates'][-1]['issues']}
    changed[-1]['conditions']['temperature']='0'
    different=b.ingest(p,kb,dv,changed)
    assert 'CONFLICT' not in {i['code'] for i in different['candidates'][-1]['issues']}


def test_reviewed_inference_stays_labeled_and_can_be_published(build_env):
    store,b,review,p,kb,dv,block=build_env
    data=candidates(block);data[-1]['provenance']='inference'
    result=b.ingest(p,kb,dv,data)
    ids=[c['id'] for c in result['candidates']]
    build=b.finish(p,kb,dv,ids,embed=False)
    with pytest.raises(ProductError): ReleaseService(store).publish(p,kb,build)
    review.decide(p,kb,[ids[-1]],'confirm','明确保留为推断，不认定为原文事实')
    rel=ReleaseService(store).publish(p,kb,build)
    assert rel


def test_event_roles_and_rule_conditions_are_domain_defined(build_env):
    from copy import deepcopy
    store,b,review,p,kb,dv,block=build_env
    domain=deepcopy(DOMAIN)
    domain['events']=[{'id':'inspection','name':'检验','roles':[{'id':'tested','object_types':['device'],'required':True}]}]
    domain['rules']=[{'id':'cold_limit','name':'低温限制','applies_to':['device'],'when':{'op':'lt','field':'temperature','value':'0'},'conclusion':'需复核'}]
    dv=b.submit_domain(p,kb,domain)
    data=candidates(block)[:2]+[
        {'kind':'event','type_id':'inspection','participants':[{'role':'tested','object':'a'}],'evidence':[{'block_id':block,'quote':'设备 A'}]},
        {'kind':'rule','subject':'a','predicate':'cold_limit','evidence':[{'block_id':block,'quote':'设备 A'}]},
    ]
    result=b.ingest(p,kb,dv,data)
    assert result['candidates'][2]['status']=='verified'
    assert result['candidates'][2]['payload']['participants'][0]['object']==result['objects']['a']
    assert result['candidates'][3]['payload']['rule']['when']['op']=='lt'
    assert result['candidates'][3]['status']=='candidate'


def test_object_reference_property_must_resolve_to_allowed_object_type(build_env):
    from copy import deepcopy
    store,b,review,p,kb,dv,block=build_env
    d=deepcopy(DOMAIN);d['properties'].append({'id':'parent','name':'上级设备','subject_types':['device'],'value_type':'object_ref','reference_types':['device']})
    dv=b.submit_domain(p,kb,d)
    data=candidates(block)[:2]+[{'kind':'assertion','subject':'a','predicate':'parent','value':'missing','evidence':[{'block_id':block,'quote':'设备 A'}]}]
    result=b.ingest(p,kb,dv,data)
    assert result['candidates'][-1]['status']=='candidate'


def test_extraction_repairs_invalid_quantity_before_returning(build_env,tmp_path):
    from gsm.application import Application
    from gsm.adapters.llm import Completion
    import json
    store,b,review,p,kb,dv,block=build_env
    from gsm.credentials import write_credentials
    profile=tmp_path/'profile.json';write_credentials(profile,'developer',[kb])
    app=Application(profile);app.store=store;app.build=b
    class Model:
        n=0
        def complete(self,*args,**kwargs):
            self.n+=1;data=candidates(block)
            if self.n==1:data[-1]['value']='10.25'
            return Completion({'candidates':data},'test',{'total_tokens':10})
    result=app.extract_candidates(kb,dv,[{'block_id':block,'text':'test'}],Model())
    assert result['attempts']==2
    assert result['result']['candidates'][-1]['status']=='verified'


def test_source_statement_cannot_attach_unstated_number_to_real_quote(build_env):
    store,b,review,p,kb,dv,block=build_env
    data=candidates(block);data[-1]['value']['value']='999'
    result=b.ingest(p,kb,dv,data)
    assert 'VALUE_NOT_IN_EVIDENCE' in {i['code'] for i in result['candidates'][-1]['issues']}
    with pytest.raises(ProductError):review.decide(p,kb,[result['candidates'][-1]['id']],'confirm','approve')

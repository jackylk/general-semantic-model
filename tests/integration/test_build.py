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


def test_unstated_condition_and_unit_are_not_verified(build_env):
    store,b,review,p,kb,dv,block=build_env
    data=candidates(block);data[-1]['conditions']['temperature']='999'
    result=b.ingest(p,kb,dv,data)
    assert 'CONDITION_NOT_IN_EVIDENCE' in {i['code'] for i in result['candidates'][-1]['issues']}
    # A declared alternative unit is not a license to reinterpret the source.
    from copy import deepcopy
    domain=deepcopy(DOMAIN);domain['properties'][1]['units']=['W','kW'];dv=b.submit_domain(p,kb,domain)
    data=candidates(block);data[-1]['value']['unit']='kW'
    result=b.ingest(p,kb,dv,data)
    assert 'UNIT_NOT_IN_EVIDENCE' in {i['code'] for i in result['candidates'][-1]['issues']}


def test_chinese_magnitude_compared_with_source_quantity(build_env):
    store,b,review,p,kb,dv,block=build_env
    from copy import deepcopy
    from gsm.sources import SourceService
    domain=deepcopy(DOMAIN);domain['properties'][1]['units']=['元'];dv=b.submit_domain(p,kb,domain)
    (store.settings.source_root/'scaled.txt').write_text('设备 A 序号 001。20℃时设备 A 标价 10 万元。')
    src=SourceService(store);v=src.import_file(p,kb,'scaled.txt');parsed=src.save_parse(p,kb,v['id'],'test',[{'text':'设备 A 序号 001。20℃时设备 A 标价 10 万元。'}]);bid=parsed['blocks'][0]['id']
    data=[{'kind':'object','local_id':'a','type_id':'device','name':'设备 A','identity':{'serial':'001'},'evidence':[{'block_id':bid,'quote':'设备 A 序号 001'}]},
          {'kind':'assertion','subject':'a','predicate':'power','value':{'value':'100000','unit':'元'},'conditions':{'temperature':'20'},'evidence':[{'block_id':bid,'quote':'20℃时设备 A 标价 10 万元'}]}]
    correct=b.ingest(p,kb,dv,data)
    assert correct['candidates'][-1]['status']=='verified'
    data[-1]['value']['value']='10'
    wrong=b.ingest(p,kb,dv,data)
    assert 'VALUE_NOT_IN_EVIDENCE' in {i['code'] for i in wrong['candidates'][-1]['issues']}


def test_rejected_and_withdrawn_assertions_do_not_conflict(build_env):
    store,b,review,p,kb,dv,block=build_env
    first=b.ingest(p,kb,dv,candidates(block))
    review.decide(p,kb,[first['candidates'][-1]['id']],'reject','错误抽取，排除')
    data=candidates(block);data[-1]['value']['value']='11.25'
    result=b.ingest(p,kb,dv,data)
    assert 'CONFLICT' not in {i['code'] for i in result['candidates'][-1]['issues']}
    # Remaining source supports have also been explicitly withdrawn.
    with store.transaction(p,kb) as conn:
        source_id=str(conn.execute('SELECT source_version_id FROM parse_versions WHERE kb_id=%s',(kb,)).fetchone()[0])
    SourceService(store).withdraw(p,kb,source_id)
    result=b.ingest(p,kb,dv,candidates(block))
    assert 'CONFLICT' not in {i['code'] for i in result['candidates'][-1]['issues']}


def test_extra_identity_keys_do_not_split_stable_object(build_env):
    store,b,review,p,kb,dv,block=build_env
    first=b.ingest(p,kb,dv,candidates(block))
    data=candidates(block);data[0]['identity']['color']='red'
    second=b.ingest(p,kb,dv,data)
    assert first['objects']['a']==second['objects']['a']
    assert 'UNDECLARED_IDENTITY_FIELD' in {i['code'] for i in second['candidates'][0]['issues']}


def test_declared_unit_aliases_support_chinese_magnitude(build_env):
    from gsm.grounding import grounded
    from gsm.domain import Property
    definition=Property(id='price',name='售价',subject_types=['device'],value_type='quantity',units=['CNY'],unit_aliases={'CNY':['元']})
    assert grounded({'value':'100000','unit':'CNY'},definition,'售价 10 万元')
    assert not grounded({'value':'10','unit':'CNY'},definition,'售价 10 万元')


def test_decimal_identity_is_canonicalized_and_rejected_repair_is_excluded(build_env):
    from copy import deepcopy
    store,b,review,p,kb,dv,block=build_env
    domain=deepcopy(DOMAIN);domain['properties'][0]['value_type']='decimal';dv=b.submit_domain(p,kb,domain)
    one=candidates(block)[:1];one[0]['identity']['serial']='1.0'
    first=b.ingest(p,kb,dv,one)
    one[0]['identity']['serial']='1.00'
    second=b.ingest(p,kb,dv,one)
    assert first['objects']['a']==second['objects']['a']


def test_malformed_evidence_structure_is_repaired_instead_of_internal_error(build_env,tmp_path):
    from gsm.application import Application
    from gsm.adapters.llm import Completion
    from gsm.credentials import write_credentials
    store,b,review,p,kb,dv,block=build_env
    profile=tmp_path/'profile.json';write_credentials(profile,'developer',[kb]);app=Application(profile);app.store=store;app.build=b
    class Model:
        n=0
        def complete(self,*args,**kwargs):
            self.n+=1;data=candidates(block)
            if self.n==1:data[0]['evidence']={'block_id':{'bad':'shape'},'quote':'bad'}
            else:
                for item in data:
                    for e in item['evidence']:e['block_id']='B0001'
            return Completion({'candidates':data},'test',{'total_tokens':10})
    result=app.extract_candidates(kb,dv,[{'block_id':block,'text':'test'}],Model())
    assert result['result']['candidates'][-1]['status']=='verified'
    assert result['attempts']==2


def test_extraction_retries_invalid_json_with_bounded_attempts(build_env):
    from gsm.application import Application
    from gsm.adapters.llm import Completion
    store,b,review,p,kb,dv,block=build_env
    app=object.__new__(Application);app.store=store;app.principal=p;app.build=b
    class Model:
        def __init__(self,always=False):self.calls=0;self.always=always
        def complete(self,*args,**kwargs):
            self.calls+=1
            if self.calls==1 or self.always:raise ProductError('INVALID_MODEL_OUTPUT','bad JSON',[{'reason':'truncated','usage':{'total_tokens':10}}])
            return Completion({'candidates':candidates(block)},'test',{'total_tokens':5})
    model=Model();result=app.extract_candidates(kb,dv,[{'block_id':block,'text':'test'}],model)
    assert model.calls==2 and result['usage']['total_tokens']==15
    bad=Model(True)
    with pytest.raises(ProductError) as exc:app.extract_candidates(kb,dv,[{'block_id':block,'text':'test'}],bad)
    assert bad.calls==2 and exc.value.retryable


def test_build_preview_filters_conditions_before_publish_without_releasing(build_env):
    store,b,review,p,kb,dv,block=build_env
    result=b.ingest(p,kb,dv,candidates(block));bid=b.finish(p,kb,dv,[r['id'] for r in result['candidates']],embed=False)
    preview=b.preview(p,kb,bid,conditions={'temperature':'20'})
    assert preview['matching_count']==1 and preview['records'][0]['payload']['conditions']=={'temperature':'20'}
    assert b.preview(p,kb,bid,conditions={'temperature':'0'})['records']==[]
    assert ReleaseService(store).current(p,kb) is None
    reader=Principal('consumer',frozenset([kb]))
    with pytest.raises(ProductError):b.preview(reader,kb,bid)
    with pytest.raises(ProductError):b.preview(p,kb,str(uuid4()))


def test_revalidation_uses_existing_payload_without_llm_and_keeps_original(build_env,monkeypatch):
    import gsm.grounding as grounding
    store,b,review,p,kb,dv,block=build_env
    original=grounding.grounded
    monkeypatch.setattr(grounding,'grounded',lambda *args:False)
    old=b.ingest(p,kb,dv,candidates(block));assert old['candidates'][-1]['status']=='candidate'
    monkeypatch.setattr(grounding,'grounded',original)
    ids=[r['id'] for r in old['candidates']];new=b.revalidate(p,kb,dv,ids)
    assert all(r['status']=='verified' for r in new['candidates'])
    assert not set(ids)&{r['id'] for r in new['candidates']}
    with store.transaction(p,kb) as conn:
        assert conn.execute('SELECT status FROM records WHERE kb_id=%s AND id=%s',(kb,ids[-1])).fetchone()[0]=='candidate'
    review.decide(p,kb,[ids[0]],'reject','business decision')
    with pytest.raises(ProductError):b.revalidate(p,kb,dv,ids)
    with pytest.raises(ProductError):b.revalidate(Principal('consumer',frozenset([kb])),kb,dv,ids)


def test_focused_extraction_keeps_fixed_domain_and_routes_only_data_instructions(build_env):
    import json
    from gsm.application import Application
    from gsm.adapters.llm import Completion
    store,b,review,p,kb,dv,block=build_env
    app=object.__new__(Application);app.store=store;app.principal=p;app.build=b
    before=b.get_domain(p,kb,dv).model_dump(mode='json')
    class Model:
        def complete(self,prompt,**kwargs):
            data=json.loads(prompt);assert data['extraction_focus']=='Inspect missing connectivity using existing declared types.'
            return Completion({'candidates':candidates(block)},'test',{})
    result=app.extract_candidates(kb,dv,[{'block_id':block,'text':'test'}],Model(),focus='Inspect missing connectivity using existing declared types.')
    assert result['result']['candidates'] and b.get_domain(p,kb,dv).model_dump(mode='json')==before

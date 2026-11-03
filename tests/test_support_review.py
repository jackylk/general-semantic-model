import json
import pytest
from gsm.adapters.llm import Completion
from gsm.errors import ProductError


def records(n):
    return [{'id':f'actual-uuid-{i}','status':'verified','payload':{'kind':'assertion','subject':'object','predicate':'property','value':'fact','evidence':[{'block_id':'b','quote':'same quote'}]}} for i in range(n)]


def test_review_uses_short_ids_and_deduplicates_shared_quotes_without_dropping_facts():
    from gsm.support_review import review_records
    class Model:
        def complete(self,prompt,**kwargs):
            p=json.loads(prompt)
            assert all(r['id'].startswith('R') and 'actual-uuid' not in r['id'] for r in p['records'])
            assert len(p['evidence_catalog'])==1 and p['evidence_catalog'][0]['quote']=='same quote'
            assert p['records'][0]['payload']['value']=='fact' and 'evidence' not in p['records'][0]['payload']
            return Completion({'reviews':[{'id':r['id'],'checks':dict.fromkeys(('subject_scope','predicate_direction','value_fidelity','conditions_complete','conditions_non_circular','evidence_sufficient'),True),'supported':True,'reason':'supported'} for r in p['records']]},'test',{'total_tokens':10})
    pending={};reviews,usage=review_records(Model(),{},records(3),[{'block_id':'b','text':'same quote','locator':{}}],pending,lambda:None)
    assert [x['id'] for x in reviews]==[f'actual-uuid-{i}' for i in range(3)]
    assert usage['total_tokens']==10


def test_completed_review_chunks_survive_a_later_invalid_response():
    from gsm.support_review import review_records
    pending={};calls=[]
    class Model:
        bad=True
        def complete(self,prompt,**kw):
            p=json.loads(prompt);calls.append(len(p['records']))
            if len(calls)==2 and self.bad:return Completion({'reviews':[]},'test',{'total_tokens':3})
            return Completion({'reviews':[{'id':r['id'],'checks':dict.fromkeys(('subject_scope','predicate_direction','value_fidelity','conditions_complete','conditions_non_circular','evidence_sufficient'),True),'supported':True} for r in p['records']]},'test',{'total_tokens':5})
    model=Model();saved=[]
    with pytest.raises(ProductError) as e:review_records(model,{},records(40),[{'block_id':'b','text':'same quote','locator':{}}],pending,lambda:saved.append(True))
    assert e.value.code=='INVALID_SUPPORT_REVIEW' and len(pending['support_reviews'])==32
    model.bad=False
    reviews,usage=review_records(model,{},records(40),[{'block_id':'b','text':'same quote','locator':{}}],pending,lambda:None)
    assert calls==[32,8,8] and len(reviews)==40 and usage['total_tokens']==13


def test_invalid_json_review_usage_is_checkpointed_before_retry():
    from gsm.support_review import review_records
    pending={};saved=[]
    class Model:
        def complete(self,*a,**k):raise ProductError('INVALID_MODEL_OUTPUT','truncated',[{'usage':{'prompt_tokens':7,'completion_tokens':4,'total_tokens':11}}],True)
    with pytest.raises(ProductError):review_records(Model(),{},records(1),[{'block_id':'b','text':'same quote','locator':{}}],pending,lambda:saved.append(True))
    assert pending['support_usage']['total_tokens']==11 and saved


def test_later_review_chunk_keeps_subject_identity_context():
    from gsm.support_review import review_records
    data=records(40);data[0]['payload']={'kind':'object','object_id':'object','type_id':'device','name':'X','identity':{'serial':'001'},'evidence':[{'block_id':'b','quote':'same quote'}]}
    class Model:
        def complete(self,prompt,**kw):
            p=json.loads(prompt)
            assert p['object_context'][0]['payload']['identity']=={'serial':'001'}
            assert p['object_context'][0]['evidence_refs'][0] in {e['id'] for e in p['evidence_catalog']}
            return Completion({'reviews':[{'id':r['id'],'checks':dict.fromkeys(('subject_scope','predicate_direction','value_fidelity','conditions_complete','conditions_non_circular','evidence_sufficient'),True),'supported':True} for r in p['records']]},'test',{})
    reviews,_=review_records(Model(),{},data,[{'block_id':'b','text':'same quote','locator':{}}],{},lambda:None)
    assert len(reviews)==40


@pytest.mark.parametrize('failed_check',['subject_scope','predicate_direction','value_fidelity','conditions_complete','conditions_non_circular','evidence_sufficient'])
def test_positive_verdict_cannot_override_failed_semantic_check(failed_check):
    from gsm.support_review import review_records
    checks={key:True for key in ('subject_scope','predicate_direction','value_fidelity','conditions_complete','conditions_non_circular','evidence_sufficient')}
    checks[failed_check]=False
    class Model:
        def complete(self,*args,**kwargs):
            return Completion({'reviews':[{'id':'R0001','supported':True,'checks':checks}]},'test',{})
    reviews,_=review_records(Model(),{},records(1),[{'block_id':'b','text':'same quote','locator':{}}],{},lambda:None)
    assert reviews[0]['supported'] is False
    assert reviews[0]['checks'][failed_check] is False


def test_unqualified_positive_support_verdict_is_rejected():
    from gsm.support_review import review_records
    class Model:
        def complete(self,*args,**kwargs):return Completion({'reviews':[{'id':'R0001','supported':True}]},'test',{'total_tokens':9})
    pending={}
    with pytest.raises(ProductError,match='逐条覆盖'):
        review_records(Model(),{},records(1),[{'block_id':'b','text':'same quote','locator':{}}],pending,lambda:None)
    assert pending['support_usage']['total_tokens']==9
    assert not pending['support_reviews']

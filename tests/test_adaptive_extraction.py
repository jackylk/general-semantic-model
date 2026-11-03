import pytest
from gsm.errors import ProductError


@pytest.mark.parametrize('reason',['truncated','empty_or_invalid_json'])
def test_truncated_batch_splits_at_blocks_and_resume_keeps_completed_parts(reason):
    from gsm.adaptive_extraction import adaptive_extract
    blocks=[{'block_id':str(i),'text':'whole block'} for i in range(4)]
    class App:
        calls=[]
        def extract_candidates(self,kb,domain,parts,model,focus=None):
            self.calls.append([b['block_id'] for b in parts])
            if len(parts)>2:raise ProductError('INVALID_MODEL_OUTPUT','invalid output',[{'reason':reason,'usage':{'total_tokens':9}}],True)
            return {'result':{'candidates':[{'id':b['block_id']} for b in parts]},'usage':{'total_tokens':3},'extraction_notes':[],'extraction_rejections':[]}
    app=App();state={};saved=[]
    result=adaptive_extract(app,'kb','domain',blocks,None,state,lambda:saved.append(True))
    assert [c['id'] for c in result['result']['candidates']]==['0','1','2','3']
    assert result['usage']['total_tokens']==15
    assert len(app.calls)==3 and saved
    again=adaptive_extract(app,'kb','domain',blocks,None,state,lambda:None)
    assert again==result and len(app.calls)==3


def test_unsplittable_structured_block_fails_without_dropping_data():
    from gsm.adaptive_extraction import adaptive_extract
    class App:
        def extract_candidates(self,*a,**k):raise ProductError('INVALID_MODEL_OUTPUT','truncated',[{'reason':'truncated','usage':{'total_tokens':7}}],True)
    state={}
    with pytest.raises(ProductError,match='安全拆分'):
        adaptive_extract(App(),'kb','domain',[{'block_id':'b','text':'whole row','locator':{'unit_type':'table_row'}}],None,state,lambda:None)
    assert state['failed_usage']['total_tokens']==7


def test_resume_does_not_reextract_successful_half_after_transport_failure():
    from gsm.adaptive_extraction import adaptive_extract
    class App:
        calls=[];fail=True
        def extract_candidates(self,kb,domain,parts,model,focus=None):
            ids=[p['block_id'] for p in parts];self.calls.append(ids)
            if len(parts)==2:raise ProductError('INVALID_MODEL_OUTPUT','length',[{'reason':'truncated','usage':{'total_tokens':5}}],True)
            if ids==['right'] and self.fail:raise ProductError('HTTP_ERROR','unavailable',retryable=True)
            return {'result':{'candidates':[{'id':ids[0]}]},'usage':{'total_tokens':2}}
    app=App();state={};blocks=[{'block_id':'left','text':'complete'},{'block_id':'right','text':'complete'}]
    with pytest.raises(ProductError):adaptive_extract(app,'k','d',blocks,None,state,lambda:None)
    app.fail=False;result=adaptive_extract(app,'k','d',blocks,None,state,lambda:None)
    assert app.calls==[['left','right'],['left'],['right'],['right']]
    assert result['usage']['total_tokens']==9

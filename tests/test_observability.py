import json
from gsm.errors import ProductError


def test_timing_logs_nested_phases_without_capturing_content_or_secrets(tmp_path,monkeypatch):
    from gsm.observability import timed
    path=tmp_path/'timings.jsonl';monkeypatch.setenv('GSM_TIMING_LOG',str(path))
    @timed('model')
    def child(prompt,api_key):return 42
    @timed('task')
    def parent(kb_id,task_id):return child('private source','private credential')
    assert parent('kb','job')==42
    data=[json.loads(l) for l in path.read_text().splitlines()]
    assert len(data)==2 and all(x['duration_ms']>=0 for x in data)
    assert data[0]['parent_id']==data[1]['span_id']
    assert data[0]['context']['task_id']=='job'
    assert 'private' not in path.read_text()
    @timed('failure')
    def failure():raise ProductError('TEST_ERROR','private failure message')
    try:failure()
    except ProductError:pass
    row=json.loads(path.read_text().splitlines()[-1]);assert row['error_code']=='TEST_ERROR'
    assert 'private failure message' not in path.read_text()


def test_retrieval_context_keeps_original_once_and_retains_conditions():
    from gsm.retrieval import model_view
    text='Long original evidence with explicit conditions.'
    record={'payload':{'value':'10','conditions':{'region':'X'},'evidence':[{'quote':text}]},'evidence_ids':['e']}
    assert model_view(record)['payload']['conditions']=={'region':'X'}
    assert 'evidence' not in model_view(record)['payload']
    evidence={'id':'e','text':text,'quote':text,'locator':{'page':1,'content':[{'content':text}],'bbox':[1,2,3,4]}}
    view=model_view(evidence)
    assert json.dumps(view).count(text)==1 and view['locator']['page']==1
    assert view['locator']['bbox']==[1,2,3,4]


def test_answer_review_deduplicates_long_originals_without_crossing_sources():
    from gsm.retrieval import review_evidence
    text='original text '*1000
    base={'text':text,'quote':text[:-1],'fingerprint':'same','parse_version_id':'p','source_version_id':'s','start_offset':0,'end_offset':len(text)-1,'source':{'filename':'source.txt'}}
    evidence=[{**base,'id':str(i)} for i in range(8)]
    compact=review_evidence(evidence)
    assert len(compact['original_blocks'])==1 and len(compact['evidence'])==8
    assert compact['original_blocks'][0]['text']==text
    assert len(json.dumps(compact))<len(text)*2
    other={**base,'id':'other','source_version_id':'other-source'}
    assert len(review_evidence(evidence+[other])['original_blocks'])==2


def test_long_quote_does_not_duplicate_the_complete_original_in_planner_context():
    from gsm.retrieval import model_view
    quote='table row '*1500;text='header\n'+quote+'\nfooter'
    view=model_view({'text':text,'quote':quote,'start_offset':7,'end_offset':7+len(quote)})
    assert view['text']==text and view['quote_is_excerpt']
    assert view['start_offset']==7 and len(json.dumps(view))<len(text)*1.2


def test_domain_vocabulary_compacts_defaults_but_keeps_constraints_and_unknown_identity():
    from gsm.retrieval import compact_vocabulary
    definition={'types':[{'id':'unknown','name':'Unknown','identity':[],'aliases':[]}],
        'properties':[{'id':'power','name':'Power','value_type':'quantity','subject_types':['device'],'units':['W'],'required_conditions':['temperature'],'unit_aliases':{},'enum_values':[],'aliases':[]}],
        'relations':[],'conditions':[{'id':'region','value_type':'enum','enum_values':['X']} ]}
    result=compact_vocabulary(definition)
    assert result['types'][0]['identity']==[]
    prop=result['properties'][0]
    assert prop['units']==['W'] and prop['required_conditions']==['temperature']
    assert 'aliases' not in prop and 'enum_values' not in prop and 'unit_aliases' not in prop
    assert result['conditions'][0]['enum_values']==['X']


def test_model_usage_ledger_logs_tokens_and_context_without_content(tmp_path,monkeypatch):
    from gsm.adapters.llm import LLM
    from gsm.observability import phase
    import gsm.adapters.llm as module
    usage=tmp_path/'usage.jsonl';monkeypatch.setenv('GSM_LLM_USAGE_LOG',str(usage))
    monkeypatch.setattr(module,'post_json',lambda *a,**k:{'choices':[{'message':{'content':'{"secret":"private output"}'},'finish_reason':'stop'}],'usage':{'prompt_tokens':11,'completion_tokens':5,'total_tokens':16,'prompt_cache_hit_tokens':3},'model':'deepseek-flash'})
    with phase('pipeline.extract',{'kb_id':'kb','task_id':'task'}):
        LLM('https://example.invalid','deepseek-flash','private key').complete('private input')
    row=json.loads(usage.read_text())
    assert row['usage']['total_tokens']==16 and row['context']['task_id']=='task'
    assert row['operation']=='pipeline.extract' and row['outcome']=='completed'
    assert 'private' not in usage.read_text()


def test_model_usage_ledger_counts_returned_tokens_on_invalid_output(tmp_path,monkeypatch):
    from gsm.adapters.llm import LLM
    import gsm.adapters.llm as module
    import pytest
    path=tmp_path/'usage.jsonl';monkeypatch.setenv('GSM_LLM_USAGE_LOG',str(path))
    monkeypatch.setattr(module,'post_json',lambda *a,**k:{'choices':[{'message':{'content':'private broken json'},'finish_reason':'length'}],'usage':{'prompt_tokens':12,'completion_tokens':7,'total_tokens':19}})
    with pytest.raises(ProductError):LLM('https://example.invalid','deepseek-flash','secret').complete('private input')
    row=json.loads(path.read_text());assert row['usage']['total_tokens']==19 and row['outcome']=='invalid_output'
    assert row['usage_available'] is True and 'private' not in path.read_text()


def test_model_usage_ledger_marks_unreported_usage_as_unknown(tmp_path,monkeypatch):
    import pytest
    from gsm.adapters.llm import LLM
    import gsm.adapters.llm as module
    target=tmp_path/'usage.jsonl';monkeypatch.setenv('GSM_LLM_USAGE_LOG',str(target))
    def fail(*a,**k):raise ProductError('UPSTREAM_HTTP','private provider message')
    monkeypatch.setattr(module,'post_json',fail)
    with pytest.raises(ProductError):LLM('https://example.invalid','deepseek-flash','secret').complete('private input')
    row=json.loads(target.read_text());assert row['usage_available'] is False and row['usage']=={}
    assert row['outcome']=='request_error' and 'private' not in target.read_text()


def test_compact_vocabulary_retains_event_roles_and_rule_conditions():
    from gsm.retrieval import compact_vocabulary
    definition={'types':[],'properties':[],'relations':[{'id':'links','name':'链接','description':'从引用者指向被引用者','subject_types':['node'],'object_types':['node']}],'conditions':[],
      'events':[{'id':'inspection','name':'检查','roles':[{'id':'actor','object_types':['node'],'required':True}]}],
      'rules':[{'id':'threshold','name':'阈值','applies_to':['node'],'when':{'op':'gt','field':'temperature','value':'30'},'conclusion':'达到阈值'}]}
    result=compact_vocabulary(definition)
    assert result['events'][0]['roles'][0]['required']
    assert result['rules'][0]['when']['value']=='30'
    assert result['relations'][0]['description']=='从引用者指向被引用者'

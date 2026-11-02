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

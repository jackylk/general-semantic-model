from types import SimpleNamespace
from gsm.wiki import render_wiki


def test_wiki_retains_source_qualifiers_next_to_record_values():
    domain=SimpleNamespace(name='测试',types=[],properties=[SimpleNamespace(id='voltage',name='模块电压')],relations=[],events=[],rules=[])
    p={'subject':'unit','predicate':'voltage','value':{'value':'100','unit':'V'},'evidence':[{'quote':'Each module manages up to 18 cells (100Vmax).'}],'conditions':{'application':'Li-ion'}}
    text=render_wiki([('r','assertion',p)],domain,[{'record_id':'r','evidence_id':'e'}])['text']
    assert '100Vmax' in text and 'up to 18' in text and 'Li-ion' in text


def test_wiki_plans_multiple_domain_pages_and_catalog_without_industry_rules():
    domain=SimpleNamespace(name='设备知识',types=[SimpleNamespace(id='device',name='设备'),SimpleNamespace(id='team',name='团队')],properties=[],relations=[],events=[],rules=[])
    rows=[('r1','object',{'object_id':'a','type_id':'device','name':'设备A','identity':{'id':'A'}}),('r2','object',{'object_id':'b','type_id':'team','name':'团队B','identity':{'id':'B'}}),('r3','relation',{'subject':'b','predicate':'owns','object':'a','conditions':{'region':'X'}})]
    refs=[{'record_id':rid,'evidence_id':'e'+rid} for rid,_,_ in rows]
    wiki=render_wiki(rows,domain,refs)
    assert len(wiki['pages'])>=3
    assert wiki['pages'][0]['path']=='index.md'
    assert set(wiki['record_ids'])=={'r1','r2','r3'}
    joined='\n'.join(p['text'] for p in wiki['pages'])
    assert 'region' in joined and 'er3' in joined
    assert all(p['path'].endswith('.md') and '..' not in p['path'] for p in wiki['pages'])

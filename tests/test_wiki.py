from types import SimpleNamespace
from gsm.wiki import render_wiki


def test_wiki_retains_source_qualifiers_next_to_record_values():
    domain=SimpleNamespace(name='测试',types=[],properties=[SimpleNamespace(id='voltage',name='模块电压')],relations=[],events=[],rules=[])
    p={'subject':'unit','predicate':'voltage','value':{'value':'100','unit':'V'},'evidence':[{'quote':'Each module manages up to 18 cells (100Vmax).'}],'conditions':{'application':'Li-ion'}}
    text=render_wiki([('r','assertion',p)],domain,[{'record_id':'r','evidence_id':'e'}])['text']
    assert '100Vmax' in text and 'up to 18' in text and 'Li-ion' in text

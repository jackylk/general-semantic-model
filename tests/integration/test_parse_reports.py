import pytest
from gsm.application import Application
from gsm.errors import ProductError
from test_build import build_env


def test_parse_units_are_immutable_and_producer_report_is_persisted(build_env):
    store,build,review,p,kb,dv,block=build_env
    from gsm.sources import SourceService
    from gsm.auth import Principal
    src=SourceService(store)
    with store.transaction(p,kb) as c:source=str(c.execute('SELECT id FROM source_versions WHERE kb_id=%s',(kb,)).fetchone()[0])
    result=src.save_parse(p,kb,source,'units-test',[{'text':'row','page':1}],raw={'original':'kept'},units=[{'unit_id':'u1','type':'image','status':'unresolved','page':2}],coverage={'status':'incomplete','unresolved_units':1})
    report=src.parse_report(p,kb,result['id'],include_units=True)
    assert report['coverage']['unresolved_units']==1 and report['units'][0]['type']=='image'
    assert src.parse_report(p,kb,result['id'])['unit_count']==1
    assert 'units' not in src.parse_report(p,kb,result['id'])
    with pytest.raises(ProductError):src.parse_report(Principal('consumer',frozenset([kb])),kb,result['id'])
    with store.transaction(p,kb) as c:
        assert c.execute('SELECT raw_output FROM parse_versions WHERE kb_id=%s AND id=%s',(kb,result['id'])).fetchone()[0]=={'original':'kept'}


def test_new_parser_does_not_reuse_legacy_pdf_parse(build_env,monkeypatch):
    from gsm.adapters.mineru import Parser,ParsedDocument
    from gsm.sources import SourceService
    from gsm.credentials import write_credentials
    store,build,review,p,kb,dv,block=build_env
    path=store.settings.source_root/'probe.pdf';path.write_bytes(b'%PDF synthetic')
    src=SourceService(store);source=src.import_file(p,kb,path.name)['id']
    old=src.save_parse(p,kb,source,'mineru-local-flash-txt',[{'text':'legacy'}])['id']
    credential=store.settings.source_root/'producer.json';write_credentials(credential,'developer',[kb],store.settings.source_root)
    app=Application(credential);app.store=store;app.sources=src
    calls=[]
    def parse(self,path):
        calls.append(str(path));return ParsedDocument(Parser.PDF_VERSION,[{'text':'fresh'}],{},[],{'status':'incomplete'})
    monkeypatch.setattr(Parser,'parse',parse)
    fresh=app.parse_source(kb,source)
    assert fresh!=old and len(calls)==1
    assert app.parse_source(kb,source)==fresh and len(calls)==1


def test_cell_evidence_expands_to_header_and_unit_context(build_env):
    from gsm.adapters.llm import Completion
    from gsm.adapters.mineru import Parser
    from gsm.sources import SourceService
    from gsm.credentials import write_credentials
    import json
    store,build,review,p,kb,dv,block=build_env
    d=build.get_domain(p,kb,dv).model_dump(mode='json');d['conditions'][0]={'id':'temperature','value_type':'quantity','units':['C']};dv=build.submit_domain(p,kb,d)
    raw={'pages':[{'page_idx':0,'blocks':[{'type':'table','content':'设备 A 序号 001','cells':[['Temperature (C)','Power (W)'],['30','12.50']]}]}]}
    parsed=Parser.from_middle(raw,'test');src=SourceService(store)
    with store.transaction(p,kb) as c:source=str(c.execute('SELECT id FROM source_versions WHERE kb_id=%s',(kb,)).fetchone()[0])
    saved=src.save_parse(p,kb,source,'test',parsed.blocks)
    blocks=[{'block_id':b['id'],'source_version_id':source,'text':b['text'],'locator':b['locator']} for b in saved['blocks']]
    credential=store.settings.source_root/'producer.json';write_credentials(credential,'developer',[kb],store.settings.source_root)
    app=Application(credential);app.store=store;app.build=build
    class Model:
        model='test'
        def complete(self,prompt):
            request=json.loads(prompt)
            condition_schema=request['candidate_schema']['properties']['conditions']
            assert condition_schema['additionalProperties'] is False
            assert set(condition_schema['properties'])=={'temperature'}
            items=json.loads(prompt)['untrusted_source_blocks'];caption=items[0]['block_id'];row=items[1]['block_id']
            return Completion({'candidates':[{'kind':'object','type_id':'device','local_id':'a','identity':{'serial':'001'},'evidence':[{'block_id':caption,'quote':'设备 A 序号 001'}]},
                {'kind':'assertion','subject':'a','predicate':'power','value':{'value':'12.50','unit':'W'},'conditions':{'temperature':{'value':'30','unit':'C'}},'evidence':[{'block_id':row,'quote':'12.50'}]}]},'test',{})
    result=app.extract_candidates(kb,dv,blocks,Model())
    row=result['result']['candidates'][-1]
    assert row['status']=='verified',row['issues']
    assert row['payload']['evidence'][0]['quote']==blocks[1]['text']


def test_build_manifest_carries_parse_gaps_for_consumers(build_env):
    from test_build import candidates
    store,build,review,p,kb,dv,block=build_env
    result=build.ingest(p,kb,dv,candidates(block))
    staged=build.finish(p,kb,dv,[r['id'] for r in result['candidates']],embed=False)
    with store.transaction(p,kb) as c:
        manifest=c.execute('SELECT manifest FROM builds WHERE kb_id=%s AND id=%s',(kb,staged)).fetchone()[0]
    assert manifest['document_coverage'][0]['coverage']['status']=='legacy_unassessed'
    assert 'units' not in manifest['document_coverage'][0]
    assert '解析覆盖' in manifest['wiki']['pages'][0]['text']


def test_inferred_layout_evidence_requires_review_before_publication(build_env):
    from test_build import candidates
    from gsm.sources import SourceService
    store,build,review,p,kb,dv,block=build_env
    with store.transaction(p,kb) as c:source=str(c.execute('SELECT id FROM source_versions WHERE kb_id=%s',(kb,)).fetchone()[0])
    parsed=SourceService(store).save_parse(p,kb,source,'inferred',[{'text':'设备 A 序号 001。设备 B 序号 002。A 连接 B。20℃时 A 功率 10.25 W。','requires_review':True,'unit_type':'table_row','representation':'native_layout_inference'}])
    result=build.ingest(p,kb,dv,candidates(parsed['blocks'][0]['id']))
    assert all(r['status']=='candidate' and 'LAYOUT_REVIEW_REQUIRED' in {i['code'] for i in r['issues']} for r in result['candidates'])


def test_unreviewed_derived_rows_do_not_bypass_gate_through_source_index(build_env):
    from test_build import candidates
    from gsm.sources import SourceService
    store,build,review,p,kb,dv,block=build_env
    with store.transaction(p,kb) as c:source=str(c.execute('SELECT id FROM source_versions WHERE kb_id=%s',(kb,)).fetchone()[0])
    extra=SourceService(store).save_parse(p,kb,source,'inferred',[{'text':'Ambiguous row','requires_review':True,'unit_type':'table_row'}],units=[],coverage={'status':'incomplete'})
    result=build.ingest(p,kb,dv,candidates(block))
    bid=build.finish(p,kb,dv,[c['id'] for c in result['candidates']],embed=False,source_parse_ids=[extra['id']])
    with store.transaction(p,kb) as c:
        manifest=c.execute('SELECT manifest FROM builds WHERE kb_id=%s AND id=%s',(kb,bid)).fetchone()[0]
        assert extra['blocks'][0]['id'] not in manifest['baseline_block_ids']
        assert len(manifest['document_coverage'])==2

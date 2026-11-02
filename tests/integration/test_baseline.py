from test_build import build_env,candidates
from gsm.releases import ReleaseService
from gsm.search import QueryService


def test_baseline_search_uses_original_blocks_and_stable_evidence(build_env):
    store,b,review,p,kb,dv,block=build_env
    result=b.ingest(p,kb,dv,candidates(block))
    bid=b.finish(p,kb,dv,[c['id'] for c in result['candidates']],embed=False)
    rel=ReleaseService(store).publish(p,kb,bid)
    hits=QueryService(store).baseline_search(p,kb,rel,'功率',use_vector=False)
    assert hits and hits[0]['evidence_id'].startswith('block:')
    original=ReleaseService(store).read_evidence(p,kb,rel,hits[0]['evidence_id'])
    assert '10.25 W' in original['text']


def test_consumer_hybrid_search_can_find_unextracted_original_text(build_env):
    from gsm.sources import SourceService
    store,b,review,p,kb,dv,block=build_env
    source=SourceService(store);path=store.settings.source_root/'original.txt'
    path.write_text('设备 A 序号 001。未被抽取的附注：U9 EEPROM Not Fitted，数量 0。')
    version=source.import_file(p,kb,'original.txt');parsed=source.save_parse(p,kb,version['id'],'test',[{'text':path.read_text(),'page':2}]);bid=parsed['blocks'][0]['id']
    data=[{'kind':'object','local_id':'a','type_id':'device','name':'设备 A','identity':{'serial':'001'},'evidence':[{'block_id':bid,'quote':'设备 A 序号 001'}]}]
    records=b.ingest(p,kb,dv,data);rel=ReleaseService(store).publish(p,kb,b.finish(p,kb,dv,[r['id'] for r in records['candidates']],embed=False))
    hits=QueryService(store).search(p,kb,rel,'U9',use_vector=False)
    original=next(hit for hit in hits if hit['kind']=='source_block')
    assert 'U9 EEPROM Not Fitted' in original['payload']['text']
    evidence=ReleaseService(store).read_evidence(p,kb,rel,original['evidence_ids'][0])
    assert evidence['locator']['page']==2

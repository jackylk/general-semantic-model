import pytest
from test_build import build_env,candidates
from gsm.releases import ReleaseService
from gsm.sources import SourceService
from gsm.search import QueryService
from gsm.errors import ProductError


def test_build_rejects_reference_outside_selected_objects(build_env):
    store,b,_,p,kb,dv,block=build_env
    result=b.ingest(p,kb,dv,candidates(block))
    with pytest.raises(ProductError) as exc:b.finish(p,kb,dv,[result['candidates'][2]['id']],embed=False)
    assert exc.value.code=='REFERENCE_CLOSURE_REQUIRED'


def test_withdrawn_support_is_not_in_new_wiki_or_source_index(build_env):
    store,b,_,p,kb,dv,block=build_env;src=SourceService(store)
    with store.transaction(p,kb) as conn:
        old=str(conn.execute('SELECT source_version_id FROM parse_versions WHERE kb_id=%s',(kb,)).fetchone()[0])
    path=store.settings.source_root/'second.txt';path.write_text('设备 A 序号 001。')
    second=src.import_file(p,kb,'second.txt');parsed=src.save_parse(p,kb,second['id'],'test',[{'text':path.read_text()}])
    data=candidates(block)[:1];data[0]['evidence'].append({'block_id':parsed['blocks'][0]['id'],'quote':'设备 A 序号 001'})
    result=b.ingest(p,kb,dv,data);src.withdraw(p,kb,old)
    bid=b.finish(p,kb,dv,[result['candidates'][0]['id']],embed=False);rel=ReleaseService(store).publish(p,kb,bid)
    wiki=QueryService(store).wiki(p,kb,rel)
    assert len(wiki['citations'])==1
    for ref in wiki['citations']:assert ReleaseService(store).read_evidence(p,kb,rel,ref['evidence_id'])['source_version_id']==second['id']
    with store.transaction(p,kb) as conn:assert conn.execute('SELECT count(*) FROM source_search_documents WHERE kb_id=%s AND build_id=%s',(kb,bid)).fetchone()[0]==1


def test_source_changes_after_build_do_not_publish_stale_files(build_env):
    store,b,_,p,kb,dv,block=build_env
    result=b.ingest(p,kb,dv,candidates(block));bid=b.finish(p,kb,dv,[r['id'] for r in result['candidates']],embed=False)
    with store.transaction(p,kb) as conn:source=str(conn.execute('SELECT source_version_id FROM parse_versions WHERE kb_id=%s',(kb,)).fetchone()[0])
    SourceService(store).withdraw(p,kb,source)
    with pytest.raises(ProductError) as exc:ReleaseService(store).publish(p,kb,bid)
    assert exc.value.code=='BUILD_STALE'


def test_identity_and_validity_cannot_be_verified_from_unrelated_quote(build_env):
    store,b,_,p,kb,dv,block=build_env
    data=candidates(block)[:1];data[0]['identity']['serial']='999';data[0]['valid_from']='not-a-date'
    result=b.ingest(p,kb,dv,data)['candidates'][0]
    assert result['status']=='candidate'
    assert {'IDENTITY_NOT_IN_EVIDENCE','INVALID_VALIDITY'}<={i['code'] for i in result['issues']}

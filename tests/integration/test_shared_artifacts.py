from gsm.workspaces import initialize_kb
from gsm.application import Application
from gsm.search import QueryService
from test_build import DOMAIN,candidates
import json


def test_product_publication_exports_versioned_wiki_records_graph_into_shared_root(tmp_path):
    root=tmp_path/'shared-kb';info=initialize_kb(root,'共享库');app=Application(info['roles']['producer']['credentials']);kb=info['kb_id']
    text='设备 A 序号 001。设备 B 序号 002。A 连接 B。20℃时 A 功率 10.25 W。';(root/'documents/a.txt').write_text(text)
    source=app.sources.import_file(app.principal,kb,'a.txt');parse=app.sources.save_parse(app.principal,kb,source['id'],'test',[{'text':text}])
    domain=app.build.submit_domain(app.principal,kb,DOMAIN);result=app.build.ingest(app.principal,kb,domain,candidates(parse['blocks'][0]['id']))
    bid=app.build.finish(app.principal,kb,domain,[r['id'] for r in result['candidates']],embed=False)
    release=app.publish(kb,bid)
    directory=root/'releases'/release
    assert (directory/'semantic/records.json').exists()
    assert len(json.loads((directory/'semantic/graph.json').read_text())['edges'])==1
    assert len(list((root/'wiki').glob('*.md')))>=2
    assert json.loads((root/'CURRENT.json').read_text())['release_id']==release
    reader=Application(info['roles']['consumer']['credentials'])
    assert QueryService(reader.store).wiki(reader.principal,kb,release)['pages']
    assert app.publish(kb,bid)==release


def test_uncommitted_artifact_preparation_is_not_visible_in_shared_releases(tmp_path,monkeypatch):
    import pytest
    import gsm.artifacts as artifacts
    from gsm.errors import ProductError
    root=tmp_path/'kb';info=initialize_kb(root,'prepare rollback');app=Application(info['roles']['producer']['credentials']);kb=info['kb_id']
    text='设备 A 序号 001。设备 B 序号 002。A 连接 B。20℃时 A 功率 10.25 W。';(root/'documents/a.txt').write_text(text)
    v=app.sources.import_file(app.principal,kb,'a.txt');parsed=app.sources.save_parse(app.principal,kb,v['id'],'test',[{'text':text}]);dv=app.build.submit_domain(app.principal,kb,DOMAIN)
    data=app.build.ingest(app.principal,kb,dv,candidates(parsed['blocks'][0]['id']));bid=app.build.finish(app.principal,kb,dv,[r['id'] for r in data['candidates']],embed=False)
    original=artifacts.prepare
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise ProductError('SYNTHETIC_PRECOMMIT_FAILURE','synthetic failure')
    monkeypatch.setattr(artifacts,'prepare',fail)
    with pytest.raises(ProductError):app.publish(kb,bid)
    assert list((root/'releases').iterdir())==[]
    with app.store.transaction(app.principal,kb) as c:assert c.execute('SELECT current_release FROM knowledge_bases WHERE id=%s',(kb,)).fetchone()[0] is None


def test_retrying_older_build_keeps_database_and_files_current_at_newer_release(tmp_path):
    root=tmp_path/'kb';info=initialize_kb(root,'idempotent publication');app=Application(info['roles']['producer']['credentials']);kb=info['kb_id']
    text='设备 A 序号 001。设备 B 序号 002。A 连接 B。20℃时 A 功率 10.25 W。';(root/'documents/a.txt').write_text(text)
    v=app.sources.import_file(app.principal,kb,'a.txt');parsed=app.sources.save_parse(app.principal,kb,v['id'],'test',[{'text':text}]);dv=app.build.submit_domain(app.principal,kb,DOMAIN)
    data=app.build.ingest(app.principal,kb,dv,candidates(parsed['blocks'][0]['id']));ids=[r['id'] for r in data['candidates']]
    a=app.build.finish(app.principal,kb,dv,ids,embed=False);ra=app.publish(kb,a)
    b=app.build.finish(app.principal,kb,dv,ids[:2],embed=False);rb=app.publish(kb,b)
    assert app.publish(kb,a)==ra
    assert json.loads((root/'CURRENT.json').read_text())['release_id']==rb
    app.rollback(kb,ra)
    assert json.loads((root/'CURRENT.json').read_text())['release_id']==ra

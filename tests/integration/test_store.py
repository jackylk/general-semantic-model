from pathlib import Path
from uuid import uuid4
import psycopg
import pytest
from gsm.auth import Principal
from gsm.config import Settings
from gsm.store import Store
from gsm.sources import SourceService
from gsm.releases import ReleaseService
from gsm.errors import ProductError


@pytest.fixture
def env(tmp_path):
    settings = Settings.load()
    settings.source_root = tmp_path / 'imports'
    settings.file_root = tmp_path / 'files'
    settings.source_root.mkdir()
    store = Store(settings)
    store.migrate()
    kb, other = str(uuid4()), str(uuid4())
    dev = Principal('developer', frozenset([kb]))
    reader = Principal('consumer', frozenset([kb]))
    store.create_kb(dev, kb, 'test')
    return store, SourceService(store), ReleaseService(store), dev, reader, kb, other


def test_cross_kb_denied_and_database_role_is_readonly(env):
    store, _, _, dev, reader, kb, other = env
    with pytest.raises(ProductError, match='授权'):
        with store.transaction(dev, other): pass
    with store.transaction(reader, kb) as conn:
        assert conn.execute('select count(*) from knowledge_bases').fetchone()[0] == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("insert into records(kb_id,kind,payload) values (%s,'object','{}')", (kb,))


def test_source_root_and_symlink_escape_denied(env, tmp_path):
    store, sources, _, dev, reader, kb, _ = env
    outside = tmp_path / 'outside.txt'; outside.write_text('secret')
    (store.settings.source_root / 'link').symlink_to(outside)
    for path in ['../outside.txt', 'link', str(outside)]:
        with pytest.raises(ProductError): sources.import_file(dev, kb, path)
    with pytest.raises(ProductError): sources.import_file(reader, kb, 'missing.txt')


def import_evidence(env, text):
    store, sources, releases, dev, reader, kb, _ = env
    (store.settings.source_root/'sample.txt').write_text(text)
    version = sources.import_file(dev, kb, 'sample.txt')
    parsed = sources.save_parse(dev, kb, version['id'], 'test-parser-v1', [{'text': text, 'page': 1}])
    record = store.add_record(dev, kb, 'assertion', {'subject': 'a', 'value': text}, status='verified')
    evidence = sources.link_evidence(dev, kb, record, parsed['blocks'][0]['id'], text)
    return version, parsed, record, evidence


def test_fixed_evidence_release_and_rollback(env):
    store, sources, releases, dev, reader, kb, _ = env
    v1, p1, r1, e1 = import_evidence(env, '旧版金额 100 元')
    b1 = releases.stage(dev, kb, [r1], ready=True)
    rel1 = releases.publish(dev, kb, b1)
    v2, p2, r2, e2 = import_evidence(env, '新版金额 200 元')
    rel2 = releases.publish(dev, kb, releases.stage(dev, kb, [r2], ready=True))
    assert releases.read_evidence(reader, kb, rel1, e1)['text'] == '旧版金额 100 元'
    with pytest.raises(ProductError): releases.read_evidence(reader, kb, rel2, e1)
    releases.rollback(dev, kb, rel1)
    assert releases.current(reader, kb) == rel1
    assert releases.read_evidence(reader, kb, rel2, e2)['text'] == '新版金额 200 元'
    with store.transaction(dev, kb) as conn:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            conn.execute('update source_blocks set text=%s where id=%s', ('changed', p1['blocks'][0]['id']))


def test_publish_gate_and_multiple_supports(env):
    store, sources, releases, dev, reader, kb, _ = env
    v1, p1, r1, e1 = import_evidence(env, '共同事实')
    (store.settings.source_root/'other.txt').write_text('另一份共同事实')
    v2=sources.import_file(dev,kb,'other.txt')
    p2=sources.save_parse(dev,kb,v2['id'],'test',[{'text':'另一份共同事实','page':1}])
    sources.link_evidence(dev,kb,r1,p2['blocks'][0]['id'],'共同事实')
    sources.withdraw(dev,kb,v1['id'])
    assert sources.active_support_count(dev,kb,r1) == 1
    b = releases.stage(dev,kb,[r1],ready=False)
    with pytest.raises(ProductError): releases.publish(dev,kb,b)
    assert releases.current(reader,kb) is None
    bare=store.add_record(dev,kb,'assertion',{'value':'unsupported'},status='verified')
    with pytest.raises(ProductError): releases.publish(dev,kb,releases.stage(dev,kb,[bare],ready=True))
    with pytest.raises(ProductError): releases.publish(reader,kb,b)

import json,subprocess,sys
from pathlib import Path
import pytest
from gsm.workspaces import initialize_kb
from gsm.shared_runtime import services,stop_services,role_policy


def test_shared_services_keep_secrets_outside_kb_and_roles_scoped(tmp_path,monkeypatch):
    from urllib.request import Request,urlopen
    from urllib.error import HTTPError
    root=tmp_path/'kb';info=initialize_kb(root,'shared')
    assert 'credentials' not in (root/'KNOWLEDGE_BASE.json').read_text()
    try:
        state=services(root)
        assert state['producer']['url']!=state['consumer']['url']
        for role in ('producer','consumer'):
            req=Request(state[role]['url'],headers={'Authorization':'Bearer '+state[role]['token']})
            # Authenticated GET is unsupported or SSE; use wrong-role tokens for deterministic checks.
            other='producer' if role=='consumer' else 'consumer'
            with pytest.raises(HTTPError) as exc:urlopen(Request(state[role]['url'],headers={'Authorization':'Bearer '+state[other]['token']}),timeout=3)
            assert exc.value.code==401
        monkeypatch.setenv('HTTP_PROXY','http://127.0.0.1:1')
        monkeypatch.setenv('NO_PROXY','')
        again=services(root)
        assert again['consumer']['pid']==state['consumer']['pid']
    finally:stop_services(root)


@pytest.mark.skipif(sys.platform!='darwin',reason='macOS OS boundary')
def test_shared_role_os_boundaries_are_enforced(tmp_path):
    root=tmp_path/'kb';initialize_kb(root,'boundary')
    (root/'documents/raw.txt').write_text('private source')
    for role in ('producer','consumer'):
        policy=tmp_path/(role+'.sb');policy.write_text(role_policy(root,role))
        prefix=['sandbox-exec','-f',str(policy)]
        own=root/'reports'/role/'allowed.txt'
        assert subprocess.run(prefix+['touch',str(own)],capture_output=True).returncode==0
        assert subprocess.run(prefix+['touch',str(Path.cwd()/'runtime/should-not-exist.txt')],capture_output=True).returncode!=0
        assert subprocess.run(prefix+['touch',str(root/'wiki/corrupt.md')],capture_output=True).returncode!=0
        assert subprocess.run(prefix+['cat',str(root/'start-producer.py')],capture_output=True).returncode==0
        if role=='consumer':assert subprocess.run(prefix+['cat',str(root/'documents/raw.txt')],capture_output=True).returncode!=0


@pytest.mark.skipif(sys.platform!='darwin',reason='macOS OS boundary')
def test_producer_cannot_read_private_benchmark_but_consumer_can(tmp_path):
    benchmark=tmp_path/'private-evaluation';benchmark.mkdir();file=benchmark/'synthetic-private.txt';file.write_text('Synthetic isolation fixture only')
    root=tmp_path/'shared';initialize_kb(root,'isolated',producer_denied_paths=[benchmark])
    for role in ('producer','consumer'):
        policy=tmp_path/(role+'.sb');policy.write_text(role_policy(root,role))
        result=subprocess.run(['sandbox-exec','-f',str(policy),'cat',str(file)],capture_output=True)
        assert (result.returncode!=0)==(role=='producer')


@pytest.mark.skipif(sys.platform!='darwin',reason='macOS OS boundary')
def test_operator_can_keep_iteration_controls_private_from_both_clients(tmp_path):
    private=tmp_path/'operator-iteration';private.mkdir();file=private/'state.json';file.write_text('{}')
    root=tmp_path/'kb';initialize_kb(root,'shared',producer_denied_paths=[private],consumer_denied_paths=[private])
    for role in ('producer','consumer'):
        policy=tmp_path/(role+'.sb');policy.write_text(role_policy(root,role))
        assert subprocess.run(['sandbox-exec','-f',str(policy),'cat',str(file)],capture_output=True).returncode!=0


@pytest.mark.skipif(sys.platform!='darwin',reason='macOS OS boundary')
def test_external_evaluation_results_are_consumer_writable_producer_unreadable(tmp_path):
    root=tmp_path/'kb';out=tmp_path/'evaluation-results'
    initialize_kb(root,'results',consumer_results_root=out)
    file=out/'synthetic-summary.json';file.write_text('{}')
    for role in ('producer','consumer'):
        policy=tmp_path/(role+'.sb');policy.write_text(role_policy(root,role));prefix=['sandbox-exec','-f',str(policy)]
        read=subprocess.run(prefix+['cat',str(file)],capture_output=True)
        write=subprocess.run(prefix+['touch',str(out/(role+'.txt'))],capture_output=True)
        assert (read.returncode==0)==(role=='consumer')
        assert (write.returncode==0)==(role=='consumer')


def test_client_environment_does_not_inherit_backend_credentials(tmp_path):
    from gsm.shared_runtime import client_environment
    env=client_environment(tmp_path,'own-role-token',{'PATH':'/bin','HOME':'/synthetic-home','HTTPS_PROXY':'http://127.0.0.1:7897','GSM_DB_PASSWORD':'synthetic-db-secret','GSM_CREDENTIAL_SIGNING_KEY':'synthetic-signing-secret','DEEPSEEK_API_KEY':'synthetic-backend-secret'})
    assert not {'GSM_DB_PASSWORD','GSM_CREDENTIAL_SIGNING_KEY','DEEPSEEK_API_KEY'} & set(env)
    assert env['GSM_ROLE_TOKEN']=='own-role-token'
    assert '127.0.0.1' in env['NO_PROXY']

import json,subprocess,os
from pathlib import Path
from gsm.workspaces import provision


def test_generated_launcher_passes_role_config_without_global_edits(tmp_path):
    workspace=tmp_path/'spaces';result=provision(workspace)
    fake=tmp_path/'codex';fake.write_text('#!/usr/bin/env python3\nimport sys,json\nprint(json.dumps(sys.argv[1:]))\n');fake.chmod(0o755)
    dev=Path(result['workspaces']['developer'])
    runner=dev/'start-codex.py'
    completed=subprocess.run(['python3',str(runner),'hello world'],env={**os.environ,'PATH':str(tmp_path)+':'+os.environ['PATH']},capture_output=True,text=True,check=True)
    args=json.loads(completed.stdout)
    assert 'hello world'==args[-1]
    assert args[args.index('--sandbox')+1]=='workspace-write'
    assert 'sandbox_workspace_write.writable_roots=[]' in args
    assert any(a.startswith('mcp_servers.gsm_developer.command=') for a in args)
    assert not any('gsm_consumer' in a for a in args)


def test_new_workspace_starts_with_empty_inbox_and_no_external_source(tmp_path):
    from gsm.credentials import read_credentials
    workspace=tmp_path/'new';result=provision(workspace)
    dev=Path(result['workspaces']['developer'])
    profile=read_credentials(dev/'credentials.json')
    assert Path(profile['source_root'])==dev/'documents'
    assert list((dev/'documents').iterdir())==[]
    assert 'automotive' not in json.dumps(profile)


def test_profile_without_documents_does_not_inherit_global_imports(tmp_path):
    from uuid import uuid4
    import pytest
    from gsm.credentials import write_credentials
    from gsm.application import Application
    from gsm.errors import ProductError
    kb=str(uuid4());profile=tmp_path/'profile.json';write_credentials(profile,'developer',[kb])
    app=Application(profile)
    assert app.store.settings.source_root is None
    with pytest.raises(ProductError) as exc:app.sources.import_file(app.principal,kb,'anything.txt')
    assert exc.value.code=='SOURCE_NOT_CONFIGURED'

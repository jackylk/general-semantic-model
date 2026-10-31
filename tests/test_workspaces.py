import json,subprocess,os
from pathlib import Path
from gsm.workspaces import provision


def test_generated_launcher_passes_role_config_without_global_edits(tmp_path):
    workspace=tmp_path/'spaces';result=provision(workspace,tmp_path/'sources')
    fake=tmp_path/'codex';fake.write_text('#!/usr/bin/env python3\nimport sys,json\nprint(json.dumps(sys.argv[1:]))\n');fake.chmod(0o755)
    dev=Path(result['workspaces']['developer'])
    runner=dev/'start-codex.py'
    completed=subprocess.run(['python3',str(runner),'hello world'],env={**os.environ,'PATH':str(tmp_path)+':'+os.environ['PATH']},capture_output=True,text=True,check=True)
    args=json.loads(completed.stdout)
    assert 'hello world'==args[-1]
    assert any(a.startswith('mcp_servers.gsm_developer.command=') for a in args)
    assert not any('gsm_consumer' in a for a in args)

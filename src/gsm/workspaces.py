import json,sys
from pathlib import Path
from uuid import uuid4
from .errors import ProductError


def provision(root:Path,source_root:Path):
    root=root.resolve();product=Path.cwd();kb_id=str(uuid4())
    if root.exists() and any(root.iterdir()):raise ProductError('WORKSPACE_EXISTS','工作区非空，拒绝覆盖')
    result={}
    for role,server in [('developer','gsm_developer'),('consumer','gsm_consumer')]:
        path=root/role;path.mkdir(parents=True);(path/'.codex').mkdir()
        from .credentials import write_credentials
        credential=path/'credentials.json';write_credentials(credential,role,[kb_id],source_root.resolve())
        config=f'[mcp_servers.{server}]\ncommand = {json.dumps(sys.executable)}\nargs = {json.dumps(["-m","gsm.cli","serve","--credentials",str(credential)])}\ncwd = {json.dumps(str(product))}\nstartup_timeout_sec = 20\ntool_timeout_sec = 300\n'
        (path/'.codex/config.toml').write_text(config)
        if role=='developer':
            for file in ('AGENTS.md','START.md'):(path/file).write_text((product/'templates/developer-workspace'/file).read_text())
            (path/'domain').mkdir()
        else:
            (path/'AGENTS.md').write_text((product/'docs/consumer-guide.md').read_text()+f'\n本工作区授权知识库 ID：{kb_id}。\n')
        (path/'start-codex.py').write_text((product/'templates/developer-workspace/start-codex.py').read_text())
        (path/'WORKSPACE.json').write_text(json.dumps({'kb_id':kb_id,'role':role},indent=2)+'\n')
        result[role]=str(path)
    return {'kb_id':kb_id,'workspaces':result}

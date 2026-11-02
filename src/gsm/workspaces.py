import json,sys
from pathlib import Path
from uuid import uuid4
from .errors import ProductError


def provision(root:Path):
    root=root.resolve();product=Path.cwd().resolve();kb_id=str(uuid4())
    if root.is_relative_to(product):
        raise ProductError('INVALID_WORKSPACE_ROOT','知识库工作区必须位于产品目录之外，请使用独立目录')
    if root.exists() and any(root.iterdir()):raise ProductError('WORKSPACE_EXISTS','工作区非空，拒绝覆盖')
    result={}
    for role,server in [('developer','gsm_developer'),('consumer','gsm_consumer')]:
        path=root/role;path.mkdir(parents=True);(path/'.codex').mkdir()
        from .credentials import write_credentials
        inbox=path/'documents'
        if role=='developer':inbox.mkdir()
        credential=path/'credentials.json';write_credentials(credential,role,[kb_id],inbox if role=='developer' else None)
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


def initialize_kb(root:Path,name:str):
    """Product-only initialization: no Codex, extraction or model calls."""
    from .config import Settings
    from .store import Store
    from .auth import Principal
    from .credentials import write_credentials
    root=root.expanduser().resolve();product=Path.cwd().resolve()
    if root.is_relative_to(product):raise ProductError('INVALID_WORKSPACE_ROOT','知识库目录必须位于产品目录之外')
    if not name.strip():raise ProductError('INVALID_NAME','知识库名称不能为空')
    if root.exists() and any(root.iterdir()):raise ProductError('WORKSPACE_EXISTS','知识库目录非空，拒绝覆盖')
    kb_id=str(uuid4());store=Store(Settings.load());store.migrate()
    # Both frontends use one root. Profiles are operator state, not domain assets.
    operator=store.settings.file_root.parent/'operators'/kb_id;operator.mkdir(parents=True,mode=0o700);operator.chmod(0o700)
    root.mkdir(parents=True,exist_ok=True)
    for folder in ('documents','domain','wiki','releases','reports'):(root/folder).mkdir()
    roles={}
    for role,internal in [('producer','developer'),('consumer','consumer')]:
        credential=operator/(role+'.json');write_credentials(credential,internal,[kb_id],root/'documents' if role=='producer' else None)
        server='gsm_'+internal
        configuration={'command':sys.executable,'args':['-m','gsm.cli','serve','--credentials',str(credential)],'cwd':str(product),'startup_timeout_sec':20,'tool_timeout_sec':300}
        launcher='''#!/usr/bin/env python3
import os,sys,json
from pathlib import Path
root=Path(__file__).resolve().parent
command=['codex','--cd',str(root),'--sandbox',MODE,'--ask-for-approval','never','-c','sandbox_workspace_write.writable_roots=[]']
for key,value in SERVER.items():command+=['-c','mcp_servers.'+NAME+'.'+key+'='+json.dumps(value)]
os.execvp(command[0],command+sys.argv[1:])
'''.replace('MODE',repr('workspace-write' if role=='producer' else 'read-only')).replace('SERVER',repr(configuration)).replace('NAME',repr(server))
        (root/f'start-{role}.py').write_text(launcher)
        roles[role]={'workspace':str(root),'credentials':str(credential),'launcher':str(root/f'start-{role}.py')}
    store.create_kb(Principal('developer',frozenset([kb_id])),kb_id,name)
    manifest={'format_version':1,'kb_id':kb_id,'name':name,'workspace':str(root),'product':str(product),'initialization':'product_command_no_codex_no_llm','status':'empty','roles':roles}
    (root/'KNOWLEDGE_BASE.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (root/'AGENTS.md').write_text('''# 共用知识库工作区

两个窗口共用本目录，依据当前连接的MCP权限区分角色。只连接gsm_developer时是producer：添加用户提供的文档、定义领域并调用产品完成构建与发布。只连接gsm_consumer时是consumer：只读已发布知识库并问答，不尝试获取建库凭据、修改领域或发布。不得启用另一个角色的MCP。两个角色都不得修改产品软件目录或固定Schema；遇到产品缺口反馈第一窗口。

知识库ID见KNOWLEDGE_BASE.json。新库没有领域或预置文档；用户说“我要开始创建知识库”时，producer先调用discover_spec并按指南引导用户提供资料。consumer固定release_id取证，未发布时等待建库者。
''')
    return manifest

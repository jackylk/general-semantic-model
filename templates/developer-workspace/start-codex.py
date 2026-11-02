#!/usr/bin/env python3
"""Use explicit per-session MCP config without changing global Codex settings."""
import json,os,sys,tomllib
from pathlib import Path

root=Path(__file__).resolve().parent
config=tomllib.loads((root/'.codex/config.toml').read_text())
command=['codex','--cd',str(root),'--sandbox','workspace-write','--ask-for-approval','on-request','-c','sandbox_workspace_write.writable_roots=[]']
for name,server in config['mcp_servers'].items():
    for key,value in server.items():command+=['-c',f'mcp_servers.{name}.{key}='+json.dumps(value)]
os.execvp(command[0],command+sys.argv[1:])

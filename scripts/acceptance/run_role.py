"""Run a real fresh/resumed Codex role under an OS product-access deny policy."""
import argparse,json,os,subprocess
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('role',choices=['developer','consumer']);p.add_argument('phase');p.add_argument('--prompt-file',type=Path);p.add_argument('--resume');a=p.parse_args()
    root=Path(Path('runtime/acceptance-root.txt').read_text());control=root/'control';run=json.loads((control/'run.json').read_text());workspace=root/a.role
    name='gsm_'+a.role;port=8241 if a.role=='developer' else 8242
    command=['sandbox-exec','-f',str(control/f'{a.role}.sb'),run['codex_binary']]
    for other in run['global_mcp_names']:command+=['-c',f'mcp_servers.{other}.enabled=false']
    for plugin in run.get('global_plugin_names',[]):command+=['-c','plugins.'+json.dumps(plugin)+'.enabled=false']
    overrides={f'mcp_servers.{name}.default_tools_approval_mode':'auto',f'mcp_servers.{name}.enabled':True,f'mcp_servers.{name}.url':f'http://127.0.0.1:{port}/mcp',f'mcp_servers.{name}.bearer_token_env_var':'GSM_ACCEPTANCE_TOKEN',f'mcp_servers.{name}.tool_timeout_sec':300}
    for key,value in overrides.items():command+=['-c',key+'='+json.dumps(value)]
    command+=['exec','--skip-git-repo-check','--json','--color','never']
    if a.resume:command+=['resume',a.resume]
    else:command+=['--approve-for-me','--cd',str(workspace)]
    command+=['--output-last-message',str(workspace/f'{a.phase}-answer.md'),'-']
    prompt=a.prompt_file.read_text() if a.prompt_file else '我要开始创建知识库'
    env={**os.environ,'PWD':str(workspace),'HTTPS_PROXY':run.get('proxy',''),'HTTP_PROXY':run.get('proxy',''),'NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost','GSM_ACCEPTANCE_TOKEN':(control/f'{a.role}.token').read_text().strip()}
    with (control/f'{a.role}-{a.phase}.jsonl').open('w') as out,(control/f'{a.role}-{a.phase}.stderr').open('w') as err:
        completed=subprocess.run(command,input=prompt,text=True,cwd=workspace,env=env,stdout=out,stderr=err)
    print(json.dumps({'role':a.role,'phase':a.phase,'exit_code':completed.returncode}))
if __name__=='__main__':main()

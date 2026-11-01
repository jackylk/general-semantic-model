import json,subprocess,sys,os,signal
from pathlib import Path

r=Path(Path('runtime/acceptance-root.txt').read_text());c=r/'control';old=c/'pids.json'
if old.exists():
 for pid in json.loads(old.read_text()).values():
  try:os.kill(pid,signal.SIGINT)
  except ProcessLookupError:pass
pids={}
for role,port in [('developer',8241),('consumer',8242)]:
 log=(c/f'{role}-server.log').open('a')
 p=subprocess.Popen([sys.executable,'scripts/acceptance/serve_role.py','--credentials',str(c/f'{role}.credentials.json'),'--token-file',str(c/f'{role}.token'),'--log',str(c/f'{role}-mcp.jsonl'),'--port',str(port)],stdout=log,stderr=log,start_new_session=True);pids[role]=p.pid
log=(c/'worker.log').open('a');p=subprocess.Popen([sys.executable,'-m','gsm.cli','worker','--credentials',str(c/'developer.credentials.json')],stdout=log,stderr=log,start_new_session=True);pids['worker']=p.pid
old.write_text(json.dumps(pids));print(pids)

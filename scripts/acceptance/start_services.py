import argparse,json,subprocess,sys,os,signal
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('--no-worker',action='store_true');args=parser.parse_args()
r=Path(Path('runtime/acceptance-root.txt').read_text());c=r/'control';old=c/'pids.json'
if old.exists():
 for pid in json.loads(old.read_text()).values():
  try:os.kill(pid,signal.SIGINT)
  except ProcessLookupError:pass
pids={}
for role,port in [('developer',8241),('consumer',8242)]:
 log=(c/f'{role}-server.log').open('a')
 p=subprocess.Popen([sys.executable,'scripts/acceptance/serve_role.py','--credentials',str(c/f'{role}.credentials.json'),'--token-file',str(c/f'{role}.token'),'--log',str(c/f'{role}-mcp.jsonl'),'--port',str(port)],stdout=log,stderr=log,start_new_session=True);pids[role]=p.pid
if not args.no_worker:
 log=(c/'worker.log').open('a');p=subprocess.Popen([sys.executable,'-m','gsm.cli','worker','--credentials',str(c/'developer.credentials.json')],stdout=log,stderr=log,start_new_session=True);pids['worker']=p.pid
old.write_text(json.dumps(pids));print(pids)

import time,urllib.request,urllib.error
for port in (8241,8242):
 for attempt in range(100):
  try:
   urllib.request.urlopen(f'http://127.0.0.1:{port}/mcp',timeout=1)
   break
  except urllib.error.HTTPError as error:
   if error.code==401:break
  except OSError:pass
  time.sleep(0.1)
 else:raise SystemExit('test MCP did not become ready')

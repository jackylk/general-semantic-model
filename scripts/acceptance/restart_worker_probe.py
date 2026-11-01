"""Interrupt only the dedicated test worker and prove task identity survives restart."""
import asyncio,json,subprocess,sys,os,signal,time
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
 r=Path(Path('runtime/acceptance-root.txt').read_text());c=r/'control';run=json.loads((c/'run.json').read_text());submissions=[]
 for l in (c/'developer-phase4.jsonl').read_text().splitlines():
  event=json.loads(l);item=event.get('item',{})
  if event['type']=='item.started' and item.get('tool')=='preview_extraction':submissions.append(item['arguments'])
 async with httpx.AsyncClient(headers={'Authorization':'Bearer '+(c/'developer.token').read_text().strip()},trust_env=False,timeout=30) as http:
  async with streamable_http_client('http://127.0.0.1:8241/mcp',http_client=http) as (read,write,_):
   async with ClientSession(read,write) as client:
    await client.initialize();target=None
    for args in submissions:
     response=await client.call_tool('preview_extraction',args);task=json.loads(response.content[0].text)
     if task.get('status')=='running':target=task;target_args=args;break
    if target is None:print({'probe':'no_running_task_yet'});return
    duplicate=await client.call_tool('preview_extraction',target_args);duplicate=json.loads(duplicate.content[0].text)
    different={**target_args,'source_version_ids':[]};conflict=json.loads((await client.call_tool('preview_extraction',different)).content[0].text)
    pids=json.loads((c/'pids.json').read_text());pid=pids['worker'];command=subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True)
    if str(c/'developer.credentials.json') not in command:raise SystemExit('refuse to stop non-test worker')
    os.kill(pid,signal.SIGINT);await asyncio.sleep(0.5)
    during=json.loads((await client.call_tool('get_task',{'kb_id':run['kb_id'],'task_id':target['id']})).content[0].text)
    log=(c/'worker.log').open('a');worker=subprocess.Popen([sys.executable,'-m','gsm.cli','worker','--credentials',str(c/'developer.credentials.json')],stdout=log,stderr=log,start_new_session=True);pids['worker']=worker.pid;(c/'pids.json').write_text(json.dumps(pids))
    record={'task_id':target['id'],'before_status':target['status'],'during_status':during['status'],'input_payload_preserved':target['payload']==during['payload'],'same_idempotency_task_id':duplicate.get('id')==target['id'],'different_payload_rejected':conflict.get('error',{}).get('code')=='IDEMPOTENCY_CONFLICT','old_worker_pid':pid,'new_worker_pid':worker.pid,'after_status':'pending_verification'}
    (c/'worker-restart-probe.json').write_text(json.dumps(record,indent=2));print(record)
if __name__=='__main__':asyncio.run(main())

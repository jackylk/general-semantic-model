"""Standard-library, readonly MCP timing fixture. Token comes only from the role environment."""
import argparse,json,os,time,urllib.request
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--endpoint',default='http://127.0.0.1:8242/mcp');args=p.parse_args()
data=json.loads(args.input.read_text());opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));sequence=0

def rpc(method,params,case=None):
    global sequence
    sequence+=1
    headers={'Authorization':'Bearer '+os.environ['GSM_ACCEPTANCE_TOKEN'],'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-06-18'}
    if case:headers['X-GSM-Test-Case']=case
    request=urllib.request.Request(args.endpoint,data=json.dumps({'jsonrpc':'2.0','id':sequence,'method':method,'params':params}).encode(),headers=headers)
    with opener.open(request,timeout=360) as response:return json.load(response)

rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'readonly-acceptance-timing','version':'1'}})
with args.output.open('w') as output:
    for question in data['questions']:
        started=datetime.now(timezone.utc).isoformat();clock=time.perf_counter()
        try:
            response=rpc('tools/call',{'name':'retrieve','arguments':{'kb_id':data['kb_id'],'release_id':data['release_id'],'question':question['question']}},question['id'])
            content=response.get('result',{}).get('content',[])
            result=json.loads(content[0]['text']) if content else response
        except Exception as error:result={'transport_error':type(error).__name__}
        row={'id':question['id'],'question':question['question'],'kb_id':data['kb_id'],'release_id':data['release_id'],'started_at':started,'elapsed_ms':round((time.perf_counter()-clock)*1000,3),'response':result}
        output.write(json.dumps(row,ensure_ascii=False)+'\n');output.flush();print(json.dumps({'id':row['id'],'elapsed_ms':row['elapsed_ms'],'status':result.get('status'),'error':result.get('error',{}).get('code') or result.get('transport_error')},ensure_ascii=False),flush=True)

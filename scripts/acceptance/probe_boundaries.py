"""C1 negative protocol checks, using public endpoints only."""
import asyncio,json,uuid,urllib.request,urllib.error
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
 root=Path(Path('runtime/acceptance-root.txt').read_text());c=root/'control';run=json.loads((c/'run.json').read_text());token=(c/'consumer.token').read_text().strip();results={}
 headers={'Authorization':'Bearer '+token}
 async with httpx.AsyncClient(headers=headers,timeout=30,trust_env=False) as http:
  async with streamable_http_client('http://127.0.0.1:8242/mcp',http_client=http) as (read,write,_):
   async with ClientSession(read,write) as client:
    await client.initialize();tools={t.name for t in (await client.list_tools()).tools}
    results['consumer_write_tools_absent']=not ({'publish','register_source','review_candidates'} & tools)
    for name,args in [('publish',{'kb_id':run['kb_id'],'build_id':str(uuid.uuid4())}),('register_source',{'kb_id':run['kb_id'],'relative_path':'x'}),('review_candidates',{'kb_id':run['kb_id'],'candidate_ids':[],'decision':'confirm','reason':'test'})]:
     response=await client.call_tool(name,args);results['direct_'+name+'_denied']=bool(response.isError)
    response=await client.call_tool('describe_kb',{'kb_id':str(uuid.uuid4())});data=json.loads(response.content[0].text)
    results['foreign_kb_denied']=data.get('error',{}).get('code')=='FORBIDDEN'
 try:
  req=urllib.request.Request('http://127.0.0.1:8241/mcp',headers=headers)
  urllib.request.urlopen(req,timeout=5);results['consumer_token_cannot_access_developer']=False
 except urllib.error.HTTPError as e:results['consumer_token_cannot_access_developer']=e.code==401
 for role in ('developer','consumer'):
  import subprocess
  prefix=['sandbox-exec','-f',str(c/f'{role}.sb')]
  tests={'product_code_read':Path('src/gsm/domain.py').resolve(),'private_reference_read':c/'gold.json'}
  for key,path in tests.items():
   p=subprocess.run(prefix+['/bin/cat',str(path)],capture_output=True);results[role+'_'+key+'_denied']=p.returncode!=0
  p=subprocess.run(prefix+['/usr/bin/touch',str(Path('runtime/acceptance-write-canary.txt').resolve())],capture_output=True);results[role+'_product_write_denied']=p.returncode!=0
 (c/'boundary-results.json').write_text(json.dumps(results,indent=2));print(results)
 if not all(results.values()):raise SystemExit('boundary probe failed')
if __name__=='__main__':asyncio.run(main())

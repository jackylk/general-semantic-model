"""Public-interface lifecycle audit of independently generated role artifacts."""
import asyncio,json
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
async def main():
 r=Path(Path('runtime/acceptance-root.txt').read_text());c=r/'control';run=json.loads((c/'run.json').read_text());life=json.loads((r/'developer/lifecycle.json').read_text());wiki=json.loads((r/'developer/wiki-regression.json').read_text());handoff=json.loads((r/'developer/handoff.json').read_text());checks={};details={}
 async with httpx.AsyncClient(headers={'Authorization':'Bearer '+(c/'consumer.token').read_text().strip()},trust_env=False,timeout=60) as http:
  async with streamable_http_client('http://127.0.0.1:8242/mcp',http_client=http) as (rd,wr,_):
   async with ClientSession(rd,wr) as cli:
    await cli.initialize()
    async def call(name,**args):return json.loads((await cli.call_tool(name,{'kb_id':run['kb_id'],**args})).content[0].text)
    v1=await call('get_release',release_id=life['V1']);v2=await call('get_release',release_id=life['V2']);v3=await call('get_release',release_id=wiki['V3']);current=await call('describe_kb')
    old=json.loads(life['old_evidence_before']['content'][0]['text']);now=await call('read_evidence',release_id=life['V1'],evidence_id=old['id']);checks['old_v1_evidence_immutable']=old==now
    checks['latest_current_matches_handoff']=current['current_release']==handoff['release_id'];checks['v3_same_record_set_as_v2']=v2['manifest']['record_ids']==v3['manifest']['record_ids'];checks['v3_same_domain_as_v2']=v2['manifest']['domain_version_id']==v3['manifest']['domain_version_id']
    newsource=life['fixture']['new_source_version'];new=next(x['evidence'] for x in life['wiki_check']['evidence'] if x['evidence']['source_version_id']==newsource)
    rejected=await call('read_evidence',release_id=life['V1'],evidence_id=new['id']);checks['new_evidence_not_exposed_in_v1']=rejected.get('error',{}).get('code')=='NOT_FOUND'
    text=v3['manifest']['wiki']['text'];checks['wiki_retains_original_qualifiers']=all(t in text for t in ['100Vmax','up to','whichever comes first']);checks['v3_citations_same_as_v2']=v3['manifest']['wiki']['citations']==v2['manifest']['wiki']['citations']
    checks['source_revision_changes_bytes']=life['fixture']['before']!=life['fixture']['after'];checks['negative_build_kept_v1_at_failure']=life['negative']['status']=='failed' and life['negative']['current_release_after_failure']==life['V1'];checks['restart_recovered']=json.loads((c/'worker-restart-probe.json').read_text())['after_status']=='succeeded'
    details={'v1':life['V1'],'v2':life['V2'],'v3':wiki['V3'],'latest':handoff['release_id'],'records':[len(v['manifest']['record_ids']) for v in [v1,v2,v3]],'baseline_blocks':[len(v['manifest']['baseline_block_ids']) for v in [v1,v2,v3]],'wiki_citations':[len(v['manifest']['wiki']['citations']) for v in [v1,v2,v3]]}
 async with httpx.AsyncClient(headers={'Authorization':'Bearer '+(c/'developer.token').read_text().strip()},trust_env=False,timeout=60) as http:
  async with streamable_http_client('http://127.0.0.1:8241/mcp',http_client=http) as (rd,wr,_):
   async with ClientSession(rd,wr) as cli:
    await cli.initialize()
    async def dev(name,**args):return json.loads((await cli.call_tool(name,{'kb_id':run['kb_id'],**args})).content[0].text)
    import uuid
    before=await dev('describe_kb');failed=await dev('publish',build_id=str(uuid.uuid4()));after=await dev('describe_kb')
    checks['failed_publish_preserves_current']=failed.get('error',{}).get('code')=='BUILD_NOT_READY' and before['current_release']==after['current_release']
    details['negative_publish_error']=failed.get('error');details['negative_publish_before_after']=[before['current_release'],after['current_release']]
 report={'checks':checks,'details':details};(c/'lifecycle-audit.json').write_text(json.dumps(report,indent=2));print(report)
 if not all(checks.values()):raise SystemExit('lifecycle failed')
if __name__=='__main__':asyncio.run(main())

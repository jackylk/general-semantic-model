"""Validate heldout references without editing consumer answers or the frozen gold."""
import asyncio,json,re,hashlib,collections
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
norm=lambda x:re.sub(r'\s+','',x).casefold()
async def main():
 r=Path(Path('runtime/acceptance-root.txt').read_text());c=r/'control';a=json.loads((r/'consumer/extension-answers.json').read_text());freeze=json.loads((c/'extension-freeze.json').read_text());assert hashlib.sha256((c/'extension-gold.json').read_bytes()).hexdigest()==freeze['gold_sha256'];assert a['release_id']==freeze['release_id']
 refs=[b for p in (c/'reference').glob('doc*.json') for b in json.loads(p.read_text())['blocks']];reads={};checks=[]
 async with httpx.AsyncClient(headers={'Authorization':'Bearer '+(c/'consumer.token').read_text().strip()},trust_env=False,timeout=60) as h:
  async with streamable_http_client('http://127.0.0.1:8242/mcp',http_client=h) as (rd,wr,_):
   async with ClientSession(rd,wr) as cli:
    await cli.initialize()
    async def call(name,**args):return json.loads((await cli.call_tool(name,{'kb_id':a['kb_id'],'release_id':a['release_id'],**args})).content[0].text)
    manifest=(await call('get_release'))['manifest']
    for answer in a['answers']:
     for cite in answer['citations']:
      eid=cite['evidence_id']
      if eid not in reads:reads[eid]=await call('read_evidence',evidence_id=eid)
      e=reads[eid];checks.append({'question':answer['id'],'id':eid,'release':e.get('release_id')==a['release_id'],'source_version':e.get('source_version_id')==cite.get('source_version_id'),'page':e.get('locator',{}).get('page')==cite.get('locator',{}).get('page'),'quote_in_original':norm(cite['quote']) in norm(e.get('text','')),'raw_source_page_match':any(b['page']==cite.get('locator',{}).get('page') and norm(cite['quote']) in norm(b['text']) for b in refs)})
    record_checks={x['id']:all(rid in manifest['record_ids'] for rid in x.get('record_ids_used',[])) for x in a['answers']}
 report={'release_id':a['release_id'],'questions':len(a['answers']),'unique_evidence':len(reads),'status_counts':dict(collections.Counter(x['status'] for x in a['answers'])),'support_channels':dict(collections.Counter(x.get('support_channel','unknown') for x in a['answers'])),'semantic_coverage':dict(collections.Counter(x.get('semantic_coverage','unknown') for x in a['answers'])),'record_ids_scoped':record_checks,'citation_checks':checks};(c/'extension-evidence-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));(c/'extension-evidence-reads.json').write_text(json.dumps(reads,ensure_ascii=False,indent=2));errors=[x for x in checks if not all(v for k,v in x.items() if k not in ('id','question'))];print({k:v for k,v in report.items() if k not in ('citation_checks','record_ids_scoped')});print('citation_errors',errors)
 if errors or not all(record_checks.values()):raise SystemExit('heldout evidence audit failed')
if __name__=='__main__':asyncio.run(main())

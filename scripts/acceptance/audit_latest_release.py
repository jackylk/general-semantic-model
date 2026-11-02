"""Deterministically read every latest Wiki citation via consumer MCP."""
import asyncio,json
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
async def main():
 r=Path(Path('runtime/acceptance-root.txt').read_text());c=r/'control';a=json.loads((r/'consumer/answers.json').read_text());kb=a['kb_id'];release=a['release_id'];report={}
 async with httpx.AsyncClient(headers={'Authorization':'Bearer '+(c/'consumer.token').read_text().strip()},trust_env=False,timeout=60) as h:
  async with streamable_http_client('http://127.0.0.1:8242/mcp',http_client=h) as (rd,wr,_):
   async with ClientSession(rd,wr) as cli:
    await cli.initialize()
    async def call(name,**args):return json.loads((await cli.call_tool(name,{'kb_id':kb,'release_id':release,**args})).content[0].text)
    manifest=(await call('get_release'))['manifest'];wiki=await call('get_wiki');records=(await call('query_records',limit=200))['records'];semaphore=asyncio.Semaphore(4)
    async def read(cite):
     async with semaphore:e=await call('read_evidence',evidence_id=cite['evidence_id'])
     return {'evidence_id':cite['evidence_id'],'record_in_release':cite['record_id'] in manifest['record_ids'],'fixed_release':e.get('release_id')==release,'source_version_id':e.get('source_version_id'),'offset_matches':e.get('text','')[e.get('start_offset',0):e.get('end_offset',0)]==e.get('quote'),'readable':not e.get('error')}
    evidence=await asyncio.gather(*(read(cite) for cite in wiki['citations']))
    conditional=[x for x in records if x['payload'].get('conditions')]
    raw_count=sum(len(json.loads(p.read_text())['blocks']) for p in (c/'reference').glob('doc*.json'))
    checks={'all_records_visible':len(records)==len(manifest['record_ids']),'all_citations_readable_and_fixed':all(e['readable'] and e['fixed_release'] and e['record_in_release'] and e['offset_matches'] for e in evidence),'six_source_versions':len(manifest['source_version_ids'])==6 and {e['source_version_id'] for e in evidence}==set(manifest['source_version_ids']),'full_selected_parse_block_count':len(manifest['baseline_block_ids'])==raw_count,'nonempty_conditions_exist':bool(conditional),'wiki_contains_structured_conditions':all('；条件：'+json.dumps(x['payload']['conditions'],ensure_ascii=False) in wiki['text'] for x in conditional)}
    report={'kb_id':kb,'release_id':release,'record_count':len(records),'wiki_citations':len(evidence),'source_count':len(manifest['source_version_ids']),'baseline_blocks':len(manifest['baseline_block_ids']),'conditional_records':len(conditional),'checks':checks,'citation_checks':evidence}
 (c/'latest-release-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print({k:v for k,v in report.items() if k!='citation_checks'})
 if not all(checks.values()):raise SystemExit('latest release audit failed')
if __name__=='__main__':asyncio.run(main())

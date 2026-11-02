"""C1 deterministic evidence/source audit; never edits the consumer answers."""
import asyncio,json,re,hashlib
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

def norm(x):return re.sub(r'\s+','',x).casefold()
async def main():
 r=Path(Path('runtime/acceptance-root.txt').read_text());c=r/'control';run=json.loads((c/'run.json').read_text());a=json.loads((r/'consumer/answers.json').read_text());gold=json.loads((c/'gold.json').read_text());manifest=json.loads((c/'reference/manifest.json').read_text());bydoc={d['id']:d for d in manifest}
 results=[];reads={};references={d['id']:json.loads((c/'reference'/f"{d['id']}.json").read_text())['blocks'] for d in manifest}
 async with httpx.AsyncClient(headers={'Authorization':'Bearer '+(c/'consumer.token').read_text().strip()},trust_env=False,timeout=60) as http:
  async with streamable_http_client('http://127.0.0.1:8242/mcp',http_client=http) as (rd,wr,_):
   async with ClientSession(rd,wr) as client:
    await client.initialize()
    for answer,g in zip(a['answers'],gold,strict=True):
     checks=[]
     for cite in answer['citations']:
      eid=cite['evidence_id']
      if eid not in reads:
       response=await client.call_tool('read_evidence',{'kb_id':a['kb_id'],'release_id':a['release_id'],'evidence_id':eid});reads[eid]=json.loads(response.content[0].text)
      e=reads[eid];checks.append({'raw_source_page_match':any(norm(cite['quote']) in norm(block['text']) and block.get('page')==cite.get('locator',{}).get('page') for doc in ([x['document'] for x in g['evidence']] or list(references)) for block in references[doc]),'id':eid,'version':e.get('source_version_id')==cite.get('source_version_id'),'page':e.get('locator',{}).get('page')==cite.get('locator',{}).get('page'),'quote_in_text':norm(cite['quote']) in norm(e.get('text','')),'release':e.get('release_id')==a['release_id']})
     expected_pages={(x['document'],loc['page']) for x in g['evidence'] for loc in x['locations']}
     # Text and page support checked above; substantive number/condition judgement is separately recorded by C1.
     results.append({'id':answer['id'],'id_matches':answer['id']==g['id'],'status':answer['status'],'must_refuse_ok':not g['must_refuse'] or answer['status']=='insufficient','graph_present':not g['requires_graph'] or bool(answer.get('graph_paths')),'citation_checks':checks})
 source_checks=[{'id':d['id'],'unchanged':hashlib.sha256(Path(d['path']).read_bytes()).hexdigest()==d['sha256']} for d in manifest]
 report={'gold_sha256':hashlib.sha256((c/'gold.json').read_bytes()).hexdigest(),'source_originals':source_checks,'answers':results,'evidence_count':len(reads)}
 (c/'answer-evidence-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));(c/'answer-evidence-reads.json').write_text(json.dumps(reads,ensure_ascii=False,indent=2))
 print(json.dumps({'source_originals_unchanged':all(s['unchanged'] for s in source_checks),'answers':len(results),'evidence_count':len(reads),'citation_errors':[{'question':a['id'],'citation':v} for a in results for v in a['citation_checks'] if not all(x for k,x in v.items() if k!='id')]},ensure_ascii=False))
 if not all(s['unchanged'] for s in source_checks) or any(not all(x for k,x in v.items() if k!='id') for a in results for v in a['citation_checks']):raise SystemExit('evidence audit failed')
if __name__=='__main__':asyncio.run(main())

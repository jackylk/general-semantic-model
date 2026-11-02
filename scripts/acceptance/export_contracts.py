"""Export actual public tool contracts, never credentials."""
import asyncio,json
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
async def main():
 r=Path(Path('runtime/acceptance-root.txt').read_text());c=r/'control'
 for role,port in [('developer',8241),('consumer',8242)]:
  async with httpx.AsyncClient(headers={'Authorization':'Bearer '+(c/f'{role}.token').read_text().strip()},trust_env=False,timeout=30) as http:
   async with streamable_http_client(f'http://127.0.0.1:{port}/mcp',http_client=http) as (rd,wr,_):
    async with ClientSession(rd,wr) as cli:
     await cli.initialize();data=[t.model_dump(mode='json',exclude_none=True) for t in (await cli.list_tools()).tools];Path(f'docs/reference/mcp.{role}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');print(role,len(data))
if __name__=='__main__':asyncio.run(main())

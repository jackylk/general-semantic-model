"""Live synthetic smoke using ONLY public MCP calls; not domain acceptance."""
import argparse,asyncio,json,subprocess,sys
from pathlib import Path
from uuid import uuid4
import yaml
from gsm.credentials import write_credentials
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]


def unpack(result):
    if result.isError:raise RuntimeError('MCP protocol error')
    data=json.loads(result.content[0].text)
    if data.get('error'):raise RuntimeError(data['error'])
    return data


async def main(pdf=False):
    kb=str(uuid4());run=ROOT/'runtime'/('smoke-'+kb);run.mkdir(parents=True)
    profile=run/'developer.json';write_credentials(profile,'developer',[kb],ROOT/'runtime/imports')
    inputs=ROOT/'runtime/imports';inputs.mkdir(parents=True,exist_ok=True)
    source=inputs/('smoke-'+kb+('.pdf' if pdf else '.txt'))
    if pdf:
        generator='from reportlab.pdfgen.canvas import Canvas;import sys;c=Canvas(sys.argv[1]);c.drawString(50,780,"Synthetic knowledge test; not a real company policy.");c.drawString(50,750,"Employee John has staff ID E001.");c.drawString(50,720,"When the applicable region is Shanghai, monthly allowance is 100.50 CNY.");c.save()'
        subprocess.run([str(ROOT/'runtime/mineru/bin/python'),'-c',generator,str(source)],check=True)
    else:source.write_text('企业制度测试样本（合成资料，非真实公司制度）。员工张三的工号为 E001。适用地区为上海时，该员工月度补贴为 100.50 CNY。')
    domain=yaml.safe_load((ROOT/'examples/minimal/domain.yaml').read_text())
    params=StdioServerParameters(command=sys.executable,args=['-m','gsm.cli','serve','--credentials',str(profile)],cwd=str(ROOT))
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            async def call(tool_name,**args):return unpack(await client.call_tool(tool_name,args))
            await call('create_kb',kb_id=kb,name='合成资料真实链路烟测')
            version=await call('register_source',kb_id=kb,relative_path=source.name)
            definition=await call('submit_domain',kb_id=kb,definition=domain)
            task=await call('preview_extraction',kb_id=kb,domain_version_id=definition['domain_version_id'],source_version_ids=[version['id']],idempotency_key='extract-1')
            subprocess.run([sys.executable,'-m','gsm.cli','worker','--credentials',str(profile),'--kb-id',kb,'--once',task['id']],cwd=ROOT,stdout=(run/'extract.json').open('w'),check=True)
            done=await call('get_task',kb_id=kb,task_id=task['id'])
            if done['status']!='succeeded':raise RuntimeError(done.get('error'))
            candidates=done['checkpoint']['result']['candidates']
            if not candidates or any(c['status']!='verified' for c in candidates):
                raise RuntimeError('Smoke candidates require correction; inspect local extraction result')
            task=await call('start_build',kb_id=kb,domain_version_id=definition['domain_version_id'],candidate_ids=[c['id'] for c in candidates],idempotency_key='build-1')
            subprocess.run([sys.executable,'-m','gsm.cli','worker','--credentials',str(profile),'--kb-id',kb,'--once',task['id']],cwd=ROOT,stdout=(run/'build.json').open('w'),check=True)
            done=await call('get_task',kb_id=kb,task_id=task['id'])
            if done['status']!='succeeded':raise RuntimeError(done.get('error'))
            release=await call('publish',kb_id=kb,build_id=done['checkpoint']['build_id'])
    consumer=run/'consumer.json';write_credentials(consumer,'consumer',[kb])
    params=StdioServerParameters(command=sys.executable,args=['-m','gsm.cli','serve','--credentials',str(consumer)],cwd=str(ROOT))
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            async def call(tool_name,**args):return unpack(await client.call_tool(tool_name,args))
            results=await call('search',kb_id=kb,release_id=release['release_id'],query='张三在上海的补贴是多少？')
            answer=await call('retrieve',kb_id=kb,release_id=release['release_id'],question='工号 E001 的员工适用上海地区时月度补贴是多少？请保留单位和地区条件。')
            report={'scope':'live model, synthetic source, public MCP smoke; not independent user/domain acceptance','kb_id':kb,'release_id':release['release_id'],'source_format':'pdf' if pdf else 'text','candidate_count':len(candidates),'search_hits':len(results['results']),'answer':answer}
            (run/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            (ROOT/('docs/validation/live-pdf-mcp-smoke.json' if pdf else 'docs/validation/live-mcp-smoke.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({'status':answer['status'],'source_format':'pdf' if pdf else 'text','candidate_count':len(candidates),'search_hits':len(results['results']),'answer':answer['answer'],'citations':answer['citations']},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pdf',action='store_true');args=parser.parse_args();asyncio.run(main(args.pdf))

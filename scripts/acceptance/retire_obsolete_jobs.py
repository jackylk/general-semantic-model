"""C1 maintenance via public API, never patching candidate facts or domain assets."""
import asyncio,json,subprocess,sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
 r=Path(Path('runtime/acceptance-root.txt').read_text());c=r/'control';run=json.loads((c/'run.json').read_text());ids=set()
 for name in ('developer-phase2.jsonl','developer-phase3.jsonl'):
  for line in (c/name).read_text().splitlines():
   try:event=json.loads(line);item=event.get('item',{})
   except ValueError:continue
   if event['type']=='item.completed' and item.get('tool')=='preview_extraction' and item.get('result'):
    try:ids.add(json.loads(item['result']['content'][0]['text'])['id'])
    except (KeyError,ValueError):pass
 results=[]
 async with httpx.AsyncClient(headers={'Authorization':'Bearer '+(c/'developer.token').read_text().strip()},trust_env=False,timeout=30) as http:
  async with streamable_http_client('http://127.0.0.1:8241/mcp',http_client=http) as (read,write,_):
   async with ClientSession(read,write) as client:
    await client.initialize()
    for task_id in ids:
     response=await client.call_tool('get_task',{'kb_id':run['kb_id'],'task_id':task_id});task=json.loads(response.content[0].text)
     if task.get('status') in ('queued','running'):
      response=await client.call_tool('cancel_task',{'kb_id':run['kb_id'],'task_id':task_id});results.append(json.loads(response.content[0].text))
 (c/'obsolete-task-cancellations.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print({'cancelled_obsolete_tasks':sum(row.get('status')=='cancelled' for row in results)})
 run.setdefault('product_upgrades',[]).append({'sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'reason':'bounded structured output and cancellation of obsolete requests'});(c/'run.json').write_text(json.dumps(run,indent=2))
 log=(c/'worker.log').open('a');worker=subprocess.Popen([sys.executable,'-m','gsm.cli','worker','--credentials',str(c/'developer.credentials.json')],stdout=log,stderr=log,start_new_session=True);pids=json.loads((c/'pids.json').read_text());pids['worker']=worker.pid;(c/'pids.json').write_text(json.dumps(pids))
 (c/'developer-phase4-prompt.txt').write_text('第一窗口已根据预览任务暴露的问题升级产品：模型结构化输出预算扩大且保持上限，INVALID_MODEL_OUTPUT 现在给出截断/格式原因和使用量；提供公开 cancel_task。此前尚未完成的旧版本预览任务已通过公开接口取消，未改任何候选事实、领域定义或原件。请 discover_spec 获取最新指南，然后只使用你最终选定的领域版本重新按来源提交六份资料的预览，先等待结果再决定是否修正领域，不提前重复排队多个新版本。所有领域定义和业务内容仍由你自己负责。保留已有失败记录，并继续核对证据、构建发布、关系路径与 Wiki。已有明确用户选择和自动发布授权，无需再次确认执行步骤。真实未解决的产品缺口仍写 issues.md，不改代码或内部表。')
if __name__=='__main__':asyncio.run(main())

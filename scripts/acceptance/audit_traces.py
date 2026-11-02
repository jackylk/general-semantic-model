"""Audit actual native role traces; structured paths must match returned tools."""
from pathlib import Path
import json
r=Path(Path('runtime/acceptance-root.txt').read_text());c=r/'control';answers=json.loads((r/'consumer/answers.json').read_text());paths=[];writes=[];commands=[];conditions=[];tools={}
for role in ['developer','consumer']:
 for f in sorted(c.glob(role+'-phase*.jsonl')):
  for line in f.read_text().splitlines():
   d=json.loads(line);i=d.get('item',{})
   if d['type']!='item.completed':continue
   if i.get('type')=='file_change':writes.extend({'role':role,'path':x['path'],'within_role':Path(x['path']).is_relative_to(r/role)} for x in i['changes'])
   if i.get('type')=='command_execution':commands.append({'role':role,'command':i['command']})
   if i.get('type')!='mcp_tool_call':continue
   name=i.get('tool');tools.setdefault(role,{});tools[role][name]=tools[role].get(name,0)+1
   if role!='consumer' or not i.get('result'):continue
   try:result=json.loads(i['result']['content'][0]['text'])
   except (KeyError,ValueError,IndexError,TypeError):continue
   if name=='query_paths':paths.extend(result.get('paths',[]))
   if name=='query_records' and i.get('arguments',{}).get('conditions'):conditions.append({'release_id':i['arguments']['release_id'],'conditions':i['arguments']['conditions'],'record_count':len(result.get('records',[])),'each_matches':all(all(row['payload'].get('conditions',{}).get(k)==v for k,v in i['arguments']['conditions'].items()) for row in result.get('records',[]))})
canon=lambda p:json.dumps(p,sort_keys=True,ensure_ascii=False)
checks={a['id']:bool(a.get('graph_paths')) and all(canon(p) in {canon(x) for x in paths} for p in a['graph_paths']) for a in answers['answers'] if a['id'] in ('Q02','Q07')}
report={'file_changes':writes,'all_file_changes_within_role':all(x['within_role'] for x in writes),'command_count':len(commands),'commands':commands,'tools':tools,'consumer_actual_paths':len(paths),'answer_paths_match_tool_results':checks,'condition_results':conditions,'audit_note':'C1 reviewed shell commands; OS probes independently enforce forbidden read/write boundaries. Audit is not a claim of malicious-agent or whole-host security.'}
(c/'role-trace-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print({k:v for k,v in report.items() if k not in ('file_changes','commands','tools')})
if not report['all_file_changes_within_role'] or not all(checks.values()):raise SystemExit('role audit failed')

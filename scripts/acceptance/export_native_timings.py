"""Export only timestamp/duration metadata from native Codex events, never auth state."""
from pathlib import Path
import json,collections
r=Path(Path('runtime/acceptance-root.txt').read_text());c=r/'control';all_tools=[];all_turns=[]
for role in ('developer','consumer'):
    turns={};tools=[]
    for path in (r/f'.codex-home-{role}/sessions').rglob('*.jsonl'):
        for line in path.open():
            d=json.loads(line);v=d.get('payload',{})
            if d.get('type')!='event_msg' or not isinstance(v,dict):continue
            kind=v.get('type');tid=v.get('turn_id')
            if kind=='task_started':turns[tid]={'role':role,'turn_id':tid,'started_at':d['timestamp']}
            elif kind in ('task_complete','turn_aborted'):
                row=turns.setdefault(tid,{'role':role,'turn_id':tid});row.update(ended_at=d['timestamp'],status=kind,duration_ms=v.get('duration_ms'),time_to_first_token_ms=v.get('time_to_first_token_ms'))
            elif kind=='item_completed' and v.get('item',{}).get('type')=='McpToolCall':
                item=v['item'];duration=item.get('duration');args=item.get('arguments',{})
                elapsed=round((duration.get('secs',0)+duration.get('nanos',0)/1e9)*1000,3) if duration is not None else (v['completed_at_ms']-v['started_at_ms'] if v.get('completed_at_ms') is not None and v.get('started_at_ms') is not None else None)
                tools.append({'role':role,'turn_id':tid,'tool':item['tool'],'started_at_ms':v.get('started_at_ms'),'completed_at_ms':v.get('completed_at_ms'),'duration_ms':elapsed,'scope':{k:args[k] for k in ['kb_id','release_id','source_version_id','domain_version_id','task_id','build_id'] if k in args},'status':item.get('status')})
    ordered=list(turns.values());phases=sorted(c.glob(role+'-phase*.jsonl'),key=lambda p:int(p.stem.split('phase')[-1]))
    # Each CLI invocation starts one native turn. Preserve turn IDs even if a count mismatch occurs.
    for index,row in enumerate(ordered):row['phase']=phases[index].stem if len(ordered)==len(phases) else None
    phase_by_id={row['turn_id']:row.get('phase') for row in ordered}
    for row in tools:row['phase']=phase_by_id.get(row['turn_id'])
    all_tools.extend(tools);all_turns.extend(ordered)
summary=[]
for key in sorted({(x['role'],x['tool']) for x in all_tools}):
    values=[x['duration_ms'] for x in all_tools if (x['role'],x['tool'])==key and x['duration_ms'] is not None]
    summary.append({'role':key[0],'tool':key[1],'calls':len(values),'sum_ms':round(sum(values),3),'min_ms':min(values),'max_ms':max(values)})
report={'definitions':'Native MCP call elapsed includes client/tool transport. Native turn time includes reasoning and polling, excludes CLI startup; shared multi-question batches cannot be allocated to individual questions. Nested timing spans must not be added to their parents.','turns':all_turns,'calls':all_tools,'summary':summary}
(c/'native-timings.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print({'turns':len(all_turns),'tool_calls':len(all_tools),'phase_mapping_missing':sum(x.get('phase') is None for x in all_turns)})

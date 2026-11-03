"""Bounded truncation recovery at whole-block boundaries, with durable partial results."""
from .errors import ProductError


def _add(target,usage):
    for key,value in usage.items():
        if type(value) is int:target[key]=target.get(key,0)+value


def adaptive_extract(app,kb_id,domain_id,blocks,model,state,save,focus=None):
    nodes=state.setdefault('nodes',{});failed=state.setdefault('failed_usage',{})
    def visit(parts,key,depth):
        node=nodes.setdefault(key,{})
        if 'result' in node:return node['result']
        if not node.get('split'):
            try:
                result=app.extract_candidates(kb_id,domain_id,parts,model,focus=focus)
            except ProductError as error:
                if error.code!='INVALID_MODEL_OUTPUT' or not any(isinstance(d,dict) and d.get('reason') in ('truncated','empty_or_invalid_json') for d in error.details):raise
                for detail in error.details:
                    if isinstance(detail,dict):_add(failed,detail.get('usage',{}))
                node['split']=True;node['reason']=next(d.get('reason') for d in error.details if isinstance(d,dict) and d.get('reason') in ('truncated','empty_or_invalid_json'));save()
            else:
                node['result']=result;save();return result
        if len(parts)<2 or depth>=3:
            raise ProductError('EXTRACTION_PARTITION_LIMIT','输出不完整或不合法且无法安全拆分完整原文块；需调整抽取协议或结构单元，不得丢弃数据',[{'blocks':len(parts),'depth':depth,'usage':failed}],retryable=False)
        # Whole blocks keep table rows and their locator/header associations intact.
        midpoint=len(parts)//2
        left=visit(parts[:midpoint],key+'L',depth+1);right=visit(parts[midpoint:],key+'R',depth+1)
        usage={};_add(usage,left.get('usage',{}));_add(usage,right.get('usage',{}))
        result={'result':{'candidates':left['result']['candidates']+right['result']['candidates']},'usage':usage,
                'extraction_notes':left.get('extraction_notes',[])+right.get('extraction_notes',[]),
                'extraction_rejections':left.get('extraction_rejections',[])+right.get('extraction_rejections',[])}
        node['result']=result;save();return result
    result=visit(blocks,'root',0)
    return {**result,'usage':{k:result.get('usage',{}).get(k,0)+failed.get(k,0) for k in set(result.get('usage',{}))|set(failed)},'adaptive_partition_count':sum(bool(n.get('split')) for n in nodes.values())}

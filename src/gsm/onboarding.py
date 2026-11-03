import json
from typing import Literal
from pydantic import Field,ValidationError
from psycopg.types.json import Jsonb
from .domain import StrictModel
from .errors import ProductError

class OnboardingState(StrictModel):
    purpose:str=''
    audience:str=''
    questions:list[str]=Field(default_factory=list)
    source_version_ids:list[str]=Field(default_factory=list)
    choices:dict[str,str]=Field(default_factory=dict)
    choice_history:list[dict]=Field(default_factory=list,max_length=50)
    topics:list[str]=Field(default_factory=list,max_length=30)
    topic_selection_origin:Literal['unconfirmed','user','simulated_user']='unconfirmed'
    unresolved:list[str|dict]=Field(default_factory=list)
    domain_version_id:str|None=None
    task_id:str|None=None
    release_id:str|None=None

class OnboardingService:
    def __init__(self,store):self.store=store

    def get(self,principal,kb_id):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            row=conn.execute('SELECT state,revision FROM onboarding WHERE kb_id=%s',(kb_id,)).fetchone()
        state=row[0] if row else OnboardingState().model_dump(mode='json')
        if not state.get('purpose') or not state.get('questions'):next_step='了解用途和代表性问题'
        elif not state.get('source_version_ids'):next_step='选择并登记资料样本'
        elif not state.get('topics') or state.get('topic_selection_origin','unconfirmed')=='unconfirmed':next_step='推荐抽取主题并由用户选择'
        elif not state.get('domain_version_id'):next_step='分析样本，提出领域草案和少量业务选择'
        elif state.get('unresolved'):next_step='处理未决业务选择，不自动确认'
        elif not state.get('release_id'):next_step='预览抽取、检查证据与冲突、修正并构建验收'
        else:next_step='知识库已发布，可交使用者窗口验证'
        return {'state':state,'revision':row[1] if row else 0,'next_step':next_step}

    def save(self,principal,kb_id,patch,expected_revision):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            conn.execute('INSERT INTO onboarding(kb_id) VALUES(%s) ON CONFLICT DO NOTHING',(kb_id,))
            row=conn.execute('SELECT state,revision FROM onboarding WHERE kb_id=%s FOR UPDATE',(kb_id,)).fetchone()
            if row[1]!=expected_revision:raise ProductError('REVISION_CONFLICT','引导进度已更新，请先读取最新状态')
            merged={**row[0],**patch}
            # Preserve choices for the same scope; changed purpose/topics archive old decisions.
            merged['choices']={**row[0].get('choices',{}),**patch.get('choices',{})}
            if any(key in patch and patch[key]!=row[0].get(key) for key in ('purpose','topics')):
                if row[0].get('choices'):
                    merged['choice_history']=[*row[0].get('choice_history',[]),{'revision':row[1],'purpose':row[0].get('purpose',''),'topics':row[0].get('topics',[]),'choices':row[0]['choices'],'topic_selection_origin':row[0].get('topic_selection_origin','unconfirmed')}]
                merged['choices']=dict(patch.get('choices',{}))
                if 'topic_selection_origin' not in patch:merged['topic_selection_origin']='unconfirmed'
                for key in ('domain_version_id','task_id','release_id'):
                    if key not in patch:merged[key]=None
            try:state=OnboardingState.model_validate(merged).model_dump(mode='json')
            except ValidationError as exc:raise ProductError('INVALID_STATE','引导状态不符合公开格式',[{'path':'.'.join(map(str,e['loc'])),'reason':e['msg']} for e in exc.errors(include_input=False,include_url=False)]) from None
            if len(json.dumps(state,ensure_ascii=False))>100000:raise ProductError('STATE_TOO_LARGE','引导状态超过限制')
            conn.execute('UPDATE onboarding SET state=%s,revision=revision+1,updated_at=now() WHERE kb_id=%s',(Jsonb(state),kb_id))
        return self.get(principal,kb_id)

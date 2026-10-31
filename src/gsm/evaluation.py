from time import monotonic
from .retrieval import RetrievalService
from .errors import ProductError

class EvaluationService:
    def __init__(self,store,llm):self.store=store;self.llm=llm

    def run(self,principal,kb_id,release_id,dataset,mode='semantic'):
        principal.require(kb_id,write=True)
        if not isinstance(dataset,list) or not 1<=len(dataset)<=100:raise ProductError('INVALID_DATASET','评测集应包含 1–100 题')
        results=[]
        for item in dataset:
            if not item.get('id') or not item.get('question') or not item.get('provenance'):
                raise ProductError('INVALID_DATASET','每题必须有 id、question 和人工基准 provenance')
            start=monotonic()
            try:
                answer=RetrievalService(self.store,self.llm,mode=mode).retrieve(principal,kb_id,release_id,item['question'])
                error=None
            except ProductError as exc:answer=None;error=exc.as_dict()
            results.append({**item,'actual':answer,'error':error,'elapsed_seconds':monotonic()-start,'human_grade':None})
        return {'kb_id':kb_id,'release_id':release_id,'mode':mode,'results':results,'status':'awaiting_human_grading','limitations':['模型不作为唯一裁判','费用需按固定计价版本结合实际 usage 计算','比较两模式前需人工确认原文范围一致']}

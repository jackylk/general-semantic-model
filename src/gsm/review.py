from .errors import ProductError

class ReviewService:
    def __init__(self,store): self.store=store

    def decide(self,principal,kb_id,candidate_ids,decision,reason):
        principal.require(kb_id,write=True)
        if decision not in ('confirm','reject') or not reason.strip() or not candidate_ids:
            raise ProductError('INVALID_REVIEW','需要审核决定、候选 ID 和依据')
        with self.store.transaction(principal,kb_id) as conn:
            for record_id in candidate_ids:
                row=conn.execute('SELECT payload FROM records WHERE kb_id=%s AND id=%s',(kb_id,record_id)).fetchone()
                if not row: raise ProductError('NOT_FOUND','候选不存在或无权限')
                if decision=='confirm' and any(i.get('fatal') for i in row[0].get('issues',[])):
                    raise ProductError('CORRECTION_REQUIRED','身份、类型、条件或证据错误需要修正后重新抽取，不能直接确认')
                conn.execute('INSERT INTO review_decisions(kb_id,record_id,decision,reason) VALUES(%s,%s,%s,%s)',(kb_id,record_id,decision,reason))
        return {'reviewed':len(candidate_ids),'decision':decision}

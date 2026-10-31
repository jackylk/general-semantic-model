import json,re
from .errors import ProductError
from .adapters.embedding import Embedding


def tokenize(text):
    tokens=re.findall(r'[a-zA-Z0-9_]+',text.lower())
    for segment in re.findall(r'[\u3400-\u9fff]+',text):
        tokens.extend(segment[i:i+2] for i in range(max(1,len(segment)-1)))
    return ' '.join(tokens)

class QueryService:
    def __init__(self,store,embedding=None): self.store=store;self.embedding=embedding or Embedding()

    def release(self,conn,kb_id,release_id):
        row=conn.execute('SELECT build_id,manifest FROM releases WHERE kb_id=%s AND id=%s',(kb_id,release_id)).fetchone()
        if not row: raise ProductError('NOT_FOUND','发布版本不存在或无权限')
        return str(row[0]),row[1]

    def records(self,principal,kb_id,release_id,kind=None,subject=None,predicate=None,conditions=None,limit=100):
        if not 1<=limit<=200: raise ProductError('INVALID_LIMIT','limit 必须在 1–200')
        with self.store.transaction(principal,kb_id) as conn:
            _,manifest=self.release(conn,kb_id,release_id)
            rows=conn.execute('SELECT id,kind,payload FROM records WHERE kb_id=%s AND id=ANY(%s::uuid[]) ORDER BY id',(kb_id,manifest['record_ids'])).fetchall()
            result=[]
            for rid,rkind,payload in rows:
                if kind and rkind!=kind: continue
                if subject and payload.get('subject',payload.get('object_id'))!=subject:continue
                if predicate and payload.get('predicate')!=predicate:continue
                if conditions and any(payload.get('conditions',{}).get(k)!=v for k,v in conditions.items()): continue
                evidence=conn.execute('SELECT id FROM evidence_links WHERE kb_id=%s AND record_id=%s AND id=ANY(%s::uuid[])',(kb_id,rid,manifest['evidence_ids'])).fetchall()
                result.append({'id':str(rid),'kind':rkind,'payload':payload,'evidence_ids':[str(e[0]) for e in evidence],'release_id':release_id})
                if len(result)>=limit:break
            return result

    def paths(self,principal,kb_id,release_id,start,target=None,max_depth=3,limit=20):
        if not 1<=max_depth<=5 or not 1<=limit<=50:raise ProductError('INVALID_LIMIT','图深度必须在 1–5，路径数在 1–50')
        with self.store.transaction(principal,kb_id) as conn:
            _,manifest=self.release(conn,kb_id,release_id)
            conn.execute("SET LOCAL statement_timeout='2000ms'")
            rows=conn.execute('''WITH RECURSIVE edges AS (
                SELECT id,payload->>'subject' AS src,payload->>'object' AS dst FROM records
                WHERE kb_id=%s AND id=ANY(%s::uuid[]) AND kind='relation'),
                walk(node,nodes,record_ids,depth) AS (
                SELECT %s::text,ARRAY[%s::text],ARRAY[]::uuid[],0
                UNION ALL SELECT e.dst,w.nodes||e.dst,w.record_ids||e.id,w.depth+1
                FROM walk w JOIN edges e ON e.src=w.node
                WHERE w.depth<%s AND NOT e.dst=ANY(w.nodes))
                SELECT node,nodes,record_ids FROM walk WHERE depth>0 AND (%s::text IS NULL OR node=%s) LIMIT %s''',
                (kb_id,manifest['record_ids'],start,start,max_depth,target,target,limit)).fetchall()
        all_records={r['id']:r for r in self.records(principal,kb_id,release_id,kind='relation',limit=200)}
        return [{'nodes':nodes,'records':[all_records[str(r)] for r in ids if str(r) in all_records],'release_id':release_id} for _,nodes,ids in rows]

    def search(self,principal,kb_id,release_id,query,use_vector=True,limit=10):
        if not query.strip() or len(query)>4000 or not 1<=limit<=50: raise ProductError('INVALID_QUERY','检索问题不能为空，最多 4000 字符，limit 1–50')
        with self.store.transaction(principal,kb_id) as conn:
            build_id,_=self.release(conn,kb_id,release_id)
            terms=tokenize(query)
            lexical=conn.execute("SELECT record_id FROM search_documents WHERE kb_id=%s AND build_id=%s AND (tokens @@ plainto_tsquery('simple',%s) OR strpos(text,%s)>0) ORDER BY ts_rank(tokens,plainto_tsquery('simple',%s)) DESC,record_id LIMIT 50",(kb_id,build_id,terms,query,terms)).fetchall()
            ranked=[[str(r[0]) for r in lexical]]
            if use_vector:
                vector=self.embedding.embed([query])[0]
                v='['+','.join(map(str,vector))+']'
                ranked.append([str(r[0]) for r in conn.execute('SELECT record_id FROM search_documents WHERE kb_id=%s AND build_id=%s AND embedding IS NOT NULL ORDER BY embedding <=> %s::vector LIMIT 50',(kb_id,build_id,v)).fetchall()])
        scores={}
        for ranking in ranked:
            for i,rid in enumerate(ranking):scores[rid]=scores.get(rid,0)+1/(60+i+1)
        records={r['id']:r for r in self.records(principal,kb_id,release_id,limit=200)}
        return [{**records[rid],'score':score} for rid,score in sorted(scores.items(),key=lambda x:-x[1]) if rid in records][:limit]

    def wiki(self,principal,kb_id,release_id):
        with self.store.transaction(principal,kb_id) as conn:
            _,manifest=self.release(conn,kb_id,release_id)
            return manifest.get('wiki',{'text':'','citations':[]})

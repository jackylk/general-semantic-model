from gsm.observability import timed,phase
from typing import Any,Literal
from hashlib import sha256
from pathlib import Path
from decimal import Decimal,InvalidOperation
from datetime import date
import json,re
from pydantic import Field,ValidationError
from psycopg.types.json import Jsonb
from .domain import StrictModel,validate_domain
from .errors import ProductError

class EvidenceInput(StrictModel):
    block_id: str
    quote: str = Field(min_length=1)

class Candidate(StrictModel):
    kind: str
    local_id: str | None = None
    type_id: str | None = None
    name: str = ''
    identity: dict = Field(default_factory=dict)
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    value: Any = None
    conditions: dict = Field(default_factory=dict)
    evidence: list[EvidenceInput] = Field(default_factory=list)
    participants: list[dict[str,str]] = Field(default_factory=list)
    provenance: Literal['source_statement','observation','calculation','inference'] = 'source_statement'
    valid_from: str | None = None
    valid_to: str | None = None


def value_issues(value,definition):
    typ=definition.value_type
    if typ=='quantity':
        if not isinstance(value,dict) or set(value)!={'value','unit'}: return ['INVALID_VALUE']
        errors=value_issues(value['value'],type('D',(),{'value_type':'decimal'})())
        if definition.units and value['unit'] not in definition.units: errors.append('UNIT_NOT_ALLOWED')
        return errors
    if typ=='decimal':
        try:
            if isinstance(value,(bool,float)) or not Decimal(str(value)).is_finite(): return ['INVALID_VALUE']
        except (ValueError,TypeError,InvalidOperation): return ['INVALID_VALUE']
    elif typ=='string' and (not isinstance(value,str) or not value.strip()): return ['INVALID_VALUE']
    elif typ=='boolean' and not isinstance(value,bool): return ['INVALID_VALUE']
    elif typ=='enum' and value not in definition.enum_values: return ['INVALID_VALUE']
    elif typ=='date':
        try: date.fromisoformat(value)
        except (ValueError,TypeError): return ['INVALID_VALUE']
    elif typ=='interval':
        if not isinstance(value,dict) or set(value)!={'start','end'}: return ['INVALID_VALUE']
        try:
            if date.fromisoformat(value['start'])>date.fromisoformat(value['end']): return ['INVALID_VALUE']
        except (ValueError,TypeError): return ['INVALID_VALUE']
    elif typ=='list':
        if not isinstance(value,list): return ['INVALID_VALUE']
        item=definition.model_copy(update={'value_type':definition.item_type,'item_type':None})
        return [err for v in value for err in value_issues(v,item)]
    elif typ=='object_ref' and not isinstance(value,str): return ['INVALID_VALUE']
    return []

class BuildService:
    def __init__(self,store): self.store=store

    def migrate(self):
        with self.store.connect('owner') as conn:
            conn.execute('SELECT pg_advisory_xact_lock(79523489)')
            if not conn.execute("SELECT 1 FROM schema_migrations WHERE version='003'").fetchone():
                conn.execute(Path('migrations/003_build.sql').read_text())
                conn.execute("INSERT INTO schema_migrations(version) VALUES('003')")

    @timed('domain.submit')
    def submit_domain(self,principal,kb_id,data):
        principal.require(kb_id,write=True)
        domain=validate_domain(data)
        with self.store.transaction(principal,kb_id) as conn:
            return str(conn.execute('INSERT INTO domain_versions(kb_id,payload) VALUES(%s,%s) RETURNING id',(kb_id,Jsonb(domain.model_dump(mode='json')))).fetchone()[0])

    def get_domain(self,principal,kb_id,domain_version_id):
        with self.store.transaction(principal,kb_id) as conn:
            row=conn.execute('SELECT payload FROM domain_versions WHERE kb_id=%s AND id=%s',(kb_id,domain_version_id)).fetchone()
            if not row: raise ProductError('NOT_FOUND','领域版本不存在或无权限')
            return validate_domain(row[0])

    @timed('semantic.ingest')
    def ingest(self,principal,kb_id,domain_version_id,raw_candidates):
        principal.require(kb_id,write=True)
        domain=self.get_domain(principal,kb_id,domain_version_id)
        try: candidates=[Candidate.model_validate(c) for c in raw_candidates]
        except ValidationError:
            raise ProductError('INVALID_EXTRACTION','抽取候选不符合产品 Schema') from None
        types={t.id:t for t in domain.types};props={p.id:p for p in domain.properties};rels={r.id:r for r in domain.relations};conds={c.id:c for c in domain.conditions}
        objects={};object_types={};unresolved=set();results=[]
        with self.store.transaction(principal,kb_id) as conn:
            existing=[(row[1],) for row in self._effective_records(conn,kb_id,domain_version_id,'object')]
            for row in existing:
                payload=row[0]
                if payload.get('object_id'): object_types[payload['object_id']]=payload.get('type_id')
            for c in candidates:
                if c.kind!='object': continue
                if not c.local_id or c.local_id in objects: raise ProductError('INVALID_EXTRACTION','对象 local_id 缺失或重复')
                definition=types.get(c.type_id)
                valid=definition and definition.identity and all(k in c.identity and not value_issues(c.identity[k],props[k]) for k in definition.identity)
                canonical={k:(str(Decimal(str(c.identity[k])).normalize()) if props[k].value_type=='decimal' else c.identity[k]) for k in definition.identity} if valid else {}
                key=sha256(json.dumps([c.type_id,canonical],sort_keys=True,ensure_ascii=False).encode()).hexdigest() if valid else 'unresolved:'+c.local_id
                objects[c.local_id]=key;object_types[key]=c.type_id
                if not valid: unresolved.add(key)
            for c in candidates:
                issues=[]
                def add(code,fatal=True): issues.append({'code':code,'fatal':fatal})
                payload=c.model_dump(mode='json');payload['domain_version_id']=domain_version_id
                payload['verification_scope']='structure_location_and_lexical_checks_not_semantic_proof'
                try:
                    start=date.fromisoformat(c.valid_from) if c.valid_from else None
                    end=date.fromisoformat(c.valid_to) if c.valid_to else None
                    if start and end and start>end:add('INVALID_VALIDITY')
                except (ValueError,TypeError):add('INVALID_VALIDITY')
                if c.provenance not in ('source_statement','observation','calculation','inference'): add('INVALID_PROVENANCE')
                if c.provenance in ('calculation','inference'): add('REVIEW_REQUIRED',False)
                if c.kind=='object':
                    payload['object_id']=objects[c.local_id]
                    if payload['object_id'] in unresolved: add('IDENTITY_UNRESOLVED')
                    if c.type_id not in types: add('UNKNOWN_TYPE')
                    elif set(c.identity)-set(types[c.type_id].identity):add('UNDECLARED_IDENTITY_FIELD')
                elif c.kind in ('assertion','relation'):
                    subject=objects.get(c.subject,c.subject);payload['subject']=subject
                    if subject not in object_types or subject in unresolved: add('SUBJECT_UNRESOLVED')
                    definition=props.get(c.predicate) if c.kind=='assertion' else rels.get(c.predicate)
                    if definition is None: add('UNKNOWN_PREDICATE')
                    else:
                        if object_types.get(subject) not in definition.subject_types: add('SUBJECT_TYPE_MISMATCH')
                        if definition.require_review: add('REVIEW_REQUIRED',False)
                        for key in definition.required_conditions:
                            if key not in c.conditions: add('MISSING_CONDITION')
                        if c.kind=='assertion':
                            if definition.value_type=='object_ref':
                                target=objects.get(c.value,c.value) if isinstance(c.value,str) else None
                                payload['value']=target
                                if target in unresolved or object_types.get(target) not in definition.reference_types:add('VALUE_REFERENCE_UNRESOLVED')
                            for code in value_issues(c.value,definition): add(code)
                        else:
                            target=objects.get(c.object,c.object);payload['object']=target
                            if target not in object_types or target in unresolved: add('OBJECT_UNRESOLVED')
                            elif object_types[target] not in definition.object_types: add('OBJECT_TYPE_MISMATCH')
                elif c.kind=='event':
                    definition=next((e for e in domain.events if e.id==c.type_id),None)
                    if definition is None: add('UNKNOWN_EVENT')
                    else:
                        roles={r.id:r for r in definition.roles};present=set();participants=[]
                        for participant in c.participants:
                            role=participant.get('role');target=objects.get(participant.get('object'),participant.get('object'))
                            present.add(role)
                            if role not in roles: add('UNKNOWN_EVENT_ROLE')
                            elif target in unresolved or object_types.get(target) not in roles[role].object_types: add('PARTICIPANT_TYPE_MISMATCH')
                            participants.append({'role':role,'object':target})
                        if any(r.required and r.id not in present for r in definition.roles):add('MISSING_PARTICIPANT')
                        payload['participants']=participants
                elif c.kind=='rule':
                    subject=objects.get(c.subject,c.subject);payload['subject']=subject
                    definition=next((r for r in domain.rules if r.id==c.predicate),None)
                    if definition is None:add('UNKNOWN_RULE')
                    else:
                        if subject in unresolved or object_types.get(subject) not in definition.applies_to:add('SUBJECT_TYPE_MISMATCH')
                        payload['rule']=definition.model_dump(mode='json')
                        if definition.require_review:add('REVIEW_REQUIRED',False)
                else: add('UNSUPPORTED_RECORD_KIND')
                for key,value in c.conditions.items():
                    if key not in conds: add('UNKNOWN_CONDITION')
                    else:
                        for code in value_issues(value,conds[key]): add(code)
                if c.kind=='assertion' and not any(i['fatal'] for i in issues):
                    previous=[(rid,old) for rid,old in self._effective_records(conn,kb_id,domain_version_id,'assertion') if old.get('subject')==payload.get('subject') and old.get('predicate')==c.predicate]
                    conflicting=[str(rid) for rid,old in previous if not any(i.get('fatal') for i in old.get('issues',[])) and old.get('conditions',{})==c.conditions and old.get('valid_from')==c.valid_from and old.get('valid_to')==c.valid_to and old.get('value')!=c.value]
                    if conflicting:
                        add('CONFLICT',False)
                        payload['conflicting_record_ids']=conflicting
                links=[]
                for e in c.evidence:
                    row=conn.execute('SELECT text,locator FROM source_blocks WHERE kb_id=%s AND id=%s',(kb_id,e.block_id)).fetchone()
                    from .grounding import locate_quote
                    span=locate_quote(row[0],e.quote) if row else None
                    if span is None:add('EVIDENCE_NOT_LOCATED')
                    else:
                        e.quote=row[0][span[0]:span[1]]
                        links.append((e,span[0]))
                        if row[1].get('requires_review'):add('LAYOUT_REVIEW_REQUIRED',False)
                payload['evidence']=[e.model_dump(mode='json') for e in c.evidence]
                if c.provenance in ('source_statement','observation'):
                    from .grounding import grounded,numbers,quantities
                    quotes='\n'.join(e.quote for e,_ in links)
                    if c.kind=='object' and c.type_id in types:
                        for key in types[c.type_id].identity:
                            if key in c.identity and key in props and not value_issues(c.identity[key],props[key]) and not grounded(c.identity[key],props[key],quotes):add('IDENTITY_NOT_IN_EVIDENCE')
                    for key,value in c.conditions.items():
                        if key in conds and not value_issues(value,conds[key]) and not grounded(value,conds[key],quotes):add('CONDITION_NOT_IN_EVIDENCE')
                    if c.kind=='assertion':
                        definition=props.get(c.predicate)
                        if definition and definition.value_type in ('quantity','decimal') and not value_issues(c.value,definition):
                            if not grounded(c.value,definition,quotes):
                                number=c.value['value'] if definition.value_type=='quantity' else c.value
                                if Decimal(str(number)) not in numbers(quotes):add('VALUE_NOT_IN_EVIDENCE')
                                else:add('UNIT_NOT_IN_EVIDENCE')
                if not links: add('EVIDENCE_REQUIRED')
                payload['issues']=issues;status='candidate' if issues else 'verified'
                record_id=str(conn.execute('INSERT INTO records(kb_id,kind,payload,status) VALUES(%s,%s,%s,%s) RETURNING id',(kb_id,c.kind if c.kind in ('object','assertion','relation','event','rule') else 'assertion',Jsonb(payload),status)).fetchone()[0])
                for e,start in links:
                    conn.execute('INSERT INTO evidence_links(kb_id,record_id,block_id,quote,start_offset,end_offset) VALUES(%s,%s,%s,%s,%s,%s)',(kb_id,record_id,e.block_id,e.quote,start,start+len(e.quote)))
                results.append({'id':record_id,'status':status,'issues':issues,'payload':payload})
        return {'objects':objects,'candidates':results}

    def _effective_records(self,conn,kb_id,domain_version_id,kind):
        return conn.execute("""SELECT r.id,r.payload FROM records r
            LEFT JOIN LATERAL (SELECT decision FROM review_decisions d WHERE d.kb_id=r.kb_id AND d.record_id=r.id ORDER BY created_at DESC,id DESC LIMIT 1) d ON true
            WHERE r.kb_id=%s AND r.kind=%s AND r.payload->>'domain_version_id'=%s
            AND COALESCE(d.decision,'')<>'reject' AND (r.status IN ('verified','confirmed') OR d.decision='confirm')
            AND EXISTS(SELECT 1 FROM evidence_links e JOIN source_blocks b ON b.kb_id=e.kb_id AND b.id=e.block_id JOIN parse_versions p ON p.kb_id=b.kb_id AND p.id=b.parse_version_id
                WHERE e.kb_id=r.kb_id AND e.record_id=r.id AND NOT EXISTS(SELECT 1 FROM source_withdrawals w WHERE w.kb_id=p.kb_id AND w.source_version_id=p.source_version_id))""",(kb_id,kind,domain_version_id)).fetchall()

    @timed('semantic.revalidate')
    def revalidate(self,principal,kb_id,domain_version_id,candidate_ids):
        principal.require(kb_id,write=True)
        if not 1<=len(candidate_ids)<=200 or len(set(candidate_ids))!=len(candidate_ids):raise ProductError('INVALID_LIMIT','重核验必须选择1–200条不重复候选')
        with self.store.transaction(principal,kb_id) as conn:
            rows=conn.execute("""SELECT r.id,r.payload,d.decision FROM records r
                LEFT JOIN LATERAL (SELECT decision FROM review_decisions WHERE kb_id=r.kb_id AND record_id=r.id ORDER BY created_at DESC,id DESC LIMIT 1) d ON true
                WHERE r.kb_id=%s AND r.id=ANY(%s::uuid[]) AND r.payload->>'domain_version_id'=%s""",(kb_id,candidate_ids,domain_version_id)).fetchall()
        if len(rows)!=len(candidate_ids):raise ProductError('NOT_FOUND','候选缺失、越权或领域版本不匹配')
        if any(row[2]=='reject' for row in rows):raise ProductError('REVIEW_REQUIRED','已拒绝候选不能通过重核验恢复')
        by_id={str(row[0]):row[1] for row in rows}
        payloads=[{key:value for key,value in by_id[rid].items() if key in Candidate.model_fields} for rid in candidate_ids]
        result=self.ingest(principal,kb_id,domain_version_id,payloads)
        result['revalidated_from']=dict(zip(candidate_ids,[c['id'] for c in result['candidates']]))
        return result

    def preview(self,principal,kb_id,build_id,kind=None,conditions=None,limit=100,offset=0):
        principal.require(kb_id,write=True)
        if not 1<=limit<=200 or offset<0:raise ProductError('INVALID_LIMIT','limit 1–200，offset 不得为负数')
        with self.store.transaction(principal,kb_id) as conn:
            build=conn.execute('SELECT record_ids,ready,manifest FROM builds WHERE kb_id=%s AND id=%s',(kb_id,build_id)).fetchone()
            if not build:raise ProductError('NOT_FOUND','构建不存在或无权限')
            if not build[1]:raise ProductError('BUILD_NOT_READY','构建尚未就绪')
            rows=conn.execute('SELECT id,kind,payload FROM records WHERE kb_id=%s AND id=ANY(%s::uuid[]) ORDER BY id',(kb_id,build[0])).fetchall()
        records=[{'id':str(rid),'kind':rkind,'payload':payload} for rid,rkind,payload in rows if (not kind or kind==rkind) and (not conditions or all(payload.get('conditions',{}).get(k)==v for k,v in conditions.items()))]
        return {'build_id':build_id,'preview_only':True,'record_ids':[str(rid) for rid in build[0]],'matching_count':len(records),'records':records[offset:offset+limit],'offset':offset,'manifest':build[2]}

    @timed('build.index_and_wiki')
    def finish(self,principal,kb_id,domain_version_id,record_ids,embed=True,source_parse_ids=None):
        from .search import tokenize
        from .adapters.embedding import Embedding
        from .releases import ReleaseService
        principal.require(kb_id,write=True)
        domain=self.get_domain(principal,kb_id,domain_version_id)
        with self.store.connect('owner') as conn:
            conn.execute('SELECT pg_advisory_xact_lock(79523489)')
            if not conn.execute("SELECT 1 FROM schema_migrations WHERE version='004'").fetchone():
                conn.execute(Path('migrations/004_artifacts.sql').read_text())
                conn.execute("INSERT INTO schema_migrations(version) VALUES('004')")
        with self.store.transaction(principal,kb_id) as conn:
            rows=conn.execute('SELECT id,kind,payload FROM records WHERE kb_id=%s AND id=ANY(%s::uuid[])',(kb_id,record_ids)).fetchall()
            if len(rows)!=len(set(record_ids)) or any(r[2].get('domain_version_id')!=domain_version_id for r in rows):
                raise ProductError('INVALID_BUILD','记录缺失或领域版本不匹配')
            from .publication_checks import reference_closure
            reference_closure(rows,domain)
            active=conn.execute('SELECT e.id,e.record_id,e.block_id,e.quote,p.id,p.source_version_id FROM evidence_links e JOIN source_blocks b ON b.kb_id=e.kb_id AND b.id=e.block_id JOIN parse_versions p ON p.kb_id=b.kb_id AND p.id=b.parse_version_id WHERE e.kb_id=%s AND e.record_id=ANY(%s::uuid[]) AND NOT EXISTS(SELECT 1 FROM source_withdrawals w WHERE w.kb_id=p.kb_id AND w.source_version_id=p.source_version_id) ORDER BY e.id',(kb_id,record_ids)).fetchall()
            by_record={};citations=[]
            for eid,rid,block,quote,parse,source in active:
                by_record.setdefault(str(rid),[]).append({'block_id':str(block),'quote':quote})
                citations.append({'record_id':str(rid),'evidence_id':str(eid)})
            if set(by_record)!={str(rid) for rid,_,_ in rows}:raise ProductError('EVIDENCE_REQUIRED','构建记录缺少有效来源')
            rows=[(rid,kind,{**payload,'evidence':by_record[str(rid)]}) for rid,kind,payload in rows]
            names={d.id:d.name for group in (domain.properties,domain.relations) for d in group}
            texts=[names.get(payload.get('predicate'),'')+' '+json.dumps(payload,ensure_ascii=False,sort_keys=True) for _,_,payload in rows]
            parse_ids=sorted({str(row[4]) for row in active} | set(source_parse_ids or []))
            parse_rows=conn.execute('SELECT p.id,p.source_version_id,p.parser_version,p.coverage,jsonb_array_length(p.document_units) FROM parse_versions p WHERE p.kb_id=%s AND p.id=ANY(%s::uuid[]) AND NOT EXISTS(SELECT 1 FROM source_withdrawals w WHERE w.kb_id=p.kb_id AND w.source_version_id=p.source_version_id) ORDER BY p.id',(kb_id,parse_ids)).fetchall()
            if len(parse_rows)!=len(parse_ids):raise ProductError('NOT_FOUND','构建来源解析版本不存在或无权限')
            document_coverage=[{'parse_version_id':str(pid),'source_version_id':str(source),'parser_version':version,'unit_count':count,'coverage':coverage or {'status':'legacy_unassessed','semantic_completeness':'not_proven'}} for pid,source,version,coverage,count in parse_rows]
            source_blocks=conn.execute("SELECT id,text FROM source_blocks WHERE kb_id=%s AND parse_version_id=ANY(%s::uuid[]) AND locator->'requires_review' IS DISTINCT FROM 'true'::jsonb ORDER BY id",(kb_id,parse_ids)).fetchall()
        with phase('build.semantic_embedding'):
            vectors=Embedding().embed(texts) if embed else [None]*len(texts)
        with phase('build.source_embedding'):
            source_vectors=Embedding().embed([r[1] for r in source_blocks]) if embed else [None]*len(source_blocks)
        build_id=ReleaseService(self.store).stage(principal,kb_id,record_ids,ready=False)
        with self.store.transaction(principal,kb_id) as conn:
            for row,text,vector in zip(rows,texts,vectors):
                encoded='['+','.join(map(str,vector))+']' if vector is not None else None
                conn.execute("INSERT INTO search_documents(kb_id,build_id,record_id,text,tokens,embedding) VALUES(%s,%s,%s,%s,to_tsvector('simple',%s),%s::vector)",(kb_id,build_id,row[0],text,tokenize(text),encoded))
            for row,vector in zip(source_blocks,source_vectors):
                encoded='['+','.join(map(str,vector))+']' if vector is not None else None
                conn.execute("INSERT INTO source_search_documents(kb_id,build_id,block_id,text,tokens,embedding) VALUES(%s,%s,%s,%s,to_tsvector('simple',%s),%s::vector)",(kb_id,build_id,row[0],row[1],tokenize(row[1]),encoded))
            from .wiki import render_wiki
            with phase('build.wiki'):
                wiki=render_wiki(rows,domain,citations)
                if any(r['coverage'].get('status') in ('incomplete','legacy_unassessed') for r in document_coverage):
                    warning='解析覆盖提示：部分资料存在未识别区域或尚未评估的解析版本；已引用内容不代表完整覆盖。'
                    wiki['limitations'].append(warning)
                    for page in wiki['pages']:page['text']+='\n\n> '+warning+'\n'
            conn.execute('UPDATE builds SET ready=true,manifest=%s WHERE kb_id=%s AND id=%s',(Jsonb({'domain_version_id':domain_version_id,'wiki':wiki,'document_coverage':document_coverage,'support_snapshot':[str(row[0]) for row in active],'vector_ready':embed,'baseline_block_ids':[str(r[0]) for r in source_blocks]}),kb_id,build_id))
        return build_id

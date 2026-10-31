from psycopg.types.json import Jsonb
from .errors import ProductError

class ReleaseService:
    def __init__(self,store): self.store=store

    def stage(self,principal,kb_id,record_ids,ready=False):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            return str(conn.execute('INSERT INTO builds(kb_id,record_ids,ready) VALUES(%s,%s,%s) RETURNING id',(kb_id,record_ids,ready)).fetchone()[0])

    def publish(self,principal,kb_id,build_id):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            conn.execute('SELECT id FROM knowledge_bases WHERE id=%s FOR UPDATE',(kb_id,))
            previous=conn.execute('SELECT id FROM releases WHERE kb_id=%s AND build_id=%s',(kb_id,build_id)).fetchone()
            if previous: return str(previous[0])
            build=conn.execute('SELECT record_ids,ready,manifest FROM builds WHERE kb_id=%s AND id=%s FOR UPDATE',(kb_id,build_id)).fetchone()
            if not build or not build[1] or not build[0]:
                raise ProductError('BUILD_NOT_READY','构建未就绪或不包含记录')
            record_ids=[str(r) for r in build[0]]
            rows=conn.execute('''SELECT r.id,CASE WHEN d.decision='confirm' THEN 'confirmed' WHEN d.decision='reject' THEN 'rejected' ELSE r.status END
                FROM records r LEFT JOIN LATERAL (SELECT decision FROM review_decisions d WHERE d.kb_id=r.kb_id AND d.record_id=r.id ORDER BY created_at DESC,id DESC LIMIT 1) d ON true WHERE r.kb_id=%s AND r.id=ANY(%s::uuid[])''',(kb_id,record_ids)).fetchall()
            if len(rows)!=len(set(record_ids)) or any(status not in ('verified','confirmed') for _,status in rows):
                raise ProductError('REVIEW_REQUIRED','包含未核验、冲突或其他知识库的记录')
            evidence=conn.execute('''SELECT e.id,e.record_id,b.id,p.id,p.source_version_id
                FROM evidence_links e JOIN source_blocks b ON b.kb_id=e.kb_id AND b.id=e.block_id
                JOIN parse_versions p ON p.kb_id=b.kb_id AND p.id=b.parse_version_id
                WHERE e.kb_id=%s AND e.record_id=ANY(%s::uuid[]) AND NOT EXISTS
                (SELECT 1 FROM source_withdrawals w WHERE w.kb_id=p.kb_id AND w.source_version_id=p.source_version_id)''',(kb_id,record_ids)).fetchall()
            supported={str(e[1]) for e in evidence}
            if supported!=set(record_ids):
                raise ProductError('EVIDENCE_REQUIRED','记录缺少有效来源支持')
            manifest={**build[2], 'record_ids':record_ids,'evidence_ids':[str(e[0]) for e in evidence],
                'block_ids':sorted({str(e[2]) for e in evidence}),'parse_version_ids':sorted({str(e[3]) for e in evidence}),
                'source_version_ids':sorted({str(e[4]) for e in evidence})}
            release=conn.execute('INSERT INTO releases(kb_id,build_id,manifest) VALUES(%s,%s,%s) RETURNING id',(kb_id,build_id,Jsonb(manifest))).fetchone()[0]
            conn.execute('UPDATE knowledge_bases SET current_release=%s WHERE id=%s',(release,kb_id))
            return str(release)

    def current(self,principal,kb_id):
        with self.store.transaction(principal,kb_id) as conn:
            row=conn.execute('SELECT current_release FROM knowledge_bases WHERE id=%s',(kb_id,)).fetchone()
            return str(row[0]) if row and row[0] else None

    def rollback(self,principal,kb_id,release_id):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            if not conn.execute('SELECT id FROM releases WHERE kb_id=%s AND id=%s',(kb_id,release_id)).fetchone():
                raise ProductError('NOT_FOUND','发布版本不存在或无权限')
            conn.execute('UPDATE knowledge_bases SET current_release=%s WHERE id=%s',(release_id,kb_id))

    def read_evidence(self,principal,kb_id,release_id,evidence_id):
        with self.store.transaction(principal,kb_id) as conn:
            release=conn.execute('SELECT manifest FROM releases WHERE kb_id=%s AND id=%s',(kb_id,release_id)).fetchone()
            if not release or evidence_id not in release[0]['evidence_ids']:
                raise ProductError('NOT_FOUND','证据不属于指定发布版本或无权限')
            row=conn.execute('''SELECT e.quote,b.text,b.locator,b.fingerprint,p.source_version_id,p.id,e.start_offset,e.end_offset
                FROM evidence_links e JOIN source_blocks b ON b.kb_id=e.kb_id AND b.id=e.block_id
                JOIN parse_versions p ON p.kb_id=b.kb_id AND p.id=b.parse_version_id
                WHERE e.kb_id=%s AND e.id=%s''',(kb_id,evidence_id)).fetchone()
            if not row: raise ProductError('NOT_FOUND','证据不存在或无权限')
            return {'id':evidence_id,'release_id':release_id,'quote':row[0],'text':row[1],
                'locator':row[2],'fingerprint':row[3],'source_version_id':str(row[4]),'parse_version_id':str(row[5]),
                'start_offset':row[6],'end_offset':row[7]}

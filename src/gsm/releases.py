from gsm.observability import timed
from psycopg.types.json import Jsonb
from .errors import ProductError

class ReleaseService:
    def __init__(self,store,workspace_root=None): self.store=store;self.workspace_root=workspace_root

    def stage(self,principal,kb_id,record_ids,ready=False):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            return str(conn.execute('INSERT INTO builds(kb_id,record_ids,ready) VALUES(%s,%s,%s) RETURNING id',(kb_id,record_ids,ready)).fetchone()[0])

    @timed('release.publish')
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
            if 'support_snapshot' in build[2] and set(build[2]['support_snapshot'])!={str(e[0]) for e in evidence}:
                raise ProductError('BUILD_STALE','来源支持在构建后变化，请重新构建再发布')
            if build[2].get('domain_version_id'):
                from .build import BuildService
                from .publication_checks import reference_closure
                domain=BuildService(self.store).get_domain(principal,kb_id,build[2]['domain_version_id'])
                payloads=conn.execute('SELECT id,kind,payload FROM records WHERE kb_id=%s AND id=ANY(%s::uuid[])',(kb_id,record_ids)).fetchall()
                reference_closure(payloads,domain)
            supported={str(e[1]) for e in evidence}
            if supported!=set(record_ids):
                raise ProductError('EVIDENCE_REQUIRED','记录缺少有效来源支持')
            scope_parse_ids={str(e[3]) for e in evidence} | {item['parse_version_id'] for item in build[2].get('document_coverage',[])}
            scope=conn.execute('SELECT p.id,p.source_version_id FROM parse_versions p WHERE p.kb_id=%s AND p.id=ANY(%s::uuid[]) AND NOT EXISTS(SELECT 1 FROM source_withdrawals w WHERE w.kb_id=p.kb_id AND w.source_version_id=p.source_version_id)',(kb_id,sorted(scope_parse_ids))).fetchall()
            if len(scope)!=len(scope_parse_ids):raise ProductError('BUILD_STALE','构建范围内的来源支持已变化，请重新构建再发布')
            manifest={**build[2], 'record_ids':record_ids,'evidence_ids':[str(e[0]) for e in evidence],
                'block_ids':sorted({str(e[2]) for e in evidence}),'parse_version_ids':sorted(str(row[0]) for row in scope),
                'source_version_ids':sorted({str(row[1]) for row in scope})}
            from uuid import uuid4
            release=str(uuid4())
            if self.workspace_root:
                from .artifacts import prepare
                from .build import BuildService
                payloads=conn.execute('SELECT id,kind,payload FROM records WHERE kb_id=%s AND id=ANY(%s::uuid[])',(kb_id,record_ids)).fetchall()
                domain=BuildService(self.store).get_domain(principal,kb_id,manifest['domain_version_id']).model_dump(mode='json')
                prepare(self.workspace_root,release,manifest,[{'id':str(rid),'kind':kind,'payload':payload} for rid,kind,payload in payloads],domain)
            conn.execute('INSERT INTO releases(id,kb_id,build_id,manifest) VALUES(%s,%s,%s,%s)',(release,kb_id,build_id,Jsonb(manifest)))
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

    @timed('evidence.read')
    def read_evidence(self,principal,kb_id,release_id,evidence_id):
        with self.store.transaction(principal,kb_id) as conn:
            release=conn.execute('SELECT manifest FROM releases WHERE kb_id=%s AND id=%s',(kb_id,release_id)).fetchone()
            if release and evidence_id.startswith('block:'):
                block_id=evidence_id[6:]
                if block_id not in release[0].get('baseline_block_ids',[]):raise ProductError('NOT_FOUND','原文块不属于该发布版')
                row=conn.execute('SELECT b.text,b.locator,b.fingerprint,p.source_version_id,p.id FROM source_blocks b JOIN parse_versions p ON p.kb_id=b.kb_id AND p.id=b.parse_version_id WHERE b.kb_id=%s AND b.id=%s',(kb_id,block_id)).fetchone()
                if not row:raise ProductError('NOT_FOUND','原文块不存在或无权限')
                return {'id':evidence_id,'release_id':release_id,'text':row[0],'quote':row[0],'locator':row[1],'fingerprint':row[2],'source_version_id':str(row[3]),'parse_version_id':str(row[4])}
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

    def read_context(self,principal,kb_id,release_id,evidence_id,before=2,after=4):
        """Published same-parse neighbors only; never treat review-only derivatives as evidence."""
        if not isinstance(before,int) or not isinstance(after,int) or not 0<=before<=4 or not 0<=after<=6:
            raise ProductError('INVALID_QUERY','邻近证据范围超过限制')
        anchor=self.read_evidence(principal,kb_id,release_id,evidence_id)
        with self.store.transaction(principal,kb_id) as conn:
            manifest=conn.execute('SELECT manifest FROM releases WHERE kb_id=%s AND id=%s',(kb_id,release_id)).fetchone()[0]
            if evidence_id.startswith('block:'):bid=evidence_id[6:]
            else:bid=conn.execute('SELECT block_id FROM evidence_links WHERE kb_id=%s AND id=%s',(kb_id,evidence_id)).fetchone()[0]
            position=conn.execute('SELECT parse_version_id,ordinal FROM source_blocks WHERE kb_id=%s AND id=%s',(kb_id,bid)).fetchone()
            rows=conn.execute('SELECT id,text FROM source_blocks WHERE kb_id=%s AND parse_version_id=%s AND ordinal BETWEEN %s AND %s AND id=ANY(%s::uuid[]) ORDER BY ordinal',
                (kb_id,position[0],position[1]-before,position[1]+after,manifest.get('baseline_block_ids',[]))).fetchall()
        result=[];size=0
        for block_id,text in rows:
            if str(block_id)==str(bid):continue
            if size+len(text)>12000:continue
            result.append(self.read_evidence(principal,kb_id,release_id,'block:'+str(block_id)));size+=len(text)
        return result

    @timed('evidence.render_page')
    def render_source_page(self,principal,kb_id,release_id,source_version_id,page):
        import os,subprocess
        from pathlib import Path
        from hashlib import sha256
        if type(page) is not int or not 1<=page<=10000:raise ProductError('INVALID_PAGE','页码必须为正整数')
        with self.store.transaction(principal,kb_id) as conn:
            release=conn.execute('SELECT manifest FROM releases WHERE kb_id=%s AND id=%s',(kb_id,release_id)).fetchone()
            if not release or source_version_id not in release[0].get('source_version_ids',[]):raise ProductError('NOT_FOUND','来源不属于该固定发布版')
            row=conn.execute('SELECT sha256,filename FROM source_versions WHERE kb_id=%s AND id=%s',(kb_id,source_version_id)).fetchone()
        if not row or Path(row[1]).suffix.lower()!='.pdf':raise ProductError('UNSUPPORTED_SOURCE','当前来源不是PDF')
        path=self.store.settings.file_root/kb_id/row[0]
        if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=row[0]:raise ProductError('SOURCE_INTEGRITY','已发布来源文件缺失或哈希不一致')
        runtime=Path(os.environ.get('GSM_PDF_PYTHON',str(Path(__file__).resolve().parents[2]/'runtime/mineru/bin/python')))
        if not runtime.is_file():raise ProductError('RENDER_UNAVAILABLE','未配置PDF渲染运行时')
        try:
            result=subprocess.run([str(runtime),str(Path(__file__).with_name('adapters')/'pdf_render.py'),str(path),str(page)],capture_output=True,timeout=45,check=True)
        except (OSError,subprocess.SubprocessError):raise ProductError('PAGE_UNAVAILABLE','页码不存在或当前PDF无法渲染') from None
        if len(result.stdout)>8*1024*1024 or not result.stdout.startswith(b'\x89PNG\r\n\x1a\n'):raise ProductError('RENDER_FAILED','PDF预览输出无效或超过限制')
        return {'png':result.stdout,'metadata':{'kb_id':kb_id,'release_id':release_id,'source_version_id':source_version_id,'source_sha256':row[0],'page':page,'method':'immutable_published_blob_pdfium_render','rendered_image_is_not_semantic_verification':True}}

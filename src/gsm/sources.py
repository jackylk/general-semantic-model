from hashlib import sha256
from pathlib import Path
from psycopg.types.json import Jsonb
from .errors import ProductError

class SourceService:
    def __init__(self, store):
        self.store=store

    def import_file(self, principal,kb_id,relative_path):
        principal.require(kb_id,write=True)
        if self.store.settings.source_root is None:raise ProductError('SOURCE_NOT_CONFIGURED','尚未配置文档收件入口，请先完成工作区初始化并由用户提供资料')
        root=self.store.settings.source_root.resolve()
        path=(root/relative_path).resolve()
        if Path(relative_path).is_absolute() or not path.is_relative_to(root) or not path.is_file():
            raise ProductError('INVALID_SOURCE','来源必须是授权目录内的文件')
        data=path.read_bytes(); digest=sha256(data).hexdigest()
        # KB-scoped blobs prevent an authorized reference from revealing another KB's existence.
        blob=self.store.settings.file_root/kb_id/digest
        blob.parent.mkdir(parents=True,exist_ok=True)
        if not blob.exists():
            with blob.open('xb') as f: f.write(data)
        with self.store.transaction(principal,kb_id) as conn:
            row=conn.execute('INSERT INTO source_versions(kb_id,source_key,sha256,filename,byte_count) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(kb_id,source_key,sha256) DO NOTHING RETURNING id',(kb_id,relative_path,digest,path.name,len(data))).fetchone()
            if row is None:
                row=conn.execute('SELECT id FROM source_versions WHERE kb_id=%s AND source_key=%s AND sha256=%s',(kb_id,relative_path,digest)).fetchone()
            return {'id':str(row[0]),'sha256':digest,'byte_count':len(data)}

    def save_parse(self,principal,kb_id,source_version_id,parser_version,blocks,raw=None):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            parse_id=conn.execute('INSERT INTO parse_versions(kb_id,source_version_id,parser_version,raw_output) VALUES(%s,%s,%s,%s) RETURNING id',(kb_id,source_version_id,parser_version,Jsonb(raw or {}))).fetchone()[0]
            result=[]
            for i,block in enumerate(blocks):
                text=block['text']; locator={k:v for k,v in block.items() if k!='text'}
                block_id=conn.execute('INSERT INTO source_blocks(kb_id,parse_version_id,ordinal,text,locator,fingerprint) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id',(kb_id,parse_id,i,text,Jsonb(locator),sha256(text.encode()).hexdigest())).fetchone()[0]
                result.append({'id':str(block_id),'text':text,'locator':locator})
            return {'id':str(parse_id),'blocks':result}

    def link_evidence(self,principal,kb_id,record_id,block_id,quote):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            row=conn.execute('SELECT text FROM source_blocks WHERE kb_id=%s AND id=%s',(kb_id,block_id)).fetchone()
            if not row or not quote or quote not in row[0]:
                raise ProductError('INVALID_EVIDENCE','摘录无法在指定原文块定位')
            start=row[0].index(quote)
            return str(conn.execute('INSERT INTO evidence_links(kb_id,record_id,block_id,quote,start_offset,end_offset) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id',(kb_id,record_id,block_id,quote,start,start+len(quote))).fetchone()[0])

    def withdraw(self,principal,kb_id,source_version_id):
        principal.require(kb_id,write=True)
        with self.store.transaction(principal,kb_id) as conn:
            conn.execute('INSERT INTO source_withdrawals(kb_id,source_version_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(kb_id,source_version_id))

    def active_support_count(self,principal,kb_id,record_id):
        with self.store.transaction(principal,kb_id) as conn:
            return conn.execute('''SELECT count(*) FROM evidence_links e JOIN source_blocks b ON b.kb_id=e.kb_id AND b.id=e.block_id JOIN parse_versions p ON p.kb_id=b.kb_id AND p.id=b.parse_version_id WHERE e.kb_id=%s AND e.record_id=%s AND NOT EXISTS(SELECT 1 FROM source_withdrawals w WHERE w.kb_id=p.kb_id AND w.source_version_id=p.source_version_id)''',(kb_id,record_id)).fetchone()[0]

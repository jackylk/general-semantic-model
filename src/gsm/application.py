"""Service composition used by CLI and MCP; no industry-specific behavior."""
import json,os,tempfile
from pydantic import ValidationError
from pathlib import Path
from .auth import Principal
from .store import Store
from .config import Settings
from .sources import SourceService
from .build import BuildService,Candidate
from .tasks import TaskService
from .worker import Worker
from .adapters.mineru import Parser
from .adapters.llm import LLM
from .errors import ProductError

class Application:
    def __init__(self,credential_path):
        self.credential_path=Path(credential_path)
        from .credentials import read_credentials
        config=read_credentials(self.credential_path)
        self.principal=Principal(config['role'],frozenset(config['kb_ids']))
        settings=Settings.load()
        settings.source_root=Path(config['source_root']).resolve() if config.get('source_root') else None
        self.store=Store(settings);self.sources=SourceService(self.store);self.build=BuildService(self.store);self.tasks=TaskService(self.store)

    def llm(self):
        from dotenv import dotenv_values
        cfg={**dotenv_values('.env'),**os.environ}
        return LLM.from_env_file(Path(cfg.get('GSM_LLM_ENV_FILE',str(Path.home()/'code/.env'))).expanduser(),cfg.get('GSM_LLM_BASE_URL','https://api.deepseek.com'),cfg.get('GSM_LLM_MODEL','deepseek-flash'))

    def parse_source(self,kb_id,source_version_id):
        self.principal.require(kb_id,write=True)
        with self.store.transaction(self.principal,kb_id) as conn:
            existing=conn.execute('SELECT id FROM parse_versions WHERE kb_id=%s AND source_version_id=%s ORDER BY id LIMIT 1',(kb_id,source_version_id)).fetchone()
            if existing:return str(existing[0])
            row=conn.execute('SELECT sha256,filename FROM source_versions WHERE kb_id=%s AND id=%s',(kb_id,source_version_id)).fetchone()
            if not row:raise ProductError('NOT_FOUND','来源版本不存在或无权限')
        blob=self.store.settings.file_root/kb_id/row[0]
        with tempfile.TemporaryDirectory(prefix='gsm-source-') as tmp:
            path=Path(tmp)/Path(row[1]).name;path.write_bytes(blob.read_bytes())
            command=os.environ.get('GSM_MINERU_COMMAND',str(Path.cwd()/'runtime/mineru/bin/mineru-kit'))
            parsed=Parser(command=command).parse(path)
        return self.sources.save_parse(self.principal,kb_id,source_version_id,parsed.parser_version,parsed.blocks,raw=parsed.raw)['id']

    def blocks(self,kb_id,source_version_ids):
        result=[]
        for source_id in source_version_ids:
            parse_id=self.parse_source(kb_id,source_id)
            with self.store.transaction(self.principal,kb_id) as conn:
                rows=conn.execute('SELECT id,text,locator FROM source_blocks WHERE kb_id=%s AND parse_version_id=%s ORDER BY ordinal',(kb_id,parse_id)).fetchall()
            result.extend({'block_id':str(r[0]),'text':r[1],'locator':r[2]} for r in rows)
        return result

    def extract_candidates(self,kb_id,domain_id,blocks,llm):
        domain=self.build.get_domain(self.principal,kb_id,domain_id)
        aliases={f'B{i+1:04d}':block['block_id'] for i,block in enumerate(blocks)}
        visible=[{**block,'block_id':f'B{i+1:04d}'} for i,block in enumerate(blocks)]
        schema=Candidate.model_json_schema()
        schema['$defs']['EvidenceInput']['properties']['block_id']['enum']=list(aliases)
        prompt={'task':'抽取语义候选，返回 JSON 对象 {"candidates":[]}。先列 object，再列 assertion/relation/event/rule。local_id 用于批次内引用；identity 只含领域身份属性。evidence 必须是数组，每项是输入块 block_id 短标识和逐字 quote，不能写页码或编造块 ID。quantity 必须是 {"value":"10.25","unit":"W"}。decimal 用十进制字符串。缺失条件不得猜测。',
            'domain':domain.model_dump(mode='json'),'candidate_schema':schema,'untrusted_source_blocks':visible}
        allowed=set(aliases.values());usage={};attempts=[]
        for attempt in range(2):
            response=llm.complete(json.dumps(prompt,ensure_ascii=False))
            for key,value in response.usage.items():
                if isinstance(value,int):usage[key]=usage.get(key,0)+value
            raw=response.data.get('candidates');errors=[];normalized=[]
            if not isinstance(raw,list):errors.append({'path':'candidates','reason':'必须为候选数组'})
            else:
                for index,candidate in enumerate(raw):
                    try:typed=Candidate.model_validate(candidate)
                    except ValidationError as error:
                        errors.extend({'path':f'candidates.{index}.'+'.'.join(map(str,e['loc'])),'reason':e['msg']} for e in error.errors(include_input=False,include_url=False))
                        continue
                    item=typed.model_dump(mode='json')
                    for evidence in item['evidence']:
                        original=aliases.get(evidence['block_id'],evidence['block_id'])
                        if original not in allowed:errors.append({'path':f'candidates.{index}.evidence.block_id','reason':'只能引用当前样本给出的 Bxxxx 标识'})
                        evidence['block_id']=original
                    normalized.append(item)
            if errors:
                attempts.append({'candidate_ids':[],'invalid_count':len(errors)})
                if attempt==1:raise ProductError('INVALID_EXTRACTION','模型候选结构或证据标识仍不合法',errors)
                prompt['repair']={'instruction':'修正结构和证据标识，重新返回完整候选数组，不得编造事实。','previous_candidates':raw,'errors':errors}
                continue
            if not normalized and attempt==0:
                attempts.append({'candidate_ids':[],'invalid_count':0,'coverage':'empty'})
                prompt['repair']={'instruction':'上次未返回候选。请再次核对样本与抽取目标；若确实无相关内容可返回空数组并说明 extraction_notes，不得编造。'}
                continue
            result=self.build.ingest(self.principal,kb_id,domain_id,normalized)
            invalid=[{'candidate':c['payload'],'issues':c['issues']} for c in result['candidates'] if any(i['fatal'] for i in c['issues'])]
            attempts.append({'candidate_ids':[c['id'] for c in result['candidates']],'invalid_count':len(invalid)})
            if not invalid:break
            if attempt==0:
                from .review import ReviewService
                ReviewService(self.store).decide(self.principal,kb_id,[c['id'] for c in result['candidates']],'reject','系统自动纠错替代本次尝试，非人工业务确认')
            prompt['repair']={'instruction':'按具体错误修正整个候选批次。不能补造证据或身份；资料无法确定的保留未决。','previous_candidates':raw,'errors':invalid}
        return {'result':result,'usage':usage,'model':response.model,'attempts':len(attempts),'attempt_log':attempts,'coverage':'empty' if not result['candidates'] else 'candidates_returned'}

    def execute_task(self,kb_id,task_id):
        def extract(payload,checkpoint):
            if checkpoint.get('result'):return checkpoint
            domain_id=payload['domain_version_id'];domain=self.build.get_domain(self.principal,kb_id,domain_id)
            blocks=self.blocks(kb_id,payload['source_version_ids'])
            if sum(len(b['text']) for b in blocks)>100000:
                raise ProductError('SAMPLE_TOO_LARGE','首版单次预览限 10 万字符，请选择更小的样本批次')
            return self.extract_candidates(kb_id,domain_id,blocks,self.llm())
        def finish(payload,checkpoint):
            return {'build_id':self.build.finish(self.principal,kb_id,payload['domain_version_id'],payload['candidate_ids'])}
        def analyze(payload,checkpoint):
            blocks=self.blocks(kb_id,payload['source_version_ids'])
            from .domain import DomainDefinition,validate_domain
            response=self.llm().complete(json.dumps({'task':'依据用途、问题与资料建议领域定义。返回 JSON {"definition":符合schema的领域定义,"questions":需要用户选择的业务歧义列表，每项包含问题、少量选项、推荐和理由}。不要要求用户填写schema。','purpose':payload['purpose'],'questions':payload['questions'],'schema':DomainDefinition.model_json_schema(),'untrusted_sample_blocks':blocks[:20]},ensure_ascii=False))
            proposal=response.data
            try:validate_domain(proposal.get('definition',{}));proposal['validation']={'valid':True}
            except ProductError as error:proposal['validation']={'valid':False,'error':error.as_dict()}
            return {'proposal':proposal,'usage':response.usage,'model':response.model}
        def evaluate(payload,checkpoint):
            from .evaluation import EvaluationService
            return EvaluationService(self.store,self.llm()).run(self.principal,kb_id,payload['release_id'],payload['dataset'],payload['mode'])
        return Worker(self.tasks,{'extract':extract,'build':finish,'analyze':analyze,'evaluate':evaluate}).run(self.principal,kb_id,task_id)

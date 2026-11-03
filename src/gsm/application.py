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
from .observability import timed

class Application:
    def __init__(self,credential_path):
        self.credential_path=Path(credential_path)
        from .credentials import read_credentials
        config=read_credentials(self.credential_path)
        self.principal=Principal(config['role'],frozenset(config['kb_ids']))
        self.workspace_root=Path(config['workspace_root']).resolve() if config.get('workspace_root') else None
        settings=Settings.load()
        settings.source_root=Path(config['source_root']).resolve() if config.get('source_root') else None
        self.store=Store(settings);self.sources=SourceService(self.store);self.build=BuildService(self.store);self.tasks=TaskService(self.store)

    def publish(self,kb_id,build_id):
        from .releases import ReleaseService
        from .artifacts import current,expose
        self.principal.require(kb_id,write=True)
        with self.store.transaction(self.principal,kb_id) as lock:
            lock.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",('publication:'+kb_id,))
            service=ReleaseService(self.store,self.workspace_root)
            release=service.publish(self.principal,kb_id,build_id)
            if self.workspace_root:
                expose(self.workspace_root,release)
                current(self.workspace_root,service.current(self.principal,kb_id))
        return release

    def rollback(self,kb_id,release_id):
        from .releases import ReleaseService
        from .artifacts import current,expose
        self.principal.require(kb_id,write=True)
        with self.store.transaction(self.principal,kb_id) as lock:
            lock.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",('publication:'+kb_id,))
            from .search import QueryService
            QueryService(self.store).release(lock,kb_id,release_id)
            if self.workspace_root:expose(self.workspace_root,release_id)
            service=ReleaseService(self.store)
            service.rollback(self.principal,kb_id,release_id)
            if self.workspace_root:current(self.workspace_root,service.current(self.principal,kb_id))

    def llm(self):
        from dotenv import dotenv_values
        cfg={**dotenv_values('.env'),**os.environ}
        return LLM.from_env_file(Path(cfg.get('GSM_LLM_ENV_FILE',str(Path.home()/'code/.env'))).expanduser(),cfg.get('GSM_LLM_BASE_URL','https://api.deepseek.com'),cfg.get('GSM_LLM_MODEL','deepseek-flash'),allow_local=cfg.get('GSM_LLM_ALLOW_LOCAL','').lower() in ('1','true'),timeout=float(cfg.get('GSM_LLM_TIMEOUT','120')),tokenizer_path=cfg.get('GSM_TOKENIZER_FILE'),tokenizer_sha256=cfg.get('GSM_TOKENIZER_SHA256'))

    @timed('source.parse_or_cache')
    def parse_source(self,kb_id,source_version_id):
        self.principal.require(kb_id,write=True)
        with self.store.transaction(self.principal,kb_id) as conn:
            row=conn.execute('SELECT sha256,filename FROM source_versions WHERE kb_id=%s AND id=%s',(kb_id,source_version_id)).fetchone()
            if not row:raise ProductError('NOT_FOUND','来源版本不存在或无权限')
            expected='plain-text-v1' if Path(row[1]).suffix.lower() in ('.txt','.md') else Parser.PDF_VERSION
            existing=conn.execute('SELECT id FROM parse_versions WHERE kb_id=%s AND source_version_id=%s AND parser_version=%s ORDER BY id LIMIT 1',(kb_id,source_version_id,expected)).fetchone()
            if existing:return str(existing[0])
        blob=self.store.settings.file_root/kb_id/row[0]
        with tempfile.TemporaryDirectory(prefix='gsm-source-') as tmp:
            path=Path(tmp)/Path(row[1]).name;path.write_bytes(blob.read_bytes())
            command=os.environ.get('GSM_MINERU_COMMAND',str(Path.cwd()/'runtime/mineru/bin/mineru-kit'))
            parsed=Parser(command=command).parse(path)
        return self.sources.save_parse(self.principal,kb_id,source_version_id,parsed.parser_version,parsed.blocks,raw=parsed.raw,units=parsed.units,coverage=parsed.coverage)['id']

    @timed('source.load_blocks')
    def blocks(self,kb_id,source_version_ids):
        result=[]
        for source_id in source_version_ids:
            parse_id=self.parse_source(kb_id,source_id)
            with self.store.transaction(self.principal,kb_id) as conn:
                rows=conn.execute('SELECT id,text,locator FROM source_blocks WHERE kb_id=%s AND parse_version_id=%s ORDER BY ordinal',(kb_id,parse_id)).fetchall()
            result.extend({'source_version_id':source_id,'block_id':str(r[0]),'text':r[1],'locator':r[2]} for r in rows)
        return result

    @timed('extraction.validate_and_repair')
    def extract_candidates(self,kb_id,domain_id,blocks,llm,focus=None):
        domain=self.build.get_domain(self.principal,kb_id,domain_id)
        aliases={f'B{i+1:04d}':block['block_id'] for i,block in enumerate(blocks)}
        from .source_context import source_context
        visible=[{**source_context(block),'block_id':f'B{i+1:04d}'} for i,block in enumerate(blocks)]
        from .extraction_contract import extraction_contract
        contract=extraction_contract(domain);schema=contract['schema']
        schema['$defs']['EvidenceInput']['properties']['block_id']['enum']=list(aliases)
        prompt={'task':'抽取语义候选，返回 JSON 对象 {"candidates":[]}。先列 object，再列 assertion/relation/event/rule。local_id 用于批次内引用；identity 只含领域身份属性。evidence 必须是数组，每项是输入块 block_id 短标识和逐字 quote，不能写页码或编造块 ID。quantity 必须是 {"value":"10.25","unit":"W"}。decimal 用十进制字符串。缺失条件不得猜测。',
            'domain':domain.model_dump(mode='json'),'candidate_schema':schema,'emission_contract':contract['emission_contract'],'untrusted_source_blocks':visible}
        prompt['document_structure_policy']='每个 table_row 块含表头和完整数据行，逐行检查领域内事实，不能因正文重复第一行就漏掉其他行。context_before/context_after 仅为邻近上下文，不自动视为该表的标题或脚注。可确认属于当前表的标题/脚注条件必须随每行保留，不只生成独立说明。conditions 不限于 required_conditions；其他已声明且明确适用的条件也必须保留。原文未明确主体归属的公式、限制、误差不得挂到最近对象；无法定位归属的内容写入 extraction_notes，不生成 subject 为空或伪指向的断言。conditions 只能使用当前领域声明的条件名；不能表达的范围写入 extraction_notes，不能发明条件名。native_layout_inference 是解析候选结构，不是已核实业务事实。provenance 仅使用 source_statement/observation/calculation/inference；table_row 和 native_layout_inference 是解析表示标签，不是 provenance。空图片/公式由覆盖报告反映，不得补造。'
        prompt['reference_policy']='kind仅使用schema列出的类型；predicate必须严格使用对应kind的emission_contract.id，不得翻译或发明字段名。对象先定义local_id，所有subject/object/participants只能引用本批已定义local_id或明确提供的已知对象ID；不能把名字当ID。关系要核对声明语义、方向、端点类型和条件，不因两对象共现就连边。领域无法表达的内容放extraction_notes，供建库者修正领域，不能硬套相近谓词或丢弃真实条件。'
        if focus is not None:
            if not isinstance(focus,str) or not focus.strip() or len(focus)>4000:raise ProductError('INVALID_FOCUS','抽取重点必须为不超过4000字符的文本')
            prompt['extraction_focus']=focus
            prompt['focus_boundary']='重点仅限定当前领域和授权来源内的抽取范围，不得改变Schema、证据门禁、身份或条件要求。'
        allowed=set(aliases.values());by_block={b['block_id']:b for b in blocks};usage={};attempts=[];final_rejections=[]
        for attempt in range(2):
            try:response=llm.complete(json.dumps(prompt,ensure_ascii=False,separators=(',',':')))
            except ProductError as error:
                if error.code!='INVALID_MODEL_OUTPUT':raise
                for detail in error.details:
                    for key,value in detail.get('usage',{}).items():
                        if isinstance(value,int):usage[key]=usage.get(key,0)+value
                attempts.append({'candidate_ids':[],'invalid_count':1,'error':error.code})
                if attempt==1:
                    raise ProductError(error.code,'模型两次未返回完整 JSON，请缩小样本后重试',error.details,retryable=True) from None
                prompt['repair']={'instruction':'上次输出不是完整 JSON。请返回紧凑的合法对象，省略可选空字段，保留必需证据与条件，不得编造或以截断内容作为事实。'}
                continue
            for key,value in response.usage.items():
                if isinstance(value,int):usage[key]=usage.get(key,0)+value
            raw=response.data.get('candidates');errors=[];normalized=[];rejections=[]
            if not isinstance(raw,list):errors.append({'path':'candidates','reason':'必须为候选数组'})
            else:
                for index,candidate in enumerate(raw):
                    try:typed=Candidate.model_validate(candidate)
                    except ValidationError as error:
                        item_errors=[{'path':f'candidates.{index}.'+'.'.join(map(str,e['loc'])),'reason':e['msg'],'type':e['type']} for e in error.errors(include_input=False,include_url=False)]
                        errors.extend(item_errors);rejections.append({'index':index,'raw_candidate':candidate,'errors':item_errors})
                        continue
                    item=typed.model_dump(mode='json');item_errors=[]
                    for evidence in item['evidence']:
                        original=aliases.get(evidence['block_id'],evidence['block_id'])
                        if original not in allowed:item_errors.append({'path':f'candidates.{index}.evidence.block_id','reason':'只能引用当前样本给出的 Bxxxx 标识','type':'evidence_scope'})
                        evidence['block_id']=original
                        source=by_block.get(original,{})
                        if source.get('locator',{}).get('unit_type')=='table_row' and evidence['quote'] and evidence['quote'] in source['text']:
                            # A cell fragment alone loses its header, units and scope.
                            # Cite the complete parser-derived row, not invented prose.
                            evidence['quote']=source['text']
                    if item_errors:errors.extend(item_errors);rejections.append({'index':index,'raw_candidate':candidate,'errors':item_errors})
                    else:normalized.append(item)
            if errors:
                if attempt==0:
                    attempts.append({'candidate_ids':[],'invalid_count':len(errors)})
                    prompt['repair']={'instruction':'修正结构和证据标识，重新返回完整候选数组，不得编造事实。','previous_candidates':raw,'errors':errors}
                    continue
                if not normalized:raise ProductError('INVALID_EXTRACTION','模型候选仍全部不合法，未生成可核验记录',errors)
                final_rejections=rejections
            if not normalized and attempt==0:
                attempts.append({'candidate_ids':[],'invalid_count':0,'coverage':'empty'})
                prompt['repair']={'instruction':'上次未返回候选。请再次核对样本与抽取目标；若确实无相关内容可返回空数组并说明 extraction_notes，不得编造。'}
                continue
            result=self.build.ingest(self.principal,kb_id,domain_id,normalized)
            invalid=[{'candidate':c['payload'],'issues':c['issues']} for c in result['candidates'] if any(i['fatal'] for i in c['issues'])]
            attempts.append({'candidate_ids':[c['id'] for c in result['candidates']],'invalid_count':len(invalid),'structural_rejected_count':len(final_rejections)})
            if not invalid:break
            if attempt==0:
                from .review import ReviewService
                ReviewService(self.store).decide(self.principal,kb_id,[c['id'] for c in result['candidates']],'reject','系统自动纠错替代本次尝试，非人工业务确认')
            prompt['repair']={'instruction':'按具体错误修正整个候选批次。不能补造证据或身份；资料无法确定的保留未决。','previous_candidates':raw,'errors':invalid}
        from .extraction_quality import extraction_quality
        quality=extraction_quality(result['candidates'],[])
        return {'quality':quality,'result':result,'usage':usage,'model':response.model,'attempts':len(attempts),'attempt_log':attempts,'coverage':'partial_structural_validation' if final_rejections else ('empty' if not result['candidates'] else 'candidates_returned'),'extraction_rejections':final_rejections,'extraction_notes':response.data.get('extraction_notes',[])}

    @timed('task.execute')
    def execute_task(self,kb_id,task_id):
        def pipeline(payload,checkpoint):
            from .pipeline import run
            return run(self,kb_id,task_id,payload,checkpoint)
        def extract(payload,checkpoint):
            if checkpoint.get('result'):return checkpoint
            domain_id=payload['domain_version_id'];domain=self.build.get_domain(self.principal,kb_id,domain_id)
            blocks=self.blocks(kb_id,payload['source_version_ids'])
            summary=None
            if payload.get('sample_chars') is not None:
                from .sampling import extraction_samples
                blocks,summary=extraction_samples(blocks,payload['sample_chars'])
            elif sum(len(b['text']) for b in blocks)>100000:
                raise ProductError('SAMPLE_TOO_LARGE','单次预览限10万字符；可设置sample_chars进行限额预览')
            result=self.extract_candidates(kb_id,domain_id,blocks,self.llm(),focus=payload.get('focus'))
            if summary is not None:result.update(sample_summary=summary,coverage='bounded_preview_not_full_source')
            return result
        def revalidate(payload,checkpoint):
            if checkpoint.get('result'):return checkpoint
            return {'result':self.build.revalidate(self.principal,kb_id,payload['domain_version_id'],payload['candidate_ids']),'model':None,'usage':{}}
        def finish(payload,checkpoint):
            return {'build_id':self.build.finish(self.principal,kb_id,payload['domain_version_id'],payload['candidate_ids'])}
        def analyze(payload,checkpoint):
            blocks=self.blocks(kb_id,payload['source_version_ids'])
            from .domain import DomainDefinition,validate_domain
            from .sampling import domain_samples
            sampled,sample_summary=domain_samples(blocks)
            response=self.llm().complete_with_json_retry(json.dumps({'task':'依据用途、问题与资料建议领域定义。返回 JSON {"definition":符合schema的领域定义,"questions":需要用户选择的业务歧义列表，每项包含问题、少量选项、推荐和理由}。不要要求用户填写schema。','purpose':payload['purpose'],'questions':payload['questions'],'schema':DomainDefinition.model_json_schema(),'untrusted_sample_blocks':sampled},ensure_ascii=False))
            proposal=response.data
            try:validate_domain(proposal.get('definition',{}));proposal['validation']={'valid':True}
            except ProductError as error:proposal['validation']={'valid':False,'error':error.as_dict()}
            return {'proposal':proposal,'usage':response.usage,'model':response.model,'sample_summary':sample_summary}
        def evaluate(payload,checkpoint):
            from .evaluation import EvaluationService
            return EvaluationService(self.store,self.llm()).run(self.principal,kb_id,payload['release_id'],payload['dataset'],payload['mode'])
        return Worker(self.tasks,{'pipeline':pipeline,'extract':extract,'revalidate':revalidate,'build':finish,'analyze':analyze,'evaluate':evaluate}).run(self.principal,kb_id,task_id)

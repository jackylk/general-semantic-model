import functools,json
from pathlib import Path
import psycopg
from mcp.server.fastmcp import FastMCP
from gsm.application import Application
from gsm.domain import validate_domain as validate
from gsm.releases import ReleaseService
from gsm.search import QueryService
from gsm.review import ReviewService
from gsm.retrieval import RetrievalService
from gsm.errors import ProductError


def create_server(app:Application):
    role=app.principal.role
    mcp=FastMCP('GSM '+role,instructions='用户说“我要开始创建知识库”时，先调用 discover_spec，按开发者指南引导定义领域；无需用户手写 Schema。所有查询必须绑定知识库和发布版本。')
    p=app.principal;store=app.store;releases=ReleaseService(store);queries=QueryService(store)
    def tool(fn):
        @functools.wraps(fn)
        def guarded(*args,**kwargs):
            try:return fn(*args,**kwargs)
            except ProductError as error:return {'error':error.as_dict()}
            except psycopg.errors.UniqueViolation:return {'error':{'code':'ALREADY_EXISTS','message':'对象已存在，请读取或使用新的幂等键','retryable':False}}
            except (psycopg.Error,ValueError,TypeError,KeyError):return {'error':{'code':'INVALID_REQUEST','message':'请求参数、状态或引用不合法','retryable':False}}
        return mcp.tool()(guarded)

    @tool
    def describe_kb(kb_id:str)->dict:
        """查看授权知识库范围、当前发布版及能力限制。"""
        with store.transaction(p,kb_id) as conn:
            row=conn.execute('SELECT name,current_release FROM knowledge_bases WHERE id=%s',(kb_id,)).fetchone()
            if not row:raise ProductError('NOT_FOUND','知识库不存在或无权限')
        return {'kb_id':kb_id,'name':row[0],'current_release':str(row[1]) if row[1] else None,'limitations':['原型，未完成三领域验收','关系不等于因果','缺证据应说明不能确定']}

    @tool
    def get_release(kb_id:str,release_id:str)->dict:
        with store.transaction(p,kb_id) as conn:
            build_id,manifest=queries.release(conn,kb_id,release_id)
        return {'release_id':release_id,'build_id':build_id,'manifest':manifest}

    @tool
    def get_definitions(kb_id:str,release_id:str)->dict:
        with store.transaction(p,kb_id) as conn:
            _,manifest=queries.release(conn,kb_id,release_id)
        return app.build.get_domain(p,kb_id,manifest['domain_version_id']).model_dump(mode='json')

    @tool
    def query_records(kb_id:str,release_id:str,kind:str|None=None,subject:str|None=None,predicate:str|None=None,conditions:dict|None=None,limit:int=100)->dict:
        return {'records':queries.records(p,kb_id,release_id,kind,subject,predicate,conditions,limit)}

    @tool
    def query_paths(kb_id:str,release_id:str,start:str,target:str|None=None,max_depth:int=3,limit:int=20)->dict:
        return {'paths':queries.paths(p,kb_id,release_id,start,target,max_depth,limit)}

    @tool
    def search(kb_id:str,release_id:str,query:str,limit:int=10)->dict:
        return {'results':queries.search(p,kb_id,release_id,query,limit=limit)}

    @tool
    def read_evidence(kb_id:str,release_id:str,evidence_id:str)->dict:
        return releases.read_evidence(p,kb_id,release_id,evidence_id)

    @tool
    def get_wiki(kb_id:str,release_id:str)->dict:
        return queries.wiki(p,kb_id,release_id)

    @tool
    def retrieve(kb_id:str,release_id:str,question:str)->dict:
        return RetrievalService(store,app.llm()).retrieve(p,kb_id,release_id,question)

    @tool
    def submit_feedback(kb_id:str,release_id:str,message:str)->dict:
        if not message.strip() or len(message)>10000:raise ProductError('INVALID_FEEDBACK','反馈需为 1–10000 字符')
        with store.transaction(p,kb_id) as conn:
            queries.release(conn,kb_id,release_id)
            row=conn.execute('INSERT INTO feedback(kb_id,release_id,message) VALUES(%s,%s,%s) RETURNING id',(kb_id,release_id,message)).fetchone()
        return {'feedback_id':str(row[0]),'status':'queued_for_review'}

    if role!='developer':return mcp

    @tool
    def discover_spec()->dict:
        """创建知识库的首个入口：发现指南、定义 Schema 和完整示例。"""
        return {'entry_phrase':'我要开始创建知识库','allowed_kb_ids':sorted(p.kb_ids),'source_root':str(store.settings.source_root),'workflow':['了解用途和问题','选择资料样本','自动分析并建议领域','用例解释与少量业务选择','提交校验并预览抽取','检查证据冲突并修正','构建验收后发布'],
        'guide':Path('docs/developer-guide.md').read_text() if Path('docs/developer-guide.md').exists() else Path('docs/reference/domain.md').read_text(),
        'domain_schema':json.loads(Path('docs/reference/domain.schema.json').read_text()),'example':Path('examples/minimal/domain.yaml').read_text()}

    @tool
    def create_kb(kb_id:str,name:str)->dict:
        store.create_kb(p,kb_id,name);return {'kb_id':kb_id,'name':name}

    @tool
    def register_source(kb_id:str,relative_path:str)->dict:
        return app.sources.import_file(p,kb_id,relative_path)

    @tool
    def validate_domain(definition:dict)->dict:
        return {'valid':True,'definition':validate(definition).model_dump(mode='json')}

    @tool
    def submit_domain(kb_id:str,definition:dict)->dict:
        return {'domain_version_id':app.build.submit_domain(p,kb_id,definition)}

    @tool
    def analyze_samples(kb_id:str,source_version_ids:list[str],purpose:str,questions:list[str],idempotency_key:str)->dict:
        return app.tasks.submit(p,kb_id,'analyze',{'source_version_ids':source_version_ids,'purpose':purpose,'questions':questions},idempotency_key)

    @tool
    def preview_extraction(kb_id:str,domain_version_id:str,source_version_ids:list[str],idempotency_key:str)->dict:
        return app.tasks.submit(p,kb_id,'extract',{'domain_version_id':domain_version_id,'source_version_ids':source_version_ids},idempotency_key)

    @tool
    def get_task(kb_id:str,task_id:str)->dict:
        return app.tasks.get(p,kb_id,task_id)

    @tool
    def retry_task(kb_id:str,task_id:str)->dict:
        return app.tasks.retry(p,kb_id,task_id)

    @tool
    def list_candidates(kb_id:str,domain_version_id:str,limit:int=100,offset:int=0)->dict:
        p.require(kb_id,write=True)
        if not 1<=limit<=200 or offset<0:raise ProductError('INVALID_LIMIT','limit 1–200，offset 非负')
        with store.transaction(p,kb_id) as conn:
            rows=conn.execute("SELECT id,kind,payload,status FROM records WHERE kb_id=%s AND payload->>'domain_version_id'=%s ORDER BY id LIMIT %s OFFSET %s",(kb_id,domain_version_id,limit,offset)).fetchall()
        return {'candidates':[{'id':str(r[0]),'kind':r[1],'payload':r[2],'initial_status':r[3]} for r in rows]}

    @tool
    def review_candidates(kb_id:str,candidate_ids:list[str],decision:str,reason:str)->dict:
        return ReviewService(store).decide(p,kb_id,candidate_ids,decision,reason)

    @tool
    def start_build(kb_id:str,domain_version_id:str,candidate_ids:list[str],idempotency_key:str)->dict:
        return app.tasks.submit(p,kb_id,'build',{'domain_version_id':domain_version_id,'candidate_ids':candidate_ids},idempotency_key)

    @tool
    def publish(kb_id:str,build_id:str)->dict:
        return {'release_id':releases.publish(p,kb_id,build_id)}

    @tool
    def rollback(kb_id:str,release_id:str)->dict:
        releases.rollback(p,kb_id,release_id);return {'current_release':release_id}

    @tool
    def evaluate(kb_id:str,release_id:str,dataset:list[dict],mode:str,idempotency_key:str)->dict:
        return app.tasks.submit(p,kb_id,'evaluate',{'release_id':release_id,'dataset':dataset,'mode':mode},idempotency_key)

    @tool
    def get_onboarding(kb_id:str)->dict:
        from gsm.onboarding import OnboardingService
        return OnboardingService(store).get(p,kb_id)

    @tool
    def save_onboarding(kb_id:str,patch:dict,expected_revision:int)->dict:
        from gsm.onboarding import OnboardingService
        return OnboardingService(store).save(p,kb_id,patch,expected_revision)

    @tool
    def read_candidate_evidence(kb_id:str,candidate_id:str)->dict:
        p.require(kb_id,write=True)
        with store.transaction(p,kb_id) as conn:
            rows=conn.execute("SELECT e.id,e.quote,b.text,b.locator,pv.source_version_id,pv.id FROM evidence_links e JOIN source_blocks b ON b.kb_id=e.kb_id AND b.id=e.block_id JOIN parse_versions pv ON pv.kb_id=b.kb_id AND pv.id=b.parse_version_id WHERE e.kb_id=%s AND e.record_id=%s",(kb_id,candidate_id)).fetchall()
        return {'evidence':[{'id':str(r[0]),'quote':r[1],'text':r[2],'locator':r[3],'source_version_id':str(r[4]),'parse_version_id':str(r[5])} for r in rows]}

    @tool
    def list_conflicts(kb_id:str,domain_version_id:str)->dict:
        result=list_candidates(kb_id,domain_version_id,limit=200)
        return {'conflicts':[c for c in result['candidates'] if any(i['code']=='CONFLICT' for i in c['payload'].get('issues',[]))]}

    @tool
    def diff_releases(kb_id:str,old_release_id:str,new_release_id:str)->dict:
        with store.transaction(p,kb_id) as conn:
            _,old=queries.release(conn,kb_id,old_release_id);_,new=queries.release(conn,kb_id,new_release_id)
        return {'added_record_ids':sorted(set(new['record_ids'])-set(old['record_ids'])),'removed_record_ids':sorted(set(old['record_ids'])-set(new['record_ids'])),'old_release_id':old_release_id,'new_release_id':new_release_id}

    @mcp.resource('gsm://domain-schema')
    def schema_resource()->str:return Path('docs/reference/domain.schema.json').read_text()
    return mcp

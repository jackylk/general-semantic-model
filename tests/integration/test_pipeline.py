import json
import pytest
from gsm.workspaces import initialize_kb
from gsm.application import Application
from gsm.adapters.llm import Completion
from test_build import DOMAIN,build_env
from gsm.pipeline import split_batches


def test_chunk_plan_covers_original_text_without_losing_long_blocks():
    text='abcdef\n'*1000
    batches=split_batches([{'block_id':'b','source_version_id':'s','text':text,'locator':{}}],1000)
    spans=[block for batch in batches for block in batch]
    assert len(batches)>1 and all(sum(len(b['text']) for b in batch)<=1000 for batch in batches)
    covered=set()
    for block in spans:covered.update(range(block['span_start'],block['span_end']))
    assert covered==set(range(len(text)))


def test_pipeline_runs_all_sources_checkpoints_and_builds_cited_pages(tmp_path,monkeypatch):
    from gsm.adapters.embedding import Embedding
    monkeypatch.setattr(Embedding,'embed',lambda self,texts:[[0.0]*1024 for t in texts])
    root=tmp_path/'kb';info=initialize_kb(root,'自动构建');app=Application(info['roles']['producer']['credentials']);kb=info['kb_id'];dv=app.build.submit_domain(app.principal,kb,DOMAIN);sources=[]
    for i in range(2):
        file=root/'documents'/f'{i}.txt';file.write_text(f'设备 A 序号 001。设备 B 序号 002。A 连接 B。20℃时 A 功率 10.25 W。')
        sources.append(app.sources.import_file(app.principal,kb,file.name)['id'])
    app.sources.save_parse(app.principal,kb,sources[0],'plain-text-v1',[{'text':(root/'documents/0.txt').read_text()},{'text':'Review-only derived row','requires_review':True,'unit_type':'table_row'}])
    class Model:
        model='test';base_url='https://test.invalid'
        def complete(self,prompt,**kw):
            data=json.loads(prompt)
            if data.get('task')=='check_record_support':return Completion({'reviews':[{'id':r['id'],'supported':r['kind']!='relation','reason':'test verdict'} for r in data['records']]},'test',{'total_tokens':10})
            assert all(not b.get('locator',{}).get('requires_review') for b in data['untrusted_source_blocks'])
            block=data['untrusted_source_blocks'][0]['block_id']
            from test_build import candidates
            return Completion({'candidates':candidates(block)+[{'kind':'assertion','subject':{'bad':'shape'}}]},'test',{'total_tokens':10})
    monkeypatch.setattr(app,'llm',lambda:Model())
    task=app.tasks.submit(app.principal,kb,'pipeline',{'domain_version_id':dv,'source_version_ids':sources,'batch_chars':20000},'pipeline')
    done=app.execute_task(kb,task['id'])
    assert done['status']=='succeeded',done.get('error')
    result=done['checkpoint'];assert len(result['completed_batches'])==2 and result['coverage']['sources']==2
    assert len(result['excluded_record_ids'])==2
    assert result['extraction_validation']['rejected_count']==2
    assert len(result['extraction_rejections'])==2
    assert result['coverage']['blocks']==3 and result['coverage']['automatic_blocks']==2
    assert result['coverage']['deferred_blocks']==1 and len(result['deferred_block_ids'])==1
    assert result['build_id'] and result['coverage']['semantic_completeness']=='not_proven'
    rel=app.publish(kb,result['build_id'])
    assert (root/'releases'/rel/'manifest.json').exists()
    manifest=json.loads((root/'releases'/rel/'manifest.json').read_text())
    assert manifest['extraction_coverage']['rejected_count']==2 and 'raw_candidate' not in str(manifest)
    assert app.execute_task(kb,task['id'])['checkpoint']['build_id']==result['build_id']


def test_pipeline_retry_reuses_extracted_batch_after_review_failure(build_env,monkeypatch):
    from gsm.errors import ProductError
    from gsm.adapters.embedding import Embedding
    from test_build import candidates
    store,b,_,p,kb,dv,block=build_env
    app=object.__new__(Application);app.store=store;app.build=b;app.principal=p;app.workspace_root=None
    from gsm.tasks import TaskService
    app.tasks=TaskService(store)
    from gsm.sources import SourceService
    app.sources=SourceService(store)
    with store.transaction(p,kb) as conn:source=str(conn.execute('SELECT source_version_id FROM parse_versions WHERE kb_id=%s',(kb,)).fetchone()[0])
    counts={'extract':0,'review':0}
    def extraction(*args,**kwargs):
        counts['extract']+=1
        return {'result':b.ingest(p,kb,dv,candidates(block)),'usage':{'total_tokens':10}}
    class Model:
        model='test';base_url='https://test.invalid'
        def complete(self,prompt,**kw):
            counts['review']+=1
            if counts['review']==1:raise ProductError('MODEL_UNAVAILABLE','synthetic transient failure',retryable=True)
            records=json.loads(prompt)['records']
            return Completion({'reviews':[{'id':r['id'],'supported':True,'reason':'synthetic support'} for r in records]},'test',{'total_tokens':10})
    monkeypatch.setattr(app,'llm',lambda:Model());monkeypatch.setattr(app,'extract_candidates',extraction)
    monkeypatch.setattr(Embedding,'embed',lambda self,texts:[[0.0]*1024 for t in texts])
    task=app.tasks.submit(p,kb,'pipeline',{'domain_version_id':dv,'source_version_ids':[source],'batch_chars':20000},'resume')
    first=app.execute_task(kb,task['id']);assert first['status']=='failed' and first['checkpoint']['pending_batch']
    from gsm.pipeline import run
    with monkeypatch.context() as patch:
        patch.setattr('gsm.pipeline.product_fingerprint',lambda:'synthetic-new-code')
        with pytest.raises(ProductError) as changed:run(app,kb,task['id'],first['payload'],first['checkpoint'])
        assert changed.value.code=='PIPELINE_VERSION_CHANGED'
    app.tasks.retry(p,kb,task['id']);second=app.execute_task(kb,task['id'])
    assert second['status']=='succeeded' and counts=={'extract':1,'review':2}


def test_pipeline_stops_before_third_batch_when_many_candidates_never_pass(tmp_path,monkeypatch):
    from gsm.errors import ProductError
    root=tmp_path/'kb';info=initialize_kb(root,'preflight guard');app=Application(info['roles']['producer']['credentials']);kb=info['kb_id'];dv=app.build.submit_domain(app.principal,kb,DOMAIN);sources=[];counts={'extract':0}
    for n in range(3):
        file=root/'documents'/f'{n}.txt';file.write_text('设备 A 序号 001。');sources.append(app.sources.import_file(app.principal,kb,file.name)['id'])
    class Model:
        model='test';base_url='https://test.invalid'
        def complete(self,prompt,**kwargs):
            data=json.loads(prompt)
            if data.get('task')=='check_record_support':return Completion({'reviews':[{'id':r['id'],'supported':False,'reason':'synthetic unsupported'} for r in data['records']]},'test',{})
            counts['extract']+=1;block=data['untrusted_source_blocks'][0]['block_id']
            return Completion({'candidates':[{'kind':'object','local_id':f'o{i}','type_id':'device','identity':{'serial':'001'},'evidence':[{'block_id':block,'quote':'设备 A 序号 001'}]} for i in range(10)]},'test',{})
    monkeypatch.setattr(app,'llm',lambda:Model())
    task=app.tasks.submit(app.principal,kb,'pipeline',{'domain_version_id':dv,'source_version_ids':sources},'guard');result=app.execute_task(kb,task['id'])
    assert result['status']=='failed' and result['error']['code']=='PIPELINE_NO_SUPPORTED_PROGRESS'
    assert counts['extract']==2 and len(result['checkpoint']['completed_batches'])==2

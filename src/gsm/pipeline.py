"""Bounded, checkpointed source-wide extraction, support review and build."""
import hashlib,json
from pathlib import Path
from .errors import ProductError
from .observability import phase


def split_batches(blocks,budget):
    batches=[];current=[];size=0;source=None
    for block in blocks:
        text=block['text']
        if block.get('locator',{}).get('unit_type')=='table_row' and len(text)>budget:
            raise ProductError('STRUCTURED_UNIT_TOO_LARGE','表格行超过批次预算；请增加预算或先修正表格结构，不得截断行列关系')
        for start in range(0,len(text),budget):
            fragment={**block,'text':text[start:start+budget],'span_start':start,'span_end':min(len(text),start+budget)}
            if current and (source!=block['source_version_id'] or size+len(fragment['text'])>budget):batches.append(current);current=[];size=0
            current.append(fragment);size+=len(fragment['text']);source=block['source_version_id']
    if current:batches.append(current)
    return batches


def automatic_blocks(blocks):
    """Review-only derivatives remain inventoried, not sent to futile auto calls."""
    selected=[];deferred=[]
    for block in blocks:
        (deferred if block.get('locator',{}).get('requires_review') is True else selected).append(block)
    return selected,deferred


def product_fingerprint():
    root=Path(__file__).resolve().parent;digest=hashlib.sha256()
    for path in sorted(root.rglob('*.py')):
        digest.update(str(path.relative_to(root)).encode());digest.update(path.read_bytes())
    return digest.hexdigest()


def run(app,kb_id,task_id,payload,checkpoint):
    p=app.principal;domain_id=payload['domain_version_id'];budget=payload.get('batch_chars',20000)
    if not isinstance(budget,int) or not 1000<=budget<=40000:raise ProductError('INVALID_BATCH_SIZE','每批正文限制1000–40000字符')
    source_ids=payload['source_version_ids']
    if not source_ids or len(set(source_ids))!=len(source_ids):raise ProductError('INVALID_SOURCE_SET','需要不重复的授权来源集合')
    domain=app.build.get_domain(p,kb_id,domain_id);model=app.llm()
    version={'model':model.model,'base_url':model.base_url,'product_sha256':product_fingerprint()}
    state={**checkpoint}
    if state.get('version') and state['version']!=version:raise ProductError('PIPELINE_VERSION_CHANGED','构建模型或产品版本已变化，请保留旧任务并创建新任务')
    state.setdefault('version',version);state.setdefault('completed_batches',[]);state.setdefault('candidate_ids',[]);state.setdefault('approved_record_ids',[]);state.setdefault('excluded_record_ids',[]);state.setdefault('usage',{})
    def save(stage):app.tasks.checkpoint(p,kb_id,task_id,stage,state)
    def quality(selected=None):
        from .extraction_quality import extraction_quality
        with app.store.transaction(p,kb_id) as conn:
            rows=conn.execute("SELECT id,kind,status,payload->'issues' FROM records WHERE kb_id=%s AND id=ANY(%s::uuid[])",(kb_id,state['candidate_ids'])).fetchall()
        return extraction_quality([{'id':str(rid),'kind':kind,'status':status,'issues':issues or []} for rid,kind,status,issues in rows],state['approved_record_ids'],selected)
    with phase('pipeline.parse'):
        blocks=app.blocks(kb_id,source_ids)
    automatic,deferred=automatic_blocks(blocks)
    batches=split_batches(automatic,budget)
    signature=hashlib.sha256(json.dumps({'automatic':[(b['block_id'],b['span_start'],b['span_end']) for batch in batches for b in batch],'deferred':[b['block_id'] for b in deferred]},sort_keys=True).encode()).hexdigest()
    if state.get('batch_plan_hash') and state['batch_plan_hash']!=signature:raise ProductError('PIPELINE_INPUT_CHANGED','解析版本或批次计划发生变化')
    state['batch_plan_hash']=signature
    state['coverage']={'sources':len(source_ids),'source_ids':source_ids,'blocks':len(blocks),'characters':sum(len(b['text']) for b in blocks),'planned_batches':len(batches),'semantic_completeness':'not_proven','note':'处理字符覆盖不等于事实、关系或主题完整覆盖；空批次和未获支持记录保持可见。'}
    state['coverage'].update({'automatic_blocks':len(automatic),'automatic_characters':sum(len(b['text']) for b in automatic),'deferred_blocks':len(deferred),'deferred_characters':sum(len(b['text']) for b in deferred),'deferred_reason':'review_required_derivative_not_eligible_for_automatic_publication'})
    state['deferred_block_ids']=[b['block_id'] for b in deferred]
    state['document_coverage']=[app.sources.parse_report(p,kb_id,app.parse_source(kb_id,source_id)) for source_id in source_ids]
    state['coverage']['document_parse_status']='incomplete' if any(r['coverage'].get('status') in ('incomplete','legacy_unassessed') for r in state['document_coverage']) else 'text_extracted_not_semantically_complete'
    save('parsed')
    for index,batch in enumerate(batches):
        if index in state['completed_batches']:continue
        pending=state.get('pending_batch')
        if not pending or pending['index']!=index:
            with phase('pipeline.extract'):
                extracted=app.extract_candidates(kb_id,domain_id,batch,model,focus=payload.get('focus'))
            records=extracted['result']['candidates'];pending={'index':index,'records':records,'extraction_usage':extracted['usage'],'extraction_notes':extracted.get('extraction_notes',[]),'extraction_rejections':extracted.get('extraction_rejections',[])};state['pending_batch']=pending;save('extracted')
        records=pending['records'];eligible=[r for r in records if r['status']=='verified']
        supported=[];reviews=[];usage={}
        if eligible:
            from .support_review import review_records
            with phase('pipeline.support_review'):
                reviews,usage=review_records(model,domain.model_dump(mode='json'),eligible,batch,pending,lambda:save('reviewing'))
            supported=[r['id'] for r in reviews if r['supported']]
        state.setdefault('extraction_rejections',[]).extend({'batch_index':index,**r} for r in pending.get('extraction_rejections',[]))
        state['extraction_validation']={'status':'partial_structural_validation' if state['extraction_rejections'] else 'structurally_validated_not_semantically_complete','rejected_count':len(state['extraction_rejections']),'semantic_completeness':'not_proven'}
        state.setdefault('supported_evidence_block_ids',[]).extend(e['block_id'] for r in records if r['id'] in supported for e in r['payload'].get('evidence',[]))
        state['candidate_ids'].extend(r['id'] for r in records);state['approved_record_ids'].extend(supported);state['excluded_record_ids'].extend(r['id'] for r in records if r['id'] not in supported)
        state.setdefault('batch_reports',[]).append({'index':index,'source_ids':sorted({b['source_version_id'] for b in batch}),'candidate_count':len(records),'support_reviews':reviews,'accepted_count':len(supported),'extraction_notes':pending.get('extraction_notes',[]),'method':'model_support_review_not_expert_confirmation'})
        for values in (pending['extraction_usage'],usage):
            for key,value in values.items():
                if isinstance(value,int):state['usage'][key]=state['usage'].get(key,0)+value
        state['completed_batches'].append(index);state.pop('pending_batch',None);state['quality']=quality();save('reviewed')
        if len(state['completed_batches'])>=2 and state['quality']['requires_extraction_correction']:
            state['status']='needs_domain_correction';save('needs_domain_correction')
            raise ProductError('PIPELINE_DOMAIN_MISMATCH' if state['quality']['requires_domain_correction'] else 'PIPELINE_EXTRACTION_QUALITY','至少半数候选未通过自动校验，已停止以避免仅发布对象掩盖事实抽取失败；请根据错误分布修正领域映射、抽取协议或原文证据，不得放宽门禁',[{'quality':state['quality']}])
        if len(state['completed_batches'])>=2 and len(state['candidate_ids'])>=20 and not state['approved_record_ids']:
            state['status']='needs_domain_correction';save('needs_domain_correction')
            raise ProductError('PIPELINE_NO_SUPPORTED_PROGRESS','连续批次产生多条候选但无通过项，已停止以避免无效Token消耗；请限额预览并修正领域/证据问题，不得放宽产品门禁')
    from .document_units import table_row_coverage
    state['table_row_coverage']=table_row_coverage(blocks,state.get('supported_evidence_block_ids',[]))
    with app.store.transaction(p,kb_id) as conn:
        rows=conn.execute('SELECT id,kind,payload FROM records WHERE kb_id=%s AND id=ANY(%s::uuid[])',(kb_id,state['approved_record_ids'])).fetchall()
    # Keep only references whose object records have themselves passed support review.
    objects={payload.get('object_id') for _,kind,payload in rows if kind=='object'}
    domain=app.build.get_domain(p,kb_id,domain_id);props={x.id:x for x in domain.properties};selected=[]
    for rid,kind,payload in rows:
        refs=[]
        if kind in ('assertion','relation','rule'):refs.append(payload.get('subject'))
        if kind=='relation':refs.append(payload.get('object'))
        if kind=='event':refs.extend(v.get('object') for v in payload.get('participants',[]))
        definition=props.get(payload.get('predicate')) if kind=='assertion' else None
        if definition and definition.value_type=='object_ref':refs.append(payload.get('value'))
        if definition and definition.value_type=='list' and definition.item_type=='object_ref':refs.extend(payload.get('value') or [])
        if all(ref in objects for ref in refs):selected.append(str(rid))
        else:state['excluded_record_ids'].append(str(rid))
    with app.store.transaction(p,kb_id) as conn:
        final_evidence=conn.execute('SELECT DISTINCT block_id FROM evidence_links WHERE kb_id=%s AND record_id=ANY(%s::uuid[])',(kb_id,selected)).fetchall()
    state['table_row_coverage']=table_row_coverage(blocks,[str(row[0]) for row in final_evidence])
    state['quality']=quality(selected);state['extraction_validation']['semantic_quality']=state['quality']
    state['selected_record_ids']=sorted(set(selected));state['excluded_record_ids']=sorted(set(state['excluded_record_ids']))
    if not selected:save('needs_correction');raise ProductError('NO_SUPPORTED_RECORDS','没有可构建的完整且获支持记录，请查看批次缺口并修正领域或资料')
    if not state.get('build_id'):
        with phase('pipeline.build'):state['build_id']=app.build.finish(p,kb_id,domain_id,state['selected_record_ids'],source_parse_ids=[r['parse_version_id'] for r in state['document_coverage']],extraction_coverage=state.get('extraction_validation'))
    state['status']='ready_for_preview_and_publication';save('build_ready')
    if app.workspace_root:
        from .artifacts import atomic,dump
        atomic(app.workspace_root/'reports/producer'/f'pipeline-{task_id}.json',dump(state))
    return state

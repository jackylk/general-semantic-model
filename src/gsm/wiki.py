"""Deterministic, cited navigation pages derived from semantic records."""
import json


def render_records(rows,domain,citations,object_names=None):
    definitions={d.id:d.name for group in (domain.types,domain.properties,domain.relations,domain.events,domain.rules) for d in group}
    objects={payload.get('object_id'):payload.get('name') or payload.get('object_id') for _,kind,payload in rows if kind=='object'}
    objects.update(object_names or {})
    support={}
    for c in citations:support.setdefault(c['record_id'],[]).append(c['evidence_id'])
    lines=[f'# {domain.name}', '本文从本发布版语义记录派生；请沿引用读取原文核验。']
    for rid,kind,p in rows:
        name=objects.get(p.get('subject'),p.get('name') or p.get('subject') or '')
        if kind=='object': sentence=f"{p.get('name') or p.get('object_id')}（{definitions.get(p.get('type_id'),p.get('type_id'))}），身份：{json.dumps(p.get('identity'),ensure_ascii=False)}"
        elif kind=='assertion': sentence=f"{name} · {definitions.get(p.get('predicate'),p.get('predicate'))}：{json.dumps(p.get('value'),ensure_ascii=False)}"
        elif kind=='relation':sentence=f"{name} → {definitions.get(p.get('predicate'),p.get('predicate'))} → {objects.get(p.get('object'),p.get('object'))}"
        elif kind=='event':sentence=f"{definitions.get(p.get('type_id'),p.get('type_id'))}：{json.dumps(p.get('participants'),ensure_ascii=False)}"
        else:sentence=f"{name} · {p.get('rule',{}).get('name','规则')}：{p.get('rule',{}).get('conclusion','')}"
        if p.get('conditions'):sentence+='；条件：'+json.dumps(p['conditions'],ensure_ascii=False)
        if p.get('provenance') in ('inference','calculation'):sentence+='；类别：'+p['provenance']
        quotes=list(dict.fromkeys(e.get('quote','') for e in p.get('evidence',[]) if e.get('quote')))
        if quotes:sentence+='；原文摘录：'+json.dumps(quotes,ensure_ascii=False)
        refs=' '.join(f'[证据 {e}]({e})' for e in support.get(str(rid),[]))
        lines.append(f'- {sentence}。{refs}（记录 {rid}）')
    return {'text':'\n\n'.join(lines),'citations':citations}



def render_wiki(rows,domain,citations):
    """Plan readable type/topic pages from the domain, never from an industry list."""
    import hashlib
    rows=sorted(rows,key=lambda r:str(r[0]));objects={p.get('object_id'):p for _,kind,p in rows if kind=='object'}
    labels={t.id:t.name for t in domain.types};groups={}
    for row in rows:
        _,kind,p=row
        key=p.get('type_id') if kind=='object' else objects.get(p.get('subject'),{}).get('type_id')
        key=key or ('events' if kind=='event' else 'records')
        groups.setdefault(key,[]).append(row)
    catalog=[];pages=[]
    for key,items in sorted(groups.items()):
        title=labels.get(key,key);slug=hashlib.sha256(key.encode()).hexdigest()[:16]
        for part in range(0,len(items),60):
            selected=items[part:part+60];ids={str(r[0]) for r in selected};refs=[c for c in citations if c['record_id'] in ids]
            path=f'topic-{slug}-{part//60+1}.md';body=render_records(selected,domain,refs,{oid:obj.get('name') or oid for oid,obj in objects.items()})['text']
            body=body.split('\n\n',1)[1] if '\n\n' in body else body
            body=f'# {title}'+(f'（{part//60+1}）' if len(items)>60 else '')+'\n\n[返回知识目录](index.md)\n\n'+body
            page={'path':path,'title':title,'text':body,'record_ids':sorted(ids),'citations':refs};pages.append(page);catalog.append({'path':path,'title':title,'record_count':len(ids)})
    index=f'# {domain.name}：知识目录\n\n以下主题来自当前领域定义及已核验记录。事实、条件和原文证据随同发布版固定。\n\n'+'\n'.join(f"- [{p['title']}]({p['path']})：{p['record_count']}条记录" for p in catalog)
    for page in pages:
        related=[entry for entry in catalog if entry['path']!=page['path']]
        if related:page['text']+='\n\n## 相关主题\n\n'+'\n'.join(f"- [{p['title']}]({p['path']})" for p in related[:12])
    overview=render_records(rows,domain,citations)
    return {**overview,'format_version':2,'pages':[{'path':'index.md','title':domain.name,'text':index,'record_ids':[],'citations':[]},*pages],'catalog':catalog,'record_ids':[str(r[0]) for r in rows],'planning_method':'domain_type_topics_with_bounded_pages','limitations':['主题页从记录确定性生成；未通过人工确认的范围外知识不会补写。']}

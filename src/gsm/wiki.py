"""Deterministic, cited navigation pages derived from semantic records."""
import json


def render_wiki(rows,domain,citations):
    definitions={d.id:d.name for group in (domain.types,domain.properties,domain.relations,domain.events,domain.rules) for d in group}
    objects={payload.get('object_id'):payload.get('name') or payload.get('object_id') for _,kind,payload in rows if kind=='object'}
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

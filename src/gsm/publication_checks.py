from .errors import ProductError


def reference_closure(rows,domain):
    objects={p.get('object_id') for _,kind,p in rows if kind=='object'};missing=set();properties={p.id:p for p in domain.properties}
    for _,kind,p in rows:
        refs=[]
        if kind in ('assertion','relation','rule'):refs.append(p.get('subject'))
        if kind=='relation':refs.append(p.get('object'))
        if kind=='event':refs.extend(x.get('object') for x in p.get('participants',[]))
        definition=properties.get(p.get('predicate')) if kind=='assertion' else None
        if definition and definition.value_type=='object_ref':refs.append(p.get('value'))
        if definition and definition.value_type=='list' and definition.item_type=='object_ref':refs.extend(p.get('value') or [])
        missing.update(str(r) for r in refs if r not in objects)
    if missing:raise ProductError('REFERENCE_CLOSURE_REQUIRED','发布集合缺少被引用的对象记录',[{'object_ids':sorted(missing)}])

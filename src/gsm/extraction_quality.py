"""Record-level quality accounting, independent of domain labels or industries."""
from collections import Counter
KINDS=('object','assertion','relation','event','rule')
BINDING_ERRORS={'UNKNOWN_TYPE','UNKNOWN_PREDICATE','UNKNOWN_EVENT','UNKNOWN_RULE','SUBJECT_UNRESOLVED','OBJECT_UNRESOLVED','SUBJECT_TYPE_MISMATCH','OBJECT_TYPE_MISMATCH','UNKNOWN_CONDITION','UNSUPPORTED_RECORD_KIND'}

def extraction_quality(records,supported_ids,selected_ids=None):
    records=list({r['id']:r for r in records}.values());supported=set(supported_ids);selected=set(selected_ids or [])
    funnel={k:{'candidates':0,'eligible_for_support':0,'support_passed':0,'selected_for_build':0 if selected_ids is not None else None,'published':None} for k in KINDS}
    issues=Counter();invalid=0;binding=0;unknown=0
    for record in records:
        payload=record.get('payload') or {};kind=record.get('kind') or payload.get('kind');errors=record.get('issues',payload.get('issues',[]))
        codes={e['code'] for e in errors if isinstance(e,dict) and isinstance(e.get('code'),str)};issues.update(codes)
        if any(e.get('fatal') for e in errors):invalid+=1
        if codes&BINDING_ERRORS:binding+=1
        if kind not in funnel:unknown+=1;continue
        row=funnel[kind];row['candidates']+=1
        if record.get('status') in ('verified','confirmed'):row['eligible_for_support']+=1
        if record['id'] in supported:row['support_passed']+=1
        if selected_ids is not None and record['id'] in selected:row['selected_for_build']+=1
    return {'semantic_funnel':funnel,'issue_counts':dict(issues),'candidate_count':len(records),'fatal_candidate_count':invalid,'binding_error_candidates':binding,'unclassified_candidates':unknown,
            'requires_domain_correction':len(records)>=20 and binding*2>=len(records) and binding>=10,
            'requires_extraction_correction':len(records)>=20 and invalid*2>=len(records),'quality_accepted':False,'semantic_recall':'not_proven','counting_note':'unique record IDs; issue tags may overlap; support is model review, not source completeness'}

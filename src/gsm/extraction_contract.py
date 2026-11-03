"""Compile a model-facing emission protocol from declarative domain data."""
from .build import Candidate

def extraction_contract(domain):
    d=domain.model_dump(mode='json');schema=Candidate.model_json_schema()
    kinds=['object']
    for group,kind in [('properties','assertion'),('relations','relation'),('events','event'),('rules','rule')]:
        if d.get(group):kinds.append(kind)
    schema['properties']['kind']={'type':'string','enum':kinds}
    predicates=sorted({item['id'] for group in ('properties','relations','rules') for item in d.get(group,[])})
    type_ids=sorted({item['id'] for group in ('types','events') for item in d.get(group,[])})
    for field,values in [('predicate',predicates),('type_id',type_ids)]:
        schema['properties'][field]={'anyOf':[{'type':'string','enum':values},{'type':'null'}]}
    schema['properties']['conditions']={'type':'object','properties':{c['id']:{'description':f"{c.get('name') or c['id']}; value_type={c['value_type']}"} for c in d['conditions']},'additionalProperties':False}
    keys={'id','name','description','identity','subject_types','object_types','required_conditions','value_type','units','enum_values','roles','applies_to','when','conclusion'}
    emission={kind:[{k:v for k,v in item.items() if k in keys} for item in d.get(group,[])] for group,kind in [('types','object'),('properties','assertion'),('relations','relation'),('events','event'),('rules','rule')]}
    return {'schema':schema,'emission_contract':emission}

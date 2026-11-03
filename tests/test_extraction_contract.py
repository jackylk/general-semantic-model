from gsm.domain import validate_domain
from gsm.extraction_contract import extraction_contract


def definition(prefix):
 return validate_domain({'schema_version':'1','id':prefix,'name':prefix,'types':[{'id':prefix,'name':prefix,'identity':['serial']}],'properties':[{'id':'serial','name':'编号','subject_types':[prefix],'value_type':'string'}],'relations':[{'id':'links','name':'有向链接','subject_types':[prefix],'object_types':[prefix]}]})


def test_contract_compiles_only_declared_predicates_and_record_kinds():
 contract=extraction_contract(definition('node'))
 props=contract['schema']['properties']
 assert props['kind']['enum']==['object','assertion','relation']
 assert set(props['predicate']['anyOf'][0]['enum'])=={'serial','links'}
 assert contract['emission_contract']['relation'][0]['object_types']==['node']
 assert contract['emission_contract']['object'][0]['identity']==['serial']


def test_contract_has_no_domain_specific_defaults():
 one=extraction_contract(definition('node'));two=extraction_contract(definition('sample'))
 assert 'node' not in str(two)
 assert one['emission_contract']['assertion'][0]['subject_types']==['node']
 assert two['emission_contract']['assertion'][0]['subject_types']==['sample']

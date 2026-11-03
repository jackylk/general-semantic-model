from gsm.extraction_quality import extraction_quality


def test_objects_cannot_hide_failed_fact_protocol():
 records=[{'id':'obj','kind':'object','status':'verified','issues':[]}]+[{'id':str(i),'kind':'assertion','status':'candidate','issues':[{'code':'UNKNOWN_PREDICATE','fatal':True}]} for i in range(20)]
 report=extraction_quality(records,['obj'])
 assert report['requires_domain_correction']
 assert report['semantic_funnel']['assertion']['support_passed']==0
 assert report['issue_counts']['UNKNOWN_PREDICATE']==20
 assert report['semantic_recall']=='not_proven'


def test_zero_edges_is_not_automatically_a_schema_failure():
 report=extraction_quality([{'id':'a','kind':'object','status':'verified','issues':[]}],['a'])
 assert not report['requires_domain_correction']
 assert report['semantic_funnel']['relation']['candidates']==0
 assert report['quality_accepted'] is False


def test_evidence_failures_are_not_misreported_as_majority_domain_failures():
 records=[]
 for i in range(100):
  code='UNKNOWN_PREDICATE' if i<10 else 'EVIDENCE_NOT_LOCATED' if i<50 else None
  records.append({'id':str(i),'kind':'assertion','status':'candidate' if code else 'verified','issues':[{'code':code,'fatal':True}] if code else []})
 report=extraction_quality(records,[])
 assert not report['requires_domain_correction']
 assert report['requires_extraction_correction']

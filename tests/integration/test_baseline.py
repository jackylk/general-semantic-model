from test_build import build_env,candidates
from gsm.releases import ReleaseService
from gsm.search import QueryService


def test_baseline_search_uses_original_blocks_and_stable_evidence(build_env):
    store,b,review,p,kb,dv,block=build_env
    result=b.ingest(p,kb,dv,candidates(block))
    bid=b.finish(p,kb,dv,[c['id'] for c in result['candidates']],embed=False)
    rel=ReleaseService(store).publish(p,kb,bid)
    hits=QueryService(store).baseline_search(p,kb,rel,'功率',use_vector=False)
    assert hits and hits[0]['evidence_id'].startswith('block:')
    original=ReleaseService(store).read_evidence(p,kb,rel,hits[0]['evidence_id'])
    assert '10.25 W' in original['text']

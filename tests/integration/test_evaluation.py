from test_build import build_env,candidates
from gsm.evaluation import EvaluationService
from gsm.releases import ReleaseService
from gsm.adapters.llm import Completion


def test_evaluation_preserves_human_ground_truth_without_self_grading(build_env):
    store,b,review,p,kb,dv,block=build_env
    records=b.ingest(p,kb,dv,candidates(block))
    rel=ReleaseService(store).publish(p,kb,b.finish(p,kb,dv,[r['id'] for r in records['candidates']],embed=False))
    class Model:
        def complete(self,*args,**kwargs):return Completion({'action':'finish','answer':'缺少证据','status':'insufficient','citations':[]},'test',{'total_tokens':10})
    report=EvaluationService(store,Model()).run(p,kb,rel,[{'id':'q1','question':'功率？','expected_answer':'20℃时10.25 W','provenance':'人工基准'}],mode='baseline')
    assert report['results'][0]['human_grade'] is None
    assert report['results'][0]['expected_answer']=='20℃时10.25 W'
    assert report['mode']=='baseline'

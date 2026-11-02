import json
from gsm.errors import ProductError


def test_timing_logs_nested_phases_without_capturing_content_or_secrets(tmp_path,monkeypatch):
    from gsm.observability import timed
    path=tmp_path/'timings.jsonl';monkeypatch.setenv('GSM_TIMING_LOG',str(path))
    @timed('model')
    def child(prompt,api_key):return 42
    @timed('task')
    def parent(kb_id,task_id):return child('private source','private credential')
    assert parent('kb','job')==42
    data=[json.loads(l) for l in path.read_text().splitlines()]
    assert len(data)==2 and all(x['duration_ms']>=0 for x in data)
    assert data[0]['parent_id']==data[1]['span_id']
    assert data[0]['context']['task_id']=='job'
    assert 'private' not in path.read_text()
    @timed('failure')
    def failure():raise ProductError('TEST_ERROR','private failure message')
    try:failure()
    except ProductError:pass
    row=json.loads(path.read_text().splitlines()[-1]);assert row['error_code']=='TEST_ERROR'
    assert 'private failure message' not in path.read_text()

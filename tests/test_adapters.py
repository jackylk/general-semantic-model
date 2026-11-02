import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import pytest
from gsm.adapters.llm import LLM
from gsm.adapters.embedding import Embedding
from gsm.adapters.mineru import Parser
from gsm.errors import ProductError

@pytest.fixture
def endpoint():
    class Handler(BaseHTTPRequestHandler):
        payload={}; status=200
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(self.status);self.end_headers();self.wfile.write(json.dumps(self.payload).encode())
        def log_message(self,*args): pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    t=threading.Thread(target=server.serve_forever,daemon=True); t.start()
    yield f'http://127.0.0.1:{server.server_port}',Handler
    server.shutdown();t.join()


def test_llm_parses_json_and_records_usage(endpoint):
    url,h=endpoint;h.payload={'choices':[{'message':{'content':'{"answer":42}'},'finish_reason':'stop'}],'usage':{'total_tokens':12},'model':'test'}
    response=LLM(url,'test','not-a-real-key',allow_local=True).complete('json please')
    assert response.data=={'answer':42}
    assert response.usage['total_tokens']==12

@pytest.mark.parametrize('content,reason',[('','stop'),('  ','stop'),('not json','stop'),('{"a":1}','length')])
def test_llm_rejects_empty_malformed_or_truncated_json(endpoint,content,reason):
    url,h=endpoint;h.payload={'choices':[{'message':{'content':content},'finish_reason':reason}]}
    with pytest.raises(ProductError): LLM(url,'test','secret',allow_local=True).complete('json')


def test_embedding_checks_batch_dimensions_and_finite_values(endpoint):
    url,h=endpoint;h.payload={'data':[{'index':0,'embedding':[1.0,float('nan')]}]}
    with pytest.raises(ProductError): Embedding(url,'test',dimensions=2).embed(['x'])
    h.payload={'data':[{'index':0,'embedding':[1.,2.]}]}
    assert Embedding(url,'test',dimensions=2).embed(['x'])==[[1.,2.]]
    with pytest.raises(ProductError): Embedding(url,'test',dimensions=3).embed(['x'])


def test_text_parser_keeps_block_locations(tmp_path):
    p=tmp_path/'sample.txt';p.write_text('第一段\n\n第二段')
    result=Parser().parse(p)
    assert [b['text'] for b in result.blocks]==['第一段','第二段']
    assert result.blocks[1]['paragraph']==2


def test_mineru_structure_keeps_page_and_table_cells():
    result=Parser.from_middle({'pages':[{'page_idx':0,'blocks':[{'type':'table','bbox':[1,2,3,4],'content':'表格','cells':[['标题','值'],['温度','20℃']]}]}]},'test-v1')
    assert result.blocks[0]['page']==1
    assert result.blocks[0]['cells'][1]==['温度','20℃']
    assert result.blocks[0]['bbox']==[1,2,3,4]


def test_mineru_inline_spans_are_text_not_python_lists():
    result=Parser.from_middle({'pages':[{'page_idx':3,'blocks':[{'type':'text','content':[{'type':'text','content':'补贴'},{'type':'text','content':'100元'}]}]}]},'v1')
    assert result.blocks[0]['text']=='补贴100元'
    assert result.blocks[0]['page']==4


def test_local_flash_pdf_uses_native_text_mode_without_loading_ocr(tmp_path):
    command=tmp_path/'mineru-kit'
    command.write_text('''#!/usr/bin/env python3
import sys,json
from pathlib import Path
args=sys.argv[1:]
if '--ocr-mode' not in args or args[args.index('--ocr-mode')+1]!='txt':sys.exit(2)
Path(args[args.index('-o')+1]).write_text(json.dumps({'pages':[{'page_idx':0,'blocks':[{'type':'text','content':'native text'}]}]}))
''')
    command.chmod(0o755);source=tmp_path/'source.pdf';source.write_bytes(b'%PDF-test')
    result=Parser(command=str(command)).parse(source)
    assert result.blocks[0]['text']=='native text'


def test_truncation_error_explains_output_budget_without_leaking_content(endpoint):
    url,h=endpoint;h.payload={'choices':[{'message':{'content':'private partial source'},'finish_reason':'length'}],'usage':{'completion_tokens':4096}}
    with pytest.raises(ProductError) as exc:LLM(url,'test','secret',allow_local=True).complete('json')
    assert exc.value.details[0]['reason']=='truncated'
    assert 'private partial source' not in str(exc.value.as_dict())


def test_embedding_bounds_requests_and_preserves_all_long_input_chunks():
    from http.server import HTTPServer,BaseHTTPRequestHandler
    import math
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));texts=body['input'];received.append(texts)
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'data':[{'index':i,'embedding':[float(len(t)),1.]} for i,t in enumerate(texts)]}).encode())
        def log_message(self,*args):pass
    server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        result=Embedding(f'http://127.0.0.1:{server.server_port}','test',dimensions=2,batch_size=2,max_text_chars=8,max_batch_chars=12).embed(['abcdefghijklmnopqrst','xy','z'])
        assert len(result)==3 and result[1:]==[[2.,1.],[1.,1.]]
        assert math.isclose(sum(v*v for v in result[0]),1.)
        assert ''.join(t for batch in received for t in batch)=='abcdefghijklmnopqrstxyz'
        assert all(len(batch)<=2 and sum(map(len,batch))<=12 and max(map(len,batch))<=8 for batch in received)
    finally:server.shutdown();thread.join()


def test_llm_per_call_output_cap_is_sent_to_provider(endpoint,monkeypatch):
    import gsm.adapters.llm as module
    sent=[]
    def post(url,payload,*args,**kwargs):
        sent.append(payload['max_tokens']);return {'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]}
    monkeypatch.setattr(module,'post_json',post)
    model=LLM('https://example.invalid','test','dummy',max_tokens=16384)
    model.complete('x',max_tokens=300);model.complete('x',max_tokens=20000)
    assert sent==[300,16384]

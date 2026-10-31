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

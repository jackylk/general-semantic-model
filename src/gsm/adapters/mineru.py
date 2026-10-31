"""Local-only MinerU process boundary. Never silently uploads documents."""
from dataclasses import dataclass
from pathlib import Path
import json
import subprocess
import tempfile
from gsm.errors import ProductError

@dataclass
class ParsedDocument:
    parser_version: str
    blocks: list[dict]
    raw: dict

class Parser:
    def __init__(self,command='mineru-kit',timeout=300):
        self.command=command;self.timeout=timeout

    def parse(self,path):
        path=Path(path)
        if path.suffix.lower() in ('.txt','.md'):
            text=path.read_text()
            return ParsedDocument('plain-text-v1',[{'text':t,'paragraph':i+1} for i,t in enumerate(text.split('\n\n')) if t.strip()],{'text':text})
        with tempfile.TemporaryDirectory(prefix='gsm-mineru-') as temp:
            output=Path(temp)/'middle.json'
            try:
                # Explicit local mode is mandatory; stdout/stderr may contain source text, so never log it.
                subprocess.run([self.command,'parse',str(path),'--tier','flash','--disable-image-analysis','--format','middle_json','-o',str(output)],check=True,capture_output=True,timeout=self.timeout)
                raw=json.loads(output.read_text())
            except FileNotFoundError:
                raise ProductError('PARSER_UNAVAILABLE','未安装配置的本地 mineru-kit 命令') from None
            except subprocess.TimeoutExpired:
                raise ProductError('PARSER_TIMEOUT','本地文档解析超时',retryable=True) from None
            except (subprocess.CalledProcessError,ValueError,OSError):
                raise ProductError('PARSE_FAILED','本地 MinerU 解析失败；原件保持不变') from None
            return self.from_middle(raw,'mineru-local-flash')

    @staticmethod
    def from_middle(raw,version):
        blocks=[]
        for page in raw.get('pages',[]):
            for i,block in enumerate(page.get('blocks',[])):
                text=_content_text(block.get('content') or block.get('text') or '')
                if not text and block.get('cells'): text=json.dumps(block['cells'],ensure_ascii=False)
                if text:
                    blocks.append({**block,'text':text,'page':page['page_idx']+1,'block_index':i})
        if not blocks: raise ProductError('NO_CONTENT','解析结果无可定位正文，不作为成功入库')
        return ParsedDocument(version,blocks,raw)


def _content_text(value):
    if isinstance(value,str): return value
    if isinstance(value,list): return ''.join(_content_text(item) for item in value)
    if isinstance(value,dict): return _content_text(value.get('content', value.get('text','')))
    return ''

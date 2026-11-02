from gsm.observability import timed
"""Local-only MinerU process boundary. Never silently uploads documents."""
from dataclasses import dataclass, field
from pathlib import Path
import shutil
import json
import subprocess
import tempfile
from gsm.errors import ProductError
from gsm.document_units import NORMALIZATION_VERSION

@dataclass
class ParsedDocument:
    parser_version: str
    blocks: list[dict]
    raw: dict
    units: list[dict] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)

class Parser:
    PDF_VERSION="mineru-local-flash-txt/"+NORMALIZATION_VERSION+"/native-v1"
    def __init__(self,command='mineru-kit',timeout=300):
        self.command=command;self.timeout=timeout

    @timed('parser.parse')
    def parse(self,path):
        path=Path(path)
        if path.suffix.lower() in ('.txt','.md'):
            text=path.read_text()
            return ParsedDocument('plain-text-v1',[{'text':t,'paragraph':i+1} for i,t in enumerate(text.split('\n\n')) if t.strip()],{'text':text})
        with tempfile.TemporaryDirectory(prefix='gsm-mineru-') as temp:
            output=Path(temp)/'middle.json'
            try:
                # Explicit local mode is mandatory; stdout/stderr may contain source text, so never log it.
                subprocess.run([self.command,'parse',str(path),'--tier','flash','--ocr-mode','txt','--disable-image-analysis','--format','middle_json','-o',str(output)],check=True,capture_output=True,timeout=self.timeout)
                raw=json.loads(output.read_text())
            except FileNotFoundError:
                raise ProductError('PARSER_UNAVAILABLE','未安装配置的本地 mineru-kit 命令') from None
            except subprocess.TimeoutExpired:
                raise ProductError('PARSER_TIMEOUT','本地文档解析超时',retryable=True) from None
            except (subprocess.CalledProcessError,ValueError,OSError):
                raise ProductError('PARSE_FAILED','本地 MinerU 解析失败；原件保持不变') from None
            native_pages,native_status=self.native_text(path)
            try:parsed=self.from_middle(raw,self.PDF_VERSION,native_pages)
            except ProductError as error:
                if error.details:error.details[0]['coverage']['native_text']=native_status
                raise
            parsed.coverage['native_text']=native_status
            return parsed

    def native_text(self,path):
        command=shutil.which(self.command) or self.command
        python=Path(command).resolve().parent/'python'
        if not python.is_file():return [],{'status':'unavailable','code':'NATIVE_RUNTIME_UNAVAILABLE'}
        try:
            output=subprocess.run([str(python),str(Path(__file__).with_name('pdf_native.py')),str(path)],check=True,capture_output=True,timeout=self.timeout)
            pages=json.loads(output.stdout)['pages']
            return pages,{'status':'completed','pages':len(pages),'character_count':sum(len(p['text']) for p in pages)}
        except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError):
            return [],{'status':'unavailable','code':'NATIVE_TEXT_FAILED'}

    @staticmethod
    def from_middle(raw,version,native_pages=None):
        from gsm.document_units import normalize_document
        blocks,units,coverage=normalize_document(raw,native_pages)
        if not blocks:raise ProductError('NO_CONTENT','解析结果无可定位正文；未识别区域已记录，不作为成功入库',[{'coverage':coverage,'units':units}])
        return ParsedDocument(version,blocks,raw,units,coverage)


from gsm.document_units import content_text as _content_text

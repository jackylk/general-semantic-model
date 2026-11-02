"""Optional matching tokenizer for input estimates; provider usage remains authoritative."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from math import ceil
import json
from tokenizers import Tokenizer
from gsm.errors import ProductError
from gsm.observability import timed

@lru_cache(maxsize=4)
@timed('tokenization.load')
def load(path,expected_hash):
    try:
        data=Path(path).read_bytes();digest=sha256(data).hexdigest()
        if expected_hash and digest!=expected_hash:raise ProductError('INVALID_TOKENIZER','分词器文件哈希不匹配')
        config=json.loads(data)
        # Literal spellings in untrusted text must not be counted as control tokens.
        config['added_tokens']=[];config['post_processor']=None
        return Tokenizer.from_str(json.dumps(config)),digest
    except ProductError:raise
    except Exception:
        raise ProductError('INVALID_TOKENIZER','无法加载已配置分词器，请检查安装、文件及模型版本') from None

class TokenBudget:
    def __init__(self,path,expected_hash=None):self.tokenizer,self.sha256=load(str(Path(path).resolve()),expected_hash)
    def count_text(self,text):return len(self.tokenizer.encode(text,add_special_tokens=False).ids)
    @timed('tokenization.estimate')
    def bound(self,prompt,system):return ceil((self.count_text(prompt)+self.count_text(system))*1.15)+256

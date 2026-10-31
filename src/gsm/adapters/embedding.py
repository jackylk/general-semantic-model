import math
from .http import post_json
from gsm.errors import ProductError

class Embedding:
    def __init__(self,base_url='http://127.0.0.1:8010/v1',model='qwen3-embedding-0.6b-mlx',dimensions=1024):
        self.base_url=base_url.rstrip('/');self.model=model;self.dimensions=dimensions

    def embed(self,texts):
        if not texts: return []
        data=post_json(self.base_url+'/embeddings',{'model':self.model,'input':texts},timeout=60)
        try:
            items=sorted(data['data'],key=lambda i:i['index'])
            if [i['index'] for i in items]!=list(range(len(texts))): raise ValueError()
            vectors=[i['embedding'] for i in items]
            if any(len(v)!=self.dimensions or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in v) for v in vectors): raise ValueError()
        except (KeyError,ValueError,TypeError):
            raise ProductError('INVALID_EMBEDDING','向量批次、维数或有限数值校验失败') from None
        return vectors

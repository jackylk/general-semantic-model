from gsm.observability import timed
import math
from .http import post_json
from gsm.errors import ProductError

class Embedding:
    def __init__(self,base_url='http://127.0.0.1:8010/v1',model='qwen3-embedding-0.6b-mlx',dimensions=1024,
                 batch_size=4,max_text_chars=2048,max_batch_chars=4096):
        if min(batch_size,max_text_chars,max_batch_chars)<1 or max_text_chars>max_batch_chars:
            raise ProductError('INVALID_CONFIG','向量批次和片段上限不合法')
        self.base_url=base_url.rstrip('/');self.model=model;self.dimensions=dimensions
        self.batch_size=batch_size;self.max_text_chars=max_text_chars;self.max_batch_chars=max_batch_chars

    @timed('embedding.request')
    def _request(self,texts):
        try:data=post_json(self.base_url+'/embeddings',{'model':self.model,'input':texts},timeout=60)
        except ProductError as error:
            raise ProductError(error.code,'本地向量服务请求失败',[{'component':'embedding'}],error.retryable) from None
        try:
            items=sorted(data['data'],key=lambda i:i['index'])
            if [i['index'] for i in items]!=list(range(len(texts))):raise ValueError()
            vectors=[i['embedding'] for i in items]
            if any(len(v)!=self.dimensions or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in v) or not any(v) for v in vectors):raise ValueError()
        except (KeyError,ValueError,TypeError):
            raise ProductError('INVALID_EMBEDDING','向量批次、维数或有限非零数值校验失败') from None
        return vectors

    @timed('embedding.total')
    def embed(self,texts):
        if not texts:return []
        if any(not isinstance(t,str) or not t.strip() for t in texts):raise ProductError('INVALID_EMBEDDING_INPUT','向量输入必须是非空文本')
        chunks=[(index,text[offset:offset+self.max_text_chars]) for index,text in enumerate(texts) for offset in range(0,len(text),self.max_text_chars)]
        grouped=[[] for _ in texts];batch=[];characters=0
        def flush():
            if not batch:return
            vectors=self._request([text for _,text in batch])
            for (index,text),vector in zip(batch,vectors):grouped[index].append((len(text),vector))
            batch.clear()
        for index,text in chunks:
            if batch and (len(batch)>=self.batch_size or characters+len(text)>self.max_batch_chars):flush();characters=0
            batch.append((index,text));characters+=len(text)
        flush();result=[]
        for items in grouped:
            if len(items)==1:result.append(items[0][1]);continue
            weight=sum(n for n,_ in items)
            pooled=[sum(n*v[d] for n,v in items)/weight for d in range(self.dimensions)]
            norm=math.sqrt(sum(x*x for x in pooled))
            if not norm:raise ProductError('INVALID_EMBEDDING','长文本聚合产生零向量')
            result.append([x/norm for x in pooled])
        return result

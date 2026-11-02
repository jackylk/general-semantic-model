import json
import time
from urllib.request import Request,urlopen,build_opener,ProxyHandler
from urllib.parse import urlsplit
from urllib.error import HTTPError,URLError
from gsm.errors import ProductError


def post_json(url,payload,headers=None,timeout=30,retries=1):
    for attempt in range(retries+1):
        try:
            req=Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json',**(headers or {})})
            open_request=build_opener(ProxyHandler({})).open if urlsplit(url).hostname in ('127.0.0.1','localhost','::1') else urlopen
            with open_request(req,timeout=timeout) as response:
                raw=response.read(16*1024*1024+1)
                if len(raw)>16*1024*1024: raise ProductError('RESPONSE_TOO_LARGE','模型响应超过限制')
                return json.loads(raw)
        except HTTPError as exc:
            retryable=exc.code in (408,429,500,502,503,504)
            error=ProductError('UPSTREAM_HTTP',f'模型服务返回 HTTP {exc.code}',retryable=retryable)
        except (URLError,TimeoutError,OSError):
            error=ProductError('UPSTREAM_UNAVAILABLE','模型服务连接失败或超时',retryable=True)
        except (ValueError,UnicodeError):
            raise ProductError('INVALID_RESPONSE','模型服务未返回有效 JSON') from None
        if not error.retryable or attempt==retries: raise error from None
        time.sleep(min(0.25*(2**attempt),1))

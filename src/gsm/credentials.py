"""Signed role and KB scopes, provisioned by the product operator only."""
import hashlib,hmac,json,os
from pathlib import Path
from dotenv import dotenv_values
from .errors import ProductError


def _key():
    key=os.environ.get('GSM_CREDENTIAL_SIGNING_KEY') or dotenv_values('.env').get('GSM_CREDENTIAL_SIGNING_KEY')
    if not key:raise ProductError('MISSING_CONFIG','未配置身份签名密钥')
    return key.encode()


def _signature(data):
    return hmac.new(_key(),json.dumps(data,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest()


def write_credentials(path,role,kb_ids,source_root=None):
    data={'role':role,'kb_ids':kb_ids}
    if source_root is not None:data['source_root']=str(source_root)
    data['signature']=_signature(data)
    path=Path(path);path.write_text(json.dumps(data,indent=2)+'\n');path.chmod(0o600)


def read_credentials(path):
    try:
        data=json.loads(Path(path).read_text());signature=data.pop('signature')
        valid=hmac.compare_digest(signature,_signature(data))
        if not valid or data['role'] not in ('developer','consumer') or not isinstance(data['kb_ids'],list):raise ValueError()
        return data
    except (OSError,ValueError,KeyError,TypeError):raise ProductError('INVALID_CREDENTIAL','身份配置无效或签名不匹配') from None

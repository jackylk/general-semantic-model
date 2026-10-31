import json
import pytest
from gsm.credentials import write_credentials,read_credentials
from gsm.errors import ProductError


def test_tampering_with_role_or_scope_is_rejected(tmp_path):
    path=tmp_path/'consumer.json'
    write_credentials(path,'consumer',['kb-1'])
    data=json.loads(path.read_text());data['role']='developer';path.write_text(json.dumps(data))
    with pytest.raises(ProductError):read_credentials(path)


def test_valid_credentials_preserve_authorized_scope(tmp_path):
    path=tmp_path/'dev.json';write_credentials(path,'developer',['kb-2'])
    assert read_credentials(path)['kb_ids']==['kb-2']

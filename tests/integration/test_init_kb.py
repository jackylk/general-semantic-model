from pathlib import Path
from gsm.workspaces import initialize_kb
from gsm.application import Application
from gsm.errors import ProductError
import pytest


def test_product_initializes_shared_empty_kb_without_codex_or_model(tmp_path,monkeypatch):
    monkeypatch.setattr('subprocess.run',lambda *a,**k:pytest.fail('initialization must not execute Codex or model processes'))
    root=tmp_path/'automotive-kb'
    result=initialize_kb(root,'用户知识库')
    assert result['workspace']==str(root)
    assert result['roles']['producer']['workspace']==result['roles']['consumer']['workspace']==str(root)
    assert not (root/'producer').exists() and not (root/'consumer').exists()
    assert list((root/'documents').iterdir())==[]
    assert list((root/'wiki').iterdir())==[]
    for role in ('producer','consumer'):
        app=Application(result['roles'][role]['credentials'])
        with app.store.transaction(app.principal,result['kb_id']) as conn:
            row=conn.execute('SELECT name,current_release FROM knowledge_bases WHERE id=%s',(result['kb_id'],)).fetchone()
            assert row==('用户知识库',None)
            assert conn.execute('SELECT count(*) FROM records WHERE kb_id=%s',(result['kb_id'],)).fetchone()[0]==0
    with pytest.raises(ProductError):initialize_kb(root,'不能覆盖')

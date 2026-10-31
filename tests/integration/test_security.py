from uuid import uuid4
import pytest
from gsm.auth import Principal
from gsm.config import Settings
from gsm.store import Store
from gsm.errors import ProductError


def test_database_rls_hides_other_kb_and_prevents_cross_reference():
    import psycopg
    store=Store(Settings.load()); store.migrate()
    a,b=str(uuid4()),str(uuid4()); admin=Principal('developer',frozenset([a,b]))
    store.create_kb(admin,a,'a'); store.create_kb(admin,b,'b')
    foreign=store.add_record(admin,b,'object',{'name':'private'},status='candidate')
    with store.transaction(admin,a) as conn:
        assert conn.execute('SELECT id FROM records WHERE id=%s',(foreign,)).fetchone() is None
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO records(kb_id,kind,payload,status) VALUES(%s,'object','{}','candidate')",(b,))
    revoked=Principal('consumer',frozenset())
    with pytest.raises(ProductError):
        with store.transaction(revoked,a): pass

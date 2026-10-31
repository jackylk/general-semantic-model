from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from .auth import Principal
from .config import Settings

TABLES = ('domain_versions','source_versions','source_withdrawals','parse_versions','source_blocks','records','evidence_links','builds','releases')
IMMUTABLE = ('domain_versions','source_versions','parse_versions','source_blocks','records','evidence_links','releases')

class Store:
    def __init__(self, settings: Settings):
        self.settings = settings

    def connect(self, role):
        return psycopg.connect(host=self.settings.host, port=self.settings.port, dbname='gsm',
            user='gsm_'+role, password=self.settings.passwords[role])

    def migrate(self):
        with self.connect('owner') as conn:
            conn.execute('SELECT pg_advisory_xact_lock(79523489)')
            exists=conn.execute("SELECT to_regclass('public.schema_migrations')").fetchone()[0]
            if exists and conn.execute("SELECT 1 FROM schema_migrations WHERE version='001'").fetchone():
                self._migrate_remaining(conn)
                return
            conn.execute(Path('migrations/001_core.sql').read_text())
            for role in ('developer','consumer'):
                name='gsm_'+role
                if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(name,)).fetchone():
                    conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(name),sql.Literal(self.settings.passwords[role])))
                conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(name)))
                conn.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}').format(sql.Identifier(name)))
            conn.execute('GRANT INSERT, UPDATE ON knowledge_bases TO gsm_developer')
            for table in TABLES:
                conn.execute(sql.SQL('ALTER TABLE {} ENABLE ROW LEVEL SECURITY').format(sql.Identifier(table)))
                conn.execute(sql.SQL("CREATE POLICY kb_scope ON {} USING(kb_id::text = current_setting('gsm.kb_id',true)) WITH CHECK(kb_id::text = current_setting('gsm.kb_id',true))").format(sql.Identifier(table)))
                conn.execute(sql.SQL('GRANT INSERT ON {} TO gsm_developer').format(sql.Identifier(table)))
            conn.execute("ALTER TABLE knowledge_bases ENABLE ROW LEVEL SECURITY")
            conn.execute("CREATE POLICY kb_scope ON knowledge_bases USING(id::text=current_setting('gsm.kb_id',true)) WITH CHECK(id::text=current_setting('gsm.kb_id',true))")
            conn.execute('GRANT UPDATE ON builds TO gsm_developer')
            for table in IMMUTABLE:
                conn.execute(sql.SQL('GRANT UPDATE ON {} TO gsm_developer').format(sql.Identifier(table)))
                conn.execute(sql.SQL('CREATE TRIGGER prevent_changes BEFORE UPDATE OR DELETE ON {} FOR EACH ROW EXECUTE FUNCTION immutable_row()').format(sql.Identifier(table)))
            conn.execute("INSERT INTO schema_migrations(version) VALUES ('001')")
            self._migrate_remaining(conn)

    def _migrate_remaining(self,conn):
        for path in sorted(Path('migrations').glob('*.sql')):
            version=path.name.split('_')[0]
            if not conn.execute('SELECT 1 FROM schema_migrations WHERE version=%s',(version,)).fetchone():
                conn.execute(path.read_text())
                conn.execute('INSERT INTO schema_migrations(version) VALUES(%s)',(version,))

    @contextmanager
    def transaction(self, principal: Principal, kb_id: str):
        principal.require(kb_id)
        with self.connect(principal.role) as conn:
            conn.execute("SELECT set_config('gsm.kb_id', %s, true)", (kb_id,))
            yield conn

    def create_kb(self, principal, kb_id, name):
        principal.require(kb_id,write=True)
        with self.transaction(principal,kb_id) as conn:
            conn.execute('INSERT INTO knowledge_bases(id,name) VALUES(%s,%s)',(kb_id,name))

    def add_record(self, principal, kb_id, kind, payload, status='candidate'):
        principal.require(kb_id,write=True)
        with self.transaction(principal,kb_id) as conn:
            return str(conn.execute('INSERT INTO records(kb_id,kind,payload,status) VALUES(%s,%s,%s,%s) RETURNING id',(kb_id,kind,Jsonb(payload),status)).fetchone()[0])

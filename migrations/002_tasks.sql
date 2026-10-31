CREATE TABLE tasks(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),kb_id uuid NOT NULL REFERENCES knowledge_bases,kind text NOT NULL,payload jsonb NOT NULL,input_hash text NOT NULL,idempotency_key text NOT NULL,status text NOT NULL DEFAULT 'queued',stage text NOT NULL DEFAULT 'queued',checkpoint jsonb NOT NULL DEFAULT '{}',error jsonb,updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(kb_id,kind,idempotency_key));
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
CREATE POLICY kb_scope ON tasks USING(kb_id::text=current_setting('gsm.kb_id',true)) WITH CHECK(kb_id::text=current_setting('gsm.kb_id',true));
GRANT SELECT,INSERT,UPDATE ON tasks TO gsm_developer;

CREATE TABLE feedback(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),kb_id uuid NOT NULL,release_id uuid NOT NULL,message text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),FOREIGN KEY(kb_id,release_id) REFERENCES releases(kb_id,id));
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
CREATE POLICY kb_scope ON feedback USING(kb_id::text=current_setting('gsm.kb_id',true)) WITH CHECK(kb_id::text=current_setting('gsm.kb_id',true));
GRANT INSERT,SELECT ON feedback TO gsm_developer,gsm_consumer;

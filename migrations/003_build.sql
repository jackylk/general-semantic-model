CREATE TABLE review_decisions(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),kb_id uuid NOT NULL,record_id uuid NOT NULL,decision text NOT NULL CHECK(decision IN ('confirm','reject')),reason text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),FOREIGN KEY(kb_id,record_id) REFERENCES records(kb_id,id));
ALTER TABLE review_decisions ENABLE ROW LEVEL SECURITY;
CREATE POLICY kb_scope ON review_decisions USING(kb_id::text=current_setting('gsm.kb_id',true)) WITH CHECK(kb_id::text=current_setting('gsm.kb_id',true));
GRANT SELECT,INSERT ON review_decisions TO gsm_developer;
GRANT SELECT ON review_decisions TO gsm_consumer;
CREATE TRIGGER prevent_changes BEFORE UPDATE OR DELETE ON review_decisions FOR EACH ROW EXECUTE FUNCTION immutable_row();

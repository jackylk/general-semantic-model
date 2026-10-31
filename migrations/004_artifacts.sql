CREATE TABLE search_documents(kb_id uuid NOT NULL,build_id uuid NOT NULL,record_id uuid NOT NULL,text text NOT NULL,tokens tsvector NOT NULL,embedding vector(1024),PRIMARY KEY(kb_id,build_id,record_id),FOREIGN KEY(kb_id,build_id) REFERENCES builds(kb_id,id),FOREIGN KEY(kb_id,record_id) REFERENCES records(kb_id,id));
CREATE INDEX search_tokens ON search_documents USING gin(tokens);
ALTER TABLE search_documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY kb_scope ON search_documents USING(kb_id::text=current_setting('gsm.kb_id',true)) WITH CHECK(kb_id::text=current_setting('gsm.kb_id',true));
GRANT SELECT,INSERT ON search_documents TO gsm_developer;
GRANT SELECT ON search_documents TO gsm_consumer;
CREATE TRIGGER prevent_changes BEFORE UPDATE OR DELETE ON search_documents FOR EACH ROW EXECUTE FUNCTION immutable_row();

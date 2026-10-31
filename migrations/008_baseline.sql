CREATE TABLE source_search_documents(kb_id uuid NOT NULL,build_id uuid NOT NULL,block_id uuid NOT NULL,text text NOT NULL,tokens tsvector NOT NULL,embedding vector(1024),PRIMARY KEY(kb_id,build_id,block_id),FOREIGN KEY(kb_id,build_id) REFERENCES builds(kb_id,id),FOREIGN KEY(kb_id,block_id) REFERENCES source_blocks(kb_id,id));
CREATE INDEX source_search_tokens ON source_search_documents USING gin(tokens);
ALTER TABLE source_search_documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY kb_scope ON source_search_documents USING(kb_id::text=current_setting('gsm.kb_id',true)) WITH CHECK(kb_id::text=current_setting('gsm.kb_id',true));
GRANT SELECT,INSERT ON source_search_documents TO gsm_developer;
GRANT SELECT ON source_search_documents TO gsm_consumer;
CREATE TRIGGER prevent_changes BEFORE UPDATE OR DELETE ON source_search_documents FOR EACH ROW EXECUTE FUNCTION immutable_row();

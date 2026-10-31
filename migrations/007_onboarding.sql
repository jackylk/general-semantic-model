CREATE TABLE onboarding(kb_id uuid PRIMARY KEY REFERENCES knowledge_bases,state jsonb NOT NULL DEFAULT '{}',revision integer NOT NULL DEFAULT 0,updated_at timestamptz NOT NULL DEFAULT now());
ALTER TABLE onboarding ENABLE ROW LEVEL SECURITY;
CREATE POLICY kb_scope ON onboarding USING(kb_id::text=current_setting('gsm.kb_id',true)) WITH CHECK(kb_id::text=current_setting('gsm.kb_id',true));
GRANT SELECT,INSERT,UPDATE ON onboarding TO gsm_developer;

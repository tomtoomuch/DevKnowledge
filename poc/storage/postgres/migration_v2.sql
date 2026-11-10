\set ON_ERROR_STOP on
CREATE TABLE IF NOT EXISTS schema_migrations (
  version_number INTEGER NOT NULL PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE evidence_items
  ADD COLUMN IF NOT EXISTS source_kind VARCHAR(32) NOT NULL DEFAULT 'PROJECT';
CREATE INDEX IF NOT EXISTS ix_competency_knowledge
  ON knowledge_competency_links (competency_id, knowledge_id);
INSERT INTO schema_migrations (version_number) VALUES (2)
  ON CONFLICT (version_number) DO NOTHING;
DO $$
BEGIN
  IF (SELECT COUNT(*) FROM schema_migrations WHERE version_number = 2) <> 1
     OR NOT EXISTS (SELECT 1 FROM information_schema.columns
       WHERE table_name='evidence_items' AND column_name='source_kind')
    THEN RAISE EXCEPTION 'Migration v2 not applied correctly';
  END IF;
END $$;
SELECT 'MIGRATION_V2_PASS postgres' AS marker;

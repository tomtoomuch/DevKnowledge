\set ON_ERROR_STOP on
CREATE TABLE rncp_referentials (
  id UUID PRIMARY KEY,
  code VARCHAR(32) NOT NULL,
  version_label VARCHAR(32) NOT NULL,
  UNIQUE (code, version_label)
);
CREATE TABLE rncp_blocks (
  id UUID PRIMARY KEY,
  referential_id UUID NOT NULL REFERENCES rncp_referentials(id),
  code VARCHAR(32) NOT NULL,
  title VARCHAR(200) NOT NULL,
  UNIQUE (referential_id, code)
);
CREATE TABLE rncp_competencies (
  id UUID PRIMARY KEY,
  block_id UUID NOT NULL REFERENCES rncp_blocks(id),
  code VARCHAR(32) NOT NULL,
  label VARCHAR(250) NOT NULL,
  UNIQUE (block_id, code)
);
CREATE TABLE knowledge_items (
  id UUID PRIMARY KEY,
  title VARCHAR(250) NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
  details_json JSONB,
  deleted_at TIMESTAMPTZ
);
CREATE TABLE evidence_items (
  id UUID PRIMARY KEY,
  knowledge_id UUID NOT NULL REFERENCES knowledge_items(id),
  title VARCHAR(250) NOT NULL,
  source_url VARCHAR(800) NOT NULL
);
CREATE TABLE knowledge_competency_links (
  knowledge_id UUID NOT NULL REFERENCES knowledge_items(id),
  competency_id UUID NOT NULL REFERENCES rncp_competencies(id),
  PRIMARY KEY (knowledge_id, competency_id)
);
SELECT 'SCHEMA_PASS postgres' AS marker;

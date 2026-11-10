USE master;
GO
IF DB_ID(N'devknowledge_poc') IS NULL CREATE DATABASE devknowledge_poc;
GO
USE devknowledge_poc;
GO
CREATE TABLE dbo.rncp_referentials (
  id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
  code NVARCHAR(32) NOT NULL,
  version_label NVARCHAR(32) NOT NULL,
  CONSTRAINT uq_rncp_version UNIQUE (code, version_label)
);
CREATE TABLE dbo.rncp_blocks (
  id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
  referential_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.rncp_referentials(id),
  code NVARCHAR(32) NOT NULL,
  title NVARCHAR(200) NOT NULL,
  CONSTRAINT uq_block_code UNIQUE (referential_id, code)
);
CREATE TABLE dbo.rncp_competencies (
  id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
  block_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.rncp_blocks(id),
  code NVARCHAR(32) NOT NULL,
  label NVARCHAR(250) NOT NULL,
  CONSTRAINT uq_competency_code UNIQUE (block_id, code)
);
CREATE TABLE dbo.knowledge_items (
  id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
  title NVARCHAR(250) NOT NULL,
  revision INT NOT NULL DEFAULT (1) CHECK (revision > 0),
  details_json NVARCHAR(MAX) NULL CHECK (details_json IS NULL OR ISJSON(details_json) = 1),
  deleted_at DATETIME2 NULL
);
CREATE TABLE dbo.evidence_items (
  id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
  knowledge_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.knowledge_items(id),
  title NVARCHAR(250) NOT NULL,
  source_url NVARCHAR(800) NOT NULL
);
CREATE TABLE dbo.knowledge_competency_links (
  knowledge_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.knowledge_items(id),
  competency_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.rncp_competencies(id),
  CONSTRAINT pk_knowledge_competency PRIMARY KEY (knowledge_id, competency_id)
);
GO
PRINT 'SCHEMA_PASS sqlserver';

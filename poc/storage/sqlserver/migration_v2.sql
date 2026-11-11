USE devknowledge_poc;
GO
IF OBJECT_ID(N'dbo.schema_migrations', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.schema_migrations (
    version_number INT NOT NULL PRIMARY KEY,
    applied_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
  );
END;
GO
IF COL_LENGTH('dbo.evidence_items', 'source_kind') IS NULL
BEGIN
  ALTER TABLE dbo.evidence_items ADD
    source_kind NVARCHAR(32) NOT NULL CONSTRAINT df_evidence_source_kind DEFAULT N'PROJECT';
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.knowledge_competency_links')
   AND name = N'ix_competency_knowledge')
BEGIN
  CREATE INDEX ix_competency_knowledge ON dbo.knowledge_competency_links (competency_id, knowledge_id);
END;
IF NOT EXISTS (SELECT 1 FROM dbo.schema_migrations WHERE version_number = 2)
  INSERT dbo.schema_migrations (version_number) VALUES (2);
IF (SELECT COUNT(*) FROM dbo.schema_migrations WHERE version_number = 2) <> 1
  THROW 51011, 'Migration record must be unique', 1;
IF COL_LENGTH('dbo.evidence_items','source_kind') IS NULL
  THROW 51012, 'Migration column missing', 1;
PRINT 'MIGRATION_V2_PASS sqlserver';
GO

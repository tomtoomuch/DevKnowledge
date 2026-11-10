USE master;
GO
BACKUP DATABASE devknowledge_poc
  TO DISK = N'/var/opt/mssql/dk_sqlpoc.bak'
  WITH INIT, CHECKSUM;
GO
RESTORE VERIFYONLY FROM DISK = N'/var/opt/mssql/dk_sqlpoc.bak' WITH CHECKSUM;
GO
DECLARE @data SYSNAME = (SELECT name FROM devknowledge_poc.sys.database_files WHERE type = 0);
DECLARE @log SYSNAME = (SELECT name FROM devknowledge_poc.sys.database_files WHERE type = 1);
IF @data IS NULL OR @log IS NULL THROW 51021, 'Missing logical files', 1;
DECLARE @sql NVARCHAR(MAX) = N'RESTORE DATABASE devknowledge_poc_restored FROM DISK = N''/var/opt/mssql/dk_sqlpoc.bak'' WITH ' +
    N'MOVE N''' + REPLACE(@data, '''', '''''') + N''' TO N''/var/opt/mssql/data/dk_sqlpoc_restored.mdf'', ' +
    N'MOVE N''' + REPLACE(@log, '''', '''''') + N''' TO N''/var/opt/mssql/data/dk_sqlpoc_restored_log.ldf'', RECOVERY, REPLACE';
EXEC sp_executesql @sql;
GO
USE devknowledge_poc_restored;
IF (SELECT COUNT(*) FROM dbo.knowledge_items) <>
   (SELECT COUNT(*) FROM devknowledge_poc.dbo.knowledge_items)
  THROW 51022, 'Restored total count mismatch', 1;
IF (SELECT COUNT(*) FROM dbo.knowledge_items WHERE revision = 2) <>
   (SELECT COUNT(*) FROM devknowledge_poc.dbo.knowledge_items WHERE revision = 2)
  THROW 51023, 'Restored revision counts mismatch', 1;
IF (SELECT COUNT(*) FROM dbo.schema_migrations WHERE version_number = 2) <> 1
  THROW 51024, 'Restored migration version missing', 1;
PRINT 'BACKUP_RESTORE_PASS sqlserver';
GO

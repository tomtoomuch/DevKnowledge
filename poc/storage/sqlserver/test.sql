USE devknowledge_poc;
GO
SET NOCOUNT ON;
INSERT INTO dbo.rncp_referentials VALUES ('10000000-0000-0000-0000-000000000001', N'RNCP-TEST', N'v1');
INSERT INTO dbo.rncp_blocks VALUES ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', N'B1', N'Developper un service');
INSERT INTO dbo.rncp_competencies VALUES ('30000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', N'C1', N'Concevoir une API');
INSERT INTO dbo.knowledge_items VALUES ('40000000-0000-0000-0000-000000000001', N'Fiche fictive API', 1, N'{"language":"Python"}', NULL);
INSERT INTO dbo.evidence_items (id, knowledge_id, title, source_url) VALUES ('50000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000001', N'Preuve de test', N'https://example.invalid/fixture');
INSERT INTO dbo.knowledge_competency_links VALUES ('40000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001');

IF (SELECT COUNT(*) FROM dbo.knowledge_items k
    JOIN dbo.knowledge_competency_links l ON l.knowledge_id = k.id
    JOIN dbo.rncp_competencies c ON c.id = l.competency_id
    JOIN dbo.rncp_blocks b ON b.id = c.block_id
    JOIN dbo.rncp_referentials r ON r.id = b.referential_id
    JOIN dbo.evidence_items e ON e.knowledge_id = k.id
    WHERE r.code = N'RNCP-TEST') <> 1
    THROW 51001, 'RNCP join did not return expected evidence', 1;

-- Database must reject both foreign key and duplicate key violations.
BEGIN TRY
    INSERT INTO dbo.rncp_blocks VALUES ('20000000-0000-0000-0000-000000000099',
      '10000000-0000-0000-0000-000000000099', N'INVALID', N'Bad parent');
    THROW 51002, 'Missing foreign key enforcement', 1;
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() <> 547 THROW;
END CATCH;
BEGIN TRY
    INSERT INTO dbo.rncp_referentials VALUES ('10000000-0000-0000-0000-000000000002', N'RNCP-TEST', N'v1');
    THROW 51003, 'Missing unique enforcement', 1;
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() NOT IN (2601, 2627) THROW;
END CATCH;
BEGIN TRY
    INSERT INTO dbo.knowledge_items VALUES ('40000000-0000-0000-0000-000000000002', N'Invalid JSON', 1, N'not json', NULL);
    THROW 51004, 'Missing JSON validation', 1;
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() <> 547 THROW;
END CATCH;

BEGIN TRANSACTION;
  UPDATE dbo.knowledge_items SET title = N'Should be rolled back'
  WHERE id = '40000000-0000-0000-0000-000000000001';
ROLLBACK TRANSACTION;
IF EXISTS (SELECT 1 FROM dbo.knowledge_items WHERE title = N'Should be rolled back')
   THROW 51005, 'Transaction rollback failed', 1;

UPDATE dbo.knowledge_items SET revision = revision + 1
 WHERE id = '40000000-0000-0000-0000-000000000001' AND revision = 1;
IF @@ROWCOUNT <> 1 THROW 51006, 'First conditional update failed', 1;
UPDATE dbo.knowledge_items SET revision = revision + 1
 WHERE id = '40000000-0000-0000-0000-000000000001' AND revision = 1;
IF @@ROWCOUNT <> 0 THROW 51007, 'Stale revision was accepted', 1;
IF (SELECT revision FROM dbo.knowledge_items
    WHERE id = '40000000-0000-0000-0000-000000000001') <> 2
    THROW 51008, 'Unexpected revision count', 1;
PRINT 'POC_PASS sqlserver: joins fk unique json rollback optimistic_lock';
GO

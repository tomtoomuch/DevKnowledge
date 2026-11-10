\set ON_ERROR_STOP on
INSERT INTO rncp_referentials VALUES ('10000000-0000-0000-0000-000000000001', 'RNCP-TEST', 'v1');
INSERT INTO rncp_blocks VALUES ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'B1', 'Développer un service');
INSERT INTO rncp_competencies VALUES ('30000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 'C1', 'Concevoir une API');
INSERT INTO knowledge_items VALUES ('40000000-0000-0000-0000-000000000001', 'Fiche fictive API', 1, '{"language":"Python"}', NULL);
INSERT INTO evidence_items (id, knowledge_id, title, source_url) VALUES ('50000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000001', 'Preuve de test', 'https://example.invalid/fixture');
INSERT INTO knowledge_competency_links VALUES ('40000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001');

DO $$
DECLARE found_count INT;
BEGIN
  SELECT COUNT(*) INTO found_count
    FROM knowledge_items k
    JOIN knowledge_competency_links l ON l.knowledge_id = k.id
    JOIN rncp_competencies c ON c.id = l.competency_id
    JOIN rncp_blocks b ON b.id = c.block_id
    JOIN rncp_referentials r ON r.id = b.referential_id
    JOIN evidence_items e ON e.knowledge_id = k.id
   WHERE r.code = 'RNCP-TEST';
  IF found_count <> 1 THEN RAISE EXCEPTION 'RNCP JOIN test failed'; END IF;

  BEGIN
    INSERT INTO rncp_blocks VALUES ('20000000-0000-0000-0000-000000000099',
     '10000000-0000-0000-0000-000000000099', 'INVALID', 'Missing parent');
    RAISE EXCEPTION 'Missing foreign key enforcement';
  EXCEPTION WHEN foreign_key_violation THEN NULL;
  END;
  BEGIN
    INSERT INTO rncp_referentials VALUES ('10000000-0000-0000-0000-000000000002', 'RNCP-TEST', 'v1');
    RAISE EXCEPTION 'Missing unique enforcement';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;
  BEGIN
    INSERT INTO knowledge_items VALUES ('40000000-0000-0000-0000-000000000002',
      'Invalid JSON', 1, 'not json', NULL);
    RAISE EXCEPTION 'Missing JSON validation';
  EXCEPTION WHEN invalid_text_representation THEN NULL;
  END;
END $$;

BEGIN;
UPDATE knowledge_items SET title = 'Should be rolled back'
 WHERE id = '40000000-0000-0000-0000-000000000001';
ROLLBACK;
DO $$
DECLARE affected INT;
BEGIN
  IF EXISTS (SELECT 1 FROM knowledge_items WHERE title = 'Should be rolled back')
    THEN RAISE EXCEPTION 'Transaction rollback failed';
  END IF;
  UPDATE knowledge_items SET revision = revision + 1
    WHERE id = '40000000-0000-0000-0000-000000000001' AND revision = 1;
  GET DIAGNOSTICS affected = ROW_COUNT;
  IF affected <> 1 THEN RAISE EXCEPTION 'First conditional update failed'; END IF;
  UPDATE knowledge_items SET revision = revision + 1
    WHERE id = '40000000-0000-0000-0000-000000000001' AND revision = 1;
  GET DIAGNOSTICS affected = ROW_COUNT;
  IF affected <> 0 THEN RAISE EXCEPTION 'Stale revision was accepted'; END IF;
  IF (SELECT revision FROM knowledge_items
      WHERE id = '40000000-0000-0000-0000-000000000001') <> 2
      THEN RAISE EXCEPTION 'Unexpected revision count';
  END IF;
END $$;
SELECT 'POC_PASS postgres: joins fk unique json rollback optimistic_lock' AS marker;

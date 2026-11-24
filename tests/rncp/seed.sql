-- Fictional fixture only; not an import of the official RNCP 37827 framework.
INSERT INTO rncp.certification_frameworks VALUES
 ('10000000-0000-0000-0000-000000000001','RNCP-TEST','Synthetic qualification','Test only');
INSERT INTO rncp.certification_framework_versions (framework_version_id,framework_id,version) VALUES
 ('20000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','v1'),
 ('20000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001','v2');
INSERT INTO rncp.certification_blocks (block_id,framework_version_id,block_code,title) VALUES
 ('30000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','B1','Synthetic v1'),
 ('30000000-0000-0000-0000-000000000002','20000000-0000-0000-0000-000000000002','B1','Synthetic v2');
INSERT INTO rncp.certification_competencies (competency_id,block_id,competency_code,official_description,is_mandatory) VALUES
 ('40000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','C1','Synthetic v1, not official',true),
 ('40000000-0000-0000-0000-000000000002','30000000-0000-0000-0000-000000000002','C1','Synthetic v2, not official',true);
INSERT INTO rncp.assessment_criteria VALUES
 ('50000000-0000-0000-0000-000000000001','40000000-0000-0000-0000-000000000001','CR1','Synthetic criterion');

-- Indexes for primary RNCP navigation and evidence access.
CREATE INDEX idx_rncp_blocks_version
    ON rncp.certification_blocks(framework_version_id);
CREATE INDEX idx_rncp_competencies_block
    ON rncp.certification_competencies(block_id);
CREATE INDEX idx_rncp_criteria_competency
    ON rncp.assessment_criteria(competency_id);
CREATE INDEX idx_rncp_evidence_by_competency
    ON rncp.competency_evidence(competency_id);
CREATE INDEX idx_rncp_knowledge_links_competency
    ON rncp.knowledge_competency_links(competency_id);

-- Types explicitly listed in the MLD v0.2, not invented official RNCP content.
INSERT INTO rncp.evidence_types (evidence_type_id, code, label)
VALUES
 ('00000000-0000-0000-0001-000000000001','SOURCE_CODE','Code source'),
 ('00000000-0000-0000-0001-000000000002','UNIT_TEST','Test unitaire'),
 ('00000000-0000-0000-0001-000000000003','INTEGRATION_TEST','Test d''intégration'),
 ('00000000-0000-0000-0001-000000000004','TECHNICAL_DOCUMENTATION','Documentation technique'),
 ('00000000-0000-0000-0001-000000000005','ARCHITECTURE_DIAGRAM','Diagramme d''architecture'),
 ('00000000-0000-0000-0001-000000000006','DATABASE_SCHEMA','Schéma de données'),
 ('00000000-0000-0000-0001-000000000007','API_DOCUMENTATION','Documentation API'),
 ('00000000-0000-0000-0001-000000000008','CI_CD_PIPELINE','Pipeline CI/CD'),
 ('00000000-0000-0000-0001-000000000009','SCREENSHOT','Capture d''écran'),
 ('00000000-0000-0000-0001-000000000010','VIDEO_DEMO','Démonstration vidéo'),
 ('00000000-0000-0000-0001-000000000011','PROFESSIONAL_REPORT','Rapport professionnel'),
 ('00000000-0000-0000-0001-000000000012','INCIDENT_REPORT','Rapport d''incident'),
 ('00000000-0000-0000-0001-000000000013','BENCHMARK','Étude comparative');

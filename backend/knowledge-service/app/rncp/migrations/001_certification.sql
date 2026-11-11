-- Faithful first slice of DevKnowledge_MLD_3NF_v0.2 sections I and J.
-- Cross-storage IDs are UUID references only; NO fictitious SQL FK to MongoDB.
CREATE TABLE rncp.certification_frameworks (
    framework_id UUID PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    certifier VARCHAR(255) NOT NULL
);

CREATE TABLE rncp.certification_framework_versions (
    framework_version_id UUID PRIMARY KEY,
    framework_id UUID NOT NULL REFERENCES rncp.certification_frameworks(framework_id),
    version VARCHAR(50) NOT NULL,
    qualification_level VARCHAR(50),
    registration_date DATE,
    expiration_date DATE,
    source_url TEXT,
    retrieved_at TIMESTAMPTZ,
    UNIQUE (framework_id, version),
    CHECK (expiration_date IS NULL OR registration_date IS NULL
           OR expiration_date >= registration_date)
);

CREATE TABLE rncp.certification_blocks (
    block_id UUID PRIMARY KEY,
    framework_version_id UUID NOT NULL
        REFERENCES rncp.certification_framework_versions(framework_version_id),
    block_code VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    evaluation_method TEXT,
    UNIQUE (framework_version_id, block_code)
);

CREATE TABLE rncp.certification_competencies (
    competency_id UUID PRIMARY KEY,
    block_id UUID NOT NULL REFERENCES rncp.certification_blocks(block_id),
    competency_code VARCHAR(100) NOT NULL,
    official_description TEXT NOT NULL,
    operational_description TEXT,
    expected_deliverables TEXT,
    evaluation_method TEXT,
    is_mandatory BOOLEAN NOT NULL,
    UNIQUE (block_id, competency_code)
);

CREATE TABLE rncp.assessment_criteria (
    criterion_id UUID PRIMARY KEY,
    competency_id UUID NOT NULL REFERENCES rncp.certification_competencies(competency_id),
    criterion_code VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    UNIQUE (competency_id, criterion_code)
);

CREATE TABLE rncp.evidence_types (
    evidence_type_id UUID PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    label VARCHAR(150) NOT NULL,
    description TEXT
);

CREATE TABLE rncp.evidence_artifacts (
    evidence_id UUID PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    evidence_type_id UUID NOT NULL REFERENCES rncp.evidence_types(evidence_type_id),
    project_id UUID,  -- external MongoDB/project reference during transition
    file_path VARCHAR(1000),
    repository_url TEXT,
    commit_hash VARCHAR(128),
    demonstration_url TEXT,
    author_role VARCHAR(150),
    created_at TIMESTAMPTZ NOT NULL,
    created_by_user_id UUID NOT NULL, -- external identity UUID during transition
    verification_status VARCHAR(30) NOT NULL,
    verification_notes TEXT
);

CREATE TABLE rncp.competency_evidence (
    id UUID PRIMARY KEY,
    competency_id UUID NOT NULL
        REFERENCES rncp.certification_competencies(competency_id),
    evidence_id UUID NOT NULL REFERENCES rncp.evidence_artifacts(evidence_id),
    evidence_role VARCHAR(30) NOT NULL,
    demonstrated_aspects TEXT,
    limitations TEXT,
    review_status VARCHAR(30) NOT NULL,
    UNIQUE (competency_id, evidence_id)
);

-- knowledge_items and users remain in MongoDB until a separate migration.
CREATE TABLE rncp.knowledge_competency_links (
    link_id UUID PRIMARY KEY,
    knowledge_id UUID NOT NULL, -- external knowledge UUID, validated by KMS
    competency_id UUID NOT NULL
        REFERENCES rncp.certification_competencies(competency_id),
    relevance_level VARCHAR(30),
    mapping_rationale TEXT,
    confidence_score NUMERIC(5,4) CHECK (
        confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1
    ),
    created_at TIMESTAMPTZ NOT NULL,
    created_by_user_id UUID NOT NULL, -- external identity UUID
    UNIQUE (knowledge_id, competency_id)
);

CREATE TABLE rncp.competency_assessments (
    assessment_id UUID PRIMARY KEY,
    competency_id UUID NOT NULL
        REFERENCES rncp.certification_competencies(competency_id),
    assessed_by_user_id UUID NOT NULL, -- external identity UUID
    assessment_level VARCHAR(30) NOT NULL,
    assessment_source VARCHAR(100),
    assessment_date TIMESTAMPTZ NOT NULL,
    strengths TEXT,
    gaps TEXT,
    improvement_plan TEXT
);

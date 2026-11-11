"""Actual PostgreSQL + FastAPI TestClient: version isolation, evidence and integrity."""
from pathlib import Path
import uuid

import psycopg
from fastapi.testclient import TestClient
import pytest

from rncp.api import create_test_app
from rncp.migrate import apply_migrations, connection_string

DSN = connection_string()
MIGRATIONS = Path("/app/migrations")
FRAMEWORK = uuid.UUID("10000000-0000-0000-0000-000000000001")
VERSION1 = uuid.UUID("20000000-0000-0000-0000-000000000001")
VERSION2 = uuid.UUID("20000000-0000-0000-0000-000000000002")
BLOCK1 = uuid.UUID("30000000-0000-0000-0000-000000000001")
BLOCK2 = uuid.UUID("30000000-0000-0000-0000-000000000002")
COMP1 = uuid.UUID("40000000-0000-0000-0000-000000000001")
COMP2 = uuid.UUID("40000000-0000-0000-0000-000000000002")
EVIDENCE = uuid.UUID("50000000-0000-0000-0000-000000000001")
ACTOR = uuid.UUID("60000000-0000-0000-0000-000000000001")
KNOWLEDGE = uuid.UUID("70000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="session", autouse=True)
def database():
    # The same session-scoped fixture is reused by the API route test module.
    # It may be invoked under a second pytest fixture identity, so seeding is
    # idempotent without hiding missing/partially committed test fixtures.
    first = apply_migrations(DSN, MIGRATIONS)
    assert first in ([1, 2], [])
    assert apply_migrations(DSN, MIGRATIONS) == []
    if first == []:
        with psycopg.connect(DSN) as conn:
            assert conn.execute(
                "SELECT count(*) FROM rncp.certification_frameworks WHERE code = 'RNCP-TEST'"
            ).fetchone()[0] == 1
        yield
        return
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO rncp.certification_frameworks VALUES (%s, %s, %s, %s)",
                (FRAMEWORK, "RNCP-TEST", "Test uniquement", "Organisme fictif"),
            )
            c.execute(
                """INSERT INTO rncp.certification_framework_versions
                   (framework_version_id, framework_id, version)
                   VALUES (%s,%s,%s),(%s,%s,%s)""",
                (VERSION1, FRAMEWORK, "v1", VERSION2, FRAMEWORK, "v2"),
            )
            c.execute(
                """INSERT INTO rncp.certification_blocks
                   (block_id, framework_version_id, block_code, title)
                   VALUES (%s,%s,'B1','Bloc v1'),(%s,%s,'B1','Bloc v2')""",
                (BLOCK1, VERSION1, BLOCK2, VERSION2),
            )
            c.execute(
                """INSERT INTO rncp.certification_competencies
                   (competency_id, block_id, competency_code, official_description, is_mandatory)
                   VALUES (%s,%s,'C1','Compétence fictive v1',true),
                          (%s,%s,'C1','Compétence fictive v2',true)""",
                (COMP1, BLOCK1, COMP2, BLOCK2),
            )
            c.execute(
                """INSERT INTO rncp.assessment_criteria
                   VALUES (%s, %s, 'CR1', 'Critère fictif de validation')""",
                (uuid.uuid4(), COMP1),
            )
            c.execute(
                """INSERT INTO rncp.evidence_artifacts
                   (evidence_id, title, evidence_type_id, created_at,
                    created_by_user_id, verification_status)
                   SELECT %s, 'Preuve fictive', evidence_type_id, now(), %s, 'PENDING'
                   FROM rncp.evidence_types WHERE code = 'SOURCE_CODE'""",
                (EVIDENCE, ACTOR),
            )
            c.execute(
                """INSERT INTO rncp.competency_evidence
                   (id, competency_id, evidence_id, evidence_role, review_status)
                   VALUES (%s,%s,%s,'SUPPORT','PENDING')""",
                (uuid.uuid4(), COMP1, EVIDENCE),
            )
            c.execute(
                """INSERT INTO rncp.knowledge_competency_links
                   (link_id,knowledge_id,competency_id,confidence_score,created_at,created_by_user_id)
                   VALUES (%s,%s,%s,0.75,now(),%s)""",
                (uuid.uuid4(), KNOWLEDGE, COMP1, ACTOR),
            )
    yield


def test_mld_schema_versioned_and_catalog_seeded(database):
    with psycopg.connect(DSN) as conn:
        assert conn.execute("SELECT count(*) FROM rncp.schema_migrations").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM rncp.evidence_types").fetchone()[0] == 13
        assert conn.execute("SELECT count(*) FROM rncp.certification_framework_versions").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM rncp.certification_competencies").fetchone()[0] == 2


def test_fastapi_version_isolation_and_evidence(database):
    with TestClient(create_test_app(DSN)) as client:
        assert client.get("/health/ready").json()["status"] == "ok"
        response = client.get("/api/v1/rncp/frameworks/RNCP-TEST/versions/v1")
        assert response.status_code == 200
        one = response.json()["blocks"][0]["competencies"][0]
        assert one["code"] == "C1"
        assert one["criteria_count"] == 1
        assert one["evidence_count"] == 1

        response = client.get("/api/v1/rncp/frameworks/RNCP-TEST/versions/v2")
        assert response.status_code == 200
        two = response.json()["blocks"][0]["competencies"][0]
        assert two["code"] == "C1"
        assert two["criteria_count"] == 0
        assert two["evidence_count"] == 0

        evidence = client.get(f"/api/v1/rncp/competencies/{COMP1}/evidence")
        assert evidence.status_code == 200
        assert evidence.json()["evidence"][0]["verification_status"] == "PENDING"
        assert evidence.json()["evidence"][0]["type"] == "SOURCE_CODE"
        assert client.get(f"/api/v1/rncp/competencies/{COMP2}/evidence").json()["evidence"] == []
        assert client.get("/api/v1/rncp/frameworks/UNKNOWN/versions/v1").status_code == 404
        assert client.get(f"/api/v1/rncp/competencies/{uuid.uuid4()}/evidence").status_code == 404


def test_fk_and_uniqueness_enforced(database):
    with pytest.raises(psycopg.errors.UniqueViolation):
        with psycopg.connect(DSN) as conn:
            conn.execute(
                """INSERT INTO rncp.certification_frameworks
                   VALUES (%s, 'RNCP-TEST', 'Duplicate', 'Fixture')""",
                (uuid.uuid4(),),
            )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with psycopg.connect(DSN) as conn:
            conn.execute(
                """INSERT INTO rncp.certification_blocks
                   (block_id,framework_version_id,block_code,title)
                   VALUES (%s,%s,'INVALID','Bad FK')""",
                (uuid.uuid4(), uuid.uuid4()),
            )
    with pytest.raises(psycopg.errors.UniqueViolation):
        with psycopg.connect(DSN) as conn:
            conn.execute(
                """INSERT INTO rncp.competency_evidence
                   (id,competency_id,evidence_id,evidence_role,review_status)
                   VALUES (%s,%s,%s,'SUPPORT','PENDING')""",
                (uuid.uuid4(), COMP1, EVIDENCE),
            )


def test_knowledge_reference_confidence_guard(database):
    with pytest.raises(psycopg.errors.CheckViolation):
        with psycopg.connect(DSN) as conn:
            conn.execute(
                """INSERT INTO rncp.knowledge_competency_links
                   (link_id,knowledge_id,competency_id,confidence_score,created_at,created_by_user_id)
                   VALUES (%s,%s,%s,1.50,now(),%s)""",
                (uuid.uuid4(), uuid.uuid4(), COMP1, ACTOR),
            )
    with psycopg.connect(DSN) as conn:
        assert conn.execute(
            "SELECT count(*) FROM rncp.knowledge_competency_links WHERE competency_id=%s",
            (COMP1,),
        ).fetchone()[0] == 1


def test_transactions_rollback(database):
    with psycopg.connect(DSN) as conn:
        with pytest.raises(RuntimeError):
            with conn.transaction():
                conn.execute(
                    """INSERT INTO rncp.certification_frameworks
                       VALUES (%s,'RNCP-ROLLBACK','Temp','Fictif')""",
                    (uuid.uuid4(),),
                )
                raise RuntimeError("expected rollback")
        result = conn.execute(
            "SELECT count(*) FROM rncp.certification_frameworks WHERE code='RNCP-ROLLBACK'"
        ).fetchone()[0]
        assert result == 0


def test_migration_checksum_drift_is_rejected(database, tmp_path):
    # An already-applied script must not be silently modified after release.
    source = MIGRATIONS / "001_certification.sql"
    (tmp_path / source.name).write_text(
        source.read_text(encoding="utf-8") + "\n-- unexpected change\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="changed after being applied"):
        apply_migrations(DSN, tmp_path)
    with psycopg.connect(DSN) as conn:
        assert conn.execute("SELECT count(*) FROM rncp.schema_migrations").fetchone()[0] == 2

"""Read-only RNCP queries against PostgreSQL.

The KMS production router does not yet import this module. All public requests
must eventually pass the Gateway and the configured internal authentication.
"""
import uuid

import psycopg
from psycopg.rows import dict_row


class MissingCompetency(Exception):
    """Referenced RNCP competency does not exist."""


class InvalidEvidenceType(Exception):
    """Unknown evidence type code."""


class DuplicateKnowledgeLink(Exception):
    """Knowledge/competency association already exists."""


class RncpRepository:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def overview(self, framework_code: str, version: str) -> dict | None:
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT f.framework_id, f.code, f.title, fv.framework_version_id,
                           fv.version
                      FROM rncp.certification_frameworks f
                      JOIN rncp.certification_framework_versions fv
                        ON fv.framework_id = f.framework_id
                     WHERE f.code = %s AND fv.version = %s
                    """,
                    (framework_code, version),
                )
                framework = cur.fetchone()
                if framework is None:
                    return None

                cur.execute(
                    """
                    SELECT b.block_id, b.block_code, b.title AS block_title,
                           c.competency_id, c.competency_code,
                           c.official_description,
                           COUNT(DISTINCT cr.criterion_id)::int AS criteria_count,
                           COUNT(DISTINCT ce.evidence_id)::int AS evidence_count
                      FROM rncp.certification_blocks b
                      LEFT JOIN rncp.certification_competencies c
                        ON c.block_id = b.block_id
                      LEFT JOIN rncp.assessment_criteria cr
                        ON cr.competency_id = c.competency_id
                      LEFT JOIN rncp.competency_evidence ce
                        ON ce.competency_id = c.competency_id
                     WHERE b.framework_version_id = %s
                     GROUP BY b.block_id, b.block_code, b.title,
                              c.competency_id, c.competency_code,
                              c.official_description
                     ORDER BY b.block_code, c.competency_code
                    """,
                    (framework["framework_version_id"],),
                )
                result = {
                    "code": framework["code"],
                    "title": framework["title"],
                    "version": framework["version"],
                    "blocks": [],
                }
                blocks = {}
                for row in cur.fetchall():
                    key = row["block_id"]
                    if key not in blocks:
                        block = {
                            "code": row["block_code"],
                            "title": row["block_title"],
                            "competencies": [],
                        }
                        blocks[key] = block
                        result["blocks"].append(block)
                    if row["competency_id"] is not None:
                        blocks[key]["competencies"].append({
                            "id": str(row["competency_id"]),
                            "code": row["competency_code"],
                            "description": row["official_description"],
                            "criteria_count": row["criteria_count"],
                            "evidence_count": row["evidence_count"],
                        })
                return result

    def competency_evidence(self, competency_id: uuid.UUID) -> list[dict] | None:
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM rncp.certification_competencies WHERE competency_id = %s",
                    (competency_id,),
                )
                if cur.fetchone() is None:
                    return None
                cur.execute(
                    """
                    SELECT e.evidence_id, e.title, t.code AS evidence_type,
                           ce.evidence_role, ce.review_status,
                           e.verification_status
                      FROM rncp.competency_evidence ce
                      JOIN rncp.evidence_artifacts e ON e.evidence_id = ce.evidence_id
                      JOIN rncp.evidence_types t ON t.evidence_type_id = e.evidence_type_id
                     WHERE ce.competency_id = %s
                     ORDER BY e.title
                    """,
                    (competency_id,),
                )
                return [
                    {
                        "id": str(row["evidence_id"]),
                        "title": row["title"],
                        "type": row["evidence_type"],
                        "role": row["evidence_role"],
                        "review_status": row["review_status"],
                        "verification_status": row["verification_status"],
                    }
                    for row in cur.fetchall()
                ]

    def create_evidence(self, competency_id: uuid.UUID, title: str,
                        evidence_type_code: str, user_id: uuid.UUID,
                        repository_url: str | None) -> dict:
        """Persist evidence and competency association atomically."""
        evidence_id = uuid.uuid4()
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM rncp.certification_competencies WHERE competency_id = %s",
                    (competency_id,),
                )
                if cur.fetchone() is None:
                    raise MissingCompetency
                cur.execute(
                    "SELECT evidence_type_id FROM rncp.evidence_types WHERE code = %s",
                    (evidence_type_code,),
                )
                kind = cur.fetchone()
                if kind is None:
                    raise InvalidEvidenceType
                cur.execute(
                    """INSERT INTO rncp.evidence_artifacts
                       (evidence_id,title,evidence_type_id,repository_url,created_at,
                        created_by_user_id,verification_status)
                       VALUES (%s,%s,%s,%s,now(),%s,'PENDING')""",
                    (evidence_id, title, kind["evidence_type_id"], repository_url, user_id),
                )
                cur.execute(
                    """INSERT INTO rncp.competency_evidence
                       (id,competency_id,evidence_id,evidence_role,review_status)
                       VALUES (%s,%s,%s,'SUPPORT','PENDING')""",
                    (uuid.uuid4(), competency_id, evidence_id),
                )
        return {"id": str(evidence_id), "title": title,
                "competency_id": str(competency_id), "type": evidence_type_code,
                "verification_status": "PENDING"}

    def create_knowledge_link(self, competency_id: uuid.UUID, knowledge_id: uuid.UUID,
                              user_id: uuid.UUID, confidence: float | None,
                              rationale: str | None) -> dict:
        """Link an existing external MongoDB knowledge UUID, atomically in SQL."""
        link_id = uuid.uuid4()
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM rncp.certification_competencies WHERE competency_id = %s",
                    (competency_id,),
                )
                if cur.fetchone() is None:
                    raise MissingCompetency
                cur.execute(
                    """INSERT INTO rncp.knowledge_competency_links
                       (link_id,knowledge_id,competency_id,confidence_score,
                        mapping_rationale,created_at,created_by_user_id)
                       VALUES (%s,%s,%s,%s,%s,now(),%s)
                       ON CONFLICT (knowledge_id,competency_id) DO NOTHING
                       RETURNING link_id""",
                    (link_id, knowledge_id, competency_id, confidence, rationale, user_id),
                )
                if cur.fetchone() is None:
                    raise DuplicateKnowledgeLink
        return {"id": str(link_id), "competency_id": str(competency_id),
                "knowledge_id": str(knowledge_id), "confidence_score": confidence}

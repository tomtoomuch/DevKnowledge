"""Read-only RNCP queries against PostgreSQL.

The KMS production router does not yet import this module. All public requests
must eventually pass the Gateway and the configured internal authentication.
"""
import uuid

import psycopg
from psycopg.rows import dict_row


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

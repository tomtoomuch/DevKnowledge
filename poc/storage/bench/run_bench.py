"""Integration/size test through FastAPI TestClient and actual SQL Server/Postgres.

Metrics include Python/HTTP/SQLAlchemy/docker overhead; use only as POC
measurements (not DB microbenchmarks, and not a production load test).
"""
import json
import os
import statistics
import time
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, func, insert, select
from api import BENCH_COMPETENCY_ID, create_app


def engine_from_env():
    engine_name = os.environ["POC_ENGINE"]
    password = os.environ["POC_DB_PASSWORD"]
    if engine_name == "sqlserver":
        params = (
            "DRIVER={ODBC Driver 18 for SQL Server};SERVER=sqlserver,1433;"
            f"DATABASE=devknowledge_poc;UID=sa;PWD={password};"
            "Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=15"
        )
        # TrustServerCertificate is safe ONLY in this isolated disposable POC.
        return create_engine(
            URL.create("mssql+pyodbc", query={"odbc_connect": params}),
            pool_pre_ping=True, pool_size=5,
        )
    if engine_name == "postgres":
        return create_engine(
            URL.create("postgresql+psycopg", username="postgres", password=password,
                       host="postgres", database="devknowledge_poc"),
            pool_pre_ping=True, pool_size=5,
        )
    raise ValueError("Unknown engine")


def timed(f):
    start = time.perf_counter()
    result = f()
    return result, (time.perf_counter() - start) * 1000


def latency_summary(samples):
    samples = sorted(samples)
    return {
        "n": len(samples),
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(samples[int(0.95 * (len(samples) - 1))], 3),
    }


def main():
    engine = engine_from_env()
    app, tables = create_app(engine)
    knowledge, links, evidence = tables["knowledge"], tables["links"], tables["evidence"]
    n = int(os.environ.get("POC_ROWS", "1500"))
    if n < 100 or n > 10000:
        raise ValueError("POC_ROWS must be 100..10000")
    namespace = uuid.UUID("3ab74a61-c301-48fd-84a7-7f25512ec77a")
    rows_k, rows_l, rows_e = [], [], []
    for i in range(n):
        kid = uuid.uuid5(namespace, f"knowledge-{i}")
        rows_k.append({
            "id": kid,
            "title": f"POC fixture knowledge {i}",
            "revision": 1,
            "details_json": {"fixture": i, "language": "Python"} if engine.dialect.name == "postgresql"
                else json.dumps({"fixture": i, "language": "Python"}),
        })
        rows_l.append({"knowledge_id": kid, "competency_id": BENCH_COMPETENCY_ID})
        rows_e.append({
            "id": uuid.uuid5(namespace, f"evidence-{i}"),
            "knowledge_id": kid,
            "title": f"POC evidence {i}",
            "source_url": f"https://example.invalid/proof/{i}",
        })
    start = time.perf_counter()
    with engine.begin() as connection:
        # Bulk data inserted within ONE transaction across three related tables.
        # SQL Server and PostgreSQL implementations use identical batch size.
        for start_idx in range(0, n, 200):
            end_idx = start_idx + 200
            connection.execute(insert(knowledge), rows_k[start_idx:end_idx])
            connection.execute(insert(links), rows_l[start_idx:end_idx])
            connection.execute(insert(evidence), rows_e[start_idx:end_idx])
    bulk_ms = (time.perf_counter() - start) * 1000
    with engine.connect() as connection:
        count = connection.execute(
            select(func.count()).select_from(knowledge)
        ).scalar_one()
    if count != n + 1:  # +1 from original POC fixture
        raise AssertionError(f"Unexpected number of knowledge records: {count}")

    http_read = []
    http_write = []
    with TestClient(app) as client:
        status = client.get("/health")
        assert status.status_code == 200, status.text
        coverage = client.get("/coverage")
        assert coverage.status_code == 200, coverage.text
        assert coverage.json()["evidence_count"] == n + 1, coverage.json()

        for _ in range(50):
            response, ms = timed(lambda: client.get("/coverage"))
            assert response.status_code == 200, response.text
            assert response.json()["evidence_count"] == n + 1
            http_read.append(ms)

        for i in range(15):
            response, ms = timed(lambda i=i: client.post(
                "/knowledge", json={"title": f"Bench HTTP knowledge {i}"}))
            assert response.status_code == 201, response.text
            http_write.append(ms)
            knowledge_id = response.json()["id"]
            assert client.patch(
                f"/knowledge/{knowledge_id}",
                json={"title": "Should reject missing ETag"},
            ).status_code == 428
            accepted = client.patch(
                f"/knowledge/{knowledge_id}",
                headers={"If-Match": '"1"'},
                json={"title": "Revision 2"},
            )
            assert accepted.status_code == 200, accepted.text
            denied = client.patch(
                f"/knowledge/{knowledge_id}",
                headers={"If-Match": '"1"'},
                json={"title": "Must not overwrite revision 2"},
            )
            assert denied.status_code == 412, denied.text

    report = {
        "engine": os.environ["POC_ENGINE"],
        "fixture_rows": n,
        "knowledge_count_verified_before_http": count,
        "bulk_insert_three_tables_ms": round(bulk_ms, 3),
        "fastapi_get_coverage": latency_summary(http_read),
        "fastapi_post_knowledge": latency_summary(http_write),
        "fastapi_statuses_validated": [200, 201, 412, 428],
        "migration_version": 2,
        "connection": "real SQLAlchemy with ODBC 18 or Psycopg; ASGI HTTP TestClient",
    }
    engine.dispose()
    print("BENCH_REPORT_JSON=" + json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

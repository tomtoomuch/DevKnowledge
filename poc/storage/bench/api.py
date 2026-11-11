"""Minimal real FastAPI HTTP/ASGI surface over the tested relational stores.

The application never connects to MongoDB or the real KMS. SQLAlchemy Core
uses DB-native UUID/JSON types; the endpoints are test-only, not published.
"""
import json
import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, MetaData, Table, Uuid, Unicode, UnicodeText
from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import JSONB

BENCH_COMPETENCY_ID = uuid.UUID("30000000-0000-0000-0000-000000000001")


class KnowledgeIn(BaseModel):
    title: str = Field(min_length=1, max_length=250)


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=250)


def create_app(engine):
    is_pg = engine.dialect.name == "postgresql"
    metadata = MetaData()
    knowledge = Table(
        "knowledge_items", metadata,
        Column("id", Uuid(as_uuid=True), primary_key=True),
        Column("title", Unicode(250)),
        Column("revision", Integer),
        Column("details_json", JSONB if is_pg else UnicodeText),
    )
    links = Table(
        "knowledge_competency_links", metadata,
        Column("knowledge_id", Uuid(as_uuid=True), primary_key=True),
        Column("competency_id", Uuid(as_uuid=True), primary_key=True),
    )
    evidence = Table(
        "evidence_items", metadata,
        Column("id", Uuid(as_uuid=True), primary_key=True),
        Column("knowledge_id", Uuid(as_uuid=True)),
        Column("title", Unicode(250)),
        Column("source_url", Unicode(800)),
    )
    app = FastAPI(title="DevKnowledge SQL POC", docs_url=None, redoc_url=None)

    @app.get("/health")
    def health():
        with engine.connect() as connection:
            connection.execute(select(func.count()).select_from(knowledge)).scalar_one()
        return {"status": "ok", "engine": engine.dialect.name}

    @app.get("/coverage")
    def coverage():
        stmt = (
            select(func.count(evidence.c.id))
            .select_from(
                knowledge.join(links, knowledge.c.id == links.c.knowledge_id)
                .join(evidence, knowledge.c.id == evidence.c.knowledge_id)
            )
            .where(links.c.competency_id == BENCH_COMPETENCY_ID)
        )
        with engine.connect() as connection:
            count = connection.execute(stmt).scalar_one()
        return {"competency_id": str(BENCH_COMPETENCY_ID), "evidence_count": count}

    @app.post("/knowledge", status_code=201)
    def create_knowledge(body: KnowledgeIn):
        knowledge_id = uuid.uuid4()
        details = {"language": "Python", "fixture": True}
        with engine.begin() as connection:
            connection.execute(insert(knowledge).values(
                id=knowledge_id,
                title=body.title,
                revision=1,
                details_json=details if is_pg else json.dumps(details),
            ))
        return {"id": str(knowledge_id), "revision": 1}

    @app.patch("/knowledge/{knowledge_id}")
    def rename_knowledge(knowledge_id: uuid.UUID, body: RenameIn,
                         if_match: str | None = Header(None, alias="If-Match")):
        if if_match is None:
            raise HTTPException(status_code=428, detail="If-Match is required")
        try:
            revision = int(if_match.strip('"'))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid If-Match") from exc
        with engine.begin() as connection:
            changed = connection.execute(
                update(knowledge)
                .where(knowledge.c.id == knowledge_id, knowledge.c.revision == revision)
                .values(title=body.title, revision=knowledge.c.revision + 1)
            ).rowcount
        if changed != 1:
            raise HTTPException(status_code=412, detail="Revision conflict")
        return {"id": str(knowledge_id), "revision": revision + 1}

    return app, {"knowledge": knowledge, "links": links, "evidence": evidence}

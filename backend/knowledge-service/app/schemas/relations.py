"""Typed relationships between knowledge items, faithful to MLD v0.2."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RelationTypeRead(BaseModel):
    relation_type_id: UUID
    code: str
    label: str
    is_directed: bool


class RelationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_knowledge_id: UUID
    target_knowledge_id: UUID
    relation_type_id: UUID
    relation_notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def reject_self_links(self) -> "RelationCreate":
        if self.origin_knowledge_id == self.target_knowledge_id:
            raise ValueError("A knowledge item cannot link to itself")
        return self


class RelationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})

    relation_notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def reject_empty_patch(self) -> "RelationUpdate":
        if "relation_notes" not in self.model_fields_set:
            raise ValueError("relation_notes must be explicitly supplied")
        return self


class RelationRead(RelationCreate):
    relation_id: UUID
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class RelationPage(BaseModel):
    items: list[RelationRead]
    total: int = Field(ge=0)
    skip: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)

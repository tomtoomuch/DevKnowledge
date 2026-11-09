"""Validated technology catalogs and independently identifiable versions."""
from datetime import date
import unicodedata
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalized_text(value: str, limit: int) -> str:
    text = unicodedata.normalize("NFKC", value).strip()
    if not text or len(text) > limit:
        raise ValueError(f"Must contain 1–{limit} non-whitespace characters")
    return text


class TechnologyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    category: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def normalized_name(cls, value: str) -> str:
        return normalized_text(value, 100)

    @field_validator("category")
    @classmethod
    def normalized_category(cls, value: str | None) -> str | None:
        return normalized_text(value, 100) if value is not None else None


class TechnologyRead(TechnologyCreate):
    technology_id: UUID


class TechnologyPage(BaseModel):
    items: list[TechnologyRead]
    total: int = Field(ge=0)
    skip: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class TechnologyVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    technology_id: UUID
    version: str = Field(min_length=1, max_length=50)
    release_date: date | None = None

    @field_validator("version")
    @classmethod
    def normalized_version(cls, value: str) -> str:
        return normalized_text(value, 50)


class TechnologyVersionRead(TechnologyVersionCreate):
    technology_version_id: UUID


class TechnologyVersionPage(BaseModel):
    items: list[TechnologyVersionRead]
    total: int = Field(ge=0)
    skip: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)

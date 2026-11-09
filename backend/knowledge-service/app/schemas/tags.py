"""Tag catalog payloads. Identifiers are server owned and names are case-folded."""
import unicodedata
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).strip()
        if not normalized or len(normalized) > 100:
            raise ValueError("Tag name must contain 1–100 non-whitespace characters")
        return normalized


class TagRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag_id: UUID
    name: str


class TagPage(BaseModel):
    items: list[TagRead]
    total: int = Field(ge=0)
    skip: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)

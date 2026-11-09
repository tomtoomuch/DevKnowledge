"""Public contracts for generic knowledge items; audit fields are server owned."""

from typing import Any
from typing import Annotated
from uuid import UUID

from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StringConstraints,
    field_validator, model_validator,
)
from pydantic.json_schema import SkipJsonSchema

from app.schemas.specializations import KnowledgeType, normalize_details


Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Status = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Language = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10)]
Difficulty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Content = Annotated[str, StringConstraints(min_length=1)]


class KnowledgeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_type: KnowledgeType
    title: Title
    content: Content
    description: str | None = None
    language_code: Language | None = None
    difficulty_level: Difficulty | None = None
    status: Status = "DRAFT"
    is_favorite: StrictBool = False
    # No details is valid for pre-existing generic knowledge documents.
    details: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_details_kind(self) -> "KnowledgeCreate":
        if self.details is not None:
            self.details = normalize_details(self.knowledge_type, self.details)
        return self

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Content must not be blank")
        return value


class KnowledgeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})

    # None is an omission sentinel here; explicitly supplied null is rejected.
    # Hide that sentinel from OpenAPI so clients see the actual PATCH contract.
    knowledge_type: KnowledgeType | SkipJsonSchema[None] = None
    title: Title | SkipJsonSchema[None] = None
    content: Content | SkipJsonSchema[None] = None
    description: str | None = None
    language_code: Language | None = None
    difficulty_level: Difficulty | None = None
    status: Status | SkipJsonSchema[None] = None
    is_favorite: StrictBool | SkipJsonSchema[None] = None
    # PATCH replaces the complete specialization. A null clears it.
    details: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> "KnowledgeUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        non_nullable = {"knowledge_type", "title", "content", "status", "is_favorite"}
        for name in self.model_fields_set & non_nullable:
            if getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        if self.content is not None and not self.content.strip():
            raise ValueError("Content must not be blank")
        return self


class KnowledgeRead(KnowledgeCreate):
    # Legacy documents without this field are read as revision zero.
    revision: int = Field(default=0, ge=0)
    knowledge_id: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    validated_at: AwareDatetime | None
    created_by_user_id: UUID | None
    deleted_at: AwareDatetime | None


class KnowledgePage(BaseModel):
    items: list[KnowledgeRead]
    total: int = Field(ge=0)
    skip: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)

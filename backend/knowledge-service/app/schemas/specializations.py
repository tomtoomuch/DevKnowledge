"""Typed knowledge specializations from the logical MLD v0.2.

A specialization is optional for legacy generic knowledge. When supplied,
the entire document is validated against exactly one schema determined by
knowledge_type. Physically embedded in knowledge_items for atomic writes.
"""
from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool


class KnowledgeType(StrEnum):
    CODE_SNIPPET = "CODE_SNIPPET"
    TERMINAL_COMMAND = "TERMINAL_COMMAND"
    TECHNICAL_PROCEDURE = "TECHNICAL_PROCEDURE"
    COURSE_NOTE = "COURSE_NOTE"
    BUG_FIX = "BUG_FIX"
    DOCUMENTATION_RESOURCE = "DOCUMENTATION_RESOURCE"
    BEST_PRACTICE = "BEST_PRACTICE"
    COMPLIANCE_STANDARD = "COMPLIANCE_STANDARD"


class DetailsBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CodeSnippetDetails(DetailsBase):
    code: str = Field(min_length=1)
    programming_language: str = Field(min_length=1, max_length=50)
    framework: str | None = Field(default=None, max_length=100)
    snippet_version: str | None = Field(default=None, max_length=30)
    entry_point: str | None = Field(default=None, max_length=255)
    input_example: str | None = None
    output_example: str | None = None
    execution_context: str | None = None
    is_executable: StrictBool | None = None
    license: str | None = Field(default=None, max_length=100)


class TerminalCommandDetails(DetailsBase):
    command: str = Field(min_length=1)
    shell: str = Field(min_length=1, max_length=50)
    operating_system: str | None = Field(default=None, max_length=100)
    working_directory: str | None = Field(default=None, max_length=500)
    parameters: str | None = None
    expected_output: str | None = None
    risk_level: str | None = Field(default=None, max_length=30)
    requires_sudo: StrictBool | None = None
    is_destructive: StrictBool | None = None
    execution_notes: str | None = None


class TechnicalProcedureDetails(DetailsBase):
    objective: str | None = None
    environment: str | None = None
    estimated_duration_minutes: int | None = Field(default=None, ge=0)
    difficulty: str | None = Field(default=None, max_length=30)
    rollback_procedure: str | None = None
    validation_criteria: str | None = None


class CourseNoteDetails(DetailsBase):
    module_id: UUID | None = None
    concept: str | None = Field(default=None, max_length=255)
    definition: str | None = None
    explanation: str | None = None
    mastery_level: int | None = Field(default=None, ge=0, le=32767)


class BugFixDetails(DetailsBase):
    error_title: str | None = Field(default=None, max_length=255)
    error_message: str | None = None
    error_code: str | None = Field(default=None, max_length=100)
    symptoms: str | None = None
    root_cause: str | None = None
    solution: str | None = None
    code_before: str | None = None
    code_after: str | None = None
    environment: str | None = None
    resolution_status: str | None = Field(default=None, max_length=30)
    verified_at: AwareDatetime | None = None


class DocumentationResourceDetails(DetailsBase):
    url: str | None = None
    resource_type: str | None = Field(default=None, max_length=50)
    publisher: str | None = Field(default=None, max_length=150)
    publication_date: date | None = None
    accessed_at: AwareDatetime | None = None
    version_reference: str | None = Field(default=None, max_length=50)
    summary: str | None = None
    reliability_level: str | None = Field(default=None, max_length=30)
    is_official: StrictBool | None = None


class BestPracticeDetails(DetailsBase):
    principle: str | None = None
    rationale: str | None = None
    recommendation: str | None = None
    anti_pattern: str | None = None
    benefits: str | None = None
    application_context: str | None = None
    reference_standard_id: UUID | None = None
    validation_criteria: str | None = None


class ComplianceStandardDetails(DetailsBase):
    reference_code: str = Field(min_length=1, max_length=100)
    compliance_type: str | None = Field(default=None, max_length=50)
    issuing_organization: str | None = Field(default=None, max_length=150)
    jurisdiction: str | None = Field(default=None, max_length=100)
    scope: str | None = None
    applicability: str | None = None
    official_url: str | None = None


SCHEMAS: dict[KnowledgeType, type[DetailsBase]] = {
    KnowledgeType.CODE_SNIPPET: CodeSnippetDetails,
    KnowledgeType.TERMINAL_COMMAND: TerminalCommandDetails,
    KnowledgeType.TECHNICAL_PROCEDURE: TechnicalProcedureDetails,
    KnowledgeType.COURSE_NOTE: CourseNoteDetails,
    KnowledgeType.BUG_FIX: BugFixDetails,
    KnowledgeType.DOCUMENTATION_RESOURCE: DocumentationResourceDetails,
    KnowledgeType.BEST_PRACTICE: BestPracticeDetails,
    KnowledgeType.COMPLIANCE_STANDARD: ComplianceStandardDetails,
}

LABELS: dict[KnowledgeType, str] = {
    KnowledgeType.CODE_SNIPPET: "Extrait de code",
    KnowledgeType.TERMINAL_COMMAND: "Commande terminal",
    KnowledgeType.TECHNICAL_PROCEDURE: "Procédure technique",
    KnowledgeType.COURSE_NOTE: "Note de cours",
    KnowledgeType.BUG_FIX: "Correction de bug",
    KnowledgeType.DOCUMENTATION_RESOURCE: "Ressource documentaire",
    KnowledgeType.BEST_PRACTICE: "Bonne pratique",
    KnowledgeType.COMPLIANCE_STANDARD: "Norme ou réglementation",
}


def normalize_details(kind: KnowledgeType | str, value: dict[str, Any]) -> dict[str, Any]:
    """Reject unknown fields or mismatched types; return BSON-safe primitive data.

    UUID and dates become ISO strings inside the embedded specialization.
    The generic content and existing legacy data remain untouched.
    """
    schema = SCHEMAS[KnowledgeType(kind)]
    return schema.model_validate(value).model_dump(mode="json", exclude_unset=True)

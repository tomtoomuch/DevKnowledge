"""Contract tests for the eight typed specializations (no MongoDB required)."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.knowledge import KnowledgeCreate, KnowledgeRead, KnowledgeUpdate
from app.schemas.specializations import KnowledgeType, SCHEMAS, normalize_details
from app.services.knowledge_service import (
    KnowledgeDetailsValidationError, KnowledgeNotFound, KnowledgeService,
)


VALID = {
    "CODE_SNIPPET": {"code": "print('bonjour')", "programming_language": "Python",
                     "is_executable": True},
    "TERMINAL_COMMAND": {"command": "git status", "shell": "bash",
                         "is_destructive": False},
    "TECHNICAL_PROCEDURE": {"objective": "Configurer Docker",
                             "estimated_duration_minutes": 15},
    "COURSE_NOTE": {"concept": "Normalisation", "mastery_level": 2},
    "BUG_FIX": {"error_title": "Index missing", "root_cause": "Index not initialized"},
    "DOCUMENTATION_RESOURCE": {"url": "https://example.org/manual",
                               "publication_date": "2026-11-09", "is_official": True},
    "BEST_PRACTICE": {"principle": "Moindre privilège"},
    "COMPLIANCE_STANDARD": {"reference_code": "ISO/IEC 27001",
                            "issuing_organization": "ISO"},
}


@pytest.mark.parametrize("kind", list(KnowledgeType))
def test_all_eight_details_models_are_persistable_and_readable(kind):
    data = VALID[kind.value]
    payload = KnowledgeCreate(
        knowledge_type=kind, title="Exemple", content="Description générique", details=data
    )
    assert payload.details == normalize_details(kind, data)
    assert SCHEMAS[kind].model_validate(payload.details)
    now = datetime(2026, 11, 9, tzinfo=timezone.utc)
    item = KnowledgeRead.model_validate({
        **payload.model_dump(), "knowledge_id": uuid4(), "created_at": now,
        "updated_at": now, "validated_at": None, "deleted_at": None,
        "created_by_user_id": None, "revision": 1,
    })
    assert item.details == payload.details


def test_old_generic_payloads_do_not_require_specialization():
    for kind in KnowledgeType:
        payload = KnowledgeCreate(knowledge_type=kind, title="Historique", content="Sans détails")
        assert payload.details is None


@pytest.mark.parametrize("kind,details", [
    ("CODE_SNIPPET", {"shell": "bash", "command": "ls"}),
    ("TERMINAL_COMMAND", {"code": "print(1)", "programming_language": "Python"}),
    ("CODE_SNIPPET", {"code": "x", "programming_language": "Python", "unknown": 1}),
    ("CODE_SNIPPET", {"code": "x", "programming_language": "Python", "is_executable": "yes"}),
    ("TECHNICAL_PROCEDURE", {"estimated_duration_minutes": -1}),
    ("COMPLIANCE_STANDARD", {}),
    ("COURSE_NOTE", {"mastery_level": -1}),
    ("DOCUMENTATION_RESOURCE", {"accessed_at": "2026-11-09T10:00:00"}),
])
def test_invalid_specializations_are_rejected(kind, details):
    with pytest.raises(ValidationError):
        KnowledgeCreate(knowledge_type=kind, title="Invalid", content="Something", details=details)


def test_details_cannot_be_set_to_a_non_document():
    with pytest.raises(ValidationError):
        KnowledgeCreate(knowledge_type="BUG_FIX", title="X", content="C", details=["not", "a", "map"])


def test_patch_atomically_replaces_details_and_discards_them_on_type_change():
    async def scenario():
        ident = uuid4()
        now = datetime(2026, 11, 9, tzinfo=timezone.utc)
        item = dict(
            knowledge_id=ident, knowledge_type="CODE_SNIPPET", title="Python", content="Code",
            description=None, language_code=None, difficulty_level=None, status="DRAFT",
            is_favorite=False, details=VALID["CODE_SNIPPET"], revision=1,
            created_at=now, updated_at=now, validated_at=None,
            deleted_at=None, created_by_user_id=None,
        )
        repo = AsyncMock()
        repo.get.return_value = item
        repo.update.side_effect = lambda knowledge_id, changes, revision: {
            **item, **changes, "revision": revision + 1,
        }
        svc = KnowledgeService(repo)
        result = await svc.update(ident, KnowledgeUpdate(details={
            "code": "print(2)", "programming_language": "Python",
        }), expected_revision=1)
        assert result.details["code"] == "print(2)"
        assert repo.update.await_args.args[1]["details"]["code"] == "print(2)"

        # A change in principal type never retains incompatible old fields.
        switched = await svc.update(ident, KnowledgeUpdate(knowledge_type="BUG_FIX"), 1)
        assert switched.details is None
        assert repo.update.await_args.args[1]["details"] is None

        with pytest.raises(KnowledgeDetailsValidationError):
            await svc.update(ident, KnowledgeUpdate(
                knowledge_type="TERMINAL_COMMAND", details={"code": "not a command"}
            ), 1)
        assert repo.update.await_count == 2
        repo.get.return_value = None
        with pytest.raises(KnowledgeNotFound):
            await svc.update(ident, KnowledgeUpdate(details={"solution": "fixed"}), 1)

    asyncio.run(scenario())


def test_patch_with_only_general_fields_does_not_issue_an_extra_read():
    async def scenario():
        repo = AsyncMock()
        ident = uuid4()
        now = datetime(2026, 11, 9, tzinfo=timezone.utc)
        repo.update.return_value = {
            "knowledge_id": ident, "knowledge_type": "BUG_FIX",
            "title": "Updated", "content": "C", "description": None,
            "language_code": None, "difficulty_level": None,
            "status": "DRAFT", "is_favorite": False, "details": None,
            "revision": 2, "created_at": now, "updated_at": now,
            "deleted_at": None, "validated_at": None, "created_by_user_id": None,
        }
        await KnowledgeService(repo).update(ident, KnowledgeUpdate(title="Updated"), 1)
        repo.get.assert_not_awaited()
    asyncio.run(scenario())

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest

from app.db.models import Visibility
from app.services.knowledge_ops_store import KnowledgeOpsStore


class _ScalarSession:
    def __init__(self, value: Visibility | None) -> None:
        self.value = value

    async def scalar(self, _statement: object) -> Visibility | None:
        return self.value


@pytest.mark.parametrize(
    ("stored", "expected"),
    [(Visibility.INTERNAL, "internal"), (Visibility.PUBLIC, "public"), (None, "public")],
)
async def test_version_visibility_comes_from_the_first_chunk(
    stored: Visibility | None,
    expected: str,
) -> None:
    session = cast(Any, _ScalarSession(stored))

    assert await KnowledgeOpsStore._version_visibility(session, uuid.uuid4()) == expected

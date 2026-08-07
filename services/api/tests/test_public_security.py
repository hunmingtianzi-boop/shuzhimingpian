from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.api.errors import ApiError
from app.api.routes.public_conversations import create_visit as create_visit_route
from app.api.routes.public_conversations import stream_message
from app.api.schemas import ConsentRequest, CreateMessageRequest, CreateVisitRequest
from app.core.config import Settings
from app.core.tokens import VisitorPrincipal, issue_profile_link_token
from app.db.models import (
    Card,
    CardKind,
    ConsentRecord,
    ConsentScope,
    ContentStatus,
    Conversation,
    ConversationStatus,
    IdempotencyStatus,
    Message,
    MessageRole,
    MessageStatus,
)
from app.services.public_store import CardScope, IdempotencyClaim, PublicStore


class _AsyncContext:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one(self) -> Any:
        return self.value

    def scalar_one_or_none(self) -> Any:
        return self.value

    def scalars(self) -> "_ScalarResult":
        return self

    def all(self) -> Any:
        return self.value


class _Session:
    def __init__(self, *, card: Card | None = None, result: Any = None) -> None:
        self.card = card
        self.result = result
        self.added: list[Any] = []
        self.executed: list[Any] = []

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self) -> _AsyncContext:
        return _AsyncContext()

    async def get(self, _model: Any, _identifier: Any, **_kwargs: Any) -> Any:
        return self.card

    async def execute(self, statement: Any, _parameters: Any = None) -> _ScalarResult:
        self.executed.append(statement)
        return _ScalarResult(self.result)

    def add_all(self, values: list[Any]) -> None:
        self.added.extend(values)

    async def flush(self) -> None:
        return None


class _SessionFactory:
    def __init__(self, session: _Session) -> None:
        self.session = session

    def __call__(self) -> _Session:
        return self.session


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        field_encryption_key="field-encryption-secret-material-v1",
    )


def _card(*, chat_notice: str = "chat-v2", privacy: str = "privacy-v2") -> Card:
    tenant_id = uuid.uuid4()
    company_id = uuid.uuid4()
    return Card(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        company_id=company_id,
        card_kind=CardKind.ENTERPRISE,
        owner_user_id=None,
        responsible_user_id=uuid.uuid4(),
        slug="secure-card",
        display_name="安全名片",
        status=ContentStatus.PUBLISHED,
        published_at=datetime.now(UTC),
        settings={
            "policy_versions": {
                "privacy": privacy,
                "chat_notice": chat_notice,
                "lead_consent": "lead-v2",
                "profile_personalization": "profile-v2",
            }
        },
    )


def _principal(card: Card, *, visitor_id: uuid.UUID | None = None) -> VisitorPrincipal:
    return VisitorPrincipal(
        visitor_id=visitor_id or uuid.uuid4(),
        visit_id=uuid.uuid4(),
        tenant_id=card.tenant_id,
        company_id=card.company_id,
        card_id=card.id,
        token_id=uuid.uuid4(),
    )


def _consent(
    card: Card,
    principal: VisitorPrincipal,
    *,
    policy_version: str = "chat-v2",
    granted: bool = True,
    expires_at: datetime | None = None,
    visitor_id: uuid.UUID | None = None,
    evidence_card_id: uuid.UUID | None = None,
) -> ConsentRecord:
    return ConsentRecord(
        id=uuid.uuid4(),
        tenant_id=card.tenant_id,
        company_id=card.company_id,
        visitor_id=visitor_id or principal.visitor_id,
        scope=ConsentScope.CHAT_NOTICE,
        policy_version=policy_version,
        granted=granted,
        recorded_at=datetime.now(UTC),
        expires_at=expires_at,
        evidence={"card_id": str(evidence_card_id or card.id)},
    )


@pytest.mark.asyncio
async def test_current_consent_accepts_only_exact_current_card_policy() -> None:
    card = _card()
    principal = _principal(card)
    current = _consent(card, principal)
    session = _Session(result=current)

    result = await PublicStore._require_current_consent(  # noqa: SLF001
        session,  # type: ignore[arg-type]
        principal=principal,
        card=card,
        scope=ConsentScope.CHAT_NOTICE,
    )

    assert result is current


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["upgraded", "withdrawn", "expired", "visitor", "card"])
async def test_old_withdrawn_expired_or_cross_scope_consent_is_rejected(failure: str) -> None:
    card = _card()
    principal = _principal(card)
    consent = _consent(
        card,
        principal,
        policy_version="chat-v1" if failure == "upgraded" else "chat-v2",
        granted=failure != "withdrawn",
        expires_at=(datetime.now(UTC) - timedelta(seconds=1)) if failure == "expired" else None,
        visitor_id=uuid.uuid4() if failure == "visitor" else None,
        evidence_card_id=uuid.uuid4() if failure == "card" else None,
    )

    with pytest.raises(ApiError) as captured:
        await PublicStore._require_current_consent(  # noqa: SLF001
            _Session(result=consent),  # type: ignore[arg-type]
            principal=principal,
            card=card,
            scope=ConsentScope.CHAT_NOTICE,
        )

    assert captured.value.code == "CONSENT_REQUIRED"


@pytest.mark.asyncio
async def test_visit_and_consent_reject_client_supplied_non_current_policy(
    monkeypatch: Any,
) -> None:
    card = _card()
    scope = CardScope(
        card_id=card.id,
        tenant_id=card.tenant_id,
        company_id=card.company_id,
        slug=card.slug,
    )
    session = _Session(card=card)
    store = PublicStore(_SessionFactory(session), _settings())  # type: ignore[arg-type]
    monkeypatch.setattr(store, "_resolve_public_card", AsyncMock(return_value=scope))
    monkeypatch.setattr(
        store,
        "_claim_idempotency",
        AsyncMock(side_effect=AssertionError("must reject before persistence")),
    )

    with pytest.raises(ApiError) as visit_error:
        await store.create_visit(
            slug=card.slug,
            request=CreateVisitRequest(
                source="direct",
                privacy_notice_version="privacy-v1",
            ),
            idempotency_key="visit-1",
        )
    assert visit_error.value.code == "POLICY_VERSION_MISMATCH"

    principal = _principal(card)
    monkeypatch.setattr(store, "_set_principal_scope", AsyncMock())
    monkeypatch.setattr(store, "_require_principal_card", AsyncMock(return_value=card))
    with pytest.raises(ApiError) as consent_error:
        await store.record_consent(
            slug=card.slug,
            principal=principal,
            request=ConsentRequest(
                scope="chat_notice",
                policy_version="chat-v1",
                granted=True,
            ),
            idempotency_key="consent-1",
        )
    assert consent_error.value.code == "POLICY_VERSION_MISMATCH"


@pytest.mark.asyncio
async def test_profile_link_requires_exact_latest_active_consent_and_company() -> None:
    card = _card()
    scope = CardScope(
        card_id=card.id,
        tenant_id=card.tenant_id,
        company_id=card.company_id,
        slug=card.slug,
    )
    visitor_id = uuid.uuid4()
    consent = ConsentRecord(
        id=uuid.uuid4(),
        tenant_id=card.tenant_id,
        company_id=card.company_id,
        visitor_id=visitor_id,
        scope=ConsentScope.PROFILE_PERSONALIZATION,
        policy_version="profile-v2",
        granted=True,
        recorded_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=1),
        evidence={},
    )
    token, _ = issue_profile_link_token(
        signing_key=_settings().jwt_signing_key.get_secret_value(),
        issuer=_settings().app_name,
        ttl_seconds=86_400,
        visitor_id=visitor_id,
        tenant_id=card.tenant_id,
        company_id=card.company_id,
        consent_id=consent.id,
    )
    store = PublicStore(None, _settings())  # type: ignore[arg-type]
    session = AsyncMock()
    session.scalar.side_effect = [consent, visitor_id]
    assert (
        await store._valid_profile_link_consent(  # noqa: SLF001
            session, token=token, scope=scope, expected_policy="profile-v2"
        )
        is consent
    )

    session.scalar.side_effect = [consent]
    assert (
        await store._valid_profile_link_consent(  # noqa: SLF001
            session, token=token, scope=scope, expected_policy="profile-v3"
        )
        is None
    )

    revoked = ConsentRecord(
        id=uuid.uuid4(),
        tenant_id=card.tenant_id,
        company_id=card.company_id,
        visitor_id=visitor_id,
        scope=ConsentScope.PROFILE_PERSONALIZATION,
        policy_version="profile-v2",
        granted=False,
        recorded_at=datetime.now(UTC) + timedelta(seconds=1),
        evidence={},
    )
    session.scalar.side_effect = [revoked]
    assert (
        await store._valid_profile_link_consent(  # noqa: SLF001
            session, token=token, scope=scope, expected_policy="profile-v2"
        )
        is None
    )

    cross_scope = CardScope(
        card_id=uuid.uuid4(),
        tenant_id=card.tenant_id,
        company_id=uuid.uuid4(),
        slug="other-company",
    )
    session.scalar.reset_mock()
    assert (
        await store._valid_profile_link_consent(  # noqa: SLF001
            session, token=token, scope=cross_scope, expected_policy="profile-v2"
        )
        is None
    )
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_message_persists_and_forwards_only_redacted_content(
    monkeypatch: Any,
) -> None:
    card = _card()
    principal = _principal(card)
    conversation = Conversation(
        id=uuid.uuid4(),
        tenant_id=card.tenant_id,
        company_id=card.company_id,
        card_id=card.id,
        visitor_id=principal.visitor_id,
        visit_id=principal.visit_id,
        status=ConversationStatus.ACTIVE,
    )
    session = _Session(card=card, result=0)
    store = PublicStore(_SessionFactory(session), _settings())  # type: ignore[arg-type]
    claim_record = SimpleNamespace(
        resource_id=None,
        resource_type=None,
        status=IdempotencyStatus.PROCESSING,
    )
    monkeypatch.setattr(store, "_set_principal_scope", AsyncMock())
    monkeypatch.setattr(store, "_require_conversation", AsyncMock(return_value=conversation))
    monkeypatch.setattr(store, "_require_current_consent", AsyncMock())
    monkeypatch.setattr(
        store,
        "_claim_idempotency",
        AsyncMock(return_value=IdempotencyClaim(claim_record, created=True, replay=False)),
    )
    raw_secret = "sk-" + "testonly0123456789abcdefABCDEF"  # noqa: S105 - synthetic canary
    raw_email = "alice@example.test"
    raw_phone = "13800138000"

    prepared = await store.prepare_message(
        conversation_id=conversation.id,
        principal=principal,
        content=f"密钥 {raw_secret}，联系 {raw_email} 或 {raw_phone}",
        idempotency_key="message-1",
    )

    user_message = next(
        item for item in session.added if isinstance(item, Message) and item.content
    )
    assert user_message.content_redacted is True
    assert prepared.question == user_message.content
    for sensitive in (raw_secret, raw_email, raw_phone):
        assert sensitive not in user_message.content
        assert sensitive not in prepared.question
    summary_update = next(
        str(statement)
        for statement in session.executed
        if "UPDATE visit_summaries" in str(statement)
    )
    assert "is_current" in summary_update
    assert "stale_at" in summary_update


@pytest.mark.asyncio
async def test_ai_configuration_is_provisioned_before_first_enterprise_answer(
    monkeypatch: Any,
) -> None:
    card = _card()
    principal = _principal(card)
    session = _Session(card=card)
    settings = _settings()
    settings.llm_provider = "test-provider"
    settings.llm_model = "test-chat-model"
    store = PublicStore(_SessionFactory(session), settings)  # type: ignore[arg-type]
    monkeypatch.setattr(store, "_set_principal_scope", AsyncMock())
    profile_id = uuid.uuid4()

    await store.ensure_ai_configuration(
        principal=principal,
        runtime_settings=settings,
        profile_id=profile_id,
    )

    prompt_insert = next(
        statement
        for statement in session.executed
        if "INSERT INTO prompt_versions" in str(statement)
    )
    model_insert = next(
        statement
        for statement in session.executed
        if "INSERT INTO model_configs" in str(statement)
    )
    prompt_parameters = prompt_insert.compile().params
    model_parameters = model_insert.compile().params
    assert prompt_parameters["purpose"] == "rag_answer"
    assert prompt_parameters["published_by"] == card.responsible_user_id
    assert model_parameters["purpose"] == "chat"
    assert model_parameters["provider"] == "test-provider"
    assert model_parameters["model_name"] == "test-chat-model"
    assert model_parameters["secret_ref"] == f"platform-llm-profile:{profile_id}"


@pytest.mark.asyncio
async def test_conversation_history_keeps_user_before_assistant_when_timestamps_match(
    monkeypatch: Any,
) -> None:
    card = _card()
    principal = _principal(card)
    created_at = datetime.now(UTC)
    user = Message(
        id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
        tenant_id=card.tenant_id,
        company_id=card.company_id,
        conversation_id=uuid.uuid4(),
        role=MessageRole.USER,
        content="企业有什么商业模式？",
        status=MessageStatus.COMPLETED,
        created_at=created_at,
    )
    assistant = Message(
        id=uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
        tenant_id=card.tenant_id,
        company_id=card.company_id,
        conversation_id=user.conversation_id,
        role=MessageRole.ASSISTANT,
        content="当前资料没有披露具体盈利模式。",
        status=MessageStatus.COMPLETED,
        created_at=created_at,
    )
    # This is the deterministic descending order requested from PostgreSQL.
    session = _Session(result=[assistant, user])
    store = PublicStore(_SessionFactory(session), _settings())  # type: ignore[arg-type]
    monkeypatch.setattr(store, "_set_principal_scope", AsyncMock())
    prepared = SimpleNamespace(
        conversation_id=user.conversation_id,
        user_message_id=uuid.uuid4(),
    )

    history = await store.load_conversation_history(
        prepared=prepared,  # type: ignore[arg-type]
        principal=principal,
    )

    assert [(item.role, item.content) for item in history] == [
        ("user", user.content),
        ("assistant", assistant.content),
    ]
    statement = str(session.executed[-1])
    assert "CASE WHEN" in statement
    assert "messages.role" in statement


@pytest.mark.asyncio
async def test_chat_ip_card_limit_cannot_be_bypassed_by_rotating_visitor_tokens() -> None:
    class BlockingRedis:
        def __init__(self) -> None:
            self.keys: list[str] = []

        async def eval(
            self,
            _script: str,
            _number_of_keys: int,
            key: str,
            _window_seconds: int,
        ) -> tuple[int, int]:
            self.keys.append(key)
            return 2, 60

    settings = _settings()
    settings.public_chat_ip_card_rate_limit_per_minute = 1
    redis = BlockingRedis()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/messages:stream",
            "raw_path": b"/messages:stream",
            "query_string": b"",
            "headers": [],
            "client": ("203.0.113.9", 443),
            "server": ("api.example.test", 443),
            "app": SimpleNamespace(
                state=SimpleNamespace(settings=settings, redis=redis)
            ),
        }
    )
    card = _card()
    first = _principal(card)
    rotated = _principal(card)

    for principal in (first, rotated):
        with pytest.raises(ApiError) as captured:
            await stream_message(
                conversation_id=uuid.uuid4(),
                body=CreateMessageRequest(content="普通问题"),
                request=request,
                principal=principal,
                idempotency_key=str(uuid.uuid4()),
            )
        assert captured.value.code == "RATE_LIMITED"
        assert captured.value.safe_message == "请求过于频繁，请稍后重试"

    assert len(redis.keys) == 2
    assert redis.keys[0] == redis.keys[1]
    assert str(first.token_id) not in redis.keys[0]
    assert str(rotated.token_id) not in redis.keys[0]


@pytest.mark.asyncio
async def test_visit_ip_card_limit_applies_before_a_visitor_token_is_issued() -> None:
    class BlockingRedis:
        def __init__(self) -> None:
            self.keys: list[str] = []

        async def eval(
            self,
            _script: str,
            _number_of_keys: int,
            key: str,
            _window_seconds: int,
        ) -> tuple[int, int]:
            self.keys.append(key)
            return 2, 60

    settings = _settings()
    settings.public_visit_ip_card_rate_limit_per_minute = 1
    redis = BlockingRedis()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/public/cards/secure-card/visits",
            "raw_path": b"/public/cards/secure-card/visits",
            "query_string": b"",
            "headers": [],
            "client": ("203.0.113.9", 443),
            "server": ("api.example.test", 443),
            "app": SimpleNamespace(
                state=SimpleNamespace(settings=settings, redis=redis)
            ),
        }
    )

    for _ in range(2):
        with pytest.raises(ApiError) as captured:
            await create_visit_route(
                slug="secure-card",
                body=CreateVisitRequest(
                    source="direct",
                    privacy_notice_version="privacy-v2",
                ),
                request=request,
                idempotency_key=str(uuid.uuid4()),
            )
        assert captured.value.code == "RATE_LIMITED"

    assert redis.keys[0] == redis.keys[1]
    assert "secure-card" not in redis.keys[0]

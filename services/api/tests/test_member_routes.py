from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.member_schemas import (
    BulkMemberResult,
    BulkMemberRowResult,
    BulkMemberSummary,
    MemberRecord,
    PasswordResetRecord,
)
from app.api.routes import members as member_routes
from app.core.tokens import StaffPrincipal


class RouteMemberStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.member = _member()

    async def list_members(self, **kwargs: Any) -> tuple[list[MemberRecord], int]:
        self.calls.append(("list", kwargs))
        return [self.member], 1

    async def create_member(self, **kwargs: Any) -> MemberRecord:
        self.calls.append(("create", kwargs))
        return self.member

    async def get_member(self, **kwargs: Any) -> MemberRecord:
        self.calls.append(("get", kwargs))
        return self.member

    async def update_access(self, **kwargs: Any) -> MemberRecord:
        self.calls.append(("access", kwargs))
        return self.member.model_copy(update={"role": "company_admin"})

    async def update_self_profile(self, **kwargs: Any) -> MemberRecord:
        self.calls.append(("self_profile", kwargs))
        return self.member.model_copy(update={"avatar_url": kwargs["body"].avatar_url})

    async def set_status(self, **kwargs: Any) -> MemberRecord:
        self.calls.append(("status", kwargs))
        return self.member.model_copy(
            update={"status": kwargs["status"], "credential_enabled": False}
        )

    async def reset_password(self, **kwargs: Any) -> PasswordResetRecord:
        self.calls.append(("password", kwargs))
        return PasswordResetRecord(
            membership_id=self.member.membership_id,
            password_changed_at=datetime.now(UTC),
            sessions_revoked=2,
        )

    async def bulk_upsert(self, **kwargs: Any) -> BulkMemberResult:
        self.calls.append(("bulk", kwargs))
        body = kwargs["body"]
        return BulkMemberResult(
            batch_id=uuid.uuid4(),
            summary=BulkMemberSummary(
                total=len(body.rows),
                succeeded=len(body.rows),
                created=len(body.rows),
                updated=0,
                unchanged=0,
                duplicated=0,
                failed=0,
            ),
            rows=[
                BulkMemberRowResult(
                    row_number=index,
                    account=str(row["account"]),
                    outcome="created",
                    member=self.member,
                )
                for index, row in enumerate(body.rows, start=1)
            ],
        )


@pytest.fixture
def route_client() -> tuple[TestClient, RouteMemberStore, dict[str, StaffPrincipal]]:
    store = RouteMemberStore()
    principal_box = {"value": _principal(role="company_admin")}
    app = FastAPI()
    app.state.member_store = store
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(member_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
    with TestClient(app) as client:
        yield client, store, principal_box


def _principal(*, role: str, permissions: tuple[str, ...] = ()) -> StaffPrincipal:
    return StaffPrincipal(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        role=role,
        permissions=permissions,
        session_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
    )


def _member() -> MemberRecord:
    now = datetime.now(UTC)
    return MemberRecord(
        membership_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        account="member@example.test",
        display_name="Example Member",
        role="card_owner",
        permissions=["card.read"],
        status="active",
        credential_enabled=True,
        created_at=now,
        updated_at=now,
    )


def test_member_router_exposes_complete_user_management_contract(
    route_client: tuple[TestClient, RouteMemberStore, dict[str, StaffPrincipal]],
) -> None:
    client, _, _ = route_client
    paths = client.app.openapi()["paths"]

    assert paths["/api/v1/admin/members"]["get"]["operationId"] == "listCompanyMembers"
    assert paths["/api/v1/admin/members"]["post"]["operationId"] == "createCompanyMember"
    assert paths["/api/v1/admin/members/{membership_id}"]["get"]["operationId"] == (
        "getCompanyMember"
    )
    assert paths["/api/v1/admin/members/{membership_id}"]["patch"]["operationId"] == (
        "updateCompanyMemberAccess"
    )
    assert paths["/api/v1/admin/members/me/profile"]["patch"]["operationId"] == (
        "updateCurrentCompanyMemberProfile"
    )
    assert paths["/api/v1/admin/members/{membership_id}/status"]["put"]["operationId"] == (
        "updateCompanyMemberStatus"
    )
    assert paths["/api/v1/admin/members/{membership_id}/password:reset"]["post"][
        "operationId"
    ] == "resetCompanyMemberPassword"
    assert paths["/api/v1/admin/members/bulk"]["post"]["operationId"] == (
        "bulkUpsertCompanyMembers"
    )
    assert paths["/api/v1/admin/members/bulk:csv"]["post"]["operationId"] == (
        "bulkUpsertCompanyMembersCsv"
    )


def test_member_routes_bind_scope_from_principal_and_never_from_request(
    route_client: tuple[TestClient, RouteMemberStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = route_client
    principal = principal_box["value"]

    response = client.get(
        "/api/v1/admin/members",
        params={"tenant_id": str(uuid.uuid4()), "company_id": str(uuid.uuid4())},
    )

    assert response.status_code == 200
    scope = store.calls[-1][1]["scope"]
    assert scope.tenant_id == principal.tenant_id
    assert scope.company_id == principal.company_id
    assert scope.actor_user_id == principal.user_id
    assert scope.actor_session_id == principal.session_id
    assert scope.actor_role == "company_admin"
    assert scope.actor_permissions == ()


def test_company_admin_can_create_update_disable_and_rotate_password(
    route_client: tuple[TestClient, RouteMemberStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = route_client
    member_id = store.member.membership_id

    created = client.post(
        "/api/v1/admin/members",
        json={
            "account": "new@example.test",
            "display_name": "New Member",
            "password": "Member-Password-2026!",
            "role": "card_owner",
            "status": "active",
        },
    )
    updated = client.patch(
        f"/api/v1/admin/members/{member_id}",
        json={"role": "company_admin", "permissions": ["members.manage"]},
    )
    disabled = client.put(
        f"/api/v1/admin/members/{member_id}/status",
        json={"status": "disabled"},
    )
    reset = client.post(
        f"/api/v1/admin/members/{member_id}/password:reset",
        json={"password": "Replacement-Password-2026!", "revoke_sessions": True},
    )

    assert created.status_code == 201
    assert updated.status_code == 200
    assert updated.json()["data"]["role"] == "company_admin"
    assert disabled.json()["data"]["status"] == "disabled"
    assert reset.json()["data"]["sessions_revoked"] == 2
    password_call = next(values for name, values in store.calls if name == "password")
    assert password_call["password"] == "Replacement-Password-2026!"  # noqa: S105


def test_card_owner_without_member_permission_is_forbidden(
    route_client: tuple[TestClient, RouteMemberStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = route_client
    principal_box["value"] = _principal(role="card_owner", permissions=("card.write",))

    response = client.get("/api/v1/admin/members")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert store.calls == []


def test_card_owner_can_update_only_their_own_avatar(
    route_client: tuple[TestClient, RouteMemberStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = route_client
    principal = _principal(role="card_owner", permissions=("card.write",))
    principal_box["value"] = principal
    avatar_url = "/api/v1/public/card-assets/" + str(principal.company_id) + "/avatar.webp"

    response = client.patch(
        "/api/v1/admin/members/me/profile",
        json={"avatar_url": avatar_url},
    )

    assert response.status_code == 200
    assert response.json()["data"]["avatar_url"] == avatar_url
    name, values = store.calls[-1]
    assert name == "self_profile"
    assert values["membership_id"] == principal.membership_id
    assert values["scope"].actor_user_id == principal.user_id


def test_self_profile_cannot_name_another_member_or_use_an_unsafe_asset(
    route_client: tuple[TestClient, RouteMemberStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = route_client
    principal_box["value"] = _principal(role="card_owner", permissions=("card.write",))

    other = client.patch(
        "/api/v1/admin/members/me/profile",
        json={"avatar_url": "/assets/avatar.webp", "membership_id": str(uuid.uuid4())},
    )
    unsafe = client.patch(
        "/api/v1/admin/members/me/profile",
        json={"avatar_url": "javascript:alert(1)"},
    )
    admin_only_path = client.patch(
        f"/api/v1/admin/members/{uuid.uuid4()}",
        json={"avatar_url": "/assets/avatar.webp"},
    )

    assert other.status_code == 422
    assert unsafe.status_code == 422
    assert admin_only_path.status_code == 403
    assert store.calls == []


def test_explicit_member_permission_allows_non_admin_role(
    route_client: tuple[TestClient, RouteMemberStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = route_client
    principal_box["value"] = _principal(
        role="card_owner",
        permissions=("members.manage",),
    )

    response = client.get("/api/v1/admin/members")

    assert response.status_code == 200
    assert store.calls[-1][0] == "list"
    scope = store.calls[-1][1]["scope"]
    assert scope.actor_role == "card_owner"
    assert scope.actor_permissions == ("members.manage",)


def test_json_and_csv_bulk_routes_preserve_rows_and_parse_permissions(
    route_client: tuple[TestClient, RouteMemberStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = route_client
    json_response = client.post(
        "/api/v1/admin/members/bulk",
        json={
            "rows": [
                {
                    "account": "json@example.test",
                    "display_name": "JSON Member",
                    "password": "JSON-Password-2026!",
                }
            ]
        },
    )
    csv_response = client.post(
        "/api/v1/admin/members/bulk:csv",
        json={
            "csv_text": (
                "account,display_name,password,role,permissions,status\n"
                "csv@example.test,CSV Member,CSV-Password-2026!,card_owner,"
                "card.read|leads.read,active\n"
            )
        },
    )

    assert json_response.status_code == 200
    assert csv_response.status_code == 200
    bulk_calls = [values for name, values in store.calls if name == "bulk"]
    assert bulk_calls[0]["body"].rows[0]["account"] == "json@example.test"
    assert bulk_calls[1]["body"].rows[0]["permissions"] == ["card.read", "leads.read"]


def test_csv_rejects_missing_or_unknown_columns_before_store_call(
    route_client: tuple[TestClient, RouteMemberStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = route_client

    missing = client.post(
        "/api/v1/admin/members/bulk:csv",
        json={"csv_text": "account,display_name\na@example.test,Member\n"},
    )
    unknown = client.post(
        "/api/v1/admin/members/bulk:csv",
        json={
            "csv_text": (
                "account,display_name,password,tenant_id\n"
                "a@example.test,Member,Member-Password-2026!,other\n"
            )
        },
    )

    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "CSV_COLUMNS_INVALID"
    assert unknown.status_code == 422
    assert unknown.json()["error"]["details"] == {"fields": ["tenant_id"]}
    assert store.calls == []


def test_json_and_csv_bulk_routes_reject_more_than_one_hundred_rows(
    route_client: tuple[TestClient, RouteMemberStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = route_client
    json_rows = [
        {
            "account": f"member-{index}",
            "display_name": f"Member {index}",
            "password": "Member-Password-2026!",
        }
        for index in range(101)
    ]
    csv_rows = "".join(
        f"member-{index},Member {index},Member-Password-2026!\n"
        for index in range(101)
    )

    json_response = client.post(
        "/api/v1/admin/members/bulk",
        json={"rows": json_rows},
    )
    csv_response = client.post(
        "/api/v1/admin/members/bulk:csv",
        json={
            "csv_text": "account,display_name,password\n" + csv_rows,
        },
    )

    assert json_response.status_code == 422
    assert csv_response.status_code == 422
    assert csv_response.json()["error"]["code"] == "CSV_TOO_MANY_ROWS"
    assert store.calls == []

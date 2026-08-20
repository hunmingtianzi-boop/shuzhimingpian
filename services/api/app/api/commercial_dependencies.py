from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.core.tokens import StaffPrincipal
from app.services.commercial_store import CommercialActor, CommercialStore

StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]


def commercial_actor(principal: StaffPrincipal) -> CommercialActor:
    return CommercialActor(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        session_id=principal.session_id,
        role=str(getattr(principal.role, "value", principal.role)),
    )


def require_commercial_feature(
    feature_id: str,
) -> Callable[[Request, StaffDependency], Awaitable[None]]:
    async def dependency(request: Request, principal: StaffDependency) -> None:
        if str(getattr(principal.role, "value", principal.role)) == "platform_admin":
            return
        session_factory = getattr(request.app.state, "session_factory", None)
        if session_factory is None:
            # Router-only embedded apps (used by contract/unit harnesses) do not
            # have a persistence runtime. The production app always installs a
            # session factory before routers are mounted.
            return
        record = await CommercialStore(session_factory).get_entitlements(
            actor=commercial_actor(principal)
        )
        if not record.features.get(feature_id, False):
            feature = next(
                (item for item in record.feature_catalog if item.id == feature_id),
                None,
            )
            raise ApiError(
                403,
                "FEATURE_NOT_ENTITLED",
                "当前企业套餐未开通此功能",
                details={
                    "feature_id": feature_id,
                    "feature_name": feature.name if feature else feature_id,
                    "plan_code": record.plan_code,
                },
            )

    return dependency


async def require_commercial_feature_for_admin_path(
    request: Request,
    principal: StaffDependency,
) -> None:
    path = request.url.path
    feature_id: str | None = None
    if ":schedule-publish" in path or "/admin/scheduled-publishes" in path:
        await require_commercial_feature("catalog.scheduled_publish")(request, principal)
    path_rules = (
        ("/admin/cards/", "/wecom-contact-way", "integration.wecom"),
        ("/admin/company/profile", None, "company.profile"),
        ("/admin/products", None, "catalog.manage"),
        ("/admin/case-studies", None, "catalog.manage"),
        ("/admin/cases", None, "catalog.manage"),
        ("/admin/knowledge", None, "knowledge.manage"),
        ("/admin/forbidden-topics", None, "knowledge.manage"),
        ("/admin/card-plugins", None, "card.core"),
        ("/admin/card-composer", None, "card.core"),
        ("/admin/cards", None, "card.core"),
        ("/admin/card", None, "card.core"),
        ("/admin/setup", None, "card.core"),
        ("/admin/analytics/employees", None, "analytics.advanced"),
        ("/admin/analytics/topics", None, "ai.topic_analysis"),
        ("/admin/visits", None, "customer.visits"),
        ("/admin/conversations", None, "ai.conversations"),
        ("/admin/opportunities", None, "customer.opportunities"),
        ("/admin/knowledge-gaps", None, "knowledge.manage"),
    )
    for prefix, contains, candidate in path_rules:
        if prefix in path and (contains is None or contains in path):
            feature_id = candidate
            break
    if feature_id is not None:
        await require_commercial_feature(feature_id)(request, principal)


async def require_commercial_feature_for_knowledge_path(
    request: Request,
    principal: StaffDependency,
) -> None:
    path = request.url.path
    if "/admin/knowledge/imports" in path or "/admin/content-import" in path:
        await require_commercial_feature("knowledge.import")(request, principal)


__all__ = [
    "commercial_actor",
    "require_commercial_feature",
    "require_commercial_feature_for_admin_path",
    "require_commercial_feature_for_knowledge_path",
]

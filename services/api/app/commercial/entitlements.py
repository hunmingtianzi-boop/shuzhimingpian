from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Mapping

PlanCode = Literal["starter", "professional", "enterprise"]
BillingCycle = Literal["monthly", "yearly", "contract"]


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    id: str
    name: str
    group: str
    description: str
    minimum_plan: PlanCode
    overrideable: bool = True


@dataclass(frozen=True, slots=True)
class LimitDefinition:
    id: str
    name: str
    group: str
    description: str
    unit: str
    plan_defaults: Mapping[PlanCode, int | None]


@dataclass(frozen=True, slots=True)
class PlanDefinition:
    code: PlanCode
    name: str
    description: str
    sort_order: int


@dataclass(frozen=True, slots=True)
class CommercialEntitlementState:
    plan_code: PlanCode
    billing_cycle: BillingCycle
    contract_price_cny: Decimal | None
    feature_overrides: dict[str, bool]
    features: dict[str, bool]
    limit_overrides: dict[str, int | None]
    limits: dict[str, int | None]


PLAN_CATALOG: tuple[PlanDefinition, ...] = (
    PlanDefinition("starter", "基础版", "名片、内容展示和基础客户访问能力", 10),
    PlanDefinition("professional", "专业版", "增加 AI、知识运营和客户线索能力", 20),
    PlanDefinition("enterprise", "企业版", "增加高级经营、导出和企业集成能力", 30),
)

FEATURE_CATALOG: tuple[FeatureDefinition, ...] = (
    FeatureDefinition(
        "card.core",
        "数智名片",
        "名片与内容",
        "名片编辑、发布与基础身份展示",
        "starter",
        overrideable=False,
    ),
    FeatureDefinition(
        "catalog.manage", "产品与案例", "名片与内容", "产品和案例内容管理", "starter"
    ),
    FeatureDefinition(
        "catalog.scheduled_publish",
        "内容定时发布",
        "名片与内容",
        "产品、案例和知识内容预约发布",
        "professional",
    ),
    FeatureDefinition(
        "card.blocks.actions", "行动按钮区块", "名片与内容", "电话、微信和外链行动入口", "starter"
    ),
    FeatureDefinition(
        "customer.visits", "访问记录", "客户经营", "访问事件与基础访问统计", "starter"
    ),
    FeatureDefinition("team.members", "企业员工", "企业治理", "员工账号和员工名片管理", "starter"),
    FeatureDefinition(
        "company.profile", "企业资料", "企业治理", "企业介绍和品牌资料维护", "starter"
    ),
    FeatureDefinition(
        "privacy.manage", "隐私治理", "企业治理", "访客授权与隐私请求处理", "starter"
    ),
    FeatureDefinition(
        "card.blocks.faq", "FAQ 名片区块", "AI 与知识", "在名片中展示已发布 FAQ", "professional"
    ),
    FeatureDefinition(
        "knowledge.manage",
        "知识库",
        "AI 与知识",
        "FAQ、资料导入、禁答主题和知识缺口",
        "professional",
    ),
    FeatureDefinition(
        "knowledge.import",
        "文件与批量导入",
        "AI 与知识",
        "PDF、Word、表格和图片等资料的批量解析入库",
        "professional",
    ),
    FeatureDefinition(
        "ai.conversations", "AI 对话", "AI 与知识", "访客 AI 接待与对话记录", "professional"
    ),
    FeatureDefinition(
        "ai.topic_analysis",
        "AI 主题分析",
        "AI 与知识",
        "对话主题、客户意图和内容缺口聚合分析",
        "enterprise",
    ),
    FeatureDefinition(
        "customer.profiles", "访客画像", "客户经营", "访客识别、标签和画像管理", "professional"
    ),
    FeatureDefinition(
        "customer.leads", "销售线索", "客户经营", "线索收集、状态和跟进管理", "professional"
    ),
    FeatureDefinition(
        "customer.opportunities", "潜在机会", "客户经营", "基于对话和行为识别商机", "enterprise"
    ),
    FeatureDefinition(
        "data.exports", "数据导出", "客户经营", "访问、对话和线索数据导出", "enterprise"
    ),
    FeatureDefinition(
        "analytics.advanced", "高级经营分析", "客户经营", "员工与客户经营聚合分析", "enterprise"
    ),
    FeatureDefinition(
        "integration.wecom",
        "企业微信集成",
        "企业集成",
        "企业微信登录、绑定和客户联系能力",
        "enterprise",
    ),
    FeatureDefinition(
        "integration.wechat",
        "微信公众号访客授权",
        "企业集成",
        "公众号 OAuth 访客识别",
        "enterprise",
    ),
)

LIMIT_CATALOG: tuple[LimitDefinition, ...] = (
    LimitDefinition(
        "members.max",
        "员工账号数",
        "账号与内容",
        "企业内可启用的员工账号上限",
        "人",
        {"starter": 5, "professional": 50, "enterprise": None},
    ),
    LimitDefinition(
        "cards.max",
        "名片数量",
        "账号与内容",
        "企业可创建的员工名片总数",
        "张",
        {"starter": 5, "professional": 100, "enterprise": None},
    ),
    LimitDefinition(
        "knowledge.documents.max",
        "知识文档数",
        "AI 与数据",
        "知识库中可维护的文档总数",
        "篇",
        {"starter": 20, "professional": 500, "enterprise": None},
    ),
    LimitDefinition(
        "ai.conversations.monthly",
        "AI 对话额度",
        "AI 与数据",
        "每个自然月可发起的 AI 对话次数",
        "次/月",
        {"starter": 0, "professional": 5000, "enterprise": 50000},
    ),
    LimitDefinition(
        "exports.rows.monthly",
        "数据导出行数",
        "AI 与数据",
        "每个自然月允许导出的数据总行数",
        "行/月",
        {"starter": 0, "professional": 0, "enterprise": 100000},
    ),
    LimitDefinition(
        "storage.mb",
        "文件存储空间",
        "AI 与数据",
        "企业上传文件可使用的存储空间",
        "MB",
        {"starter": 1024, "professional": 10240, "enterprise": 102400},
    ),
)

_PLAN_ORDER = {plan.code: plan.sort_order for plan in PLAN_CATALOG}
_FEATURE_BY_ID = {feature.id: feature for feature in FEATURE_CATALOG}
_LIMIT_BY_ID = {limit.id: limit for limit in LIMIT_CATALOG}


def resolve_commercial_entitlements(
    company_settings: Mapping[str, Any] | None,
) -> CommercialEntitlementState:
    raw = (company_settings or {}).get("commercial_entitlements")
    is_configured = isinstance(raw, Mapping)
    config = raw if isinstance(raw, Mapping) else {}
    requested_plan = config.get("plan_code")
    plan_code: PlanCode = (
        requested_plan
        if isinstance(requested_plan, str) and requested_plan in _PLAN_ORDER
        else "enterprise"
    )
    requested_cycle = config.get("billing_cycle")
    billing_cycle: BillingCycle = (
        requested_cycle
        if isinstance(requested_cycle, str) and requested_cycle in {"monthly", "yearly", "contract"}
        else "contract"
    )
    contract_price_cny = _optional_decimal(config.get("contract_price_cny"))
    raw_overrides = config.get("feature_overrides")
    overrides: dict[str, bool] = {}
    if isinstance(raw_overrides, Mapping):
        for feature_id, enabled in raw_overrides.items():
            definition = _FEATURE_BY_ID.get(str(feature_id))
            if definition is not None and definition.overrideable and isinstance(enabled, bool):
                overrides[definition.id] = enabled

    raw_limit_overrides = config.get("limit_overrides")
    limit_overrides: dict[str, int | None] = {}
    if isinstance(raw_limit_overrides, Mapping):
        for limit_id, value in raw_limit_overrides.items():
            definition = _LIMIT_BY_ID.get(str(limit_id))
            if definition is None:
                continue
            if value is None:
                limit_overrides[definition.id] = None
            elif isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                limit_overrides[definition.id] = value

    plan_rank = _PLAN_ORDER[plan_code]
    features = {
        definition.id: plan_rank >= _PLAN_ORDER[definition.minimum_plan]
        for definition in FEATURE_CATALOG
    }
    features.update(overrides)
    for definition in FEATURE_CATALOG:
        if not definition.overrideable:
            features[definition.id] = True
    limits = {
        definition.id: definition.plan_defaults[plan_code] if is_configured else None
        for definition in LIMIT_CATALOG
    }
    limits.update(limit_overrides)
    return CommercialEntitlementState(
        plan_code=plan_code,
        billing_cycle=billing_cycle,
        contract_price_cny=contract_price_cny,
        feature_overrides=overrides,
        features=features,
        limit_overrides=limit_overrides,
        limits=limits,
    )


def feature_is_enabled(company_settings: Mapping[str, Any] | None, feature_id: str) -> bool:
    if feature_id not in _FEATURE_BY_ID:
        return False
    return resolve_commercial_entitlements(company_settings).features[feature_id]


def commercial_settings_payload(
    *,
    plan_code: PlanCode,
    billing_cycle: BillingCycle,
    contract_price_cny: Decimal | None,
    feature_overrides: Mapping[str, bool],
    limit_overrides: Mapping[str, int | None] | None = None,
) -> dict[str, Any]:
    normalized_overrides: dict[str, bool] = {}
    for feature_id, enabled in feature_overrides.items():
        definition = _FEATURE_BY_ID.get(feature_id)
        if definition is not None and definition.overrideable:
            normalized_overrides[feature_id] = bool(enabled)
    normalized_limit_overrides: dict[str, int | None] = {}
    for limit_id, value in (limit_overrides or {}).items():
        if limit_id not in _LIMIT_BY_ID:
            continue
        if value is None:
            normalized_limit_overrides[limit_id] = None
        elif isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            normalized_limit_overrides[limit_id] = value
    return {
        "plan_code": plan_code,
        "billing_cycle": billing_cycle,
        "contract_price_cny": (
            str(contract_price_cny.quantize(Decimal("0.01")))
            if contract_price_cny is not None
            else None
        ),
        "feature_overrides": normalized_overrides,
        "limit_overrides": normalized_limit_overrides,
    }


def feature_definition(feature_id: str) -> FeatureDefinition | None:
    return _FEATURE_BY_ID.get(feature_id)


def limit_definition(limit_id: str) -> LimitDefinition | None:
    return _LIMIT_BY_ID.get(limit_id)


def limit_value(company_settings: Mapping[str, Any] | None, limit_id: str) -> int | None:
    definition = _LIMIT_BY_ID.get(limit_id)
    if definition is None:
        return 0
    return resolve_commercial_entitlements(company_settings).limits[limit_id]


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed.quantize(Decimal("0.01"))


__all__ = [
    "BillingCycle",
    "CommercialEntitlementState",
    "FEATURE_CATALOG",
    "FeatureDefinition",
    "LIMIT_CATALOG",
    "LimitDefinition",
    "PLAN_CATALOG",
    "PlanCode",
    "commercial_settings_payload",
    "feature_definition",
    "feature_is_enabled",
    "limit_definition",
    "limit_value",
    "resolve_commercial_entitlements",
]

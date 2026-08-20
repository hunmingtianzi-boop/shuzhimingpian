from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommercialModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CommercialPlanRecord(CommercialModel):
    code: Literal["starter", "professional", "enterprise"]
    name: str
    description: str


class CommercialFeatureRecord(CommercialModel):
    id: str
    name: str
    group: str
    description: str
    minimum_plan: Literal["starter", "professional", "enterprise"]
    overrideable: bool


class CommercialLimitRecord(CommercialModel):
    id: str
    name: str
    group: str
    description: str
    unit: str
    plan_defaults: dict[Literal["starter", "professional", "enterprise"], int | None]


class CommercialEntitlementRecord(CommercialModel):
    company_id: uuid.UUID
    company_version: int = Field(ge=1)
    plan_code: Literal["starter", "professional", "enterprise"]
    billing_cycle: Literal["monthly", "yearly", "contract"]
    contract_price_cny: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    feature_overrides: dict[str, bool]
    features: dict[str, bool]
    limit_overrides: dict[str, int | None]
    limits: dict[str, int | None]
    plans: list[CommercialPlanRecord]
    feature_catalog: list[CommercialFeatureRecord]
    limit_catalog: list[CommercialLimitRecord]


class CommercialEntitlementEnvelope(CommercialModel):
    data: CommercialEntitlementRecord


class UpdateCommercialEntitlementRequest(CommercialModel):
    expected_version: int = Field(ge=1)
    plan_code: Literal["starter", "professional", "enterprise"]
    billing_cycle: Literal["monthly", "yearly", "contract"] = "contract"
    contract_price_cny: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    feature_overrides: dict[str, bool] = Field(default_factory=dict)
    limit_overrides: dict[str, int | None] = Field(default_factory=dict)

    @field_validator("limit_overrides", mode="before")
    @classmethod
    def validate_limit_overrides(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        invalid = [
            key
            for key, item in value.items()
            if item is not None
            and (not isinstance(item, int) or isinstance(item, bool) or item < 0)
        ]
        if invalid:
            raise ValueError("套餐额度必须是非负整数或 null")
        return value


__all__ = [
    "CommercialEntitlementEnvelope",
    "CommercialEntitlementRecord",
    "CommercialFeatureRecord",
    "CommercialLimitRecord",
    "CommercialPlanRecord",
    "UpdateCommercialEntitlementRequest",
]

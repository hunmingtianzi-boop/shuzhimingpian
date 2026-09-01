import { apiClient, ApiClient, ApiError } from "./client";
import type {
  ActivatePlatformLlmProfileInput,
  CommercialBillingCycle,
  CommercialEntitlements,
  CommercialPlanCode,
  CreatePlatformLlmProfileInput,
  CreatePlatformEnterpriseInput,
  CreatedPlatformEnterprise,
  PlatformCardProjection,
  PlatformAuditProjection,
  PlatformAssociationMember,
  PlatformAssociationSummary,
  PlatformCompanyAggregate,
  PlatformEnterprise,
  PlatformEnterpriseDetail,
  PlatformEnterpriseLifecycle,
  PlatformLlmConnectionTest,
  PlatformLlmProfile,
  PlatformOnboardingImportStatus,
  PlatformOnboardingSession,
  PlatformOnboardingStatus,
  PlatformOnboardingSuggestion,
  PlatformOnboardingCandidate,
  PlatformOnboardingCandidateCategory,
  RenamePlatformOnboardingInput,
  PlatformOverview,
  PlatformServiceHealth,
  PlatformTaskProjection,
  ConfirmPlatformOnboardingInput,
  StartPlatformOnboardingInput,
  UpdatePlatformLlmProfileInput,
} from "./types";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function invalid(label: string): never {
  throw new ApiError(`${label}接口返回了无法识别的数据。`, {
    code: "INVALID_API_RESPONSE",
  });
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) invalid(label);
  return value;
}

function optionalString(value: unknown, label: string): string | undefined {
  if (value === null || value === undefined) return undefined;
  return requiredString(value, label);
}

function requiredBoolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") invalid(label);
  return value;
}

function requiredNumber(
  value: unknown,
  label: string,
  options: { integer?: boolean } = {},
): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    (options.integer && !Number.isInteger(value))
  ) {
    invalid(label);
  }
  return value;
}

function optionalNumber(
  value: unknown,
  label: string,
  options: { integer?: boolean } = {},
): number | undefined {
  if (value === null || value === undefined) return undefined;
  return requiredNumber(value, label, options);
}

function nonNegativeInteger(value: unknown, label: string): number {
  const result = requiredNumber(value, label, { integer: true });
  if (result < 0) invalid(label);
  return result;
}

function optionalHttpUrl(value: unknown, label: string): string | undefined {
  if (value === null || value === undefined) return undefined;
  const result = requiredString(value, label);
  try {
    const parsed = new URL(result);
    if (!(["http:", "https:"] as const).includes(parsed.protocol as "http:" | "https:")) {
      invalid(label);
    }
  } catch {
    invalid(label);
  }
  return result;
}

function oneOf<T extends string>(
  value: unknown,
  values: readonly T[],
  label: string,
): T {
  if (typeof value !== "string" || !values.includes(value as T)) invalid(label);
  return value as T;
}

function unwrapData(value: unknown, label: string): unknown {
  if (!isRecord(value) || !("data" in value)) invalid(label);
  return value.data;
}

function enterprise(value: unknown): PlatformEnterprise {
  if (!isRecord(value)) invalid("企业");
  const companyName = requiredString(
    value.legal_name ?? value.company_name,
    "company_name",
  );
  const tenantSlug = requiredString(value.tenant_slug, "tenant_slug");
  return {
    tenantId: requiredString(value.tenant_id, "tenant_id"),
    tenantSlug,
    tenantName: optionalString(value.tenant_name, "tenant_name"),
    companyId: requiredString(value.company_id, "company_id"),
    companyName,
    legalName: companyName,
    shortName: optionalString(value.short_name, "short_name"),
    subjectType: oneOf(
      value.subject_type ?? "pending_registration",
      ["domestic_enterprise", "association", "overseas", "pending_registration"] as const,
      "subject_type",
    ),
    socialCreditCode: optionalString(value.social_credit_code, "social_credit_code"),
    businessTenantKey: requiredString(
      value.business_tenant_key ?? tenantSlug,
      "business_tenant_key",
    ),
    status: requiredString(value.status ?? value.company_status, "status"),
    createdAt: requiredString(value.created_at, "created_at"),
    updatedAt: optionalString(value.updated_at, "updated_at"),
  };
}

function associationSummary(value: unknown): PlatformAssociationSummary {
  if (!isRecord(value)) invalid("协会");
  return {
    companyId: requiredString(value.company_id, "association.company_id"),
    legalName: requiredString(value.legal_name, "association.legal_name"),
    shortName: optionalString(value.short_name, "association.short_name"),
    businessTenantKey: requiredString(value.business_tenant_key, "association.business_tenant_key"),
    memberCount: nonNegativeInteger(value.member_count, "association.member_count"),
    allocatedSeats: nonNegativeInteger(value.allocated_seats, "association.allocated_seats"),
  };
}

function associationMember(value: unknown): PlatformAssociationMember {
  if (!isRecord(value) || !isRecord(value.benefits)) invalid("协会成员");
  return {
    id: requiredString(value.id, "association_member.id"),
    associationCompanyId: requiredString(value.association_company_id, "association_member.association_company_id"),
    companyId: requiredString(value.company_id, "association_member.company_id"),
    legalName: requiredString(value.legal_name, "association_member.legal_name"),
    shortName: optionalString(value.short_name, "association_member.short_name"),
    businessTenantKey: requiredString(value.business_tenant_key, "association_member.business_tenant_key"),
    memberTier: optionalString(value.member_tier, "association_member.member_tier"),
    allocatedSeats: nonNegativeInteger(value.allocated_seats, "association_member.allocated_seats"),
    benefits: value.benefits,
    version: nonNegativeInteger(value.version, "association_member.version"),
    updatedAt: requiredString(value.updated_at, "association_member.updated_at"),
  };
}

function enterpriseLifecycle(value: unknown): PlatformEnterpriseLifecycle {
  if (!isRecord(value)) invalid("企业状态");
  return {
    tenantId: requiredString(value.tenant_id, "lifecycle.tenant_id"),
    companyId: requiredString(value.company_id, "lifecycle.company_id"),
    previousStatus: oneOf(
      value.previous_status,
      ["active", "suspended", "disabled"] as const,
      "lifecycle.previous_status",
    ),
    status: oneOf(
      value.status,
      ["active", "suspended"] as const,
      "lifecycle.status",
    ),
    version: nonNegativeInteger(value.version, "lifecycle.version"),
    changed: requiredBoolean(value.changed, "lifecycle.changed"),
    updatedAt: requiredString(value.updated_at, "lifecycle.updated_at"),
  };
}

function commercialEntitlements(value: unknown): CommercialEntitlements {
  if (!isRecord(value)) invalid("商业授权");
  const plansValue = value.plans;
  const featuresValue = value.feature_catalog;
  const limitsValue = value.limit_catalog;
  if (!Array.isArray(plansValue) || !Array.isArray(featuresValue) || !Array.isArray(limitsValue)) invalid("商业授权目录");
  const booleanRecord = (candidate: unknown): Record<string, boolean> => {
    if (!isRecord(candidate)) return {};
    return Object.fromEntries(
      Object.entries(candidate).filter((entry): entry is [string, boolean] => typeof entry[1] === "boolean"),
    );
  };
  const rawPrice = value.contract_price_cny;
  const limitRecord = (candidate: unknown): Record<string, number | null> => {
    if (!isRecord(candidate)) return {};
    return Object.fromEntries(
      Object.entries(candidate).filter((entry): entry is [string, number | null] =>
        entry[1] === null || (typeof entry[1] === "number" && Number.isInteger(entry[1]) && entry[1] >= 0),
      ),
    );
  };
  const usageRecord = (candidate: unknown): Record<string, number> => {
    if (!isRecord(candidate)) return {};
    return Object.fromEntries(
      Object.entries(candidate).filter((entry): entry is [string, number] =>
        typeof entry[1] === "number" && Number.isInteger(entry[1]) && entry[1] >= 0,
      ),
    );
  };
  const contractPriceCny = typeof rawPrice === "number"
    ? rawPrice
    : typeof rawPrice === "string" && Number.isFinite(Number(rawPrice))
      ? Number(rawPrice)
      : undefined;
  return {
    companyId: requiredString(value.company_id, "商业授权 company_id"),
    companyVersion: nonNegativeInteger(value.company_version, "商业授权 company_version"),
    planCode: oneOf(
      value.plan_code,
      ["starter", "professional", "enterprise"] as const,
      "商业授权 plan_code",
    ),
    billingCycle: oneOf(
      value.billing_cycle,
      ["monthly", "yearly", "contract"] as const,
      "商业授权 billing_cycle",
    ),
    ...(contractPriceCny !== undefined ? { contractPriceCny } : {}),
    serviceValidUntil: optionalString(value.service_valid_until, "商业授权 service_valid_until"),
    featureOverrides: booleanRecord(value.feature_overrides),
    features: booleanRecord(value.features),
    limitOverrides: limitRecord(value.limit_overrides),
    limits: limitRecord(value.limits),
    limitUsage: usageRecord(value.limit_usage),
    limitRemaining: limitRecord(value.limit_remaining),
    usagePeriodStartedAt: optionalString(value.usage_period_started_at, "商业授权 usage_period_started_at"),
    usagePeriodEndsAt: optionalString(value.usage_period_ends_at, "商业授权 usage_period_ends_at"),
    plans: plansValue.map((item) => {
      if (!isRecord(item)) invalid("商业套餐");
      return {
        code: oneOf(item.code, ["starter", "professional", "enterprise"] as const, "商业套餐 code"),
        name: requiredString(item.name, "商业套餐 name"),
        description: typeof item.description === "string" ? item.description : "",
      };
    }),
    featureCatalog: featuresValue.map((item) => {
      if (!isRecord(item)) invalid("商业功能");
      return {
        id: requiredString(item.id, "商业功能 id"),
        name: requiredString(item.name, "商业功能 name"),
        group: requiredString(item.group, "商业功能 group"),
        description: typeof item.description === "string" ? item.description : "",
        minimumPlan: oneOf(item.minimum_plan, ["starter", "professional", "enterprise"] as const, "商业功能 minimum_plan"),
        overrideable: requiredBoolean(item.overrideable, "商业功能 overrideable"),
      };
    }),
    limitCatalog: limitsValue.map((item) => {
      if (!isRecord(item)) invalid("商业额度");
      const defaults = limitRecord(item.plan_defaults);
      return {
        id: requiredString(item.id, "商业额度 id"),
        name: requiredString(item.name, "商业额度 name"),
        group: requiredString(item.group, "商业额度 group"),
        description: typeof item.description === "string" ? item.description : "",
        unit: requiredString(item.unit, "商业额度 unit"),
        planDefaults: {
          starter: defaults.starter ?? null,
          professional: defaults.professional ?? null,
          enterprise: defaults.enterprise ?? null,
        },
      };
    }),
  };
}

function createdEnterprise(value: unknown): CreatedPlatformEnterprise {
  if (!isRecord(value)) invalid("新建企业");
  const delivery = isRecord(value.credential_delivery)
    ? {
        account: requiredString(value.credential_delivery.account, "credential_delivery.account"),
        temporaryPassword: requiredString(
          value.credential_delivery.temporary_password,
          "credential_delivery.temporary_password",
        ),
        expiresAt: requiredString(value.credential_delivery.expires_at, "credential_delivery.expires_at"),
        shownOnce: true as const,
      }
    : undefined;
  return {
    ...enterprise(value),
    adminUserId: requiredString(value.admin_user_id, "admin_user_id"),
    adminMembershipId: requiredString(
      value.admin_membership_id,
      "admin_membership_id",
    ),
    credentialDelivery: delivery,
    initialCardId: optionalString(value.initial_card_id, "initial_card_id"),
    initialCardSlug: optionalString(value.initial_card_slug, "initial_card_slug"),
  };
}

const onboardingStatuses = [
  "draft",
  "processing",
  "review",
  "manual_required",
  "ready_to_confirm",
  "confirmed",
  "cancelled",
  "expired",
  "failed",
] as const satisfies readonly PlatformOnboardingStatus[];

function onboardingSuggestion(value: unknown): PlatformOnboardingSuggestion {
  if (!isRecord(value) || !Array.isArray(value.sources)) invalid("建企建议");
  return {
    field: requiredString(value.field, "suggestion.field"),
    value: typeof value.value === "string" ? value.value : invalid("suggestion.value"),
    confidence: optionalNumber(value.confidence, "suggestion.confidence"),
    generationVersion: nonNegativeInteger(
      value.generation_version,
      "suggestion.generation_version",
    ),
    sources: value.sources.map((source) => {
      if (!isRecord(source)) invalid("建企建议来源");
      return {
        importItemId: requiredString(source.import_item_id, "source.import_item_id"),
        fileName: requiredString(source.file_name, "source.file_name"),
        documentId: optionalString(source.document_id, "source.document_id"),
        excerpt: optionalString(source.excerpt, "source.excerpt"),
      };
    }),
  };
}

const onboardingCandidateCategories = new Set<PlatformOnboardingCandidateCategory>([
  "enterprise_profile",
  "products",
  "case_studies",
  "faqs",
  "unclassified",
]);

function onboardingCandidate(value: unknown): PlatformOnboardingCandidate {
  if (!isRecord(value) || !isRecord(value.payload)) invalid("资料候选");
  const category = requiredString(
    value.category,
    "candidate.category",
  ) as PlatformOnboardingCandidateCategory;
  if (!onboardingCandidateCategories.has(category)) invalid("资料候选分类");
  return {
    id: requiredString(value.id, "candidate.id"),
    runId: requiredString(value.run_id, "candidate.run_id"),
    category,
    payload: Object.fromEntries(
      Object.entries(value.payload).map(([key, field]) => [
        key,
        typeof field === "string" ? field : "",
      ]),
    ),
    sourceId: requiredString(value.source_id, "candidate.source_id"),
    sourceText: requiredString(value.source_text, "candidate.source_text"),
    confidence: typeof value.confidence === "number" ? value.confidence : 0,
    status: requiredString(
      value.status,
      "candidate.status",
    ) as PlatformOnboardingCandidate["status"],
    version: nonNegativeInteger(value.version, "candidate.version"),
  };
}

function onboardingContentReview(value: JsonRecord) {
  if (!Array.isArray(value.candidates) || !isRecord(value.counts)) {
    invalid("资料候选任务");
  }
  return {
    id: requiredString(value.id, "review.id"),
    batchId: requiredString(value.batch_id, "review.batch_id"),
    status: requiredString(
      value.status,
      "review.status",
    ) as "processing" | "review" | "manual_required",
    provider: requiredString(value.provider, "review.provider"),
    model: requiredString(value.model, "review.model"),
    attempts: nonNegativeInteger(value.attempts, "review.attempts"),
    failureCode: optionalString(value.failure_code, "review.failure_code"),
    counts: Object.fromEntries(
      Object.entries(value.counts).map(([key, count]) => [
        key,
        typeof count === "number" ? count : 0,
      ]),
    ),
    stage: oneOf(
      value.stage ?? "completed",
      ["queued", "discovering", "enriching", "validating", "finalizing", "completed", "failed"] as const,
      "review.stage",
    ),
    stageMessage: optionalString(value.stage_message, "review.stage_message"),
    progressCurrent: nonNegativeInteger(value.progress_current ?? 0, "review.progress_current"),
    progressTotal: nonNegativeInteger(value.progress_total ?? 1, "review.progress_total"),
    startedAt: optionalString(value.started_at, "review.started_at"),
    completedAt: optionalString(value.completed_at, "review.completed_at"),
    candidates: value.candidates.map(onboardingCandidate),
  };
}

function onboardingSession(value: unknown): PlatformOnboardingSession {
  if (!isRecord(value) || !Array.isArray(value.import_batch_ids)) {
    invalid("资料辅助建企会话");
  }
  if (!Array.isArray(value.suggestions)) invalid("资料辅助建企建议");
  if (value.business_profile !== undefined && !Array.isArray(value.business_profile)) invalid("资料辅助建企业务画像");
  const contentReview = isRecord(value.content_review)
    ? onboardingContentReview(value.content_review)
    : undefined;
  return {
    id: requiredString(value.id, "id"),
    displayName: requiredString(value.display_name, "display_name"),
    status: oneOf(value.status, onboardingStatuses, "status"),
    tenantSlug: requiredString(value.tenant_slug, "tenant_slug"),
    tenantName: optionalString(value.tenant_name, "tenant_name"),
    legalName: optionalString(value.legal_name, "legal_name"),
    shortName: optionalString(value.short_name, "short_name"),
    subjectType:
      value.subject_type === undefined || value.subject_type === null
        ? undefined
        : oneOf(
            value.subject_type,
            ["domestic_enterprise", "association", "overseas", "pending_registration"] as const,
            "subject_type",
          ),
    socialCreditCode: optionalString(value.social_credit_code, "social_credit_code"),
    industry: optionalString(value.industry, "industry"),
    adminAccount: optionalString(value.admin_account, "admin_account"),
    adminDisplayName: optionalString(
      value.admin_display_name,
      "admin_display_name",
    ),
    initialCardDisplayName: optionalString(
      value.initial_card_display_name,
      "initial_card_display_name",
    ),
    initialCardTitle: optionalString(
      value.initial_card_title,
      "initial_card_title",
    ),
    version: nonNegativeInteger(value.version, "version"),
    importBatchIds: value.import_batch_ids.map((item) =>
      requiredString(item, "import_batch_id"),
    ),
    suggestions: value.suggestions.map(onboardingSuggestion),
    businessProfile: Array.isArray(value.business_profile)
      ? value.business_profile.map(onboardingSuggestion)
      : [],
    synthesisStatus: oneOf(
      value.synthesis_status ?? "pending",
      ["pending", "processing", "ready", "failed"] as const,
      "synthesis_status",
    ),
    synthesisFailureCode: optionalString(value.synthesis_failure_code, "synthesis_failure_code"),
    synthesisStartedAt: optionalString(value.synthesis_started_at, "synthesis_started_at"),
    synthesisCompletedAt: optionalString(value.synthesis_completed_at, "synthesis_completed_at"),
    synthesisVersion: nonNegativeInteger(value.synthesis_version ?? 0, "synthesis_version"),
    contentReview,
    expiresAt: optionalString(value.expires_at, "expires_at"),
    confirmedEnterprise:
      value.confirmed_enterprise === null || value.confirmed_enterprise === undefined
        ? undefined
        : createdEnterprise(value.confirmed_enterprise),
    credentialDelivery:
      isRecord(value.credential_delivery)
        ? {
            account: requiredString(value.credential_delivery.account, "credential account"),
            temporaryPassword: requiredString(
              value.credential_delivery.temporary_password,
              "temporary password",
            ),
            expiresAt: requiredString(value.credential_delivery.expires_at, "credential expiry"),
            shownOnce: true,
          }
        : undefined,
    temporaryCredentialResetAvailable: requiredBoolean(
      value.temporary_credential_reset_available,
      "temporary_credential_reset_available",
    ),
    createdAt: requiredString(value.created_at, "created_at"),
    updatedAt: requiredString(value.updated_at, "updated_at"),
  };
}

const onboardingImportItemStatuses = [
  "pending",
  "processing",
  "completed",
  "failed",
  "dead_letter",
] as const;

function onboardingImportStatus(value: unknown): PlatformOnboardingImportStatus {
  if (!isRecord(value) || !Array.isArray(value.batches)) {
    invalid("资料辅助建企导入进度");
  }

  const sessionId = requiredString(
    value.session_id,
    "onboarding_imports.session_id",
  );
  return {
    sessionId,
    settled: requiredBoolean(value.settled, "onboarding_imports.settled"),
    items: value.batches.flatMap((batch) => {
      if (!isRecord(batch) || !Array.isArray(batch.items)) {
        invalid("资料辅助建企导入批次");
      }
      const batchId = requiredString(batch.id, "onboarding_import_batch.id");
      const batchVersion = nonNegativeInteger(
        batch.version ?? 1,
        "onboarding_import_batch.version",
      );
      return batch.items.map((item) => {
        if (!isRecord(item)) invalid("资料辅助建企导入文件");
        return {
          id: requiredString(item.id, "onboarding_import_item.id"),
          batchId,
          batchVersion,
          fileName: requiredString(
            item.file_name,
            "onboarding_import_item.file_name",
          ),
          sourceType: requiredString(
            item.source_type,
            "onboarding_import_item.source_type",
          ),
          status: oneOf(
            item.status,
            onboardingImportItemStatuses,
            "onboarding_import_item.status",
          ),
          errorCode: optionalString(
            item.error_code,
            "onboarding_import_item.error_code",
          ),
          attempts: nonNegativeInteger(
            item.attempts ?? 0,
            "onboarding_import_item.attempts",
          ),
          maxAttempts: nonNegativeInteger(
            item.max_attempts ?? 6,
            "onboarding_import_item.max_attempts",
          ),
          retryAvailable: item.retry_available === true,
          createdAt: requiredString(
            item.created_at,
            "onboarding_import_item.created_at",
          ),
          completedAt: optionalString(
            item.completed_at,
            "onboarding_import_item.completed_at",
          ),
        };
      });
    }),
  };
}

function cardProjection(value: unknown): PlatformCardProjection {
  if (!isRecord(value)) invalid("名片投影");
  const status = requiredString(value.status, "card.status");
  const shareUrl = optionalHttpUrl(value.share_url, "card.share_url");
  if (shareUrl && status !== "published") invalid("card.share_url");
  return {
    id: requiredString(value.id, "card.id"),
    cardKind: oneOf(
      value.card_kind,
      ["enterprise", "employee"] as const,
      "card.card_kind",
    ),
    displayName: requiredString(value.display_name, "card.display_name"),
    title: typeof value.title === "string" ? value.title : invalid("card.title"),
    status,
    updatedAt: requiredString(value.updated_at, "card.updated_at"),
    shareUrl,
  };
}

function enterpriseDetail(value: unknown): PlatformEnterpriseDetail {
  if (!isRecord(value)) invalid("企业详情");
  const profileCompletion = nonNegativeInteger(
    value.profile_completion,
    "profile_completion",
  );
  if (profileCompletion > 100) invalid("profile_completion");
    const cards = value.cards;
    if (!Array.isArray(cards)) invalid("cards");
    const businessProfile = value.business_profile;
    if (businessProfile !== undefined && !Array.isArray(businessProfile)) {
      invalid("business_profile");
    }
  return {
    ...enterprise(value),
    version: nonNegativeInteger(value.version, "version"),
    onboardingStatus: requiredString(
      value.onboarding_status,
      "onboarding_status",
    ),
    profileCompletion,
    employeeCount: nonNegativeInteger(value.employee_count, "employee_count"),
    cardCount: nonNegativeInteger(value.card_count, "card_count"),
    publishedCardCount: nonNegativeInteger(
      value.published_card_count,
      "published_card_count",
    ),
    visits30d: nonNegativeInteger(value.visits_30d, "visits_30d"),
    conversations30d: nonNegativeInteger(
      value.conversations_30d,
      "conversations_30d",
    ),
      uniqueVisitors30d: nonNegativeInteger(value.unique_visitors_30d ?? 0, "unique_visitors_30d"),
      consentedLeads30d: nonNegativeInteger(value.consented_leads_30d ?? value.leads_30d ?? 0, "consented_leads_30d"),
      leads30d: nonNegativeInteger(value.consented_leads_30d ?? value.leads_30d ?? 0, "leads_30d"),
      actionableTaskCount: nonNegativeInteger(value.actionable_task_count ?? 0, "actionable_task_count"),
      failedTaskCount: nonNegativeInteger(value.failed_task_count ?? 0, "failed_task_count"),
      serviceValidUntil: optionalString(value.service_valid_until, "service_valid_until"),
      serviceRiskLevel: oneOf(
        value.service_risk_level ?? "missing",
        ["healthy", "warning", "expired", "missing"] as const,
        "service_risk_level",
      ),
      lastActivityAt: optionalString(value.last_activity_at, "last_activity_at"),
      cards: cards.map(cardProjection),
      businessProfile: Array.isArray(businessProfile)
        ? businessProfile.map(onboardingSuggestion)
        : [],
      recentTasks: Array.isArray(value.recent_tasks)
        ? value.recent_tasks.map(taskProjection)
        : [],
      updatedAt: requiredString(value.updated_at, "updated_at"),
  };
}

function platformOverview(value: unknown): PlatformOverview {
  if (!isRecord(value)) invalid("平台总览");
  const enabled = nonNegativeInteger(
    value.enabled_enterprise_count ?? value.active_enterprise_count ?? 0,
    "enabled_enterprise_count",
  );
  const pendingActivation = nonNegativeInteger(
    value.pending_activation_count ?? value.onboarding_count ?? 0,
    "pending_activation_count",
  );
  const consentedLeads = nonNegativeInteger(
    value.consented_leads_30d ?? value.leads_30d ?? 0,
    "consented_leads_30d",
  );
  return {
    generatedAt: requiredString(value.generated_at, "generated_at"),
    enabledEnterpriseCount: enabled,
    activeEnterprise30dCount: nonNegativeInteger(value.active_enterprise_30d_count ?? 0, "active_enterprise_30d_count"),
    pendingActivationCount: pendingActivation,
    uniqueVisitors30d: nonNegativeInteger(value.unique_visitors_30d ?? 0, "unique_visitors_30d"),
    consentedLeads30d: consentedLeads,
    pendingTaskCount: nonNegativeInteger(value.pending_task_count ?? 0, "pending_task_count"),
    serviceRiskCount: nonNegativeInteger(value.service_risk_count ?? 0, "service_risk_count"),
    enterpriseCount: nonNegativeInteger(value.enterprise_count ?? enabled, "enterprise_count"),
    activeEnterpriseCount: enabled,
    onboardingCount: pendingActivation,
    publishedCardCount: nonNegativeInteger(
      value.published_card_count,
      "published_card_count",
    ),
    visits30d: nonNegativeInteger(value.visits_30d, "visits_30d"),
    conversations30d: nonNegativeInteger(
      value.conversations_30d,
      "conversations_30d",
    ),
    leads30d: consentedLeads,
    failedTaskCount: nonNegativeInteger(value.failed_task_count, "failed_task_count"),
    llmReady: requiredBoolean(value.llm_ready, "llm_ready"),
    importReady: requiredBoolean(value.import_ready, "import_ready"),
  };
}

function companyAggregate(value: unknown): PlatformCompanyAggregate {
  if (!isRecord(value)) invalid("企业员工访客聚合");
  return {
    companyId: requiredString(value.company_id, "company_id"),
    companyName: requiredString(value.company_name, "company_name"),
    legalName: requiredString(value.legal_name ?? value.company_name, "legal_name"),
    shortName: optionalString(value.short_name, "short_name"),
    businessTenantKey: requiredString(value.business_tenant_key ?? value.company_id, "business_tenant_key"),
    status: requiredString(value.status ?? "active", "status"),
    employeeCount: nonNegativeInteger(value.employee_count, "employee_count"),
    cardCount: nonNegativeInteger(value.card_count ?? 0, "card_count"),
    publishedCardCount: nonNegativeInteger(value.published_card_count ?? 0, "published_card_count"),
    visits30d: nonNegativeInteger(value.visits_30d, "visits_30d"),
    uniqueVisitors30d: nonNegativeInteger(
      value.unique_visitors_30d,
      "unique_visitors_30d",
    ),
    conversations30d: nonNegativeInteger(value.conversations_30d ?? 0, "conversations_30d"),
    consentedLeads30d: nonNegativeInteger(value.consented_leads_30d ?? 0, "consented_leads_30d"),
    actionableTaskCount: nonNegativeInteger(value.actionable_task_count ?? 0, "actionable_task_count"),
    failedTaskCount: nonNegativeInteger(value.failed_task_count ?? 0, "failed_task_count"),
    serviceValidUntil: optionalString(value.service_valid_until, "service_valid_until"),
    serviceRiskLevel: oneOf(
      value.service_risk_level ?? "missing",
      ["healthy", "warning", "expired", "missing"] as const,
      "service_risk_level",
    ),
    lastActivityAt: optionalString(value.last_activity_at, "last_activity_at"),
    lastVisitAt: optionalString(value.last_activity_at ?? value.last_visit_at, "last_visit_at"),
  };
}

function taskProjection(value: unknown): PlatformTaskProjection {
  if (!isRecord(value)) invalid("平台任务");
  const rawType = requiredString(value.task_type, "task.task_type");
  const taskType = (
    ["onboarding", "knowledge_import", "content_review", "enterprise_risk", "service_validity"].includes(rawType)
      ? rawType
      : "enterprise_risk"
  ) as PlatformTaskProjection["taskType"];
  const rawStatus = requiredString(value.status, "task.status");
  const status = (
    ["pending", "in_progress", "blocked", "failed", "completed", "cancelled", "expired"].includes(rawStatus)
      ? rawStatus
      : ["queued", "processing", "running"].includes(rawStatus)
        ? "in_progress"
        : ["error", "dead_letter"].includes(rawStatus)
          ? "failed"
          : "completed"
  ) as PlatformTaskProjection["status"];
  return {
    id: requiredString(value.id, "task.id"),
    taskType,
    businessLabel: requiredString(value.business_label, "task.business_label"),
    status,
    companyId: optionalString(value.company_id, "task.company_id"),
    companyName: optionalString(value.company_name, "task.company_name"),
    tenantSlug: optionalString(value.tenant_slug, "task.tenant_slug"),
    errorCode: optionalString(value.error_code, "task.error_code"),
    createdAt: requiredString(value.created_at, "task.created_at"),
    updatedAt: requiredString(value.updated_at, "task.updated_at"),
  };
}

function auditProjection(value: unknown): PlatformAuditProjection {
  if (!isRecord(value)) invalid("平台审计");
  return {
    id: requiredString(value.id, "audit.id"),
    actorDisplayName: requiredString(
      value.actor_display_name,
      "audit.actor_display_name",
    ),
    action: requiredString(value.action, "audit.action"),
    businessLabel: requiredString(value.business_label, "audit.business_label"),
    resourceType: requiredString(value.resource_type, "audit.resource_type"),
    resourceId: optionalString(value.resource_id, "audit.resource_id"),
    result: requiredString(value.result, "audit.result"),
    createdAt: requiredString(value.created_at, "audit.created_at"),
  };
}

function serviceHealth(value: unknown): PlatformServiceHealth {
  if (!isRecord(value)) invalid("平台服务健康");
  return {
    service: oneOf(
      value.service,
      ["api", "database", "redis", "object_storage", "worker"] as const,
      "health.service",
    ),
    status: oneOf(
      value.status,
      ["healthy", "degraded", "unavailable"] as const,
      "health.status",
    ),
    checkedAt: requiredString(value.checked_at, "health.checked_at"),
    latencyMs: optionalNumber(value.latency_ms, "health.latency_ms", {
      integer: true,
    }),
    errorCode: optionalString(value.error_code, "health.error_code"),
  };
}

function llmProfile(value: unknown): PlatformLlmProfile {
  if (!isRecord(value)) invalid("LLM 配置");
  return {
    id: requiredString(value.id, "id"),
    name: requiredString(value.name, "name"),
    purpose: oneOf(value.purpose, ["chat_main"] as const, "purpose"),
    provider: requiredString(value.provider, "provider"),
    baseUrl: requiredString(value.base_url, "base_url"),
    model: requiredString(value.model, "model"),
    thinking: oneOf(
      value.thinking,
      ["enabled", "disabled"] as const,
      "thinking",
    ),
    reasoningEffort:
      value.reasoning_effort === null || value.reasoning_effort === undefined
        ? undefined
        : oneOf(
            value.reasoning_effort,
            ["high", "max"] as const,
            "reasoning_effort",
          ),
    timeoutSeconds: requiredNumber(value.timeout_seconds, "timeout_seconds"),
    maxRetries: requiredNumber(value.max_retries, "max_retries", {
      integer: true,
    }),
    maxConcurrency: requiredNumber(value.max_concurrency, "max_concurrency", {
      integer: true,
    }),
    maxOutputTokens: requiredNumber(
      value.max_output_tokens,
      "max_output_tokens",
      { integer: true },
    ),
    temperature: requiredNumber(value.temperature, "temperature"),
    dailyBudgetCny: requiredNumber(value.daily_budget_cny, "daily_budget_cny"),
    inputPriceCnyPerMillion: requiredNumber(
      value.input_price_cny_per_million,
      "input_price_cny_per_million",
    ),
    outputPriceCnyPerMillion: requiredNumber(
      value.output_price_cny_per_million,
      "output_price_cny_per_million",
    ),
    allowGeneralAnswers: requiredBoolean(
      value.allow_general_answers,
      "allow_general_answers",
    ),
    faqFastPathEnabled: requiredBoolean(
      value.faq_fast_path_enabled,
      "faq_fast_path_enabled",
    ),
    keyConfigured: requiredBoolean(value.key_configured, "key_configured"),
    keyHint: optionalString(value.key_hint, "key_hint"),
    enabled: requiredBoolean(value.enabled, "enabled"),
    isActive: requiredBoolean(value.is_active, "is_active"),
    version: requiredNumber(value.version, "version", { integer: true }),
    lastTestStatus: oneOf(
      value.last_test_status,
      ["untested", "succeeded", "failed"] as const,
      "last_test_status",
    ),
    lastTestLatencyMs: optionalNumber(
      value.last_test_latency_ms,
      "last_test_latency_ms",
      { integer: true },
    ),
    lastTestedAt: optionalString(value.last_tested_at, "last_tested_at"),
    createdAt: requiredString(value.created_at, "created_at"),
    updatedAt: requiredString(value.updated_at, "updated_at"),
  };
}

function llmConnectionTest(value: unknown): PlatformLlmConnectionTest {
  if (!isRecord(value)) invalid("LLM 连接测试");
  return {
    status: oneOf(
      value.status,
      ["succeeded", "failed"] as const,
      "status",
    ),
    provider: requiredString(value.provider, "provider"),
    model: requiredString(value.model, "model"),
    latencyMs: requiredNumber(value.latency_ms, "latency_ms", {
      integer: true,
    }),
    errorCode: optionalString(value.error_code, "error_code"),
  };
}

function llmProfilePayload(
  input: CreatePlatformLlmProfileInput | UpdatePlatformLlmProfileInput,
): JsonRecord {
  const body: JsonRecord = {};
  if (input.name !== undefined) body.name = input.name.trim();
  if (input.provider !== undefined) body.provider = input.provider.trim();
  if (input.baseUrl !== undefined) body.base_url = input.baseUrl.trim();
  if (input.model !== undefined) body.model = input.model.trim();
  if (input.apiKey?.trim()) body.api_key = input.apiKey.trim();
  if (input.thinking !== undefined) body.thinking = input.thinking;
  if (input.reasoningEffort !== undefined) {
    body.reasoning_effort = input.reasoningEffort;
  }
  if (input.timeoutSeconds !== undefined) {
    body.timeout_seconds = input.timeoutSeconds;
  }
  if (input.maxRetries !== undefined) body.max_retries = input.maxRetries;
  if (input.maxConcurrency !== undefined) {
    body.max_concurrency = input.maxConcurrency;
  }
  if (input.maxOutputTokens !== undefined) {
    body.max_output_tokens = input.maxOutputTokens;
  }
  if (input.temperature !== undefined) body.temperature = input.temperature;
  if (input.dailyBudgetCny !== undefined) {
    body.daily_budget_cny = input.dailyBudgetCny;
  }
  if (input.inputPriceCnyPerMillion !== undefined) {
    body.input_price_cny_per_million = input.inputPriceCnyPerMillion;
  }
  if (input.outputPriceCnyPerMillion !== undefined) {
    body.output_price_cny_per_million = input.outputPriceCnyPerMillion;
  }
  if (input.allowGeneralAnswers !== undefined) {
    body.allow_general_answers = input.allowGeneralAnswers;
  }
  if (input.faqFastPathEnabled !== undefined) {
    body.faq_fast_path_enabled = input.faqFastPathEnabled;
  }
  if (input.enabled !== undefined) body.enabled = input.enabled;
  return body;
}

export function createPlatformApi(client: ApiClient) {
  return {
    async listEnterprises(
      options: {
        search?: string;
        status?: "active" | "suspended" | "disabled";
        activityLevel?: "active_30d" | "inactive_30d";
        hasActionableTasks?: boolean;
        serviceRisk?: "healthy" | "warning" | "expired" | "missing";
        sortBy?: "created_at" | "last_activity_at" | "actionable_task_count" | "service_risk";
        sortOrder?: "asc" | "desc";
        limit?: number;
        offset?: number;
      } = {},
    ): Promise<PlatformEnterprise[]> {
      const params = new URLSearchParams({
        limit: String(options.limit ?? 50),
        offset: String(options.offset ?? 0),
      });
      if (options.search?.trim()) params.set("search", options.search.trim());
      if (options.status) params.set("status", options.status);
      if (options.activityLevel) params.set("activity_level", options.activityLevel);
      if (options.hasActionableTasks !== undefined) {
        params.set("has_actionable_tasks", String(options.hasActionableTasks));
      }
      if (options.serviceRisk) params.set("service_risk", options.serviceRisk);
      if (options.sortBy) params.set("sort_by", options.sortBy);
      if (options.sortOrder) params.set("sort_order", options.sortOrder);
      const payload = await client.get(`/platform/enterprises?${params.toString()}`);
      const values = unwrapData(payload, "企业列表");
      if (!Array.isArray(values)) invalid("企业列表");
      return values.map(enterprise);
    },

    async listAssociations(): Promise<PlatformAssociationSummary[]> {
      const values = unwrapData(await client.get("/platform/associations"), "协会列表");
      if (!Array.isArray(values)) invalid("协会列表");
      return values.map(associationSummary);
    },

    async listAssociationMembers(associationCompanyId: string): Promise<PlatformAssociationMember[]> {
      const values = unwrapData(
        await client.get(`/platform/associations/${encodeURIComponent(associationCompanyId)}/members`),
        "协会成员列表",
      );
      if (!Array.isArray(values)) invalid("协会成员列表");
      return values.map(associationMember);
    },

    async upsertAssociationMember(
      associationCompanyId: string,
      memberCompanyId: string,
      input: { expectedVersion: number; memberTier?: string; allocatedSeats: number; benefits?: Record<string, unknown> },
    ): Promise<PlatformAssociationMember> {
      return associationMember(unwrapData(await client.put(
        `/platform/associations/${encodeURIComponent(associationCompanyId)}/members/${encodeURIComponent(memberCompanyId)}`,
        {
          expected_version: input.expectedVersion,
          member_tier: input.memberTier?.trim() || null,
          allocated_seats: input.allocatedSeats,
          benefits: input.benefits ?? {},
        },
      ), "协会成员"));
    },

    async removeAssociationMember(
      associationCompanyId: string,
      memberCompanyId: string,
      expectedVersion: number,
    ): Promise<void> {
      await client.delete(
        `/platform/associations/${encodeURIComponent(associationCompanyId)}/members/${encodeURIComponent(memberCompanyId)}?expected_version=${expectedVersion}`,
      );
    },

    async getOverview(): Promise<PlatformOverview> {
      return platformOverview(
        unwrapData(await client.get("/platform/overview"), "平台总览"),
      );
    },

    async getEnterpriseDetail(companyId: string): Promise<PlatformEnterpriseDetail> {
      return enterpriseDetail(
        unwrapData(
          await client.get(
            `/platform/enterprises/${encodeURIComponent(companyId)}`,
          ),
          "企业详情",
        ),
      );
    },

    async transitionEnterprise(
      companyId: string,
      input: {
        expectedVersion: number;
        targetStatus: "active" | "suspended";
        reason: string;
      },
    ): Promise<PlatformEnterpriseLifecycle> {
      return enterpriseLifecycle(
        unwrapData(
          await client.put(
            `/platform/enterprises/${encodeURIComponent(companyId)}/status`,
            {
              expected_version: input.expectedVersion,
              target_status: input.targetStatus,
              reason: input.reason.trim(),
            },
          ),
          "企业状态",
        ),
      );
    },

    async getEnterpriseEntitlements(companyId: string): Promise<CommercialEntitlements> {
      return commercialEntitlements(
        unwrapData(
          await client.get(`/platform/enterprises/${encodeURIComponent(companyId)}/entitlements`),
          "商业授权",
        ),
      );
    },

    async updateEnterpriseEntitlements(
      companyId: string,
      input: {
        expectedVersion: number;
        planCode: CommercialPlanCode;
        billingCycle: CommercialBillingCycle;
        contractPriceCny?: number;
        serviceValidUntil?: string;
        featureOverrides: Record<string, boolean>;
        limitOverrides: Record<string, number | null>;
      },
    ): Promise<CommercialEntitlements> {
      return commercialEntitlements(
        unwrapData(
          await client.put(
            `/platform/enterprises/${encodeURIComponent(companyId)}/entitlements`,
            {
              expected_version: input.expectedVersion,
              plan_code: input.planCode,
              billing_cycle: input.billingCycle,
              contract_price_cny: input.contractPriceCny ?? null,
              service_valid_until: input.serviceValidUntil ?? null,
              feature_overrides: input.featureOverrides,
              limit_overrides: input.limitOverrides,
            },
          ),
          "商业授权",
        ),
      );
    },

    async listCompanyAggregates(): Promise<PlatformCompanyAggregate[]> {
      const values = unwrapData(
        await client.get("/platform/company-aggregates?limit=100&offset=0"),
        "企业员工访客聚合",
      );
      if (!Array.isArray(values)) invalid("企业员工访客聚合");
      return values.map(companyAggregate);
    },

    async listTasks(options: {
      view?: "timeline" | "company";
      companyId?: string;
      status?: string;
      taskType?: string;
      updatedFrom?: string;
      updatedTo?: string;
      limit?: number;
      offset?: number;
    } = {}): Promise<PlatformTaskProjection[]> {
      const params = new URLSearchParams({
        view: options.view ?? "timeline",
        limit: String(options.limit ?? 100),
        offset: String(options.offset ?? 0),
      });
      if (options.companyId) params.set("company_id", options.companyId);
      if (options.status) params.set("status", options.status);
      if (options.taskType) params.set("task_type", options.taskType);
      if (options.updatedFrom) params.set("updated_from", options.updatedFrom);
      if (options.updatedTo) params.set("updated_to", options.updatedTo);
      const values = unwrapData(
        await client.get(`/platform/tasks?${params.toString()}`),
        "平台任务",
      );
      if (!Array.isArray(values)) invalid("平台任务");
      return values.map(taskProjection);
    },

    async listAudit(): Promise<PlatformAuditProjection[]> {
      const values = unwrapData(
        await client.get("/platform/audit?limit=100&offset=0"),
        "平台审计",
      );
      if (!Array.isArray(values)) invalid("平台审计");
      return values.map(auditProjection);
    },

    async getServiceHealth(): Promise<PlatformServiceHealth[]> {
      const values = unwrapData(
        await client.get("/platform/health"),
        "平台服务健康",
      );
      if (!Array.isArray(values)) invalid("平台服务健康");
      return values.map(serviceHealth);
    },

    async createEnterprise(
      input: CreatePlatformEnterpriseInput,
    ): Promise<CreatedPlatformEnterprise> {
      const legalName = input.legalName ?? input.companyName ?? input.tenantName ?? "";
      const subjectType = input.subjectType ?? (input.socialCreditCode ? "domestic_enterprise" : "pending_registration");
      const payload = await client.post("/platform/enterprises", {
        legal_name: legalName.trim(),
        short_name: input.shortName?.trim() || null,
        subject_type: subjectType,
        social_credit_code: input.socialCreditCode?.trim() || null,
        industry: input.industry?.trim() || null,
        admin_account: input.adminAccount.trim(),
        admin_display_name: input.adminDisplayName.trim(),
        default_plan_code: input.defaultPlanCode ?? "starter",
      });
      return createdEnterprise(unwrapData(payload, "新建企业"));
    },

    async startOnboarding(
      input: StartPlatformOnboardingInput,
    ): Promise<PlatformOnboardingSession> {
      const legalName = input.legalName ?? input.tenantName ?? input.tenantSlug ?? "";
      const subjectType = input.subjectType ?? (input.socialCreditCode ? "domestic_enterprise" : "pending_registration");
      const payload = await client.post("/platform/onboarding", {
        display_name: input.displayName?.trim() || null,
        legal_name: legalName.trim(),
        short_name: input.shortName?.trim() || null,
        subject_type: subjectType,
        social_credit_code: input.socialCreditCode?.trim() || null,
        industry: input.industry?.trim() || null,
        admin_account: input.adminAccount.trim(),
        admin_display_name: input.adminDisplayName.trim(),
      });
      return onboardingSession(unwrapData(payload, "资料辅助建企会话"));
    },

    async listOnboarding(
      options: { limit?: number; offset?: number } = {},
    ): Promise<PlatformOnboardingSession[]> {
      const params = new URLSearchParams({
        limit: String(options.limit ?? 20),
        offset: String(options.offset ?? 0),
      });
      const values = unwrapData(
        await client.get(`/platform/onboarding?${params.toString()}`),
        "资料辅助建企任务列表",
      );
      if (!Array.isArray(values)) invalid("资料辅助建企任务列表");
      return values.map(onboardingSession);
    },

    async getOnboarding(sessionId: string): Promise<PlatformOnboardingSession> {
      const payload = await client.get(
        `/platform/onboarding/${encodeURIComponent(sessionId)}`,
      );
      return onboardingSession(unwrapData(payload, "资料辅助建企会话"));
    },

    async renameOnboarding(
      sessionId: string,
      input: RenamePlatformOnboardingInput,
    ): Promise<PlatformOnboardingSession> {
      const payload = await client.patch(
        `/platform/onboarding/${encodeURIComponent(sessionId)}`,
        {
          expected_version: input.expectedVersion,
          display_name: input.displayName.trim(),
        },
      );
      return onboardingSession(unwrapData(payload, "资料辅助建企会话"));
    },

    async getOnboardingImports(
      sessionId: string,
    ): Promise<PlatformOnboardingImportStatus> {
      const payload = await client.get(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/imports`,
      );
      return onboardingImportStatus(
        unwrapData(payload, "资料辅助建企导入进度"),
      );
    },

    async uploadOnboardingDocuments(
      sessionId: string,
      files: File[],
    ): Promise<PlatformOnboardingSession> {
      const form = new FormData();
      for (const file of files) form.append("files", file);
      const payload = await client.postForm(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/imports`,
        form,
      );
      return onboardingSession(unwrapData(payload, "资料辅助建企会话"));
    },

    async retryOnboardingImportItem(
      sessionId: string,
      item: PlatformOnboardingImportStatus["items"][number],
    ): Promise<PlatformOnboardingImportStatus> {
      if (!item.batchId || !item.batchVersion) {
        throw new ApiError("资料任务缺少批次信息，请刷新后重试。", {
          code: "INVALID_IMPORT_RETRY_STATE",
        });
      }
      const payload = await client.post(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/imports/${encodeURIComponent(item.batchId)}/items/${encodeURIComponent(item.id)}:retry`,
        { expected_batch_version: item.batchVersion },
      );
      return onboardingImportStatus(
        unwrapData(payload, "资料辅助建企导入进度"),
      );
    },

    async clearOnboardingImportItemPayload(
      sessionId: string,
      item: PlatformOnboardingImportStatus["items"][number],
    ): Promise<PlatformOnboardingImportStatus> {
      if (!item.batchId || !item.batchVersion) {
        throw new ApiError("资料任务缺少批次信息，请刷新后重试。", { code: "INVALID_IMPORT_CLEAR_STATE" });
      }
      const payload = await client.post(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/imports/${encodeURIComponent(item.batchId)}/items/${encodeURIComponent(item.id)}:clear`,
        { expected_batch_version: item.batchVersion },
      );
      return onboardingImportStatus(unwrapData(payload, "资料辅助建企导入进度"));
    },

    async generateOnboardingSuggestions(
      sessionId: string,
      expectedVersion: number,
    ): Promise<PlatformOnboardingSession> {
      const payload = await client.post(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/suggestions`,
        { expected_version: expectedVersion },
      );
      return onboardingSession(unwrapData(payload, "资料辅助建企会话"));
    },

    async synthesizeOnboardingSources(
      sessionId: string,
      expectedVersion: number,
    ): Promise<PlatformOnboardingSession> {
      const payload = await client.post(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/synthesis`,
        { expected_version: expectedVersion },
      );
      return onboardingSession(unwrapData(payload, "资料综合归纳"));
    },

    async updateOnboardingCandidate(
      sessionId: string,
      candidate: PlatformOnboardingCandidate,
    ): Promise<PlatformOnboardingCandidate> {
      const payload = await client.put(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/candidates/${encodeURIComponent(candidate.id)}`,
        {
          expected_version: candidate.version,
          category: candidate.category,
          payload: candidate.payload,
        },
      );
      return onboardingCandidate(unwrapData(payload, "资料辅助建企候选"));
    },

    async ignoreOnboardingCandidate(
      sessionId: string,
      candidate: PlatformOnboardingCandidate,
    ): Promise<PlatformOnboardingCandidate> {
      const payload = await client.post(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/candidates/${encodeURIComponent(candidate.id)}/ignore`,
        { expected_version: candidate.version, apply_fields: [] },
      );
      return onboardingCandidate(unwrapData(payload, "资料辅助建企候选"));
    },

    async acceptOnboardingCandidate(
      sessionId: string,
      candidate: PlatformOnboardingCandidate,
    ): Promise<PlatformOnboardingCandidate> {
      const applyFields = candidate.category === "enterprise_profile"
        ? Object.entries(candidate.payload)
            .filter(([, value]) => value.trim().length > 0)
            .map(([field]) => field)
        : [];
      const payload = await client.post(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/candidates/${encodeURIComponent(candidate.id)}/accept`,
        {
          expected_version: candidate.version,
          apply_fields: applyFields,
          confirm_sensitive_fields: true,
        },
      );
      return onboardingCandidate(unwrapData(payload, "资料辅助建企候选"));
    },

    async confirmOnboarding(
      sessionId: string,
      input: ConfirmPlatformOnboardingInput,
    ): Promise<PlatformOnboardingSession> {
      const legalName = input.legalName ?? input.companyName ?? input.tenantName ?? "";
      const subjectType = input.subjectType ?? (input.socialCreditCode ? "domestic_enterprise" : "pending_registration");
      const payload = await client.post(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/confirm`,
        {
          expected_version: input.expectedVersion,
          legal_name: legalName.trim(),
          short_name: input.shortName?.trim() || null,
          subject_type: subjectType,
          social_credit_code: input.socialCreditCode?.trim() || null,
          industry: input.industry?.trim() || null,
          summary: input.summary?.trim() || null,
          website: input.website?.trim() || null,
          candidate_selections: input.candidateSelections.map((selection) => ({
            id: selection.id,
            expected_version: selection.expectedVersion,
            apply_fields: selection.applyFields,
          })),
        },
      );
      return onboardingSession(unwrapData(payload, "资料辅助建企会话"));
    },

    async regenerateOnboardingTemporaryCredential(
      sessionId: string,
      expectedVersion: number,
    ): Promise<PlatformOnboardingSession> {
      const payload = await client.post(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/temporary-credential:regenerate`,
        { expected_version: expectedVersion },
      );
      return onboardingSession(unwrapData(payload, "一次性企业管理员凭证"));
    },

    async cancelOnboarding(
      sessionId: string,
      reason: string,
      expectedVersion: number,
    ): Promise<PlatformOnboardingSession> {
      const payload = await client.post(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/cancel`,
        { expected_version: expectedVersion, reason: reason.trim() },
      );
      return onboardingSession(unwrapData(payload, "资料辅助建企会话"));
    },

    async listLlmProfiles(): Promise<PlatformLlmProfile[]> {
      const values = unwrapData(
        await client.get("/platform/settings/llm/profiles"),
        "LLM 配置列表",
      );
      if (!Array.isArray(values)) invalid("LLM 配置列表");
      return values.map(llmProfile);
    },

    async createLlmProfile(
      input: CreatePlatformLlmProfileInput,
    ): Promise<PlatformLlmProfile> {
      const payload = await client.post(
        "/platform/settings/llm/profiles",
        llmProfilePayload(input),
      );
      return llmProfile(unwrapData(payload, "LLM 配置"));
    },

    async updateLlmProfile(
      profileId: string,
      input: UpdatePlatformLlmProfileInput,
    ): Promise<PlatformLlmProfile> {
      const payload = await client.put(
        `/platform/settings/llm/profiles/${encodeURIComponent(profileId)}`,
        {
          ...llmProfilePayload(input),
          expected_version: input.expectedVersion,
        },
      );
      return llmProfile(unwrapData(payload, "LLM 配置"));
    },

    async testLlmProfile(
      profileId: string,
      apiKey?: string,
    ): Promise<PlatformLlmConnectionTest> {
      const payload = await client.post(
        `/platform/settings/llm/profiles/${encodeURIComponent(profileId)}/test`,
        apiKey?.trim() ? { api_key: apiKey.trim() } : {},
      );
      return llmConnectionTest(unwrapData(payload, "LLM 连接测试"));
    },

    async activateLlmProfile(
      profileId: string,
      input: ActivatePlatformLlmProfileInput,
    ): Promise<PlatformLlmProfile> {
      const payload = await client.post(
        `/platform/settings/llm/profiles/${encodeURIComponent(profileId)}/activate`,
        {
          expected_version: input.expectedVersion,
          expected_active_profile_id: input.expectedActiveProfileId ?? null,
        },
      );
      return llmProfile(unwrapData(payload, "LLM 主配置"));
    },
  };
}

export const platformApi = createPlatformApi(apiClient);

import { apiClient, ApiClient, ApiError } from "./client";
import type {
  ActivatePlatformLlmProfileInput,
  CreatePlatformLlmProfileInput,
  CreatePlatformEnterpriseInput,
  CreatedPlatformEnterprise,
  PlatformCardProjection,
  PlatformAuditProjection,
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
  return {
    tenantId: requiredString(value.tenant_id, "tenant_id"),
    tenantSlug: requiredString(value.tenant_slug, "tenant_slug"),
    tenantName: requiredString(value.tenant_name, "tenant_name"),
    companyId: requiredString(value.company_id, "company_id"),
    companyName: requiredString(value.company_name, "company_name"),
    status: requiredString(value.status ?? value.company_status, "status"),
    createdAt: requiredString(value.created_at, "created_at"),
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

function createdEnterprise(value: unknown): CreatedPlatformEnterprise {
  if (!isRecord(value)) invalid("新建企业");
  return {
    ...enterprise(value),
    adminUserId: requiredString(value.admin_user_id, "admin_user_id"),
    adminMembershipId: requiredString(
      value.admin_membership_id,
      "admin_membership_id",
    ),
    initialCardId: requiredString(value.initial_card_id, "initial_card_id"),
    initialCardSlug: requiredString(value.initial_card_slug, "initial_card_slug"),
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
    status: oneOf(value.status, onboardingStatuses, "status"),
    tenantSlug: requiredString(value.tenant_slug, "tenant_slug"),
    tenantName: optionalString(value.tenant_name, "tenant_name"),
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
      return batch.items.map((item) => {
        if (!isRecord(item)) invalid("资料辅助建企导入文件");
        return {
          id: requiredString(item.id, "onboarding_import_item.id"),
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
      leads30d: nonNegativeInteger(value.leads_30d, "leads_30d"),
      cards: cards.map(cardProjection),
      businessProfile: Array.isArray(businessProfile)
        ? businessProfile.map(onboardingSuggestion)
        : [],
      updatedAt: requiredString(value.updated_at, "updated_at"),
  };
}

function platformOverview(value: unknown): PlatformOverview {
  if (!isRecord(value)) invalid("平台总览");
  return {
    generatedAt: requiredString(value.generated_at, "generated_at"),
    enterpriseCount: nonNegativeInteger(value.enterprise_count, "enterprise_count"),
    activeEnterpriseCount: nonNegativeInteger(
      value.active_enterprise_count,
      "active_enterprise_count",
    ),
    onboardingCount: nonNegativeInteger(value.onboarding_count, "onboarding_count"),
    publishedCardCount: nonNegativeInteger(
      value.published_card_count,
      "published_card_count",
    ),
    visits30d: nonNegativeInteger(value.visits_30d, "visits_30d"),
    conversations30d: nonNegativeInteger(
      value.conversations_30d,
      "conversations_30d",
    ),
    leads30d: nonNegativeInteger(value.leads_30d, "leads_30d"),
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
    employeeCount: nonNegativeInteger(value.employee_count, "employee_count"),
    visits30d: nonNegativeInteger(value.visits_30d, "visits_30d"),
    uniqueVisitors30d: nonNegativeInteger(
      value.unique_visitors_30d,
      "unique_visitors_30d",
    ),
    lastVisitAt: optionalString(value.last_visit_at, "last_visit_at"),
  };
}

function taskProjection(value: unknown): PlatformTaskProjection {
  if (!isRecord(value)) invalid("平台任务");
  return {
    id: requiredString(value.id, "task.id"),
    taskType: requiredString(value.task_type, "task.task_type"),
    businessLabel: requiredString(value.business_label, "task.business_label"),
    status: requiredString(value.status, "task.status"),
    companyId: optionalString(value.company_id, "task.company_id"),
    companyName: optionalString(value.company_name, "task.company_name"),
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
      const payload = await client.get(`/platform/enterprises?${params.toString()}`);
      const values = unwrapData(payload, "企业列表");
      if (!Array.isArray(values)) invalid("企业列表");
      return values.map(enterprise);
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

    async listCompanyAggregates(): Promise<PlatformCompanyAggregate[]> {
      const values = unwrapData(
        await client.get("/platform/company-aggregates?limit=100&offset=0"),
        "企业员工访客聚合",
      );
      if (!Array.isArray(values)) invalid("企业员工访客聚合");
      return values.map(companyAggregate);
    },

    async listTasks(): Promise<PlatformTaskProjection[]> {
      const values = unwrapData(
        await client.get("/platform/tasks?limit=100&offset=0"),
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
      const payload = await client.post("/platform/enterprises", {
        tenant_slug: input.tenantSlug.trim(),
        tenant_name: input.tenantName.trim(),
        company_name: input.companyName.trim(),
        industry: input.industry?.trim() || null,
        admin_account: input.adminAccount.trim(),
        admin_display_name: input.adminDisplayName.trim(),
        admin_password: input.adminPassword,
        initial_card_title: input.initialCardTitle?.trim() || null,
      });
      return createdEnterprise(unwrapData(payload, "新建企业"));
    },

    async startOnboarding(
      input: StartPlatformOnboardingInput,
    ): Promise<PlatformOnboardingSession> {
      const payload = await client.post("/platform/onboarding", {
        tenant_slug: input.tenantSlug.trim(),
        tenant_name: input.tenantName?.trim() || null,
        admin_account: input.adminAccount.trim(),
        admin_display_name: input.adminDisplayName.trim(),
      });
      return onboardingSession(unwrapData(payload, "资料辅助建企会话"));
    },

    async getOnboarding(sessionId: string): Promise<PlatformOnboardingSession> {
      const payload = await client.get(
        `/platform/onboarding/${encodeURIComponent(sessionId)}`,
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

    async confirmOnboarding(
      sessionId: string,
      input: ConfirmPlatformOnboardingInput,
    ): Promise<PlatformOnboardingSession> {
      const payload = await client.post(
        `/platform/onboarding/${encodeURIComponent(sessionId)}/confirm`,
        {
          expected_version: input.expectedVersion,
          tenant_name: input.tenantName.trim(),
          company_name: input.companyName.trim(),
          industry: input.industry?.trim() || null,
          summary: input.summary?.trim() || null,
          website: input.website?.trim() || null,
          initial_card_display_name: input.initialCardDisplayName.trim(),
          initial_card_title: input.initialCardTitle?.trim() || null,
          assistant_name: input.assistantName?.trim() || null,
          welcome_message: input.welcomeMessage?.trim() || null,
        },
      );
      return onboardingSession(unwrapData(payload, "资料辅助建企会话"));
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

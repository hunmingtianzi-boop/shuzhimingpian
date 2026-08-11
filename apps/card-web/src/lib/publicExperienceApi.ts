import {
  AssistantApiError,
  clearAssistantSession,
  createAssistantIdempotencyKey,
  ensurePublicVisitorSession,
  getPublicApiBaseUrl,
  type PublicPolicyVersions,
  type VisitorSession,
} from "./assistantApi";
import {
  canPersistProfileLink,
  clearProfileLinkToken,
  clearProfileRevokePending,
  markProfileRevokePending,
  writeProfileLinkToken,
} from "./profileLink";

type JsonRecord = Record<string, unknown>;

export type PublicProduct = {
  slug: string;
  name: string;
  category?: string;
  summary: string;
  detail: string;
  audience?: string;
  priceBoundary?: string;
  imageUrl?: string;
  sortOrder: number;
  publishedAt: string;
};

export type PublicCaseStudy = {
  slug: string;
  title: string;
  industry?: string;
  background: string;
  solution: string;
  result: string;
  clientDisplayName?: string;
  imageUrl?: string;
  sortOrder: number;
  publishedAt: string;
};

export type PublicCatalog = {
  products: PublicProduct[];
  cases: PublicCaseStudy[];
};

export type PublicRecommendation = {
  resourceType: "product" | "case_study" | "knowledge_document";
  resourceId: string;
  title: string;
  summary: string;
  url: string;
  reason: string;
  evidence: {
    sourceType: "product" | "case_study" | "knowledge_document";
    sourceId: string;
    sourceVersion?: number;
    title: string;
    excerpt: string;
  };
};

export type PublicLeadInput = {
  conversationId?: string;
  name: string;
  mobile?: string;
  email?: string;
  wechat?: string;
  companyName?: string;
  demand: string;
  interestTags?: string[];
};

export type PublicLeadResult = {
  id: string;
  status: string;
  createdAt: string;
};

export type PrivacyRequestType =
  | "access"
  | "correction"
  | "deletion"
  | "withdraw_consent";

export type PrivacyRequestInput = {
  requestType: PrivacyRequestType;
  note?: string;
  consentScope?: "chat_notice" | "lead_contact" | "profile_personalization";
};

export type PrivacyRequestResult = {
  id: string;
  status: string;
  requestType: string;
  createdAt: string;
};

export type ProfilePersonalizationConsentResult = {
  granted: boolean;
  recordedAt: string;
};

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, label: string): JsonRecord {
  if (!isRecord(value)) {
    throw new AssistantApiError(`公开服务返回了无效的${label}。`, {
      code: "INVALID_API_RESPONSE",
      retryable: true,
    });
  }
  return value;
}

function requireString(value: unknown, label: string) {
  if (typeof value !== "string" || !value.trim()) {
    throw new AssistantApiError(`公开服务响应缺少${label}。`, {
      code: "INVALID_API_RESPONSE",
      retryable: true,
    });
  }
  return value.trim();
}

function optionalString(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function requireNumber(value: unknown, label: string) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new AssistantApiError(`公开服务响应缺少${label}。`, {
      code: "INVALID_API_RESPONSE",
      retryable: true,
    });
  }
  return value;
}

function isAbortError(error: unknown) {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : isRecord(error) && error.name === "AbortError";
}

async function responseError(response: Response) {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }

  const envelope = isRecord(payload) && isRecord(payload.error) ? payload.error : undefined;
  const code =
    typeof envelope?.code === "string" ? envelope.code : `HTTP_${response.status}`;
  const message =
    typeof envelope?.message === "string"
      ? envelope.message
      : `公开服务请求失败（${response.status}）。`;
  const requestId =
    typeof envelope?.request_id === "string"
      ? envelope.request_id
      : response.headers.get("X-Request-Id") ?? undefined;
  const retryAfterHeader = response.headers.get("Retry-After");
  const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : undefined;

  return new AssistantApiError(message, {
    code,
    status: response.status,
    retryable:
      response.status === 401 ||
      response.status === 403 ||
      response.status === 408 ||
      response.status === 429 ||
      response.status >= 500 ||
      code === "IDEMPOTENCY_IN_PROGRESS" ||
      code === "POLICY_VERSION_MISMATCH",
    requestId,
    retryAfterSeconds:
      retryAfter !== undefined && Number.isFinite(retryAfter) ? retryAfter : undefined,
  });
}

async function publicRequestJson(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<unknown> {
  const baseUrl = getPublicApiBaseUrl();
  if (!baseUrl) {
    throw new AssistantApiError("公开服务 API 尚未配置。", {
      code: "API_NOT_CONFIGURED",
    });
  }

  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, { ...init, signal });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new AssistantApiError("无法连接公开服务，请检查网络后重试。", {
      code: "NETWORK_ERROR",
      retryable: true,
    });
  }
  if (!response.ok) throw await responseError(response);

  try {
    return await response.json();
  } catch {
    throw new AssistantApiError("公开服务返回了无法解析的响应。", {
      code: "INVALID_API_RESPONSE",
      retryable: true,
    });
  }
}

function jsonHeaders(token?: string, idempotencyKey?: string) {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
  return headers;
}

function parseProduct(value: unknown): PublicProduct {
  const record = requireRecord(value, "产品数据");
  return {
    slug: requireString(record.slug, "产品标识"),
    name: requireString(record.name, "产品名称"),
    category: optionalString(record.category),
    summary: requireString(record.summary, "产品摘要"),
    detail: requireString(record.detail, "产品详情"),
    audience: optionalString(record.audience),
    priceBoundary: optionalString(record.price_boundary),
    imageUrl: optionalString(record.image_url),
    sortOrder: requireNumber(record.sort_order, "产品排序"),
    publishedAt: requireString(record.published_at, "产品发布时间"),
  };
}

function parseCaseStudy(value: unknown): PublicCaseStudy {
  const record = requireRecord(value, "案例数据");
  return {
    slug: requireString(record.slug, "案例标识"),
    title: requireString(record.title, "案例标题"),
    industry: optionalString(record.industry),
    background: requireString(record.background, "案例背景"),
    solution: requireString(record.solution, "案例方案"),
    result: requireString(record.result, "案例结果"),
    clientDisplayName: optionalString(record.client_display_name),
    imageUrl: optionalString(record.image_url),
    sortOrder: requireNumber(record.sort_order, "案例排序"),
    publishedAt: requireString(record.published_at, "案例发布时间"),
  };
}

function recommendationResourceType(value: unknown, label: string): PublicRecommendation["resourceType"] {
  if (value === "product" || value === "case_study" || value === "knowledge_document") return value;
  throw new AssistantApiError(`公开服务响应包含无效${label}。`, {
    code: "INVALID_API_RESPONSE",
    retryable: true,
  });
}

function parseRecommendation(value: unknown): PublicRecommendation {
  const record = requireRecord(value, "推荐内容");
  const evidence = requireRecord(record.evidence, "推荐依据");
  const version = evidence.source_version ?? evidence.sourceVersion;
  return {
    resourceType: recommendationResourceType(record.resource_type ?? record.resourceType, "推荐类型"),
    resourceId: requireString(record.resource_id ?? record.resourceId, "推荐资源"),
    title: requireString(record.title, "推荐标题"),
    summary: requireString(record.summary, "推荐摘要"),
    url: requireString(record.url, "推荐链接"),
    reason: requireString(record.reason, "推荐理由"),
    evidence: {
      sourceType: recommendationResourceType(evidence.source_type ?? evidence.sourceType, "依据类型"),
      sourceId: requireString(evidence.source_id ?? evidence.sourceId, "依据资源"),
      sourceVersion: typeof version === "number" && Number.isFinite(version) ? version : undefined,
      title: requireString(evidence.title, "依据标题"),
      excerpt: requireString(evidence.excerpt, "依据摘要"),
    },
  };
}

function parseList<T>(value: unknown, parser: (item: unknown) => T, label: string) {
  const envelope = requireRecord(value, `${label}列表`);
  if (!Array.isArray(envelope.data)) {
    throw new AssistantApiError(`公开服务响应缺少${label}列表。`, {
      code: "INVALID_API_RESPONSE",
      retryable: true,
    });
  }
  return envelope.data.map(parser);
}

export function createPublicIdempotencyKey() {
  return createAssistantIdempotencyKey();
}

export function isPublicExperienceConfigured() {
  return getPublicApiBaseUrl().length > 0;
}

export async function fetchPublicCatalog(
  cardSlug: string,
  signal?: AbortSignal,
): Promise<PublicCatalog> {
  const slug = encodeURIComponent(cardSlug.trim());
  const [productsEnvelope, casesEnvelope] = await Promise.all([
    publicRequestJson(
      `/public/cards/${slug}/products?limit=50&offset=0`,
      { method: "GET", headers: { Accept: "application/json" } },
      signal,
    ),
    publicRequestJson(
      `/public/cards/${slug}/case-studies?limit=50&offset=0`,
      { method: "GET", headers: { Accept: "application/json" } },
      signal,
    ),
  ]);
  return {
    products: parseList(productsEnvelope, parseProduct, "产品"),
    cases: parseList(casesEnvelope, parseCaseStudy, "案例"),
  };
}

export async function fetchPublicRecommendations(
  cardSlug: string,
  signal?: AbortSignal,
): Promise<PublicRecommendation[]> {
  const envelope = await publicRequestJson(
    `/public/cards/${encodeURIComponent(cardSlug.trim())}/recommendations?limit=4`,
    { method: "GET", headers: { Accept: "application/json" } },
    signal,
  );
  return parseList(envelope, parseRecommendation, "推荐内容");
}

export async function fetchPublicProduct(
  cardSlug: string,
  productSlug: string,
  signal?: AbortSignal,
) {
  const envelope = requireRecord(
    await publicRequestJson(
      `/public/cards/${encodeURIComponent(cardSlug.trim())}/products/${encodeURIComponent(
        productSlug,
      )}`,
      { method: "GET", headers: { Accept: "application/json" } },
      signal,
    ),
    "产品详情",
  );
  return parseProduct(envelope.data);
}

export async function fetchPublicCaseStudy(
  cardSlug: string,
  caseSlug: string,
  signal?: AbortSignal,
) {
  const envelope = requireRecord(
    await publicRequestJson(
      `/public/cards/${encodeURIComponent(
        cardSlug.trim(),
      )}/case-studies/${encodeURIComponent(caseSlug)}`,
      { method: "GET", headers: { Accept: "application/json" } },
      signal,
    ),
    "案例详情",
  );
  return parseCaseStudy(envelope.data);
}

async function withCurrentVisitor<T>(
  cardSlug: string,
  policyVersions: PublicPolicyVersions,
  signal: AbortSignal | undefined,
  operation: (session: VisitorSession, recovered: boolean) => Promise<T>,
  companyId?: string,
) {
  let session = await ensurePublicVisitorSession({
    cardSlug,
    policyVersions,
    companyId,
    signal,
  });
  try {
    return await operation(session, false);
  } catch (error) {
    if (!(error instanceof AssistantApiError) || error.status !== 401) throw error;
    clearAssistantSession(cardSlug);
    session = await ensurePublicVisitorSession({
      cardSlug,
      policyVersions,
      companyId,
      signal,
    });
    return operation(session, true);
  }
}

export async function submitPublicLead({
  cardSlug,
  policyVersions,
  input,
  consentIdempotencyKey,
  leadIdempotencyKey,
  signal,
}: {
  cardSlug: string;
  policyVersions: PublicPolicyVersions;
  input: PublicLeadInput;
  consentIdempotencyKey: string;
  leadIdempotencyKey: string;
  signal?: AbortSignal;
}): Promise<PublicLeadResult> {
  return withCurrentVisitor(cardSlug, policyVersions, signal, async (session, recovered) => {
    const slug = encodeURIComponent(cardSlug.trim());
    await publicRequestJson(
      `/public/cards/${slug}/consents`,
      {
        method: "POST",
        headers: jsonHeaders(session.token, consentIdempotencyKey),
        body: JSON.stringify({
          scope: "lead_contact",
          policy_version: policyVersions.leadConsent,
          granted: true,
        }),
      },
      signal,
    );

    const envelope = requireRecord(
      await publicRequestJson(
        `/public/cards/${slug}/leads`,
        {
          method: "POST",
          headers: jsonHeaders(session.token, leadIdempotencyKey),
          body: JSON.stringify({
            conversation_id: recovered ? undefined : input.conversationId,
            name: input.name.trim(),
            mobile: input.mobile?.trim() || undefined,
            email: input.email?.trim() || undefined,
            wechat: input.wechat?.trim() || undefined,
            company_name: input.companyName?.trim() || undefined,
            demand: input.demand.trim(),
            interest_tags: input.interestTags ?? [],
            consent_policy_version: policyVersions.leadConsent,
            consent_granted: true,
          }),
        },
        signal,
      ),
      "留资结果",
    );
    const data = requireRecord(envelope.data, "留资数据");
    return {
      id: requireString(data.id, "线索编号"),
      status: requireString(data.status, "线索状态"),
      createdAt: requireString(data.created_at, "提交时间"),
    };
  });
}

export async function submitPrivacyRequest({
  cardSlug,
  policyVersions,
  input,
  idempotencyKey,
  signal,
}: {
  cardSlug: string;
  policyVersions: PublicPolicyVersions;
  input: PrivacyRequestInput;
  idempotencyKey: string;
  signal?: AbortSignal;
}): Promise<PrivacyRequestResult> {
  return withCurrentVisitor(cardSlug, policyVersions, signal, async (session) => {
    const envelope = requireRecord(
      await publicRequestJson(
        "/public/privacy-requests",
        {
          method: "POST",
          headers: jsonHeaders(session.token, idempotencyKey),
          body: JSON.stringify({
            request_type: input.requestType,
            note: input.note?.trim() || undefined,
            consent_scope:
              input.requestType === "withdraw_consent" ? input.consentScope : undefined,
          }),
        },
        signal,
      ),
      "隐私请求结果",
    );
    const data = requireRecord(envelope.data, "隐私请求数据");
    return {
      id: requireString(data.id, "请求编号"),
      status: requireString(data.status, "请求状态"),
      requestType: requireString(data.request_type, "请求类型"),
      createdAt: requireString(data.created_at, "创建时间"),
    };
  });
}

export async function setProfilePersonalizationConsent({
  cardSlug,
  companyId,
  policyVersions,
  granted,
  idempotencyKey,
  signal,
}: {
  cardSlug: string;
  companyId: string;
  policyVersions: PublicPolicyVersions;
  granted: boolean;
  idempotencyKey: string;
  signal?: AbortSignal;
}): Promise<ProfilePersonalizationConsentResult> {
  if (granted && !canPersistProfileLink()) {
    throw new AssistantApiError(
      "浏览器当前无法保存长期授权，请允许本地存储后重试。",
      { code: "PROFILE_STORAGE_UNAVAILABLE", retryable: true },
    );
  }
  if (!granted) {
    clearProfileLinkToken(companyId);
    markProfileRevokePending(companyId);
  }

  try {
    return await withCurrentVisitor(cardSlug, policyVersions, signal, async (session) => {
    const slug = encodeURIComponent(cardSlug.trim());
    const consent = async (nextGranted: boolean, key: string) => {
      const envelope = requireRecord(
        await publicRequestJson(
          `/public/cards/${slug}/consents`,
          {
            method: "POST",
            headers: jsonHeaders(session.token, key),
            body: JSON.stringify({
              scope: "profile_personalization",
              policy_version: policyVersions.profilePersonalization,
              granted: nextGranted,
            }),
          },
          signal,
        ),
        "画像授权结果",
      );
      return requireRecord(envelope.data, "画像授权数据");
    };

    const data = await consent(granted, idempotencyKey);
    const responseGranted = data.granted === true;
    if (responseGranted !== granted) {
      throw new AssistantApiError("公开服务返回了无效的画像授权状态。", {
        code: "INVALID_API_RESPONSE",
        retryable: true,
      });
    }

    if (granted) {
      const profileLinkToken = requireString(data.profile_link_token, "长期画像令牌");
      if (!writeProfileLinkToken(companyId, profileLinkToken)) {
        clearProfileLinkToken(companyId);
        markProfileRevokePending(companyId);
        try {
          await consent(false, createPublicIdempotencyKey());
          clearProfileRevokePending(companyId);
        } catch {
          throw new AssistantApiError(
            "长期授权已在服务器开启，但本设备无法保存关联信息，且服务器暂未确认撤回。请重试完成撤回。",
            { code: "PROFILE_REVOKE_PENDING", retryable: true },
          );
        }
        throw new AssistantApiError(
          "浏览器未能保存长期授权，已停止在本设备记住兴趣。请调整浏览器设置后重试。",
          { code: "PROFILE_STORAGE_UNAVAILABLE", retryable: true },
        );
      }
    }

    clearProfileRevokePending(companyId);

    return {
      granted,
      recordedAt: requireString(data.recorded_at, "画像授权时间"),
    };
    }, companyId);
  } catch (error) {
    if (!granted) {
      markProfileRevokePending(companyId);
      if (error instanceof AssistantApiError && error.code === "PROFILE_REVOKE_PENDING") {
        throw error;
      }
      throw new AssistantApiError(
        "本设备上的长期关联已删除，但服务器暂未确认撤回。请重试完成撤回。",
        { code: "PROFILE_REVOKE_PENDING", retryable: true },
      );
    }
    throw error;
  }
}

export function safeContactHref(field: Record<string, string>) {
  const explicit = field.href?.trim();
  if (explicit) {
    if (/^(?:tel|mailto|sms):/i.test(explicit)) return explicit;
    try {
      const parsed = new URL(explicit);
      if (parsed.protocol === "https:" || parsed.protocol === "http:") return parsed.href;
    } catch {
      return undefined;
    }
    return undefined;
  }

  const value = field.value?.trim();
  if (!value) return undefined;
  const kind = `${field.kind || ""} ${field.type || ""} ${field.label || ""}`.toLowerCase();
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return `mailto:${value}`;
  if (/^\+?[\d\s()-]{5,40}$/.test(value)) {
    return `tel:${value.replace(/[^\d+]/g, "")}`;
  }
  if (/location|address|地址|地区/.test(kind)) {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(value)}`;
  }
  if (/website|site|官网|网站/.test(kind)) {
    try {
      const parsed = new URL(/^https?:\/\//i.test(value) ? value : `https://${value}`);
      return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : undefined;
    } catch {
      return undefined;
    }
  }
  return undefined;
}

export function canonicalShareUrl(location: Pick<Location, "origin" | "pathname">) {
  return `${location.origin}${location.pathname}`;
}

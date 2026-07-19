import {
  clearProfileLinkToken,
  readProfileLinkToken,
  writeProfileLinkToken,
} from "./profileLink";

export type AssistantCitation = {
  id: string;
  label: string;
  sourceType: string;
  url?: string;
};

export type AssistantStreamEvent =
  | { type: "started"; messageId: string; requestId: string }
  | { type: "delta"; text: string }
  | { type: "citation"; citation: AssistantCitation }
  | {
      type: "completed";
      messageId: string;
      finishReason: string;
      leadPrompt: boolean;
    }
  | { type: "error"; code: string; retryable: boolean; requestId?: string };

export type PublicPolicyVersions = {
  privacy: string;
  chatNotice: string;
  leadConsent: string;
  profilePersonalization: string;
};

export type VisitorSession = {
  token: string;
  expiresAt: string;
  privacyVersion: string;
  chatNoticeVersion: string;
  conversationId?: string;
};

type JsonRecord = Record<string, unknown>;

type StreamAssistantMessageOptions = {
  cardSlug: string;
  content: string;
  signal?: AbortSignal;
  idempotencyKey?: string;
  onEvent: (event: AssistantStreamEvent) => void;
};

const SESSION_PREFIX = "cf-card-assistant-session:";
const EXPIRY_SAFETY_WINDOW_MS = 30_000;

export class AssistantApiError extends Error {
  readonly code: string;
  readonly status?: number;
  readonly retryable: boolean;
  readonly requestId?: string;
  readonly retryAfterSeconds?: number;

  constructor(
    message: string,
    options: {
      code?: string;
      status?: number;
      retryable?: boolean;
      requestId?: string;
      retryAfterSeconds?: number;
    } = {},
  ) {
    super(message);
    this.name = "AssistantApiError";
    this.code = options.code ?? "ASSISTANT_API_ERROR";
    this.status = options.status;
    this.retryable = options.retryable ?? false;
    this.requestId = options.requestId;
    this.retryAfterSeconds = options.retryAfterSeconds;
  }
}

export function getPublicApiBaseUrl() {
  return (import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
}

export function isAssistantApiConfigured() {
  return getPublicApiBaseUrl().length > 0;
}

export function getAssistantSessionStorageKey(cardSlug: string) {
  return `${SESSION_PREFIX}${cardSlug}`;
}

export function createAssistantIdempotencyKey() {
  const cryptoApi = globalThis.crypto;
  if (typeof cryptoApi?.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }

  if (typeof cryptoApi?.getRandomValues !== "function") {
    throw new AssistantApiError("当前浏览器不支持安全的请求标识。", {
      code: "RANDOM_UUID_UNAVAILABLE",
    });
  }

  // randomUUID is restricted to secure contexts, while getRandomValues remains
  // a cryptographically secure Web Crypto primitive on legacy HTTP deployments.
  const bytes = cryptoApi.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0"));
  return [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10, 16).join(""),
  ].join("-");
}

function getSessionStorage() {
  try {
    return globalThis.sessionStorage;
  } catch {
    return undefined;
  }
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, label: string): JsonRecord {
  if (!isRecord(value)) {
    throw new AssistantApiError(`AI 服务返回了无效的 ${label}。`, {
      code: "INVALID_API_RESPONSE",
      retryable: true,
    });
  }
  return value;
}

function requireString(value: unknown, label: string) {
  if (typeof value !== "string" || value.length === 0) {
    throw new AssistantApiError(`AI 服务响应缺少 ${label}。`, {
      code: "INVALID_API_RESPONSE",
      retryable: true,
    });
  }
  return value;
}

function readSession(cardSlug: string): VisitorSession | undefined {
  const storage = getSessionStorage();
  if (!storage) return undefined;

  try {
    const raw = storage.getItem(getAssistantSessionStorageKey(cardSlug));
    if (!raw) return undefined;
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) throw new Error("Invalid session");

    const token = parsed.token;
    const expiresAt = parsed.expiresAt;
    const privacyVersion = parsed.privacyVersion;
    const chatNoticeVersion = parsed.chatNoticeVersion;
    const conversationId = parsed.conversationId;
    if (
      typeof token !== "string" ||
      typeof expiresAt !== "string" ||
      typeof privacyVersion !== "string" ||
      typeof chatNoticeVersion !== "string" ||
      (conversationId !== undefined && typeof conversationId !== "string")
    ) {
      throw new Error("Invalid session");
    }

    const expiry = Date.parse(expiresAt);
    if (!Number.isFinite(expiry) || expiry <= Date.now() + EXPIRY_SAFETY_WINDOW_MS) {
      clearAssistantSession(cardSlug);
      return undefined;
    }

    return { token, expiresAt, privacyVersion, chatNoticeVersion, conversationId };
  } catch {
    clearAssistantSession(cardSlug);
    return undefined;
  }
}

function writeSession(cardSlug: string, session: VisitorSession) {
  try {
    getSessionStorage()?.setItem(
      getAssistantSessionStorageKey(cardSlug),
      JSON.stringify(session),
    );
  } catch {
    // The chat remains usable when storage is unavailable; it just cannot resume.
  }
}

export function clearAssistantSession(cardSlug: string) {
  try {
    getSessionStorage()?.removeItem(getAssistantSessionStorageKey(cardSlug));
  } catch {
    // Ignore unavailable or blocked session storage.
  }
}

export function getActiveAssistantConversationId(cardSlug: string) {
  return readSession(cardSlug)?.conversationId;
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

  const envelope = isRecord(payload) ? payload.error : undefined;
  const apiError = isRecord(envelope) ? envelope : undefined;
  const code =
    typeof apiError?.code === "string" ? apiError.code : `HTTP_${response.status}`;
  const message =
    typeof apiError?.message === "string"
      ? apiError.message
      : `AI 服务请求失败（${response.status}）。`;
  const requestId =
    typeof apiError?.request_id === "string"
      ? apiError.request_id
      : response.headers.get("X-Request-Id") ?? undefined;
  const retryAfterHeader = response.headers.get("Retry-After");
  const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : undefined;

  return new AssistantApiError(message, {
    code,
    status: response.status,
    retryable:
      response.status === 401 ||
      response.status === 403 ||
      response.status === 429 ||
      (response.status === 409 && code === "POLICY_VERSION_MISMATCH") ||
      response.status >= 500,
    requestId,
    retryAfterSeconds:
      retryAfter !== undefined && Number.isFinite(retryAfter) ? retryAfter : undefined,
  });
}

async function request(url: string, init: RequestInit, signal?: AbortSignal) {
  try {
    return await fetch(url, { ...init, signal });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new AssistantApiError("无法连接 AI 服务，请检查网络后重试。", {
      code: "NETWORK_ERROR",
      retryable: true,
    });
  }
}

async function requestJson<T>(
  url: string,
  init: RequestInit,
  signal?: AbortSignal,
): Promise<T> {
  const response = await request(url, init, signal);
  if (!response.ok) throw await responseError(response);

  try {
    return (await response.json()) as T;
  } catch {
    throw new AssistantApiError("AI 服务返回了无法解析的响应。", {
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

async function getPublicCardContext(
  baseUrl: string,
  cardSlug: string,
  signal?: AbortSignal,
) {
  const envelope = await requestJson<unknown>(
    `${baseUrl}/public/cards/${encodeURIComponent(cardSlug)}`,
    { method: "GET", headers: { Accept: "application/json" } },
    signal,
  );
  const data = requireRecord(requireRecord(envelope, "card envelope").data, "card data");
  const versions = requireRecord(data.policy_versions, "policy versions");
  const company = requireRecord(data.company, "company");
  return {
    companyId: requireString(company.id, "company id"),
    policyVersions: {
      privacy: requireString(versions.privacy, "privacy policy version"),
      chatNotice: requireString(versions.chat_notice, "chat notice version"),
      leadConsent: requireString(versions.lead_consent, "lead consent version"),
      profilePersonalization: requireString(
        versions.profile_personalization,
        "profile personalization version",
      ),
    },
  };
}

async function createVisit(
  baseUrl: string,
  cardSlug: string,
  privacyVersion: string,
  companyId: string | undefined,
  signal?: AbortSignal,
) {
  const storedProfileLinkToken = companyId
    ? readProfileLinkToken(companyId)
    : undefined;
  const envelope = await requestJson<unknown>(
    `${baseUrl}/public/cards/${encodeURIComponent(cardSlug)}/visits`,
    {
      method: "POST",
      headers: jsonHeaders(undefined, createAssistantIdempotencyKey()),
      body: JSON.stringify({
        source: "card_web",
        privacy_notice_version: privacyVersion,
        profile_link_token: storedProfileLinkToken,
      }),
    },
    signal,
  );
  const data = requireRecord(requireRecord(envelope, "visit envelope").data, "visit data");
  const profileLinkToken =
    typeof data.profile_link_token === "string" && data.profile_link_token.trim()
      ? data.profile_link_token.trim()
      : undefined;
  if (
    companyId &&
    profileLinkToken &&
    !writeProfileLinkToken(companyId, profileLinkToken)
  ) {
    clearProfileLinkToken(companyId);
  }
  if (companyId && storedProfileLinkToken && !profileLinkToken) {
    clearProfileLinkToken(companyId);
  }
  return {
    token: requireString(data.visitor_session_token, "visitor session token"),
    expiresAt: requireString(data.expires_at, "visitor session expiry"),
  };
}

async function recordChatConsent(
  baseUrl: string,
  cardSlug: string,
  token: string,
  chatNoticeVersion: string,
  signal?: AbortSignal,
) {
  await requestJson<unknown>(
    `${baseUrl}/public/cards/${encodeURIComponent(cardSlug)}/consents`,
    {
      method: "POST",
      headers: jsonHeaders(token, createAssistantIdempotencyKey()),
      body: JSON.stringify({
        scope: "chat_notice",
        policy_version: chatNoticeVersion,
        granted: true,
      }),
    },
    signal,
  );
}

async function createConversation(
  baseUrl: string,
  cardSlug: string,
  token: string,
  chatNoticeVersion: string,
  signal?: AbortSignal,
) {
  const envelope = await requestJson<unknown>(
    `${baseUrl}/public/cards/${encodeURIComponent(cardSlug)}/conversations`,
    {
      method: "POST",
      headers: jsonHeaders(token, createAssistantIdempotencyKey()),
      body: JSON.stringify({ chat_notice_version: chatNoticeVersion }),
    },
    signal,
  );
  const data = requireRecord(
    requireRecord(envelope, "conversation envelope").data,
    "conversation data",
  );
  return requireString(data.id, "conversation id");
}

async function ensureAssistantSession(
  baseUrl: string,
  cardSlug: string,
  signal?: AbortSignal,
) {
  const saved = readSession(cardSlug);
  if (saved?.conversationId) return saved;

  let session = saved;
  if (!session) {
    const context = await getPublicCardContext(baseUrl, cardSlug, signal);
    const versions = context.policyVersions;
    const visit = await createVisit(
      baseUrl,
      cardSlug,
      versions.privacy,
      context.companyId,
      signal,
    );
    session = {
      ...visit,
      privacyVersion: versions.privacy,
      chatNoticeVersion: versions.chatNotice,
    };
    writeSession(cardSlug, session);
  }

  await recordChatConsent(
    baseUrl,
    cardSlug,
    session.token,
    session.chatNoticeVersion,
    signal,
  );
  const conversationId = await createConversation(
    baseUrl,
    cardSlug,
    session.token,
    session.chatNoticeVersion,
    signal,
  );
  const completedSession = { ...session, conversationId };
  writeSession(cardSlug, completedSession);
  return completedSession;
}

export async function ensurePublicVisitorSession({
  cardSlug,
  policyVersions,
  companyId,
  signal,
}: {
  cardSlug: string;
  policyVersions?: PublicPolicyVersions;
  companyId?: string;
  signal?: AbortSignal;
}): Promise<VisitorSession> {
  const baseUrl = getPublicApiBaseUrl();
  const normalizedSlug = cardSlug.trim();
  if (!baseUrl) {
    throw new AssistantApiError("公开服务 API 尚未配置。", {
      code: "API_NOT_CONFIGURED",
    });
  }
  if (!normalizedSlug) {
    throw new AssistantApiError("缺少名片标识。", { code: "INVALID_CARD_SLUG" });
  }

  const saved = readSession(normalizedSlug);
  if (saved) return saved;

  const context = policyVersions
    ? { policyVersions, companyId }
    : await getPublicCardContext(baseUrl, normalizedSlug, signal);
  const versions = policyVersions ?? context.policyVersions;
  const visit = await createVisit(
    baseUrl,
    normalizedSlug,
    versions.privacy,
    companyId ?? context.companyId,
    signal,
  );
  const session: VisitorSession = {
    ...visit,
    privacyVersion: versions.privacy,
    chatNoticeVersion: versions.chatNotice,
  };
  writeSession(normalizedSlug, session);
  return session;
}

function parseEventBlock(block: string) {
  let eventName = "";
  const dataLines: string[] = [];

  for (const rawLine of block.replace(/^\uFEFF/, "").split(/\r\n|\n|\r/)) {
    if (!rawLine || rawLine.startsWith(":")) continue;
    const separator = rawLine.indexOf(":");
    const field = separator === -1 ? rawLine : rawLine.slice(0, separator);
    let value = separator === -1 ? "" : rawLine.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") eventName = value;
    if (field === "data") dataLines.push(value);
  }

  return { eventName, data: dataLines.join("\n") };
}

function findEventBoundary(buffer: string) {
  const candidates = [
    { index: buffer.indexOf("\r\n\r\n"), length: 4 },
    { index: buffer.indexOf("\n\n"), length: 2 },
    { index: buffer.indexOf("\r\r"), length: 2 },
  ].filter((candidate) => candidate.index >= 0);
  candidates.sort((a, b) => a.index - b.index || b.length - a.length);
  return candidates[0];
}

function parseJsonEvent(eventName: string, rawData: string) {
  try {
    return requireRecord(JSON.parse(rawData), `${eventName} event`);
  } catch (error) {
    if (error instanceof AssistantApiError) throw error;
    throw new AssistantApiError("AI 消息流包含无效数据。", {
      code: "INVALID_SSE_EVENT",
      retryable: true,
    });
  }
}

function throwIfAborted(signal?: AbortSignal) {
  if (!signal?.aborted) return;
  throw signal.reason ?? new DOMException("The operation was aborted.", "AbortError");
}

export async function parseAssistantEventStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: AssistantStreamEvent) => void,
  signal?: AbortSignal,
) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;

  const dispatch = (block: string) => {
    const { eventName, data } = parseEventBlock(block);
    if (!eventName || !data || data === "[DONE]") return;
    if (
      eventName !== "message.started" &&
      eventName !== "message.delta" &&
      eventName !== "message.citation" &&
      eventName !== "message.completed" &&
      eventName !== "message.error"
    ) {
      return;
    }

    const payload = parseJsonEvent(eventName, data);
    switch (eventName) {
      case "message.started":
        onEvent({
          type: "started",
          messageId: requireString(payload.message_id, "message id"),
          requestId: requireString(payload.request_id, "request id"),
        });
        break;
      case "message.delta":
        if (typeof payload.text !== "string") {
          throw new AssistantApiError(
            "AI service returned an invalid message delta.",
            { code: "INVALID_API_RESPONSE", retryable: true },
          );
        }
        onEvent({ type: "delta", text: payload.text });
        break;
      case "message.citation": {
        const url =
          typeof payload.url === "string"
            ? payload.url
            : typeof payload.source_url === "string"
              ? payload.source_url
              : undefined;
        onEvent({
          type: "citation",
          citation: {
            id: requireString(payload.citation_id, "citation id"),
            label: requireString(payload.label, "citation label"),
            sourceType: requireString(payload.source_type, "citation source type"),
            url,
          },
        });
        break;
      }
      case "message.completed":
        completed = true;
        onEvent({
          type: "completed",
          messageId: requireString(payload.message_id, "message id"),
          finishReason: requireString(payload.finish_reason, "finish reason"),
          leadPrompt: payload.lead_prompt === true,
        });
        break;
      case "message.error": {
        const code = requireString(payload.code, "error code");
        const retryable = payload.retryable === true;
        const requestId =
          typeof payload.request_id === "string" ? payload.request_id : undefined;
        onEvent({ type: "error", code, retryable, requestId });
        throw new AssistantApiError(`AI 服务未完成本次回答（${code}）。`, {
          code,
          retryable,
          requestId,
        });
      }
    }
  };

  try {
    while (true) {
      throwIfAborted(signal);
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });

      let boundary = findEventBoundary(buffer);
      while (boundary) {
        const block = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary.length);
        dispatch(block);
        boundary = findEventBoundary(buffer);
      }

      if (done) break;
    }

    buffer += decoder.decode();
    if (buffer.trim()) dispatch(buffer);
    if (!completed) {
      throw new AssistantApiError("AI 消息流在完成前中断。", {
        code: "INCOMPLETE_SSE_STREAM",
        retryable: true,
      });
    }
  } catch (error) {
    await reader.cancel().catch(() => undefined);
    throw error;
  } finally {
    reader.releaseLock();
  }
}

export async function streamAssistantMessage({
  cardSlug,
  content,
  signal,
  idempotencyKey,
  onEvent,
}: StreamAssistantMessageOptions) {
  const baseUrl = getPublicApiBaseUrl();
  if (!baseUrl) {
    throw new AssistantApiError("AI API 尚未配置。", {
      code: "API_NOT_CONFIGURED",
    });
  }

  const normalizedSlug = cardSlug.trim();
  const normalizedContent = content.trim();
  if (!normalizedSlug) {
    throw new AssistantApiError("缺少名片标识。", { code: "INVALID_CARD_SLUG" });
  }
  if (!normalizedContent || normalizedContent.length > 2_000) {
    throw new AssistantApiError("问题长度应为 1–2000 个字符。", {
      code: "INVALID_MESSAGE_CONTENT",
    });
  }

  try {
    const session = await ensureAssistantSession(baseUrl, normalizedSlug, signal);
    const response = await request(
      `${baseUrl}/public/conversations/${encodeURIComponent(
        session.conversationId!,
      )}/messages:stream`,
      {
        method: "POST",
        headers: {
          ...jsonHeaders(
            session.token,
            idempotencyKey ?? createAssistantIdempotencyKey(),
          ),
          Accept: "text/event-stream",
        },
        body: JSON.stringify({ content: normalizedContent }),
      },
      signal,
    );

    if (!response.ok) throw await responseError(response);
    if (!response.body) {
      throw new AssistantApiError("AI 服务未返回消息流。", {
        code: "EMPTY_SSE_STREAM",
        retryable: true,
      });
    }

    await parseAssistantEventStream(response.body, onEvent, signal);
  } catch (error) {
    if (
      error instanceof AssistantApiError &&
      (error.status === 401 ||
        error.status === 403 ||
        error.status === 404 ||
        error.status === 410 ||
        (error.status === 409 && error.code === "POLICY_VERSION_MISMATCH"))
    ) {
      clearAssistantSession(normalizedSlug);
    }
    throw error;
  }
}

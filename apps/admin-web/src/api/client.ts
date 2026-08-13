type JsonRecord = Record<string, unknown>;

type ApiClientOptions = {
  baseUrl: string;
  fetcher?: typeof fetch;
  storage?: Storage;
};

type RequestOptions = {
  authenticated?: boolean;
  retryAfterRefresh?: boolean;
};

type VersionRequestOptions = {
  version?: number;
  idempotencyKey?: string;
};

type SessionTokens = {
  accessToken: string;
  csrfToken: string;
};

export const ADMIN_AUTH_EXPIRED_EVENT = "cf-admin-auth-expired";
export const ADMIN_CSRF_TOKEN_KEY = "cf-admin-csrf-token";
export const ADMIN_WECOM_RETURN_TO_KEY = "cf-admin-wecom-return-to";
export const ADMIN_WECOM_FLOW_KEY = "cf-admin-wecom-flow";

export class ApiError extends Error {
  readonly code: string;
  readonly status?: number;
  readonly requestId?: string;

  constructor(
    message: string,
    options: { code?: string; status?: number; requestId?: string } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.code = options.code ?? "ADMIN_API_ERROR";
    this.status = options.status;
    this.requestId = options.requestId;
  }
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function unwrapData(payload: unknown): unknown {
  if (isRecord(payload) && "data" in payload) return payload.data;
  return payload;
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ApiError(`接口响应缺少 ${field}。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value;
}

function readSessionTokens(payload: unknown): SessionTokens {
  const data = unwrapData(payload);
  if (!isRecord(data)) {
    throw new ApiError("认证接口返回了无法识别的数据。", {
      code: "INVALID_API_RESPONSE",
    });
  }

  return {
    accessToken: requiredString(
      data.access_token ?? data.accessToken,
      "access_token",
    ),
    csrfToken: requiredString(data.csrf_token ?? data.csrfToken, "csrf_token"),
  };
}

function defaultMessage(status: number): string {
  if (status === 401) return "登录状态已失效，请重新登录。";
  if (status === 403) return "当前账号没有执行此操作的权限。";
  if (status === 404) return "管理接口不存在，服务可能尚未接通。";
  if (status === 409) return "数据已被其他管理员更新，请刷新后重试。";
  if (status === 422) return "提交内容未通过服务端校验。";
  if (status === 429) return "请求过于频繁，请稍后重试。";
  if (status >= 500) return "管理服务暂时不可用，请稍后重试。";
  return `管理服务请求失败，状态码 ${status}。`;
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }

  const envelope = isRecord(payload) && isRecord(payload.error) ? payload.error : undefined;
  const detail = isRecord(payload) ? payload.detail : undefined;
  const message =
    (typeof envelope?.message === "string" && envelope.message) ||
    (typeof detail === "string" && detail) ||
    defaultMessage(response.status);
  const code =
    (typeof envelope?.code === "string" && envelope.code) ||
    `HTTP_${response.status}`;
  const requestId =
    (typeof envelope?.request_id === "string" && envelope.request_id) ||
    response.headers.get("X-Request-Id") ||
    undefined;

  return new ApiError(message, { code, status: response.status, requestId });
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, "");
}

export class ApiClient {
  private accessToken: string | null = null;
  private csrfToken: string | null = null;
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;
  private readonly injectedStorage?: Storage;
  private refreshPromise: Promise<void> | null = null;

  constructor({
    baseUrl,
    fetcher,
    storage,
  }: ApiClientOptions) {
    this.baseUrl = normalizeBaseUrl(baseUrl);
    this.fetcher = fetcher ?? globalThis.fetch.bind(globalThis);
    this.injectedStorage = storage;
  }

  isConfigured(): boolean {
    return this.baseUrl.length > 0;
  }

  clearSession(): void {
    this.accessToken = null;
    this.csrfToken = null;
    try {
      this.getStorage()?.removeItem(ADMIN_CSRF_TOKEN_KEY);
    } catch {
      // Storage may be disabled. In-memory session state is still cleared.
    }
  }

  private notifyAuthExpired(): void {
    if (typeof globalThis.dispatchEvent === "function") {
      globalThis.dispatchEvent(new Event(ADMIN_AUTH_EXPIRED_EVENT));
    }
  }

  async login(account: string, credential: string): Promise<void> {
    const payload = await this.execute(
      "/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ account, credential, method: "password" }),
      },
      { authenticated: false, retryAfterRefresh: false },
    );
    this.storeSessionTokens(readSessionTokens(payload));
  }

  async createWeComLoginUrl(returnTo = "/"): Promise<string> {
    const safeReturnTo = safeRelativePath(returnTo);
    const payload = await this.execute(
      `/auth/wecom/login-url?return_to=${encodeURIComponent(safeReturnTo)}`,
      { method: "GET" },
      { authenticated: false, retryAfterRefresh: false },
    );
    const data = unwrapData(payload);
    if (!isRecord(data)) {
      throw new ApiError("企业微信登录接口返回了无法识别的数据。", {
        code: "INVALID_API_RESPONSE",
      });
    }
    const authorizeUrl = requiredString(data.authorize_url, "authorize_url");
    try {
      this.getStorage()?.setItem(ADMIN_WECOM_RETURN_TO_KEY, safeReturnTo);
      this.getStorage()?.setItem(ADMIN_WECOM_FLOW_KEY, "login");
    } catch {
      // A failed storage write does not prevent OAuth; the callback falls back to root.
    }
    return authorizeUrl;
  }

  async createWeComBindingUrl(returnTo = "/"): Promise<string> {
    const safeReturnTo = safeRelativePath(returnTo);
    const payload = await this.get(
      `/auth/wecom/bind-url?return_to=${encodeURIComponent(safeReturnTo)}`,
    );
    const data = unwrapData(payload);
    if (!isRecord(data)) {
      throw new ApiError("企业微信绑定接口返回了无法识别的数据。", {
        code: "INVALID_API_RESPONSE",
      });
    }
    const authorizeUrl = requiredString(data.authorize_url, "authorize_url");
    try {
      this.getStorage()?.setItem(ADMIN_WECOM_RETURN_TO_KEY, safeReturnTo);
      this.getStorage()?.setItem(ADMIN_WECOM_FLOW_KEY, "bind");
    } catch {
      // OAuth can continue; the callback falls back to the current workspace.
    }
    return authorizeUrl;
  }

  async loginWithWeCom(code: string, state: string): Promise<void> {
    const payload = await this.execute(
      "/auth/wecom/login",
      {
        method: "POST",
        body: JSON.stringify({ code, state }),
      },
      { authenticated: false, retryAfterRefresh: false },
    );
    this.storeSessionTokens(readSessionTokens(payload));
  }

  async bindWithWeCom(code: string, state: string): Promise<void> {
    await this.post("/auth/wecom/bind", { code, state });
  }

  consumeWeComFlow(): "login" | "bind" {
    try {
      const value = this.getStorage()?.getItem(ADMIN_WECOM_FLOW_KEY);
      this.getStorage()?.removeItem(ADMIN_WECOM_FLOW_KEY);
      return value === "bind" ? "bind" : "login";
    } catch {
      return "login";
    }
  }

  consumeWeComReturnTo(): string {
    try {
      const value = this.getStorage()?.getItem(ADMIN_WECOM_RETURN_TO_KEY) ?? "/";
      this.getStorage()?.removeItem(ADMIN_WECOM_RETURN_TO_KEY);
      return safeRelativePath(value);
    } catch {
      return "/";
    }
  }

  async refreshSession(): Promise<void> {
    if (this.refreshPromise) return this.refreshPromise;

    this.refreshPromise = this.performRefresh().finally(() => {
      this.refreshPromise = null;
    });
    return this.refreshPromise;
  }

  async logout(): Promise<void> {
    try {
      const csrfToken = this.csrfToken ?? this.readStoredCsrfToken();
      if (this.baseUrl && this.accessToken && csrfToken) {
        const headers = new Headers({ "X-CSRF-Token": csrfToken });
        await this.execute(
          "/auth/logout",
          { method: "POST", headers },
          { authenticated: true, retryAfterRefresh: false },
        );
      }
    } finally {
      this.clearSession();
    }
  }

  async get(path: string): Promise<unknown> {
    return this.request(path, { method: "GET" });
  }

  async post(
    path: string,
    body?: unknown,
    options: VersionRequestOptions = {},
  ): Promise<unknown> {
    const headers = versionHeaders(options);
    return this.request(path, {
      method: "POST",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  async postForm(
    path: string,
    body: FormData,
    options: VersionRequestOptions = {},
  ): Promise<unknown> {
    return this.request(path, {
      method: "POST",
      headers: versionHeaders(options),
      body,
    });
  }

  async put(
    path: string,
    body: unknown,
    options: VersionRequestOptions = {},
  ): Promise<unknown> {
    const headers = versionHeaders(options);
    return this.request(path, {
      method: "PUT",
      headers,
      body: JSON.stringify(body),
    });
  }

  async patch(
    path: string,
    body: unknown,
    options: VersionRequestOptions = {},
  ): Promise<unknown> {
    return this.request(path, {
      method: "PATCH",
      headers: versionHeaders(options),
      body: JSON.stringify(body),
    });
  }

  async delete(
    path: string,
    options: VersionRequestOptions = {},
  ): Promise<unknown> {
    return this.request(path, {
      method: "DELETE",
      headers: versionHeaders(options),
    });
  }

  async download(path: string): Promise<Response> {
    if (!this.accessToken) {
      await this.refreshSession();
    }
    return this.executeDownload(path, true);
  }

  private storeSessionTokens(tokens: SessionTokens): void {
    this.accessToken = tokens.accessToken;
    this.csrfToken = tokens.csrfToken;
    try {
      this.getStorage()?.setItem(ADMIN_CSRF_TOKEN_KEY, tokens.csrfToken);
    } catch {
      // The active tab remains usable even when storage is unavailable.
    }
  }

  private getStorage(): Storage | undefined {
    if (this.injectedStorage) return this.injectedStorage;
    try {
      return globalThis.sessionStorage;
    } catch {
      return undefined;
    }
  }

  private readStoredCsrfToken(): string | null {
    try {
      return this.getStorage()?.getItem(ADMIN_CSRF_TOKEN_KEY) ?? null;
    } catch {
      return null;
    }
  }

  private async performRefresh(): Promise<void> {
    const csrfToken = this.csrfToken ?? this.readStoredCsrfToken();
    if (!csrfToken) {
      this.clearSession();
      throw new ApiError("没有可用的安全会话，请重新登录。", {
        code: "CSRF_TOKEN_MISSING",
        status: 403,
      });
    }

    try {
      const payload = await this.execute(
        "/auth/refresh",
        {
          method: "POST",
          headers: new Headers({ "X-CSRF-Token": csrfToken }),
        },
        { authenticated: false, retryAfterRefresh: false },
      );
      this.storeSessionTokens(readSessionTokens(payload));
    } catch (error) {
      this.clearSession();
      this.notifyAuthExpired();
      throw error;
    }
  }

  private async request(path: string, init: RequestInit): Promise<unknown> {
    if (!this.accessToken) {
      await this.refreshSession();
    }
    return this.execute(path, init, {
      authenticated: true,
      retryAfterRefresh: true,
    });
  }

  private async execute(
    path: string,
    init: RequestInit,
    options: RequestOptions,
  ): Promise<unknown> {
    if (!this.baseUrl) {
      throw new ApiError("尚未配置管理 API 地址。", {
        code: "API_NOT_CONFIGURED",
      });
    }

    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body !== undefined && !(init.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    if (options.authenticated && this.accessToken) {
      headers.set("Authorization", `Bearer ${this.accessToken}`);
    }

    let response: Response;
    try {
      response = await this.fetcher(`${this.baseUrl}${path}`, {
        ...init,
        headers,
        credentials: "include",
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError("无法连接管理服务，请检查服务地址和网络状态。", {
        code: "NETWORK_ERROR",
      });
    }

    if (
      response.status === 401 &&
      options.authenticated &&
      options.retryAfterRefresh
    ) {
      await this.refreshSession();
      return this.execute(path, init, {
        authenticated: true,
        retryAfterRefresh: false,
      });
    }

    if (response.status === 401 && options.authenticated) {
      this.clearSession();
      this.notifyAuthExpired();
    }

    if (!response.ok) throw await parseError(response);
    if (response.status === 204) return undefined;

    const text = await response.text();
    if (!text) return undefined;
    try {
      return JSON.parse(text) as unknown;
    } catch {
      throw new ApiError("管理服务返回了无法解析的响应。", {
        code: "INVALID_API_RESPONSE",
        status: response.status,
      });
    }
  }

  private async executeDownload(
    path: string,
    retryAfterRefresh: boolean,
  ): Promise<Response> {
    if (!this.baseUrl) {
      throw new ApiError("尚未配置管理 API 地址。", {
        code: "API_NOT_CONFIGURED",
      });
    }
    const headers = new Headers({ Accept: "text/csv" });
    if (this.accessToken) {
      headers.set("Authorization", `Bearer ${this.accessToken}`);
    }
    let response: Response;
    try {
      response = await this.fetcher(`${this.baseUrl}${path}`, {
        method: "GET",
        headers,
        credentials: "include",
      });
    } catch {
      throw new ApiError("无法连接管理服务，请检查服务地址和网络状态。", {
        code: "NETWORK_ERROR",
      });
    }
    if (response.status === 401 && retryAfterRefresh) {
      await this.refreshSession();
      return this.executeDownload(path, false);
    }
    if (response.status === 401) {
      this.clearSession();
      this.notifyAuthExpired();
    }
    if (!response.ok) throw await parseError(response);
    return response;
  }
}

function versionHeaders(options: VersionRequestOptions): Headers {
  const headers = new Headers();
  if (options.version !== undefined) {
    headers.set("If-Match", String(options.version));
  }
  if (options.idempotencyKey) {
    headers.set("Idempotency-Key", options.idempotencyKey);
  }
  return headers;
}

function safeRelativePath(value: string): string {
  const normalized = value.trim() || "/";
  if (
    !normalized.startsWith("/") ||
    normalized.startsWith("//") ||
    normalized.includes("\\") ||
    normalized.includes("\r") ||
    normalized.includes("\n") ||
    normalized.length > 500
  ) {
    return "/";
  }
  return normalized;
}

export function apiBaseUrlFromEnvironment(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) return configured;
  return import.meta.env.DEV ? "/api/v1" : "";
}

export const apiClient = new ApiClient({
  baseUrl: apiBaseUrlFromEnvironment(),
});

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ADMIN_CSRF_TOKEN_KEY,
  ADMIN_WECOM_RETURN_TO_KEY,
  ApiClient,
} from "./client";

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sessionResponse(accessToken: string, csrfToken: string) {
  return jsonResponse({
    data: {
      access_token: accessToken,
      csrf_token: csrfToken,
      token_type: "bearer",
      expires_in: 900,
      refresh_expires_in: 604800,
    },
  });
}

describe("ApiClient cookie and CSRF authentication", () => {
  beforeEach(() => {
    sessionStorage.clear();
    globalThis.localStorage?.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("keeps access in memory, persists only CSRF, and never stores a refresh token", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(sessionResponse("access-one", "csrf-one"))
      .mockResolvedValueOnce(jsonResponse({ data: { id: "user-1" } }));
    const client = new ApiClient({
      baseUrl: "https://api.example.test",
      fetcher,
    });

    await client.login("admin@example.test", "password");
    await client.get("/auth/me");

    expect(sessionStorage.getItem(ADMIN_CSRF_TOKEN_KEY)).toBe("csrf-one");
    expect(sessionStorage.getItem("refresh_token")).toBeNull();
    expect(sessionStorage.getItem("cf-admin-refresh-token")).toBeNull();
    expect(
      Array.from({ length: sessionStorage.length }, (_, index) => {
        const key = sessionStorage.key(index) ?? "";
        return `${key}:${sessionStorage.getItem(key) ?? ""}`;
      }).join("\n"),
    ).not.toMatch(/refresh[_-]?token|access-one/i);
    expect(globalThis.localStorage?.length ?? 0).toBe(0);
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toEqual({
      account: "admin@example.test",
      credential: "password",
      method: "password",
    });
    expect(fetcher.mock.calls[0][1]?.credentials).toBe("include");
    expect(fetcher.mock.calls[1][1]?.credentials).toBe("include");
    expect(
      (fetcher.mock.calls[1][1]?.headers as Headers).get("Authorization"),
    ).toBe("Bearer access-one");
  });

  it("starts and exchanges a one-time WeCom login without persisting access", async () => {
    const authorizeUrl =
      "https://open.weixin.qq.com/connect/oauth2/authorize?state=signed-state";
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ data: { authorize_url: authorizeUrl } }))
      .mockResolvedValueOnce(sessionResponse("wecom-access", "wecom-csrf"))
      .mockResolvedValueOnce(jsonResponse({ data: { id: "user-1" } }));
    const client = new ApiClient({
      baseUrl: "https://api.example.test",
      fetcher,
    });

    await expect(client.createWeComLoginUrl("/c/admin/")).resolves.toBe(
      authorizeUrl,
    );
    expect(sessionStorage.getItem(ADMIN_WECOM_RETURN_TO_KEY)).toBe("/c/admin/");
    await client.loginWithWeCom("oauth-code", "signed-state");
    await client.get("/auth/me");

    expect(fetcher.mock.calls[0][0]).toBe(
      "https://api.example.test/auth/wecom/login-url?return_to=%2Fc%2Fadmin%2F",
    );
    expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual({
      code: "oauth-code",
      state: "signed-state",
    });
    expect(
      (fetcher.mock.calls[2][1]?.headers as Headers).get("Authorization"),
    ).toBe("Bearer wecom-access");
    expect(sessionStorage.getItem(ADMIN_CSRF_TOKEN_KEY)).toBe("wecom-csrf");
    expect(client.consumeWeComReturnTo()).toBe("/c/admin/");
    expect(sessionStorage.getItem(ADMIN_WECOM_RETURN_TO_KEY)).toBeNull();
  });

  it("bootstraps from stored CSRF and the HttpOnly cookie with a bodyless refresh", async () => {
    sessionStorage.setItem(ADMIN_CSRF_TOKEN_KEY, "cold-csrf");
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(sessionResponse("access-one", "csrf-rotated"))
      .mockResolvedValueOnce(jsonResponse({ data: { id: "user-1" } }));
    const client = new ApiClient({
      baseUrl: "https://api.example.test/",
      fetcher,
    });

    await client.get("/auth/me");

    const refreshRequest = fetcher.mock.calls[0];
    expect(refreshRequest[0]).toBe("https://api.example.test/auth/refresh");
    expect(refreshRequest[1]?.method).toBe("POST");
    expect(refreshRequest[1]?.body).toBeUndefined();
    expect(refreshRequest[1]?.credentials).toBe("include");
    expect(
      (refreshRequest[1]?.headers as Headers).get("X-CSRF-Token"),
    ).toBe("cold-csrf");
    expect(
      (fetcher.mock.calls[1][1]?.headers as Headers).get("Authorization"),
    ).toBe("Bearer access-one");
    expect(sessionStorage.getItem(ADMIN_CSRF_TOKEN_KEY)).toBe("csrf-rotated");
  });

  it("rotates CSRF tokens across repeated refreshes and retries only once", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(sessionResponse("access-one", "csrf-one"))
      .mockResolvedValueOnce(jsonResponse({}, 401))
      .mockResolvedValueOnce(sessionResponse("access-two", "csrf-two"))
      .mockResolvedValueOnce(jsonResponse({ data: { id: "first" } }))
      .mockResolvedValueOnce(jsonResponse({}, 401))
      .mockResolvedValueOnce(sessionResponse("access-three", "csrf-three"))
      .mockResolvedValueOnce(jsonResponse({ data: { id: "second" } }));
    const client = new ApiClient({
      baseUrl: "https://api.example.test",
      fetcher,
    });
    await client.login("admin@example.test", "password");

    await client.get("/first");
    await client.get("/second");

    expect(
      (fetcher.mock.calls[2][1]?.headers as Headers).get("X-CSRF-Token"),
    ).toBe("csrf-one");
    expect(fetcher.mock.calls[2][1]?.body).toBeUndefined();
    expect(
      (fetcher.mock.calls[5][1]?.headers as Headers).get("X-CSRF-Token"),
    ).toBe("csrf-two");
    expect(fetcher.mock.calls[5][1]?.body).toBeUndefined();
    expect(
      (fetcher.mock.calls[6][1]?.headers as Headers).get("Authorization"),
    ).toBe("Bearer access-three");
    expect(sessionStorage.getItem(ADMIN_CSRF_TOKEN_KEY)).toBe("csrf-three");
  });

  it("does not enter a refresh loop when the retried request is unauthorized", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(sessionResponse("access-one", "csrf-one"))
      .mockResolvedValueOnce(jsonResponse({}, 401))
      .mockResolvedValueOnce(sessionResponse("access-two", "csrf-two"))
      .mockResolvedValueOnce(jsonResponse({}, 401));
    const client = new ApiClient({
      baseUrl: "https://api.example.test",
      fetcher,
    });
    await client.login("admin@example.test", "password");

    await expect(client.get("/admin/company/profile")).rejects.toMatchObject({
      status: 401,
    });
    expect(
      fetcher.mock.calls.filter(([url]) => String(url).endsWith("/auth/refresh")),
    ).toHaveLength(1);
  });

  it("clears in-memory access and CSRF state when refresh fails", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(sessionResponse("access-one", "csrf-one"))
      .mockResolvedValueOnce(jsonResponse({}, 401))
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: "CSRF_VALIDATION_FAILED" } }, 403),
      );
    const client = new ApiClient({
      baseUrl: "https://api.example.test",
      fetcher,
    });
    await client.login("admin@example.test", "password");

    await expect(client.get("/admin/cards")).rejects.toMatchObject({ status: 403 });
    expect(sessionStorage.getItem(ADMIN_CSRF_TOKEN_KEY)).toBeNull();
    await client.logout();

    expect(fetcher).toHaveBeenCalledTimes(3);
    await expect(client.get("/admin/cards")).rejects.toMatchObject({
      code: "CSRF_TOKEN_MISSING",
    });
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("sends logout with Bearer, CSRF and cookies before clearing memory", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(sessionResponse("access-one", "csrf-one"))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = new ApiClient({
      baseUrl: "https://api.example.test",
      fetcher,
    });
    await client.login("admin@example.test", "password");

    await client.logout();

    const request = fetcher.mock.calls[1];
    expect(request[0]).toBe("https://api.example.test/auth/logout");
    expect(request[1]?.method).toBe("POST");
    expect(request[1]?.body).toBeUndefined();
    expect(request[1]?.credentials).toBe("include");
    expect((request[1]?.headers as Headers).get("Authorization")).toBe(
      "Bearer access-one",
    );
    expect((request[1]?.headers as Headers).get("X-CSRF-Token")).toBe("csrf-one");
    expect(sessionStorage.getItem(ADMIN_CSRF_TOKEN_KEY)).toBeNull();
  });

  it("adds If-Match to post, patch and delete mutations", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(sessionResponse("access-one", "csrf-one"))
      .mockResolvedValueOnce(jsonResponse({ data: { version: 4 } }))
      .mockResolvedValueOnce(jsonResponse({ data: { version: 5 } }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = new ApiClient({
      baseUrl: "https://api.example.test",
      fetcher,
    });
    await client.login("admin@example.test", "password");

    await client.post("/admin/products/product-1:publish", {}, { version: 3 });
    await client.patch("/admin/products/product-1", { name: "更新" }, { version: 4 });
    await client.delete("/admin/products/product-1", { version: 5 });

    expect(fetcher.mock.calls[1][1]?.method).toBe("POST");
    expect((fetcher.mock.calls[1][1]?.headers as Headers).get("If-Match")).toBe("3");
    expect(fetcher.mock.calls[2][1]?.method).toBe("PATCH");
    expect((fetcher.mock.calls[2][1]?.headers as Headers).get("If-Match")).toBe("4");
    expect(fetcher.mock.calls[3][1]?.method).toBe("DELETE");
    expect((fetcher.mock.calls[3][1]?.headers as Headers).get("If-Match")).toBe("5");
    expect(fetcher.mock.calls.every(([, init]) => init?.credentials === "include")).toBe(true);
  });
});

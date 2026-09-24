import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient, ApiError, ADMIN_WECOM_RETURN_TO_KEY } from "../api/client";
import { APP_PATHS, appHref, WECOM_CALLBACK_PATH, WECOM_ENTRY_PATH } from "../routing";
import { AuthProvider, useAuth } from "./AuthContext";

function AuthProbe() {
  const auth = useAuth();
  return (
    <>
      <span>{auth.status}</span>
      {auth.error && <span>{auth.error.message}</span>}
    </>
  );
}

describe("WeCom workbench authentication entry", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
    window.history.replaceState({}, "", appHref("/"));
  });

  it("restarts an expired callback once, preserving the destination across redirects", async () => {
    vi.spyOn(apiClient, "isConfigured").mockReturnValue(true);
    const exchange = vi.spyOn(apiClient, "loginWithWeCom").mockRejectedValue(
      new ApiError("企业微信登录状态已失效，请重试", { code: "WECOM_OAUTH_STATE_INVALID" }),
    );
    const createLoginUrl = vi.spyOn(apiClient, "createWeComLoginUrl").mockResolvedValue(
      "https://open.weixin.qq.com/connect/oauth2/authorize?state=fresh",
    );
    const redirect = vi.fn();
    const target = appHref(`${APP_PATHS.visits}?visitId=visit-1`);
    sessionStorage.setItem(ADMIN_WECOM_RETURN_TO_KEY, target);
    window.history.replaceState({}, "", `${appHref(WECOM_CALLBACK_PATH)}?code=old&state=old`);
    const first = render(<AuthProvider externalRedirect={redirect}><AuthProbe /></AuthProvider>);
    await waitFor(() => expect(redirect).toHaveBeenCalledTimes(1));
    expect(exchange).toHaveBeenCalledTimes(1);
    expect(createLoginUrl).toHaveBeenCalledWith(target);
    expect(screen.getByText("bootstrapping")).toBeInTheDocument();
    first.unmount();

    window.history.replaceState({}, "", `${appHref(WECOM_CALLBACK_PATH)}?code=fresh&state=fresh`);
    render(<AuthProvider externalRedirect={redirect}><AuthProbe /></AuthProvider>);
    expect(await screen.findByText("unauthenticated")).toBeInTheDocument();
    expect(screen.getByText("企业微信登录状态已失效，请重试")).toBeInTheDocument();
    expect(redirect).toHaveBeenCalledTimes(1);
    expect(exchange).toHaveBeenCalledTimes(2);
  });

  it("keeps provider failures visible instead of repeatedly authorizing", async () => {
    vi.spyOn(apiClient, "isConfigured").mockReturnValue(true);
    vi.spyOn(apiClient, "loginWithWeCom").mockRejectedValue(
      new ApiError("企业未授权", { code: "WECOM_ENTERPRISE_NOT_AUTHORIZED" }),
    );
    const createLoginUrl = vi.spyOn(apiClient, "createWeComLoginUrl");
    window.history.replaceState({}, "", `${appHref(WECOM_CALLBACK_PATH)}?code=code&state=state`);
    render(<AuthProvider externalRedirect={vi.fn()}><AuthProbe /></AuthProvider>);
    expect(await screen.findByText("企业未授权")).toBeInTheDocument();
    expect(createLoginUrl).not.toHaveBeenCalled();
  });

  it("does not turn an expired binding into a different account login", async () => {
    vi.spyOn(apiClient, "isConfigured").mockReturnValue(true);
    vi.spyOn(apiClient, "consumeWeComFlow").mockReturnValue("bind");
    vi.spyOn(apiClient, "refreshSession").mockResolvedValue();
    vi.spyOn(apiClient, "bindWithWeCom").mockRejectedValue(
      new ApiError("绑定状态失效", { code: "WECOM_OAUTH_STATE_INVALID" }),
    );
    const createLoginUrl = vi.spyOn(apiClient, "createWeComLoginUrl");
    window.history.replaceState({}, "", `${appHref(WECOM_CALLBACK_PATH)}?code=code&state=state`);
    render(<AuthProvider externalRedirect={vi.fn()}><AuthProbe /></AuthProvider>);
    expect(await screen.findByText("绑定状态失效")).toBeInTheDocument();
    expect(createLoginUrl).not.toHaveBeenCalled();
  });

  it("offers manual login if recovery cannot obtain a fresh authorization link", async () => {
    vi.spyOn(apiClient, "isConfigured").mockReturnValue(true);
    vi.spyOn(apiClient, "loginWithWeCom").mockRejectedValue(
      new ApiError("登录状态失效", { code: "WECOM_OAUTH_STATE_INVALID" }),
    );
    const createLoginUrl = vi.spyOn(apiClient, "createWeComLoginUrl").mockRejectedValue(
      new ApiError("企业微信暂时不可用", { code: "WECOM_OAUTH_NOT_CONFIGURED" }),
    );
    window.history.replaceState({}, "", `${appHref(WECOM_CALLBACK_PATH)}?code=old&state=old`);
    render(<AuthProvider externalRedirect={vi.fn()}><AuthProbe /></AuthProvider>);
    expect(await screen.findByText("企业微信暂时不可用")).toBeInTheDocument();
    expect(screen.getByText("unauthenticated")).toBeInTheDocument();
    expect(createLoginUrl).toHaveBeenCalledWith(appHref(APP_PATHS.setup));
  });

  it("avoids automatic redirects when storage cannot preserve the retry limit", async () => {
    vi.spyOn(apiClient, "isConfigured").mockReturnValue(true);
    vi.spyOn(apiClient, "loginWithWeCom").mockRejectedValue(
      new ApiError("登录状态失效", { code: "WECOM_OAUTH_STATE_INVALID" }),
    );
    vi.stubGlobal("sessionStorage", {
      getItem: () => { throw new DOMException("Storage blocked", "SecurityError"); },
      setItem: () => { throw new DOMException("Storage blocked", "SecurityError"); },
    });
    const createLoginUrl = vi.spyOn(apiClient, "createWeComLoginUrl");
    window.history.replaceState({}, "", `${appHref(WECOM_CALLBACK_PATH)}?code=old&state=old`);
    render(<AuthProvider externalRedirect={vi.fn()}><AuthProbe /></AuthProvider>);
    expect(await screen.findByText("登录状态失效")).toBeInTheDocument();
    expect(createLoginUrl).not.toHaveBeenCalled();
  });

  it("starts OAuth automatically when the workbench entry has no session", async () => {
    const authorizeUrl =
      "https://open.weixin.qq.com/connect/oauth2/authorize?state=workbench-state";
    const redirect = vi.fn();
    vi.spyOn(apiClient, "isConfigured").mockReturnValue(true);
    vi.spyOn(apiClient, "refreshSession").mockRejectedValue(
      new ApiError("没有可用的安全会话", {
        code: "CSRF_TOKEN_MISSING",
        status: 403,
      }),
    );
    const createLoginUrl = vi
      .spyOn(apiClient, "createWeComLoginUrl")
      .mockResolvedValue(authorizeUrl);
    window.history.replaceState({}, "", appHref(WECOM_ENTRY_PATH));

    render(
      <AuthProvider externalRedirect={redirect}>
        <AuthProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(createLoginUrl).toHaveBeenCalledWith(appHref(APP_PATHS.setup));
      expect(redirect).toHaveBeenCalledWith(authorizeUrl);
    });
    expect(screen.getByText("bootstrapping")).toBeInTheDocument();
  });

  it("preserves the requested visit report through automatic OAuth", async () => {
    const authorizeUrl =
      "https://open.weixin.qq.com/connect/oauth2/authorize?state=report-state";
    const redirect = vi.fn();
    vi.spyOn(apiClient, "isConfigured").mockReturnValue(true);
    vi.spyOn(apiClient, "refreshSession").mockRejectedValue(
      new ApiError("没有可用的安全会话", {
        code: "CSRF_TOKEN_MISSING",
        status: 403,
      }),
    );
    const createLoginUrl = vi
      .spyOn(apiClient, "createWeComLoginUrl")
      .mockResolvedValue(authorizeUrl);
    const reportPath = appHref(`${APP_PATHS.visits}?visitId=visit-1`);
    window.history.replaceState(
      {},
      "",
      `${appHref(WECOM_ENTRY_PATH)}?return_to=${encodeURIComponent(reportPath)}`,
    );

    render(
      <AuthProvider externalRedirect={redirect}>
        <AuthProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(createLoginUrl).toHaveBeenCalledWith(reportPath);
      expect(redirect).toHaveBeenCalledWith(authorizeUrl);
    });
  });

  it("shows a recoverable error when the workbench OAuth start is unavailable", async () => {
    vi.spyOn(apiClient, "isConfigured").mockReturnValue(true);
    vi.spyOn(apiClient, "refreshSession").mockRejectedValue(
      new ApiError("没有可用的安全会话", {
        code: "CSRF_TOKEN_MISSING",
        status: 403,
      }),
    );
    vi.spyOn(apiClient, "createWeComLoginUrl").mockRejectedValue(
      new ApiError("企业微信登录尚未完成配置", {
        code: "WECOM_OAUTH_NOT_CONFIGURED",
        status: 409,
      }),
    );
    window.history.replaceState({}, "", appHref(WECOM_ENTRY_PATH));

    render(
      <AuthProvider externalRedirect={vi.fn()}>
        <AuthProbe />
      </AuthProvider>,
    );

    expect(await screen.findByText("unauthenticated")).toBeInTheDocument();
    expect(screen.getByText("企业微信登录尚未完成配置")).toBeInTheDocument();
  });
});

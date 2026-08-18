import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient, ApiError } from "../api/client";
import { APP_PATHS, appHref, WECOM_ENTRY_PATH } from "../routing";
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
    window.sessionStorage.clear();
    window.history.replaceState({}, "", appHref("/"));
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

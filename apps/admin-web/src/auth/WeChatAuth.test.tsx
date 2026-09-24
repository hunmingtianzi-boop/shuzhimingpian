import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient, ApiClient, ApiError } from "../api/client";
import { adminApi } from "../api/adminApi";
import { appHref, WECHAT_CALLBACK_PATH, WECHAT_ENTRY_PATH } from "../routing";
import { AuthProvider, useAuth } from "./AuthContext";

function Probe() {
  const auth = useAuth();
  return <><span>{auth.status}</span><span>{auth.error?.message}</span></>;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  sessionStorage.clear();
  history.replaceState({}, "", appHref("/"));
});

function wechat() {
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue("iPhone MicroMessenger");
  vi.spyOn(apiClient, "isConfigured").mockReturnValue(true);
  vi.spyOn(apiClient, "wechatAvailable").mockResolvedValue(true);
}

describe("Official Account H5 login", () => {
  it("starts normal WeChat OAuth from the service menu without calling WeCom", async () => {
    wechat();
    vi.spyOn(apiClient, "refreshSession").mockRejectedValue(new ApiError("expired"));
    const start = vi.spyOn(apiClient, "createWeChatLoginUrl").mockResolvedValue("https://open.weixin.qq.com/oauth");
    const wecom = vi.spyOn(apiClient, "createWeComLoginUrl");
    const redirect = vi.fn();
    history.replaceState({}, "", appHref(WECHAT_ENTRY_PATH));
    render(<StrictMode><AuthProvider externalRedirect={redirect}><Probe /></AuthProvider></StrictMode>);
    await waitFor(() => expect(redirect).toHaveBeenCalledOnce());
    expect(start).toHaveBeenCalledWith(appHref("/cards"));
    expect(wecom).not.toHaveBeenCalled();
  });

  it("exchanges the callback and lands on the server-bound destination", async () => {
    wechat();
    vi.spyOn(apiClient, "loginWithWeChat").mockResolvedValue(appHref("/cards"));
    vi.spyOn(adminApi, "me").mockResolvedValue({ role: "card_owner", id: "owner" } as Awaited<ReturnType<typeof adminApi.me>>);
    vi.spyOn(adminApi, "getCommercialEntitlements").mockRejectedValue(new Error("optional"));
    history.replaceState({}, "", `${appHref(WECHAT_CALLBACK_PATH)}?code=code&state=state`);
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("authenticated")).toBeInTheDocument();
    expect(location.pathname).toBe(appHref("/cards"));
    expect(location.search).toBe("");
  });

  it("scrubs failed callback credentials and does not create redirect loops", async () => {
    wechat();
    vi.spyOn(apiClient, "loginWithWeChat").mockRejectedValue(new ApiError("微信登录已失效"));
    const redirect = vi.fn();
    history.replaceState({}, "", `${appHref(WECHAT_CALLBACK_PATH)}?code=old&state=used`);
    render(<AuthProvider externalRedirect={redirect}><Probe /></AuthProvider>);
    expect(await screen.findByText("微信登录已失效")).toBeInTheDocument();
    expect(location.search).toBe("");
    expect(redirect).not.toHaveBeenCalled();
  });

  it("does not attempt web authorization outside ordinary WeChat", async () => {
    vi.spyOn(apiClient, "isConfigured").mockReturnValue(true);
    vi.spyOn(apiClient, "refreshSession").mockRejectedValue(new ApiError("expired"));
    const start = vi.spyOn(apiClient, "createWeChatLoginUrl");
    history.replaceState({}, "", appHref(WECHAT_ENTRY_PATH));
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("请在普通微信中打开服务号菜单，进入我的名片。")).toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
  });

  it("deduplicates a callback exchange and keeps session access tokens out of storage", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ data: {
      access_token: "wechat-access", csrf_token: "csrf-token", return_to: "/admin/cards",
    } }), { status: 200 }));
    const client = new ApiClient({ baseUrl: "https://cards.example/api/v1", fetcher });
    const first = client.loginWithWeChat("code", "state");
    const second = client.loginWithWeChat("code", "state");
    expect(first).toBe(second);
    await expect(first).resolves.toBe("/admin/cards");
    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher.mock.calls[0][1]?.credentials).toBe("include");
    expect(JSON.stringify(sessionStorage)).not.toContain("wechat-access");
  });
});

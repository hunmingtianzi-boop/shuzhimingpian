import { afterEach, describe, expect, it, vi } from "vitest";
import type { PublicCardData } from "./publicCardApi";
import { configureWeChatShare, isOrdinaryWeChat, shareData } from "./wechatShare";

const card = { slug: "personal-one", display_name: "张三", title: "产品设计师",
  avatar_url: "/assets/avatar.jpg", company: { summary: "个人介绍", logo_url: null },
} as PublicCardData;

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  delete (window as Window & { wx?: unknown }).wx;
  history.replaceState({}, "", "/");
});

describe("ordinary WeChat sharing", () => {
  it("does not sign pages in WeCom or ordinary browsers", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://cards.example/api/v1");
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue("MicroMessenger wxwork");
    expect(isOrdinaryWeChat()).toBe(false);
    await configureWeChatShare(card, new AbortController().signal);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("configures friend and timeline metadata using the published card", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://cards.example/api/v1");
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue("Android MicroMessenger");
    history.replaceState({}, "", "/c/personal-one?from=friend#card");
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: {
      app_id: "wx-app", timestamp: 123, nonce_str: "nonce", signature: "signed",
    } }), { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    let ready: () => void = () => undefined;
    const wx = { config: vi.fn(() => ready()), ready: vi.fn((fn) => { ready = fn; }), error: vi.fn(),
      updateAppMessageShareData: vi.fn(), updateTimelineShareData: vi.fn() };
    (window as Window & { wx?: unknown }).wx = wx;
    await configureWeChatShare(card, new AbortController().signal);
    expect(wx.config).toHaveBeenCalledWith(expect.objectContaining({ appId: "wx-app", signature: "signed" }));
    expect(wx.updateAppMessageShareData).toHaveBeenCalledWith(expect.objectContaining({
      title: "张三的名片", desc: "产品设计师",
    }));
    expect(wx.updateTimelineShareData).toHaveBeenCalledOnce();
    expect(fetcher.mock.calls[0][0]).not.toContain("%23card");
    expect(shareData(card).link).not.toContain("#");
  });

  it("does not set stale share data after navigating away", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://cards.example/api/v1");
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue("Android MicroMessenger");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: {
      app_id: "wx-app", timestamp: 123, nonce_str: "nonce", signature: "signed",
    } }), { status: 200 })));
    const controller = new AbortController();
    let ready: () => void = () => undefined;
    const wx = { config: vi.fn(() => { controller.abort(); ready(); }),
      ready: vi.fn((fn) => { ready = fn; }), error: vi.fn(),
      updateAppMessageShareData: vi.fn(), updateTimelineShareData: vi.fn() };
    (window as Window & { wx?: unknown }).wx = wx;
    await configureWeChatShare(card, controller.signal);
    expect(wx.updateAppMessageShareData).not.toHaveBeenCalled();
  });
});

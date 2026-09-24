import { getPublicApiBaseUrl } from "./assistantApi";
import type { PublicCardData } from "./publicCardApi";
import { canonicalShareUrl } from "./publicExperienceApi";

type ShareData = { title: string; desc: string; link: string; imgUrl: string };
type WeChatSDK = {
  config(options: Record<string, unknown>): void;
  ready(callback: () => void): void;
  error(callback: (error: unknown) => void): void;
  updateAppMessageShareData(data: ShareData): void;
  updateTimelineShareData(data: ShareData): void;
};

const SDK_URL = "https://res.wx.qq.com/open/js/jweixin-1.6.0.js";
// iOS WeChat signs the document entry URL even after history.pushState.
const entryUrl = typeof window === "undefined" ? "" : window.location.href.split("#")[0];
let sdkPromise: Promise<WeChatSDK> | undefined;

export function isOrdinaryWeChat(): boolean {
  return /micromessenger/i.test(navigator.userAgent) && !/wxwork/i.test(navigator.userAgent);
}

function currentSDK(): WeChatSDK | undefined {
  return (window as Window & { wx?: WeChatSDK }).wx;
}

function loadSDK(): Promise<WeChatSDK> {
  const sdk = currentSDK();
  if (sdk) return Promise.resolve(sdk);
  if (sdkPromise) return sdkPromise;
  sdkPromise = new Promise<WeChatSDK>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${SDK_URL}"]`);
    const script = existing ?? document.createElement("script");
    const cleanup = () => {
      clearTimeout(timer);
      script.removeEventListener("load", loaded);
      script.removeEventListener("error", failed);
    };
    const failed = () => {
      cleanup();
      sdkPromise = undefined;
      if (!existing) script.remove();
      reject(new Error("微信分享组件加载失败"));
    };
    const loaded = () => {
      const wx = currentSDK();
      if (!wx) { failed(); return; }
      cleanup();
      resolve(wx);
    };
    const timer = setTimeout(failed, 10_000);
    script.addEventListener("load", loaded);
    script.addEventListener("error", failed);
    if (!existing) {
      script.src = SDK_URL;
      script.async = true;
      document.head.append(script);
    }
  });
  return sdkPromise;
}

export function shareData(card: PublicCardData): ShareData {
  const image = card.avatar_url || card.company.logo_url || "";
  return {
    title: `${card.display_name}的名片`,
    desc: card.title || card.company.summary || "查看我的数智名片",
    link: canonicalShareUrl(window.location),
    imgUrl: image ? new URL(image, window.location.href).href : "",
  };
}

export async function configureWeChatShare(card: PublicCardData, signal: AbortSignal): Promise<void> {
  if (!isOrdinaryWeChat() || !getPublicApiBaseUrl()) return;
  const signedUrl = /iphone|ipad|ipod/i.test(navigator.userAgent)
    ? entryUrl : window.location.href.split("#")[0];
  const response = await fetch(
    `${getPublicApiBaseUrl()}/public/cards/${encodeURIComponent(card.slug)}/wechat-js-sdk?url=${encodeURIComponent(signedUrl)}`,
    { signal, headers: { Accept: "application/json" } },
  );
  if (!response.ok) throw new Error("微信分享尚未就绪");
  const { data } = await response.json();
  if (!data || typeof data.app_id !== "string" || typeof data.signature !== "string"
    || typeof data.nonce_str !== "string" || typeof data.timestamp !== "number") {
    throw new Error("微信分享配置无效");
  }
  const wx = await loadSDK();
  if (signal.aborted) return;
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("微信分享配置超时")), 10_000);
    wx.ready(() => {
      clearTimeout(timer);
      if (!signal.aborted) {
        const details = shareData(card);
        wx.updateAppMessageShareData(details);
        wx.updateTimelineShareData(details);
      }
      resolve();
    });
    wx.error(() => { clearTimeout(timer); reject(new Error("微信分享签名验证失败")); });
    wx.config({ debug: false, appId: data.app_id, timestamp: data.timestamp,
      nonceStr: data.nonce_str, signature: data.signature,
      jsApiList: ["updateAppMessageShareData", "updateTimelineShareData"] });
  });
}

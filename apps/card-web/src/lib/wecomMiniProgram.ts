import { getPublicApiBaseUrl } from "./assistantApi";

const TARGET_PATH = "/__wecom/miniprogram";
const SDK_SOURCE = "https://res.wx.qq.com/open/js/jweixin-1.6.0.js";

type WeComMiniProgramTarget = { appId: string; path: string };
type WeComInvokeResult = { err_msg?: string; errMsg?: string };
type WeComWx = {
  config(options: Record<string, unknown>): void;
  ready(callback: () => void): void;
  error(callback: (error: unknown) => void): void;
  agentConfig(options: Record<string, unknown>): void;
  invoke(name: string, options: Record<string, unknown>, callback: (result: WeComInvokeResult) => void): void;
};

type WeComJSSDKConfig = {
  corpId: string;
  agentId: number;
  timestamp: number;
  nonceStr: string;
  configSignature: string;
  agentConfigSignature: string;
  jsApiList: string[];
};

let sdkPromise: Promise<WeComWx> | undefined;

export function parseWeComMiniProgramTarget(value: string): WeComMiniProgramTarget | undefined {
  try {
    const url = new URL(value, "https://card.local");
    if (url.origin !== "https://card.local" || url.pathname !== TARGET_PATH) return undefined;
    const appId = (url.searchParams.get("app_id") || "").trim();
    const path = (url.searchParams.get("path") || "").trim().replace(/^\/+/, "");
    if (!/^wx[A-Za-z0-9]{16}$/.test(appId)) return undefined;
    if (!path || path.length > 1_024 || /[\\\u0000-\u001f]/.test(path)) return undefined;
    return { appId, path };
  } catch {
    return undefined;
  }
}

export function isWeComMiniProgramTarget(value: string) {
  return Boolean(parseWeComMiniProgramTarget(value));
}

export async function launchWeComMiniProgram({
  cardSlug,
  targetValue,
}: {
  cardSlug: string;
  targetValue: string;
}) {
  const target = parseWeComMiniProgramTarget(targetValue);
  if (!target) throw new Error("小程序入口配置无效");
  if (!/wxwork/i.test(navigator.userAgent)) {
    throw new Error("请在已安装本应用的企业微信内打开名片后使用此入口");
  }
  const [wx, config] = await Promise.all([
    loadWeComSDK(),
    fetchWeComJSSDKConfig(cardSlug),
  ]);
  await configureWeComSDK(wx, config);
  await invokeMiniProgram(wx, target);
}

async function fetchWeComJSSDKConfig(cardSlug: string): Promise<WeComJSSDKConfig> {
  const baseUrl = getPublicApiBaseUrl();
  if (!baseUrl) throw new Error("企业微信签名接口尚未配置");
  const signedUrl = window.location.href.split("#", 1)[0];
  const response = await fetch(
    `${baseUrl}/public/cards/${encodeURIComponent(cardSlug)}/wecom-js-sdk?url=${encodeURIComponent(signedUrl)}`,
    { headers: { Accept: "application/json" } },
  );
  const payload = await response.json().catch(() => undefined) as Record<string, unknown> | undefined;
  if (!response.ok) {
    const error = payload?.error as Record<string, unknown> | undefined;
    throw new Error(typeof error?.message === "string" ? error.message : "企业微信签名暂时不可用");
  }
  const data = payload?.data as Record<string, unknown> | undefined;
  if (
    !data
    || typeof data.corp_id !== "string"
    || typeof data.agent_id !== "number"
    || typeof data.timestamp !== "number"
    || typeof data.nonce_str !== "string"
    || typeof data.config_signature !== "string"
    || typeof data.agent_config_signature !== "string"
  ) throw new Error("企业微信签名响应无效");
  return {
    corpId: data.corp_id,
    agentId: data.agent_id,
    timestamp: data.timestamp,
    nonceStr: data.nonce_str,
    configSignature: data.config_signature,
    agentConfigSignature: data.agent_config_signature,
    jsApiList: Array.isArray(data.js_api_list)
      ? data.js_api_list.filter((item): item is string => typeof item === "string")
      : ["launchMiniprogram"],
  };
}

function loadWeComSDK(): Promise<WeComWx> {
  const existing = (window as Window & { wx?: WeComWx }).wx;
  if (existing) return Promise.resolve(existing);
  if (sdkPromise) return sdkPromise;
  sdkPromise = new Promise<WeComWx>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SDK_SOURCE;
    script.async = true;
    script.onload = () => {
      const wx = (window as Window & { wx?: WeComWx }).wx;
      if (wx) resolve(wx);
      else reject(new Error("企业微信 JS-SDK 加载失败"));
    };
    script.onerror = () => reject(new Error("企业微信 JS-SDK 加载失败"));
    document.head.append(script);
  });
  return sdkPromise;
}

async function configureWeComSDK(wx: WeComWx, config: WeComJSSDKConfig) {
  await withTimeout(new Promise<void>((resolve, reject) => {
    wx.error(reject);
    wx.ready(resolve);
    wx.config({
      beta: true,
      debug: false,
      appId: config.corpId,
      timestamp: config.timestamp,
      nonceStr: config.nonceStr,
      signature: config.configSignature,
      jsApiList: config.jsApiList,
    });
  }), "企业微信基础鉴权超时");
  await withTimeout(new Promise<void>((resolve, reject) => {
    wx.agentConfig({
      corpid: config.corpId,
      agentid: config.agentId,
      timestamp: config.timestamp,
      nonceStr: config.nonceStr,
      signature: config.agentConfigSignature,
      jsApiList: config.jsApiList,
      success: resolve,
      fail: reject,
    });
  }), "企业微信应用鉴权超时");
}

async function invokeMiniProgram(wx: WeComWx, target: WeComMiniProgramTarget) {
  await withTimeout(new Promise<void>((resolve, reject) => {
    wx.invoke("launchMiniprogram", { appid: target.appId, path: target.path }, (result) => {
      const message = result.err_msg || result.errMsg || "";
      if (/(:|\s)ok$/i.test(message)) resolve();
      else reject(new Error(message || "企业微信未能打开目标小程序"));
    });
  }), "打开小程序超时");
}

function withTimeout<T>(promise: Promise<T>, message: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(message)), 10_000);
    promise.then(
      (value) => { window.clearTimeout(timer); resolve(value); },
      (error) => { window.clearTimeout(timer); reject(error); },
    );
  });
}

import { useSyncExternalStore } from "react";

export const APP_PATHS = {
  overview: "/",
  setup: "/setup",
  visits: "/visits",
  visitorProfiles: "/visitor-profiles",
  conversations: "/conversations",
  opportunities: "/opportunities",
  leads: "/leads",
  exports: "/exports",
  knowledgeGaps: "/knowledge-gaps",
  notifications: "/notifications",
  privacyRequests: "/privacy-requests",
  privacySettings: "/privacy/settings",
  company: "/company",
  members: "/members",
  card: "/card",
  cards: "/cards",
  products: "/products",
  answerPolicy: "/ai/answer-policy",
  modelAccess: "/ai/model-access",
  notificationSettings: "/notifications/settings",
  cases: "/cases",
  forbiddenTopics: "/forbidden-topics",
  knowledge: "/knowledge",
  imports: "/imports",
  platformOverview: "/platform",
  platformEnterprises: "/platform/enterprises",
  platformOnboarding: "/platform/onboarding",
  platformAssociations: "/platform/associations",
  platformEmployees: "/platform/employees",
  platformVisitors: "/platform/visitors",
  platformTasks: "/platform/tasks",
  platformAudit: "/platform/audit",
  platformHealth: "/platform/health",
  platformLlmSettings: "/platform/settings/llm",
} as const;

// These are authentication transport routes rather than workspace pages. The
// workbench entry always starts (or resumes) WeCom OAuth, while the callback is
// consumed by AuthProvider before the authenticated shell is mounted.
export const WECOM_ENTRY_PATH = "/wecom/entry";
export const WECOM_CALLBACK_PATH = "/wecom/callback";

export type AppPath = (typeof APP_PATHS)[keyof typeof APP_PATHS];
export const PLATFORM_ENTERPRISE_SECTIONS = [
  "overview", "operations", "members-cards", "content",
  "tasks", "ai", "entitlements", "activity",
] as const;
export type PlatformEnterpriseSection = (typeof PLATFORM_ENTERPRISE_SECTIONS)[number];
export type DynamicAppPath =
  | `/platform/enterprises/${string}/${PlatformEnterpriseSection}`
  | `/visits/${string}`
  | `/visitor-profiles/${string}`
  | `/conversations/${string}`
  | `/opportunities/${string}`
  | `/leads/${string}`
  | `/products/${string}`;
export type NavigableAppPath = AppPath | DynamicAppPath;
export type AdminWorkspace = "platform" | "enterprise";

export const PLATFORM_PATHS = [
  APP_PATHS.platformOverview,
  APP_PATHS.platformEnterprises,
  APP_PATHS.platformOnboarding,
  APP_PATHS.platformAssociations,
  APP_PATHS.platformEmployees,
  APP_PATHS.platformVisitors,
  APP_PATHS.platformTasks,
  APP_PATHS.platformAudit,
  APP_PATHS.platformHealth,
  APP_PATHS.platformLlmSettings,
] as const satisfies readonly AppPath[];

const knownPaths = new Set<string>(Object.values(APP_PATHS));
const platformPaths = new Set<string>(PLATFORM_PATHS);
const platformEnterpriseSections = new Set<string>(PLATFORM_ENTERPRISE_SECTIONS);

function safeSegment(value: string): string {
  return encodeURIComponent(value.trim());
}

function decodedSegment(value: string): string | undefined {
  try {
    const decoded = decodeURIComponent(value).trim();
    return decoded && !decoded.includes("/") && !decoded.includes("\\")
      ? decoded
      : undefined;
  } catch {
    return undefined;
  }
}

export function platformEnterprisePath(
  companyId: string,
  section: PlatformEnterpriseSection = "overview",
): DynamicAppPath {
  return `/platform/enterprises/${safeSegment(companyId)}/${section}`;
}

export function matchPlatformEnterprisePath(path: string):
  | { companyId: string; section: PlatformEnterpriseSection }
  | undefined {
  const match = /^\/platform\/enterprises\/([^/]+)\/([^/]+)$/.exec(path);
  if (!match || !platformEnterpriseSections.has(match[2])) return undefined;
  const companyId = decodedSegment(match[1]);
  return companyId
    ? { companyId, section: match[2] as PlatformEnterpriseSection }
    : undefined;
}

export function visitDetailPath(id: string): DynamicAppPath { return `/visits/${safeSegment(id)}`; }
export function visitorProfileDetailPath(id: string): DynamicAppPath { return `/visitor-profiles/${safeSegment(id)}`; }
export function conversationDetailPath(id: string): DynamicAppPath { return `/conversations/${safeSegment(id)}`; }
export function opportunityDetailPath(id: string): DynamicAppPath { return `/opportunities/${safeSegment(id)}`; }
export function leadDetailPath(id: string): DynamicAppPath { return `/leads/${safeSegment(id)}`; }
export function productDetailPath(id: string): DynamicAppPath { return `/products/${safeSegment(id)}`; }

export function matchEntityDetailPath(path: string):
  | { kind: "visit" | "visitor-profile" | "conversation" | "opportunity" | "lead" | "product"; id: string }
  | undefined {
  const match = /^\/(visits|visitor-profiles|conversations|opportunities|leads|products)\/([^/]+)$/.exec(path);
  if (!match) return undefined;
  const id = decodedSegment(match[2]);
  if (!id) return undefined;
  const kinds = {
    visits: "visit", "visitor-profiles": "visitor-profile",
    conversations: "conversation", opportunities: "opportunity",
    leads: "lead", products: "product",
  } as const;
  return { kind: kinds[match[1] as keyof typeof kinds], id };
}

function normalizeBasePath(value: string): string {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "/") return "/";
  return `/${trimmed.replace(/^\/+|\/+$/g, "")}/`;
}

export const APP_BASE_PATH = normalizeBasePath(import.meta.env.BASE_URL);

export function appHref(path: string): string {
  if (APP_BASE_PATH === "/") return path;
  if (path === "/") return APP_BASE_PATH;
  return `${APP_BASE_PATH.slice(0, -1)}${path}`;
}

export function appPathFromBrowser(pathname: string): string {
  if (APP_BASE_PATH === "/") return pathname;
  const baseWithoutSlash = APP_BASE_PATH.slice(0, -1);
  if (pathname === baseWithoutSlash || pathname === APP_BASE_PATH) return "/";
  if (!pathname.startsWith(APP_BASE_PATH)) return pathname;
  return `/${pathname.slice(APP_BASE_PATH.length)}`;
}

function subscribe(callback: () => void) {
  window.addEventListener("popstate", callback);
  return () => window.removeEventListener("popstate", callback);
}

function snapshot() {
  return appPathFromBrowser(window.location.pathname);
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, snapshot, () => APP_PATHS.overview);
}

export function isAppPath(path: string): path is NavigableAppPath {
  return Boolean(knownPaths.has(path) || matchPlatformEnterprisePath(path) || matchEntityDetailPath(path));
}

export function adminWorkspaceForPath(path: string): AdminWorkspace | undefined {
  if (!isAppPath(path)) return undefined;
  return platformPaths.has(path) || Boolean(matchPlatformEnterprisePath(path))
    ? "platform"
    : "enterprise";
}

export function wecomEntryReturnTo(search: string): string {
  const fallback = appHref(APP_PATHS.setup);
  const candidate = new URLSearchParams(search).get("return_to")?.trim();
  if (
    !candidate ||
    !candidate.startsWith("/") ||
    candidate.startsWith("//") ||
    candidate.includes("\\") ||
    candidate.includes("\r") ||
    candidate.includes("\n")
  ) {
    return fallback;
  }
  const parsed = new URL(candidate, "https://wecom-entry.invalid");
  if (
    parsed.origin !== "https://wecom-entry.invalid" ||
    (APP_BASE_PATH !== "/" && !parsed.pathname.startsWith(APP_BASE_PATH))
  ) {
    return fallback;
  }
  const appPath = appPathFromBrowser(parsed.pathname);
  if (adminWorkspaceForPath(appPath) !== "enterprise") return fallback;
  return `${parsed.pathname}${parsed.search}`;
}

export function replaceBrowserHref(href: string): void {
  window.history.replaceState({}, "", href);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function navigate(path: NavigableAppPath): void {
  const browserPath = appHref(path);
  if (window.location.pathname === browserPath) return;
  window.history.pushState({}, "", browserPath);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function onInternalLinkClick(
  event: React.MouseEvent<HTMLAnchorElement>,
  path: NavigableAppPath,
): void {
  if (
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey
  ) {
    return;
  }
  event.preventDefault();
  navigate(path);
}

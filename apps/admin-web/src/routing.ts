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
  company: "/company",
  members: "/members",
  card: "/card",
  cards: "/cards",
  products: "/products",
  cases: "/cases",
  forbiddenTopics: "/forbidden-topics",
  knowledge: "/knowledge",
  imports: "/imports",
  platformOverview: "/platform",
  platformEnterprises: "/platform/enterprises",
  platformOnboarding: "/platform/onboarding",
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
export type AdminWorkspace = "platform" | "enterprise";

export const PLATFORM_PATHS = [
  APP_PATHS.platformOverview,
  APP_PATHS.platformEnterprises,
  APP_PATHS.platformOnboarding,
  APP_PATHS.platformEmployees,
  APP_PATHS.platformVisitors,
  APP_PATHS.platformTasks,
  APP_PATHS.platformAudit,
  APP_PATHS.platformHealth,
  APP_PATHS.platformLlmSettings,
] as const satisfies readonly AppPath[];

const knownPaths = new Set<string>(Object.values(APP_PATHS));
const platformPaths = new Set<string>(PLATFORM_PATHS);

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

export function isAppPath(path: string): path is AppPath {
  return knownPaths.has(path);
}

export function adminWorkspaceForPath(path: string): AdminWorkspace | undefined {
  if (!isAppPath(path)) return undefined;
  return platformPaths.has(path) ? "platform" : "enterprise";
}

export function navigate(path: AppPath): void {
  const browserPath = appHref(path);
  if (window.location.pathname === browserPath) return;
  window.history.pushState({}, "", browserPath);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function onInternalLinkClick(
  event: React.MouseEvent<HTMLAnchorElement>,
  path: AppPath,
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

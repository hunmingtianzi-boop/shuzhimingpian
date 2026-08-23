import { afterEach, describe, expect, it, vi } from "vitest";

async function loadRouting(baseUrl: string) {
  vi.resetModules();
  vi.stubEnv("BASE_URL", baseUrl);
  return import("./routing");
}

describe("admin subpath routing", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    window.history.replaceState({}, "", "/");
  });

  it("keeps root deployment paths unchanged", async () => {
    const routing = await loadRouting("/");

    expect(routing.appHref(routing.APP_PATHS.visits)).toBe("/visits");
    expect(routing.appPathFromBrowser("/visits")).toBe("/visits");
  });

  it("maps browser URLs into and out of the production admin base", async () => {
    const routing = await loadRouting("/c/admin/");

    expect(routing.appHref(routing.APP_PATHS.overview)).toBe("/c/admin/");
    expect(routing.appHref(routing.APP_PATHS.visits)).toBe("/c/admin/visits");
    expect(routing.appHref(routing.WECOM_ENTRY_PATH)).toBe(
      "/c/admin/wecom/entry",
    );
    expect(routing.appHref("/conversations?visitorId=visitor-1")).toBe(
      "/c/admin/conversations?visitorId=visitor-1",
    );
    expect(routing.appPathFromBrowser("/c/admin/visits")).toBe("/visits");
    expect(routing.appPathFromBrowser("/c/admin/wecom/callback")).toBe(
      routing.WECOM_CALLBACK_PATH,
    );
    expect(routing.appPathFromBrowser("/c/admin/")).toBe("/");
    expect(routing.appPathFromBrowser("/unrelated")).toBe("/unrelated");
    expect(
      routing.wecomEntryReturnTo(
        `?return_to=${encodeURIComponent("/c/admin/visits?visitId=visit-1")}`,
      ),
    ).toBe("/c/admin/visits?visitId=visit-1");
    expect(
      routing.wecomEntryReturnTo(
        `?return_to=${encodeURIComponent("https://attacker.example/report")}`,
      ),
    ).toBe("/c/admin/setup");
  });

  it("classifies every platform shell without changing base-path link generation", async () => {
    const routing = await loadRouting("/c/admin/");

    expect(routing.PLATFORM_PATHS).toEqual(
      expect.arrayContaining([
        routing.APP_PATHS.platformOverview,
        routing.APP_PATHS.platformEnterprises,
        routing.APP_PATHS.platformOnboarding,
        routing.APP_PATHS.platformEmployees,
        routing.APP_PATHS.platformVisitors,
        routing.APP_PATHS.platformTasks,
        routing.APP_PATHS.platformAudit,
        routing.APP_PATHS.platformHealth,
        routing.APP_PATHS.platformLlmSettings,
      ]),
    );
    expect(routing.adminWorkspaceForPath(routing.APP_PATHS.platformLlmSettings)).toBe(
      "platform",
    );
    expect(routing.adminWorkspaceForPath(routing.APP_PATHS.knowledge)).toBe(
      "enterprise",
    );
    expect(routing.adminWorkspaceForPath("/not-an-admin-route")).toBeUndefined();
    expect(routing.appHref(routing.APP_PATHS.platformLlmSettings)).toBe(
      "/c/admin/platform/settings/llm",
    );
  });

  it("builds and parses refreshable platform enterprise section routes", async () => {
    const routing = await loadRouting("/c/admin/");
    const path = routing.platformEnterprisePath("company-one", "tasks");

    expect(path).toBe("/platform/enterprises/company-one/tasks");
    expect(routing.appHref(path)).toBe(
      "/c/admin/platform/enterprises/company-one/tasks",
    );
    expect(routing.matchPlatformEnterprisePath(path)).toEqual({
      companyId: "company-one",
      section: "tasks",
    });
    expect(routing.adminWorkspaceForPath(path)).toBe("platform");
    expect(
      routing.matchPlatformEnterprisePath(
        "/platform/enterprises/company-one/unknown",
      ),
    ).toBeUndefined();
  });

  it("keeps enterprise object details typed and workspace-scoped", async () => {
    const routing = await loadRouting("/");

    expect(routing.visitDetailPath("visit-one")).toBe("/visits/visit-one");
    expect(routing.productDetailPath("new")).toBe("/products/new");
    expect(routing.matchEntityDetailPath("/visits/visit-one")).toEqual({
      kind: "visit",
      id: "visit-one",
    });
    expect(routing.adminWorkspaceForPath("/products/product-one")).toBe(
      "enterprise",
    );
  });
});

import { describe, expect, it } from "vitest";

import type { AdminUser, CommercialEntitlements } from "../api/types";
import { APP_PATHS } from "../routing";
import {
  getPlatformNavigationPaths,
  hasCommercialFeature,
  hasNavPermission,
} from "./AppShell";

function user(role: string, permissions: string[] = []): AdminUser {
  return {
    id: "user-1",
    displayName: "林顾问",
    membershipId: "membership-1",
    tenantId: "tenant-1",
    companyId: "company-1",
    role,
    permissions,
  };
}

describe("hasNavPermission", () => {
  it("allows company administrators to reach every management area", () => {
    expect(hasNavPermission(user("company_admin"), "catalog.read")).toBe(true);
    expect(hasNavPermission(user("company_admin"), "forbidden_topic.read")).toBe(true);
    expect(hasNavPermission(user("company_admin"), "members.manage")).toBe(true);
    expect(hasNavPermission(user("company_admin"), "exports.read")).toBe(true);
  });

  it("keeps card owners inside explicitly granted areas", () => {
    const owner = user("card_owner", ["card.read"]);
    expect(hasNavPermission(owner, "card.read")).toBe(true);
    expect(hasNavPermission(owner, "visits.read", true)).toBe(true);
    expect(hasNavPermission(owner, "conversations.read", true)).toBe(true);
    expect(hasNavPermission(owner, "leads.read", true)).toBe(true);
    expect(hasNavPermission(owner, "catalog.read")).toBe(false);
    expect(hasNavPermission(owner, "privacy.manage")).toBe(false);
    expect(hasNavPermission(owner, "members.manage")).toBe(false);
    expect(hasNavPermission(owner, "exports.read", true)).toBe(true);
    expect(hasNavPermission(owner, "forbidden_topic.read")).toBe(false);
  });

  it("accepts workflow permission aliases but hides unrelated governance areas", () => {
    const operator = user("staff", ["conversations.read", "leads.write"]);
    expect(hasNavPermission(operator, "analytics.read")).toBe(true);
    expect(hasNavPermission(operator, "visits.read")).toBe(true);
    expect(hasNavPermission(operator, "leads.read")).toBe(true);
    expect(hasNavPermission(operator, "privacy.manage")).toBe(false);
  });

  it("accepts member-management aliases without granting unrelated access", () => {
    const operator = user("staff", ["members.write"]);
    expect(hasNavPermission(operator, "members.manage")).toBe(true);
    expect(hasNavPermission(operator, "privacy.manage")).toBe(false);
  });

  it("keeps the LLM API entry inside the grouped platform navigation", () => {
    const paths = getPlatformNavigationPaths();

    expect(paths).toContain(APP_PATHS.platformLlmSettings);
    expect(paths).toContain(APP_PATHS.platformOverview);
    expect(paths).toContain(APP_PATHS.platformEmployees);
    expect(paths).toContain(APP_PATHS.platformVisitors);
    expect(paths).toContain(APP_PATHS.platformTasks);
    expect(paths).toContain(APP_PATHS.platformAudit);
    expect(paths).toContain(APP_PATHS.platformHealth);
    expect(paths).toContain(APP_PATHS.platformOnboarding);
    expect(paths).not.toContain(APP_PATHS.overview);
    expect(paths).not.toContain(APP_PATHS.company);
  });

  it("uses effective commercial entitlements without hiding menus during bootstrap", () => {
    expect(hasCommercialFeature(undefined, "data.exports")).toBe(true);
    expect(hasCommercialFeature({
      features: { "data.exports": false, "customer.visits": true },
    } as unknown as CommercialEntitlements, "data.exports")).toBe(false);
    expect(hasCommercialFeature({
      features: { "data.exports": false, "customer.visits": true },
    } as unknown as CommercialEntitlements, "customer.visits")).toBe(true);
  });
});

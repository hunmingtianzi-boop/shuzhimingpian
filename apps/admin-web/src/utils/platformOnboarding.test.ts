import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import type { PlatformOnboardingSession } from "../api/types";
import {
  buildOnboardingDeliveryUrls,
  confirmOnboardingWithRecovery,
  ONBOARDING_CONFIRM_UNCERTAIN_CODE,
} from "./platformOnboarding";

function session(
  status: PlatformOnboardingSession["status"],
): PlatformOnboardingSession {
  return {
    id: "session-1",
    displayName: "阿特拉斯建企任务",
    status,
    tenantSlug: "atlas-labs",
    version: status === "confirmed" ? 8 : 7,
    importBatchIds: [],
    suggestions: [],
    temporaryCredentialResetAvailable: status === "confirmed",
    confirmedEnterprise:
      status === "confirmed"
        ? {
            tenantId: "tenant-1",
            tenantSlug: "atlas-labs",
            tenantName: "阿特拉斯租户",
            companyId: "company-1",
            companyName: "阿特拉斯材料实验室",
            status: "active",
            adminUserId: "user-1",
            adminMembershipId: "membership-1",
            initialCardId: "card-1",
            initialCardSlug: "atlas-card",
            createdAt: "2026-07-17T00:00:00Z",
          }
        : undefined,
    createdAt: "2026-07-17T00:00:00Z",
    updatedAt: "2026-07-17T00:00:00Z",
  };
}

describe("platform onboarding completion recovery", () => {
  it("recovers a commit hidden by a gateway 502 response", async () => {
    const reload = vi.fn().mockResolvedValue(session("confirmed"));

    const result = await confirmOnboardingWithRecovery({
      confirm: vi
        .fn()
        .mockRejectedValue(
          new ApiError("bad gateway", { code: "HTTP_502", status: 502 }),
        ),
      reload,
    });

    expect(result.status).toBe("confirmed");
    expect(result.confirmedEnterprise?.initialCardSlug).toBe("atlas-card");
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("bounds a hung confirmation and reports a recoverable result when no commit is visible", async () => {
    vi.useFakeTimers();
    try {
      const pending = new Promise<PlatformOnboardingSession>(() => undefined);
      const result = confirmOnboardingWithRecovery({
        confirm: () => pending,
        reload: async () => session("review"),
        confirmTimeoutMs: 50,
        recoveryTimeoutMs: 50,
      });
      const assertion = expect(result).rejects.toMatchObject({
        code: ONBOARDING_CONFIRM_UNCERTAIN_CODE,
      });

      await vi.advanceTimersByTimeAsync(50);
      await assertion;
    } finally {
      vi.useRealTimers();
    }
  });

  it("derives the card and enterprise-admin URLs from the production admin base", () => {
    expect(
      buildOnboardingDeliveryUrls("atlas-card", {
        origin: "http://47.83.235.176",
        adminBasePath: "/c/admin/",
      }),
    ).toEqual({
      cardUrl: "http://47.83.235.176/c/atlas-card",
      adminUrl: "http://47.83.235.176/c/admin/",
    });
  });
});

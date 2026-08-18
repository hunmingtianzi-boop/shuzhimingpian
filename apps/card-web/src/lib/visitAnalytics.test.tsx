import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createAssistantIdempotencyKey,
  ensureVisitSession,
  recordVisitEvent,
} from "./assistantApi";
import { useVisitAnalytics } from "./visitAnalytics";

vi.mock("./assistantApi", () => ({
  createAssistantIdempotencyKey: vi.fn(() => "entry-id"),
  ensureVisitSession: vi.fn(),
  recordVisitEvent: vi.fn(),
}));

const session = {
  token: "visitor-token",
  visitId: "visit-id",
  expiresAt: "2026-08-20T00:00:00Z",
  privacyVersion: "privacy-v1",
  chatNoticeVersion: "chat-v1",
};

describe("useVisitAnalytics", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
  });

  it("marks an enterprise WeChat WebView switch as a resumable background transition", async () => {
    vi.mocked(createAssistantIdempotencyKey).mockReturnValue("entry-id");
    vi.mocked(ensureVisitSession).mockResolvedValue(session);
    vi.mocked(recordVisitEvent).mockResolvedValue(undefined);
    const { result } = renderHook(() => useVisitAnalytics({
      enabled: true,
      cardSlug: "tuozhe",
      companyId: "company-id",
      policyVersions: {
        privacy: "privacy-v1",
        chatNotice: "chat-v1",
        leadConsent: "lead-v1",
        profilePersonalization: "profile-v1",
      },
    }));

    act(() => {
      result.current.trackPage({
        key: "company:overview",
        title: "企业首页",
        objectType: "card",
      });
    });
    await waitFor(() => expect(recordVisitEvent).toHaveBeenCalledWith(
      expect.objectContaining({ eventType: "page_view" }),
    ));

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    act(() => document.dispatchEvent(new Event("visibilitychange")));

    await waitFor(() => expect(recordVisitEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        eventType: "heartbeat",
        keepalive: true,
        metadata: expect.objectContaining({ lifecycle_state: "background" }),
      }),
    ));
  });
});

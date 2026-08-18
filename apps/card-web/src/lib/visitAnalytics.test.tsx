import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createAssistantIdempotencyKey,
  ensureVisitSession,
  markVisitorSessionBackground,
  recordVisitEvent,
  resumeVisitorSession,
} from "./assistantApi";
import { useVisitAnalytics } from "./visitAnalytics";

vi.mock("./assistantApi", () => ({
  createAssistantIdempotencyKey: vi.fn(() => "entry-id"),
  ensureVisitSession: vi.fn(),
  markVisitorSessionBackground: vi.fn(),
  recordVisitEvent: vi.fn(),
  resumeVisitorSession: vi.fn(() => false),
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
    vi.clearAllMocks();
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

    expect(markVisitorSessionBackground).toHaveBeenCalledWith("tuozhe");

    await waitFor(() => expect(recordVisitEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        eventType: "heartbeat",
        keepalive: true,
        metadata: expect.objectContaining({ lifecycle_state: "background" }),
      }),
    ));
  });

  it("starts a new visit when a WebView returns after the report grace window", async () => {
    const resumedSession = { ...session, visitId: "next-visit-id", token: "next-token" };
    vi.mocked(createAssistantIdempotencyKey)
      .mockReturnValueOnce("entry-id")
      .mockReturnValueOnce("next-entry-id");
    vi.mocked(ensureVisitSession)
      .mockResolvedValueOnce(session)
      .mockResolvedValueOnce(resumedSession);
    vi.mocked(recordVisitEvent).mockResolvedValue(undefined);
    vi.mocked(resumeVisitorSession).mockReturnValue(true);
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
    await waitFor(() => expect(ensureVisitSession).toHaveBeenCalledTimes(1));

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
    act(() => document.dispatchEvent(new Event("visibilitychange")));

    await waitFor(() => expect(ensureVisitSession).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(recordVisitEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        eventType: "page_view",
        session: resumedSession,
      }),
    ));
  });
});

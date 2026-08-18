import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Visit, VisitDetail } from "../api/types";
import { workflowApi } from "../api/workflowApi";
import { adminLightTheme } from "../theme";
import { VisitsPage } from "./VisitsPage";

const visit: Visit = {
  id: "visit-1",
  cardId: "card-1",
  cardDisplayName: "夜霜曦雪",
  visitorId: "visitor-12345678",
  source: "card_web",
  startedAt: "2026-08-08T00:00:00Z",
  durationSeconds: 90,
  activityStatus: "estimated",
  lastActivityAt: "2026-08-08T00:01:30Z",
  durationEstimated: true,
  visitorChannel: "wechat",
  visitorIdentityType: "anonymous",
  visitorIdentityLabel: "微信访客（未识别）",
  conversationCount: 1,
};

const detail: VisitDetail = {
  ...visit,
  eventCount: 6,
  pageDurations: [{
    pageKey: "product:a",
    pageTitle: "产品 A",
    objectType: "product",
    objectId: "a",
    durationSeconds: 90,
    viewCount: 1,
    lastViewedAt: "2026-08-08T00:01:30Z",
  }],
  pageTimeline: [{
    sequence: 1,
    pageKey: "product:a",
    pageTitle: "产品 A",
    objectType: "product",
    objectId: "a",
    enteredAt: "2026-08-08T00:00:00Z",
    lastActivityAt: "2026-08-08T00:01:30Z",
    durationSeconds: 90,
    exitReason: "timeout",
  }],
  actions: [{
    eventId: "event-1",
    actionType: "cta_click",
    actionLabel: "打开联系表单",
    objectType: "contact",
    objectId: "lead_form",
    occurredAt: "2026-08-08T00:01:00Z",
  }],
  questions: [{
    messageId: "message-1",
    conversationId: "conversation-1",
    question: "怎么合作？",
    askedAt: "2026-08-08T00:00:30Z",
    answerStatus: "completed",
    answer: "请留下联系方式，我们会尽快联系。",
    answeredAt: "2026-08-08T00:00:32Z",
    responseSeconds: 2,
  }],
  behaviorAnalysis: {
    summary: "本次访问表现出较强咨询意向。",
    engagementScore: 72,
    engagementLevel: "high",
    intentLevel: "high",
    trackedDurationSeconds: 90,
    uniquePages: 1,
    totalActions: 1,
    questionCount: 1,
    answeredCount: 1,
    signals: [{
      category: "intent",
      label: "出现联系行动",
      evidence: "点击联系或行动入口 1 次",
      basis: "observed",
      confidence: 0.98,
    }],
  },
};

describe("VisitsPage visit report", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows page dwell, AI questions, answers, actions and evidence-based analysis", async () => {
    vi.spyOn(workflowApi, "listVisits").mockResolvedValue({
      items: [visit], total: 1, limit: 20, offset: 0,
    });
    vi.spyOn(workflowApi, "getVisit").mockResolvedValue(detail);
    const user = userEvent.setup();

    render(
      <FluentProvider theme={adminLightTheme}>
        <VisitsPage />
      </FluentProvider>,
    );

    expect(await screen.findByText("微信访客（未识别）")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "查看" }));

    expect(await screen.findByRole("heading", { name: "智能行为分析" })).toBeInTheDocument();
    expect(screen.getByText("本次访问表现出较强咨询意向。")).toBeInTheDocument();
    expect(screen.getAllByText("产品 A")).toHaveLength(2);
    expect(screen.getByText("怎么合作？")).toBeInTheDocument();
    expect(screen.getByText("请留下联系方式，我们会尽快联系。")).toBeInTheDocument();
    expect(screen.getAllByText("打开联系表单").length).toBeGreaterThan(0);
    expect(screen.getByText("实际记录")).toBeInTheDocument();
  });

  it("refreshes the visit status when the workbench becomes visible again", async () => {
    const listVisits = vi.spyOn(workflowApi, "listVisits").mockResolvedValue({
      items: [visit], total: 1, limit: 20, offset: 0,
    });
    render(
      <FluentProvider theme={adminLightTheme}>
        <VisitsPage />
      </FluentProvider>,
    );
    expect(await screen.findByText("微信访客（未识别）")).toBeInTheDocument();

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
    fireEvent(document, new Event("visibilitychange"));

    await waitFor(() => expect(listVisits).toHaveBeenCalledTimes(2));
  });
});

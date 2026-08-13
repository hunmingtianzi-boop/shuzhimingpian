import { FluentProvider } from "@fluentui/react-components";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { visitorProfilesApi } from "../api/visitorProfilesApi";
import type { AdminUser } from "../api/types";
import { AuthContext } from "../auth/AuthContext";
import { adminLightTheme } from "../theme";
import { VisitorProfilesPage } from "./VisitorProfilesPage";

const admin: AdminUser = {
  id: "user-1",
  displayName: "管理员",
  membershipId: "membership-1",
  tenantId: "tenant-1",
  companyId: "company-1",
  role: "company_admin",
  permissions: [],
};

const listItem = {
  visitorId: "visitor-1",
  firstSeenAt: "2026-07-10T00:00:00Z",
  lastSeenAt: "2026-07-12T02:00:00Z",
  signalCount: 2,
  topInterests: [{
    label: "智能名片", strength: 0.8, confidence: 0.9,
    lastSeenAt: "2026-07-12T02:00:00Z",
  }],
};

const detail = {
  visitorId: "visitor-1",
  firstSeenAt: "2026-07-10T00:00:00Z",
  lastSeenAt: "2026-07-12T02:00:00Z",
  signals: [{
    id: "signal-interest", kind: "interest" as const, label: "智能名片",
    strength: 0.8, confidence: 0.9, firstSeenAt: "2026-07-10T00:00:00Z",
    lastSeenAt: "2026-07-12T02:00:00Z", evidenceCount: 1,
    retentionExpiresAt: "2026-10-12T02:00:00Z",
    sources: [{
      id: "source-1", visitId: "visit-1", conversationId: "conversation-1",
      summaryId: "summary-1", messageId: "message-1", contribution: 0.8,
      confidence: 0.9, observedAt: "2026-07-12T02:00:00Z",
    }],
  }, {
    id: "signal-intent", kind: "intent" as const, label: "咨询合作",
    strength: 0.7, confidence: 0.85, firstSeenAt: "2026-07-11T00:00:00Z",
    lastSeenAt: "2026-07-12T02:00:00Z", evidenceCount: 0,
    retentionExpiresAt: "2026-10-12T02:00:00Z", sources: [],
  }],
};

const overview = {
  profile: detail,
  leads: [{
    id: "lead-1", cardId: "card-1", cardDisplayName: "拓浙 AI 集团", conversationId: "conversation-1",
    status: "new", priority: "high", maskedName: "张*", maskedContact: "138****0000",
    createdAt: "2026-07-12T02:00:00Z",
  }],
  conversations: [{
    id: "conversation-1", cardId: "card-1", cardDisplayName: "拓浙 AI 集团", status: "active",
    primaryIntent: "cooperation", riskLevel: "low", startedAt: "2026-07-12T01:00:00Z",
    lastActivityAt: "2026-07-12T02:00:00Z", messageCount: 4,
  }],
  knowledgeGaps: [{
    id: "gap-1", conversationId: "conversation-1", question: "有没有最新合作报价？",
    reason: "insufficient_evidence", status: "pending", occurrenceCount: 2,
    lastSeenAt: "2026-07-12T02:00:00Z",
  }],
};

function renderPage(user: AdminUser = admin) {
  return render(
    <FluentProvider theme={adminLightTheme}>
      <AuthContext.Provider value={{
        status: "authenticated",
        user,
        loginPending: false,
        apiConfigured: true,
        login: vi.fn(),
        changePassword: vi.fn(),
        logout: vi.fn(),
      }}>
        <VisitorProfilesPage />
      </AuthContext.Provider>
    </FluentProvider>,
  );
}

describe("VisitorProfilesPage", () => {
  beforeEach(() => {
    vi.spyOn(visitorProfilesApi, "list").mockResolvedValue({
      items: [listItem], total: 1, limit: 20, offset: 0,
    });
    vi.spyOn(visitorProfilesApi, "getOverview").mockResolvedValue(overview);
  });

  afterEach(() => vi.restoreAllMocks());

  it("shows authorized profiles, masked 360 context and auditable detail identifiers", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByRole("status", { name: "正在加载" })).toBeInTheDocument();
    expect(await screen.findByText("智能名片 · 90%")).toBeInTheDocument();
    expect(screen.getByText(/不展示原始联系方式、消息正文或摘要正文/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /查看访客 visitor-1 画像详情/ }));

    expect(await screen.findByText("咨询合作")).toBeInTheDocument();
    expect(screen.getByText("意图")).toBeInTheDocument();
    await user.click(screen.getByText("查看证据来源（1）"));
    expect(screen.getByText("visit-1")).toBeInTheDocument();
    expect(screen.getByText("conversation-1")).toBeInTheDocument();
    expect(screen.getByText("summary-1")).toBeInTheDocument();
    expect(screen.getByText("message-1")).toBeInTheDocument();
    expect(screen.getByText("张* · 138****0000")).toBeInTheDocument();
    expect(screen.getByText("有没有最新合作报价？")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看完整消息与引用" })).toHaveAttribute(
      "href", "/conversations?visitorId=visitor-1",
    );
    expect(document.body).not.toHaveTextContent("message_content");
  });

  it("shows an explicit empty state", async () => {
    vi.mocked(visitorProfilesApi.list).mockResolvedValueOnce({
      items: [], total: 0, limit: 20, offset: 0,
    });
    renderPage();
    expect(await screen.findByText("暂无已授权访客画像")).toBeInTheDocument();
  });

  it("shows API permission errors without exposing the table", async () => {
    vi.mocked(visitorProfilesApi.list).mockRejectedValueOnce(
      new ApiError("禁止访问", { status: 403, code: "FORBIDDEN" }),
    );
    renderPage();
    expect(await screen.findByText("没有访问权限")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "长期访客画像列表" })).not.toBeInTheDocument();
  });

  it("prevents requests when the account lacks visitor read permission", () => {
    renderPage({ ...admin, role: "auditor", permissions: [] });
    expect(screen.getByText("没有访问权限")).toBeInTheDocument();
    expect(visitorProfilesApi.list).not.toHaveBeenCalled();
  });

  it("loads the next page and closes the selected detail", async () => {
    const user = userEvent.setup();
    vi.mocked(visitorProfilesApi.list).mockResolvedValueOnce({
      items: [listItem], total: 21, limit: 20, offset: 0,
    }).mockResolvedValueOnce({
      items: [{ ...listItem, visitorId: "visitor-21" }], total: 21, limit: 20, offset: 20,
    });
    renderPage();
    await screen.findByText("智能名片 · 90%");
    await user.click(screen.getByRole("button", { name: /查看访客 visitor-1 画像详情/ }));
    await screen.findByRole("complementary", { name: "访客画像详情" });
    await user.click(screen.getByRole("button", { name: "下一页" }));

    await waitFor(() => expect(visitorProfilesApi.list).toHaveBeenLastCalledWith({
      limit: 20, offset: 20,
    }));
    expect(screen.queryByRole("complementary", { name: "访客画像详情" })).not.toBeInTheDocument();
    expect(await screen.findByText("visitor-21")).toBeInTheDocument();
  });
});

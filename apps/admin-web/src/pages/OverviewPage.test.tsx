import { FluentProvider } from "@fluentui/react-components";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { enterpriseReadinessApi } from "../api/enterpriseReadinessApi";
import type {
  DashboardOverview,
  EmployeeAnalyticsPage,
  TopicAnalysis,
} from "../api/types";
import { workflowApi } from "../api/workflowApi";
import { AuthContext, type AuthContextValue } from "../auth/AuthContext";
import { adminLightTheme } from "../theme";
import { OverviewPage } from "./OverviewPage";

const dashboard: DashboardOverview = {
  generatedAt: "2026-07-12T03:00:00Z",
  periodDays: 30,
  visits: 20,
  uniqueVisitors: 14,
  conversations: 8,
  aiAnswers: 10,
  totalLeads: 3,
  newLeads: 3,
  pendingGaps: 1,
  unreadNotifications: 2,
  conversationRate: 0.4,
  leadRate: 0.15,
  daily: [],
};

const employees: EmployeeAnalyticsPage = {
  items: [{
    userId: "user-1",
    membershipId: "membership-1",
    displayName: "林顾问",
    role: "card_owner",
    membershipStatus: "active",
    cardCount: 2,
    visits: 20,
    uniqueVisitors: 15,
    conversations: 8,
    leads: 3,
    conversationRate: 0.4,
    leadRate: 0.15,
    lastActivityAt: "2026-07-12T02:00:00Z",
  }],
  total: 1,
  limit: 20,
  offset: 0,
  generatedAt: "2026-07-12T03:00:00Z",
  periodDays: 30,
  reconciliation: {
    cardCount: 2,
    visits: 20,
    uniqueVisitors: 14,
    employeeUniqueVisitorsSum: 15,
    conversations: 8,
    totalLeads: 3,
    conversationRate: 0.4,
    leadRate: 0.15,
    lastActivityAt: "2026-07-12T02:00:00Z",
  },
};

const topicAnalysis: TopicAnalysis = {
  status: "ready",
  generatedAt: "2026-07-12T03:00:00Z",
  periodDays: 30,
  questionCount: 12,
  analyzedQuestionCount: 12,
  summary: "客户主要关注赛事报名、项目孵化与企业合作方式。",
  topics: [
    {
      topic: "赛事报名",
      count: 6,
      share: 0.5,
      sampleQuestions: ["浙客松怎么报名？", "参赛需要什么条件？"],
    },
    {
      topic: "项目孵化",
      count: 4,
      share: 0.3333,
      sampleQuestions: ["项目能获得哪些孵化支持？"],
    },
  ],
  provider: "deepseek",
  model: "deepseek-chat",
};

const auth: AuthContextValue = {
  status: "authenticated",
  user: {
    id: "admin-1",
    displayName: "管理员",
    membershipId: "membership-admin",
    tenantId: "tenant-1",
    companyId: "company-1",
    role: "company_admin",
    permissions: ["analytics.read"],
  },
  loginPending: false,
  apiConfigured: true,
  login: vi.fn(),
  logout: vi.fn(),
};

function renderPage() {
  return render(
    <FluentProvider theme={adminLightTheme}>
      <AuthContext.Provider value={auth}>
        <OverviewPage />
      </AuthContext.Provider>
    </FluentProvider>,
  );
}

describe("OverviewPage employee analytics", () => {
  beforeEach(() => {
    vi.spyOn(enterpriseReadinessApi, "get").mockResolvedValue({
      generatedAt: "2026-07-12T03:00:00Z",
      llmReady: true,
      unpublishedCardCount: 2,
      processingImportBatchCount: 1,
      failedImportBatchCount: 0,
    });
    vi.spyOn(workflowApi, "getTopicAnalysis").mockResolvedValue(topicAnalysis);
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows employee metrics and reconciliation notes", async () => {
    vi.spyOn(workflowApi, "getDashboard").mockResolvedValue(dashboard);
    vi.spyOn(workflowApi, "listEmployeeAnalytics").mockResolvedValue(employees);
    renderPage();

    expect(await screen.findByText("林顾问")).toBeInTheDocument();
    expect(screen.getByText("与业务总览已对账")).toBeInTheDocument();
    expect(screen.getByText(/员工独立访客合计 15/)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "员工表现" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "运营就绪状态" })).toBeInTheDocument();
    expect(await screen.findByText("名片 AI")).toBeInTheDocument();
    expect(await screen.findByText("未发布名片")).toBeInTheDocument();
    expect(await screen.findByText("赛事报名")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "用户高频话题热力分布" })).toBeInTheDocument();
  });

  it("keeps the employee query period in sync and resets pagination", async () => {
    const user = userEvent.setup();
    vi.spyOn(workflowApi, "getDashboard").mockResolvedValue(dashboard);
    const list = vi.spyOn(workflowApi, "listEmployeeAnalytics").mockResolvedValue({
      ...employees,
      total: 21,
    });
    renderPage();

    await screen.findByText("林顾问");
    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(list).toHaveBeenCalledWith({ periodDays: 30, limit: 20, offset: 20 }));
    await user.selectOptions(screen.getByRole("combobox", { name: "统计周期" }), "7");
    await waitFor(() => expect(list).toHaveBeenCalledWith({ periodDays: 7, limit: 20, offset: 0 }));
  });

  it("shows an employee-specific permission state without hiding the overview", async () => {
    vi.spyOn(workflowApi, "getDashboard").mockResolvedValue(dashboard);
    vi.spyOn(workflowApi, "listEmployeeAnalytics").mockRejectedValue(
      new ApiError("没有员工分析权限。", { status: 403, code: "FORBIDDEN" }),
    );
    renderPage();

    expect(await screen.findByText("没有访问权限")).toBeInTheDocument();
    expect(screen.getByLabelText("核心指标")).toBeInTheDocument();
  });

  it("runs the AI topic summary for the selected period", async () => {
    const user = userEvent.setup();
    vi.mocked(workflowApi.getTopicAnalysis).mockResolvedValue({
      ...topicAnalysis,
      status: "not_generated",
      generatedAt: undefined,
      summary: undefined,
      topics: [],
    });
    vi.spyOn(workflowApi, "getDashboard").mockResolvedValue(dashboard);
    vi.spyOn(workflowApi, "listEmployeeAnalytics").mockResolvedValue(employees);
    const analyze = vi.spyOn(workflowApi, "analyzeTopics").mockResolvedValue(topicAnalysis);
    renderPage();

    await screen.findByText("已有 12 条用户问题可分析");
    await user.click(screen.getByRole("button", { name: "AI 总结用户问题" }));

    await waitFor(() => expect(analyze).toHaveBeenCalledWith(30));
    expect(await screen.findByText(/已分析 12 条用户问题/)).toBeInTheDocument();
  });
});

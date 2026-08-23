import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import { contentImportsApi } from "../api/knowledgeImportsApi";
import { workflowApi } from "../api/workflowApi";
import type { AuthContextValue } from "../auth/AuthContext";
import { AuthContext } from "../auth/AuthContext";
import { APP_PATHS, appHref } from "../routing";
import { AppShell } from "./AppShell";

const auth: AuthContextValue = {
  status: "authenticated",
  user: {
    id: "user-1",
    displayName: "企业管理员",
    membershipId: "membership-1",
    tenantId: "tenant-1",
    companyId: "company-1",
    role: "company_admin",
    permissions: [],
  },
  entitlements: {
    companyId: "company-1",
    companyVersion: 1,
    planCode: "starter",
    billingCycle: "monthly",
    featureOverrides: {},
    plans: [],
    features: {
      "knowledge.import": true,
      "knowledge.manage": true,
    },
    limitOverrides: {},
    limits: {},
    featureCatalog: [],
    limitCatalog: [],
  },
  loginPending: false,
  apiConfigured: true,
  login: vi.fn(),
  changePassword: vi.fn(),
  logout: vi.fn(),
};

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", appHref(APP_PATHS.overview));
});

describe("AppShell notification center", () => {
  it("exposes a dedicated navigation entry and opens the route from the stable top-bar link", async () => {
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue({
      id: "company-1",
      name: "企业",
      summary: "",
      industry: "",
      region: "",
      website: "",
      logoUrl: "",
      profilePersonalizationPolicyVersion: "profile-personalization-v1",
      aiOffTopicAnswerMode: "limited",
      aiOffTopicQuestionLimit: 3,
      visitNotificationsEnabled: true,
      visitReportNotificationsEnabled: true,
      visitNotificationInAppEnabled: true,
      visitNotificationWecomEnabled: true,
      visitNotificationRecipientScope: "both",
      onboardingStatus: "active",
      version: 1,
    });
    vi.spyOn(workflowApi, "listNotifications").mockResolvedValue({
      items: [],
      total: 0,
      unread: 0,
    });
    render(
      <FluentProvider theme={webLightTheme}>
        <AuthContext.Provider value={auth}>
          <AppShell>
            <div>当前页面</div>
          </AppShell>
        </AuthContext.Provider>
      </FluentProvider>,
    );

    expect(screen.getByRole("link", { name: "消息与待办" })).toHaveAttribute(
      "href",
      appHref(APP_PATHS.notifications),
    );
    expect(screen.getByRole("link", { name: "禁答主题" })).toHaveAttribute(
      "href",
      appHref(APP_PATHS.forbiddenTopics),
    );

    const topbarLink = screen.getByRole("link", { name: "通知中心" });
    expect(topbarLink).toHaveAttribute("href", appHref(APP_PATHS.notifications));
    await userEvent.click(topbarLink);

    await waitFor(() => {
      expect(window.location.pathname).toBe(appHref(APP_PATHS.notifications));
    });
  });

  it("does not poll content-import tasks when the enterprise lacks the feature", async () => {
    vi.spyOn(adminApi, "getCompanyProfile").mockRejectedValue(new Error("not needed"));
    vi.spyOn(workflowApi, "listNotifications").mockResolvedValue({
      items: [],
      total: 0,
      unread: 0,
    });
    const listTasks = vi.spyOn(contentImportsApi, "list").mockResolvedValue([]);

    render(
      <FluentProvider theme={webLightTheme}>
        <AuthContext.Provider
          value={{
            ...auth,
            entitlements: {
              ...auth.entitlements!,
              features: { "knowledge.import": false },
            },
          }}
        >
          <AppShell>
            <div>当前页面</div>
          </AppShell>
        </AuthContext.Provider>
      </FluentProvider>,
    );

    await waitFor(() => expect(workflowApi.listNotifications).toHaveBeenCalled());
    expect(listTasks).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("资料智能整理任务")).not.toBeInTheDocument();
  });
});

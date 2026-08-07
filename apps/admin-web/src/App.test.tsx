import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { platformApi } from "./api/platformApi";
import type {
  AdminUser,
  PlatformLlmProfile,
  PlatformOnboardingImportStatus,
  PlatformOnboardingSession,
} from "./api/types";
import { CurrentPage, SessionGate } from "./App";
import { AuthContext, type AuthContextValue } from "./auth/AuthContext";
import { APP_PATHS, appHref, WECOM_ENTRY_PATH } from "./routing";

function user(role: string, id = "user-1"): AdminUser {
  return {
    id,
    displayName: role === "platform_admin" ? "平台管理员" : "企业管理员",
    membershipId: "membership-1",
    tenantId: "tenant-1",
    companyId: "company-1",
    role,
    permissions: [],
  };
}

function authValue(role: string, id = "user-1"): AuthContextValue {
  return {
    status: "authenticated",
    user: user(role, id),
    loginPending: false,
    apiConfigured: true,
    login: vi.fn(),
    logout: vi.fn(),
  };
}

function renderCurrentPage(role: string) {
  return render(
    <FluentProvider theme={webLightTheme}>
      <AuthContext.Provider value={authValue(role)}>
        <CurrentPage />
      </AuthContext.Provider>
    </FluentProvider>,
  );
}

function onboardingSession(
  id: string,
  overrides: Partial<PlatformOnboardingSession> = {},
): PlatformOnboardingSession {
  return {
    id,
    status: "processing",
    tenantSlug: `${id}-tenant`,
    version: 2,
    importBatchIds: ["batch-1"],
    suggestions: [],
    createdAt: "2026-07-16T09:00:00Z",
    updatedAt: "2026-07-16T09:00:00Z",
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((fulfill) => {
    resolve = fulfill;
  });
  return { promise, resolve };
}

function profile(): PlatformLlmProfile {
  return {
    id: "profile-1",
    name: "DeepSeek 主模型",
    purpose: "chat_main",
    provider: "deepseek",
    baseUrl: "https://api.deepseek.com",
    model: "deepseek-chat",
    thinking: "disabled",
    timeoutSeconds: 30,
    maxRetries: 2,
    maxConcurrency: 20,
    maxOutputTokens: 1000,
    temperature: 0.1,
    dailyBudgetCny: 100,
    inputPriceCnyPerMillion: 1,
    outputPriceCnyPerMillion: 2,
    allowGeneralAnswers: false,
    faqFastPathEnabled: true,
    keyConfigured: true,
    keyHint: "sk-***1234",
    enabled: true,
    isActive: true,
    version: 4,
    lastTestStatus: "succeeded",
    lastTestLatencyMs: 82,
    lastTestedAt: "2026-07-15T12:00:00Z",
    createdAt: "2026-07-15T10:00:00Z",
    updatedAt: "2026-07-15T12:00:00Z",
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
  window.history.replaceState({}, "", appHref(APP_PATHS.overview));
});

describe("CurrentPage workspace routing", () => {
  it.each([
    ["company_admin", "/login", APP_PATHS.overview],
    ["company_admin", WECOM_ENTRY_PATH, APP_PATHS.overview],
    ["platform_admin", "/login", APP_PATHS.platformOverview],
    ["platform_admin", WECOM_ENTRY_PATH, APP_PATHS.platformOverview],
  ])(
    "leaves the authentication entry for %s after authentication",
    async (role, entry, destination) => {
      window.history.replaceState({}, "", appHref(entry));

      render(
        <FluentProvider theme={webLightTheme}>
          <AuthContext.Provider value={authValue(role)}>
            <SessionGate />
          </AuthContext.Provider>
        </FluentProvider>,
      );

      await waitFor(() => {
        expect(window.location.pathname).toBe(appHref(destination));
      });
    },
  );

  it("returns a 403 surface before an enterprise account can mount platform data", () => {
    const listProfiles = vi.spyOn(platformApi, "listLlmProfiles");
    window.history.replaceState(
      {},
      "",
      appHref(APP_PATHS.platformLlmSettings),
    );

    renderCurrentPage("company_admin");

    expect(screen.getByText("无法访问此工作区")).toBeInTheDocument();
    expect(screen.getByText(/403/)).toBeInTheDocument();
    expect(listProfiles).not.toHaveBeenCalled();
  });

  it("redirects a platform account from the enterprise root to platform overview", async () => {
    window.history.replaceState({}, "", appHref(APP_PATHS.overview));

    renderCurrentPage("platform_admin");

    await waitFor(() => {
      expect(window.location.pathname).toBe(appHref(APP_PATHS.platformOverview));
    });
  });

  it("loads the document-assisted onboarding route for a platform account", async () => {
    vi.spyOn(platformApi, "listLlmProfiles").mockResolvedValue([]);
    window.history.replaceState(
      {},
      "",
      appHref(APP_PATHS.platformOnboarding),
    );

    renderCurrentPage("platform_admin");

    expect(await screen.findByText("资料辅助建企")).toBeInTheDocument();
    expect(window.location.pathname).toBe(appHref(APP_PATHS.platformOnboarding));
  });

  it("polls session-scoped import progress and renders the real file result", async () => {
    window.sessionStorage.setItem(
      "cf-platform-onboarding-session:user-1",
      "session-1",
    );
    vi.spyOn(platformApi, "listLlmProfiles").mockResolvedValue([]);
    vi.spyOn(platformApi, "getOnboarding").mockResolvedValue(
      onboardingSession("session-1", { tenantSlug: "acme-demo" }),
    );
    vi.spyOn(platformApi, "getOnboardingImports").mockResolvedValue({
      sessionId: "session-1",
      settled: true,
      items: [
        {
          id: "item-1",
          fileName: "企业介绍.pdf",
          sourceType: "pdf",
          status: "completed",
          createdAt: "2026-07-16T09:00:00Z",
          completedAt: "2026-07-16T09:00:02Z",
        },
      ],
    });
    window.history.replaceState(
      {},
      "",
      appHref(APP_PATHS.platformOnboarding),
    );

    renderCurrentPage("platform_admin");

    expect(await screen.findByText("企业介绍.pdf")).toBeInTheDocument();
    expect(platformApi.getOnboardingImports).toHaveBeenCalledWith("session-1");
    expect(screen.getByText("1/1 个文件已处理")).toBeInTheDocument();
  });

  it("restores only the current user's safe onboarding projection after load and refresh", async () => {
    const user = userEvent.setup();
    const storageKey = "cf-platform-onboarding-session:user-1";
    window.sessionStorage.setItem(storageKey, "session-restore");
    window.sessionStorage.setItem(
      "cf-platform-onboarding-session",
      "legacy-session-must-not-load",
    );
    vi.spyOn(platformApi, "listLlmProfiles").mockResolvedValue([]);
    const getOnboarding = vi
      .spyOn(platformApi, "getOnboarding")
      .mockResolvedValue(
        onboardingSession("session-restore", {
          status: "review",
          tenantName: "安全恢复租户",
          adminAccount: "admin@safe.example",
          adminDisplayName: "安全管理员",
          initialCardDisplayName: "安全顾问",
          initialCardTitle: "企业顾问",
          importBatchIds: [],
        }),
      );
    window.history.replaceState(
      {},
      "",
      appHref(APP_PATHS.platformOnboarding),
    );

    renderCurrentPage("platform_admin");

    expect(await screen.findByText("admin@safe.example")).toBeInTheDocument();
    expect(screen.getByText("安全管理员")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByLabelText("租户名称")).toHaveValue("安全恢复租户"),
    );
    expect(screen.getByLabelText("企业名称")).toHaveValue("安全恢复租户");
    expect(screen.getByLabelText("初始名片姓名")).toHaveValue("安全顾问");
    expect(screen.getByLabelText("初始名片职位")).toHaveValue("企业顾问");

    await user.clear(screen.getByLabelText("企业名称"));
    await user.type(screen.getByLabelText("企业名称"), "本地未提交编辑");
    await user.click(screen.getByRole("button", { name: "刷新进度" }));

    await waitFor(() => expect(getOnboarding).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByLabelText("企业名称")).toHaveValue(
        "安全恢复租户",
      ),
    );
    expect(window.sessionStorage.getItem(storageKey)).toBe("session-restore");
    expect(window.sessionStorage.getItem("cf-platform-onboarding-session")).toBeNull();
    expect(JSON.stringify(window.sessionStorage)).not.toMatch(/password|credential/i);
    expect(getOnboarding).not.toHaveBeenCalledWith("legacy-session-must-not-load");
  });

  it("ignores a late import poll after the authenticated user and session change", async () => {
    const oldPoll = deferred<PlatformOnboardingImportStatus>();
    window.sessionStorage.setItem(
      "cf-platform-onboarding-session:user-1",
      "session-old",
    );
    window.sessionStorage.setItem(
      "cf-platform-onboarding-session:user-2",
      "session-new",
    );
    vi.spyOn(platformApi, "listLlmProfiles").mockResolvedValue([]);
    vi.spyOn(platformApi, "getOnboarding").mockImplementation(async (sessionId) =>
      onboardingSession(sessionId),
    );
    vi.spyOn(platformApi, "getOnboardingImports").mockImplementation(
      async (sessionId) => {
        if (sessionId === "session-old") return oldPoll.promise;
        return {
          sessionId: "session-new",
          settled: true,
          items: [
            {
              id: "item-new",
              fileName: "新用户资料.pdf",
              sourceType: "pdf",
              status: "completed",
              createdAt: "2026-07-16T09:00:00Z",
              completedAt: "2026-07-16T09:00:02Z",
            },
          ],
        };
      },
    );
    window.history.replaceState(
      {},
      "",
      appHref(APP_PATHS.platformOnboarding),
    );

    const view = render(
      <FluentProvider theme={webLightTheme}>
        <AuthContext.Provider value={authValue("platform_admin", "user-1")}>
          <CurrentPage />
        </AuthContext.Provider>
      </FluentProvider>,
    );
    await waitFor(() =>
      expect(platformApi.getOnboardingImports).toHaveBeenCalledWith("session-old"),
    );

    view.rerender(
      <FluentProvider theme={webLightTheme}>
        <AuthContext.Provider value={authValue("platform_admin", "user-2")}>
          <CurrentPage />
        </AuthContext.Provider>
      </FluentProvider>,
    );
    expect(await screen.findByText("新用户资料.pdf")).toBeInTheDocument();

    await act(async () => {
      oldPoll.resolve({
        sessionId: "session-old",
        settled: true,
        items: [
          {
            id: "item-old",
            fileName: "旧用户私密资料.pdf",
            sourceType: "pdf",
            status: "completed",
            createdAt: "2026-07-16T08:00:00Z",
            completedAt: "2026-07-16T08:00:02Z",
          },
        ],
      });
      await oldPoll.promise;
    });

    expect(screen.queryByText("旧用户私密资料.pdf")).not.toBeInTheDocument();
    expect(screen.getByText("新用户资料.pdf")).toBeInTheDocument();
  });

  it("loads the real LLM route for a platform account", async () => {
    vi.spyOn(platformApi, "listLlmProfiles").mockResolvedValue([profile()]);
    window.history.replaceState(
      {},
      "",
      appHref(APP_PATHS.platformLlmSettings),
    );

    renderCurrentPage("platform_admin");

    expect(await screen.findAllByText("DeepSeek 主模型")).not.toHaveLength(0);
    expect(platformApi.listLlmProfiles).toHaveBeenCalledTimes(1);
    expect(screen.getByText("当前主配置已通过连接测试，可供名片 AI 问答使用。")).toBeInTheDocument();
  });
});

import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

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
  it("opens the notification route from the top-bar button", async () => {
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

    await userEvent.click(screen.getByRole("button", { name: "通知中心" }));

    await waitFor(() => {
      expect(window.location.pathname).toBe(appHref(APP_PATHS.notifications));
    });
  });
});

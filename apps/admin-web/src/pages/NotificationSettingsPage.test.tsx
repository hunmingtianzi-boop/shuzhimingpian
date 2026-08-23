import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import type { CompanyNotificationSettings } from "../api/types";
import { NotificationSettingsPage } from "./NotificationSettingsPage";

vi.mock("../api/adminApi", () => ({
  adminApi: {
    getNotificationSettings: vi.fn(),
    updateNotificationSettings: vi.fn(),
  },
}));

const settings: CompanyNotificationSettings = {
  visitNotificationsEnabled: true,
  visitReportNotificationsEnabled: true,
  visitNotificationInAppEnabled: true,
  visitNotificationWecomEnabled: true,
  visitNotificationRecipientScope: "both",
  ordinaryVisitDigestEnabled: true,
  version: 7,
  updatedAt: "2026-08-15T10:00:00Z",
};

function renderPage() {
  return render(
    <FluentProvider theme={webLightTheme}>
      <NotificationSettingsPage />
    </FluentProvider>,
  );
}

describe("NotificationSettingsPage", () => {
  beforeEach(() => {
    vi.mocked(adminApi.getNotificationSettings).mockReset().mockResolvedValue(settings);
    vi.mocked(adminApi.updateNotificationSettings).mockReset().mockResolvedValue(settings);
  });

  it("saves visit notification channels and recipient scope", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("switch", { name: "企业微信应用消息" }));
    await user.click(screen.getByRole("radio", { name: "所有企业管理员" }));
    await user.click(screen.getByRole("button", { name: "保存通知设置" }));

    await waitFor(() => {
      expect(adminApi.updateNotificationSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          visitNotificationWecomEnabled: false,
          visitNotificationRecipientScope: "admins",
        }),
      );
    });
  });
});

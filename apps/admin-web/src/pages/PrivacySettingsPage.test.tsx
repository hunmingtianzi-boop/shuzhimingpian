import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import type { CompanyPrivacySettings } from "../api/types";
import { PrivacySettingsPage } from "./PrivacySettingsPage";

vi.mock("../api/adminApi", () => ({
  adminApi: {
    getPrivacySettings: vi.fn(),
    updatePrivacySettings: vi.fn(),
  },
}));

const settings: CompanyPrivacySettings = {
  profilePersonalizationPolicyVersion: "profile-personalization-v1",
  visitorProfileRetentionDays: 180,
  version: 7,
  updatedAt: "2026-08-15T10:00:00Z",
};

function renderPage() {
  return render(
    <FluentProvider theme={webLightTheme}>
      <PrivacySettingsPage />
    </FluentProvider>,
  );
}

describe("PrivacySettingsPage", () => {
  beforeEach(() => {
    vi.mocked(adminApi.getPrivacySettings).mockReset().mockResolvedValue(settings);
    vi.mocked(adminApi.updatePrivacySettings).mockReset().mockResolvedValue(settings);
  });

  it("saves the visitor-profile policy version on its own page", async () => {
    const user = userEvent.setup();
    renderPage();

    const input = await screen.findByRole("textbox", { name: "访客画像政策版本" });
    await user.clear(input);
    await user.type(input, "profile-personalization-v2");
    await user.click(screen.getByRole("button", { name: "保存数据与隐私设置" }));

    await waitFor(() => {
      expect(adminApi.updatePrivacySettings).toHaveBeenCalledWith(
        expect.objectContaining({
          profilePersonalizationPolicyVersion: "profile-personalization-v2",
        }),
      );
    });
  });
});

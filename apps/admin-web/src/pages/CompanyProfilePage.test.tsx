import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import type { CompanyProfile } from "../api/types";
import { CompanyProfilePage } from "./CompanyProfilePage";

vi.mock("../api/adminApi", () => ({
  adminApi: {
    getCompanyProfile: vi.fn(),
    updateCompanyProfile: vi.fn(),
  },
}));

const profile: CompanyProfile = {
  id: "company-1",
  name: "夜霜曦雪",
  summary: "企业简介",
  industry: "企业服务",
  region: "上海",
  website: "https://yeshuangxixue.cn",
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
  version: 7,
  updatedAt: "2026-08-15T10:00:00Z",
};

function renderPage() {
  return render(
    <FluentProvider theme={webLightTheme}>
      <CompanyProfilePage />
    </FluentProvider>,
  );
}

describe("CompanyProfilePage AI assistant boundary", () => {
  beforeEach(() => {
    vi.mocked(adminApi.getCompanyProfile).mockReset().mockResolvedValue(profile);
    vi.mocked(adminApi.updateCompanyProfile).mockReset().mockResolvedValue();
  });

  it("saves the enterprise-owned off-topic answer limit", async () => {
    const user = userEvent.setup();
    renderPage();

    const slider = await screen.findByRole("slider", { name: "无关问题回答上限" });
    fireEvent.change(slider, { target: { value: "5" } });
    expect(screen.getByText("每段对话最多回答 5 个无关问题")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "保存企业资料" }));

    await waitFor(() => {
      expect(adminApi.updateCompanyProfile).toHaveBeenCalledWith(
        expect.objectContaining({
          aiOffTopicAnswerMode: "limited",
          aiOffTopicQuestionLimit: 5,
          version: 7,
        }),
      );
    });
  });

  it("offers both completely blocked and completely allowed endpoints", async () => {
    const user = userEvent.setup();
    renderPage();

    const blocked = await screen.findByRole("radio", {
      name: "完全不回答——从第 1 个企业无关问题起拒答",
    });
    await user.click(blocked);
    expect(blocked).toBeChecked();
    expect(screen.queryByRole("slider", { name: "无关问题回答上限" })).not.toBeInTheDocument();

    const unlimited = screen.getByRole("radio", {
      name: "完全允许——不按次数限制普通无关问题",
    });
    await user.click(unlimited);
    expect(unlimited).toBeChecked();

    await user.click(screen.getByRole("button", { name: "保存企业资料" }));
    await waitFor(() => {
      expect(adminApi.updateCompanyProfile).toHaveBeenCalledWith(
        expect.objectContaining({ aiOffTopicAnswerMode: "unlimited" }),
      );
    });
  });

  it("saves visit notification channels and recipient scope", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(
      await screen.findByRole("switch", { name: "企业微信应用消息" }),
    );
    await user.click(screen.getByRole("radio", { name: "所有企业管理员" }));
    await user.click(screen.getByRole("button", { name: "保存企业资料" }));

    await waitFor(() => {
      expect(adminApi.updateCompanyProfile).toHaveBeenCalledWith(
        expect.objectContaining({
          visitNotificationWecomEnabled: false,
          visitNotificationRecipientScope: "admins",
        }),
      );
    });
  });
});

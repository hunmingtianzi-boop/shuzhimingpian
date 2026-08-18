import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import type { CompanyProfile } from "../api/types";
import { CompanySetupPage } from "./CompanySetupPage";

const company: CompanyProfile = {
  id: "company-1",
  name: "拓浙 AI 集团",
  summary: "连接青年 AI 人才、高校创新资源与产业场景。",
  industry: "AI 人才与场景服务",
  region: "浙江杭州",
  website: "https://example.test",
  logoUrl: "",
  profilePersonalizationPolicyVersion: "profile-v1",
  aiOffTopicAnswerMode: "limited",
  aiOffTopicQuestionLimit: 3,
  visitNotificationsEnabled: true,
  visitReportNotificationsEnabled: true,
  visitNotificationInAppEnabled: true,
  visitNotificationWecomEnabled: true,
  visitNotificationRecipientScope: "both",
  onboardingStatus: "content_pending",
  version: 2,
  updatedAt: "2026-08-07T00:00:00Z",
};

const card = {
  id: "card-1",
  displayName: "周顾问",
  title: "创始人",
  slug: "tuotu",
  avatarUrl: "",
  assistantName: "拓浙 AI 助手",
  welcomeMessage: "欢迎了解拓浙。",
  suggestedQuestions: ["你们有哪些业务？"],
  policyVersions: {
    privacy: "privacy-v1",
    chatNotice: "chat-v1",
    leadConsent: "lead-v1",
  },
  status: "draft",
  onboardingStatus: "content_pending",
  version: 3,
  updatedAt: "2026-08-07T00:00:00Z",
};

describe("CompanySetupPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("publishes the existing enterprise and card records as one setup flow", async () => {
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(company);
    vi.spyOn(adminApi, "getCard").mockResolvedValue(card);
    const updateCompany = vi
      .spyOn(adminApi, "updateCompanyProfile")
      .mockResolvedValue(undefined);
    const updateCard = vi.spyOn(adminApi, "updateCard").mockResolvedValue(undefined);
    const complete = vi
      .spyOn(adminApi, "completeEnterpriseSetup")
      .mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(
      <FluentProvider theme={webLightTheme}>
        <CompanySetupPage />
      </FluentProvider>,
    );

    expect(await screen.findByDisplayValue("拓浙 AI 集团")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "下一步" }));
    expect(screen.getByDisplayValue("拓浙 AI 助手")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "预览发布" }));
    await user.click(screen.getByRole("button", { name: "确认并发布" }));

    await waitFor(() => expect(complete).toHaveBeenCalledOnce());
    expect(updateCompany).toHaveBeenCalledWith(
      expect.objectContaining({ name: "拓浙 AI 集团", version: 2 }),
    );
    expect(updateCard).toHaveBeenCalledWith(
      expect.objectContaining({ slug: "tuotu", version: 3 }),
    );
    expect(screen.getByText("企业资料和名片已完成发布。")).toBeInTheDocument();
  });
});

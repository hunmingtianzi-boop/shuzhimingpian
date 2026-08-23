import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import type { CompanyIdentityProfile } from "../api/types";
import { CompanyProfilePage } from "./CompanyProfilePage";

vi.mock("../api/adminApi", () => ({
  adminApi: {
    getCompanyIdentity: vi.fn(),
    updateCompanyIdentity: vi.fn(),
  },
}));

vi.mock("../components/FormFeedback", () => ({
  FormFeedback: () => null,
}));

const profile: CompanyIdentityProfile = {
  id: "company-1",
  legalName: "夜霜曦雪（上海）科技有限公司",
  shortName: "夜霜曦雪",
  subjectType: "domestic_enterprise",
  socialCreditCode: "91310000MA1K123456",
  industry: "企业服务",
  region: "上海",
  website: "https://yeshuangxixue.cn",
  logoUrl: "",
  positioning: "企业 AI 名片",
  profileFacts: [{ id: "fact-1", label: "擅长", value: "企业知识助手" }],
  profileTags: ["可追溯", "企业级"],
  summary: "企业简介",
  status: "active",
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

describe("CompanyProfilePage", () => {
  beforeEach(() => {
    vi.mocked(adminApi.getCompanyIdentity).mockReset().mockResolvedValue(profile);
    vi.mocked(adminApi.updateCompanyIdentity).mockReset().mockResolvedValue(profile);
  });

  it("keeps only identity and outward presentation while linking to split settings", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "企业身份与对外展示" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "回答策略" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "通知设置" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "数据与隐私" })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("夜霜曦雪（上海）科技有限公司")).toBeInTheDocument();
    expect(screen.getByDisplayValue("夜霜曦雪")).toBeInTheDocument();
    expect(screen.getByDisplayValue("91310000MA1K123456")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "AI 助手回答边界" })).not.toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "企业微信应用消息" })).not.toBeInTheDocument();
  });

  it("saves through the company identity api", async () => {
    renderPage();

    const shortNameInput = (await screen.findByDisplayValue("夜霜曦雪")) as HTMLInputElement;
    shortNameInput.focus();
    shortNameInput.setSelectionRange(0, shortNameInput.value.length);
    await userEvent.clear(shortNameInput);
    await userEvent.type(shortNameInput, "夜霜");
    await userEvent.click(screen.getByRole("button", { name: "保存企业资料" }));

    await waitFor(() => {
      expect(adminApi.updateCompanyIdentity).toHaveBeenCalledWith(
        expect.objectContaining({
          legalName: "夜霜曦雪（上海）科技有限公司",
          shortName: "夜霜",
          subjectType: "domestic_enterprise",
          positioning: "企业 AI 名片",
          profileFacts: [{ id: "fact-1", label: "擅长", value: "企业知识助手" }],
          profileTags: ["可追溯", "企业级"],
          version: 7,
        }),
      );
    });
  });
});

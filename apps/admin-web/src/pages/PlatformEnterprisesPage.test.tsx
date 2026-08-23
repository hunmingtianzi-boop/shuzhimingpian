import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { platformApi } from "../api/platformApi";
import { adminLightTheme } from "../theme";
import { PlatformEnterprisesPage } from "./PlatformEnterprisesPage";

function renderPage() {
  return render(
    <FluentProvider theme={adminLightTheme}>
      <PlatformEnterprisesPage />
    </FluentProvider>,
  );
}

describe("PlatformEnterprisesPage", () => {
  beforeEach(() => {
    vi.spyOn(platformApi, "listEnterprises").mockResolvedValue([]);
    vi.spyOn(platformApi, "listCompanyAggregates").mockResolvedValue([]);
    vi.spyOn(platformApi, "listTasks").mockResolvedValue([]);
    vi.spyOn(platformApi, "getOverview").mockResolvedValue({
      generatedAt: "2026-08-23T10:00:00Z",
      enterpriseCount: 0,
      activeEnterpriseCount: 0,
      onboardingCount: 0,
      publishedCardCount: 0,
      visits30d: 0,
      conversations30d: 0,
      leads30d: 0,
      failedTaskCount: 0,
      llmReady: true,
      importReady: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("collects identity-first fields, submits legacy-compatible create payload, and shows one-time credentials with zero cards", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(platformApi, "createEnterprise").mockResolvedValue({
      tenantId: "tenant-1",
      tenantSlug: "91330100ma27xg019b",
      tenantName: "阿特拉斯",
      companyId: "company-1",
      companyName: "阿特拉斯材料实验室",
      status: "active",
      createdAt: "2026-08-23T10:02:00Z",
      adminUserId: "user-1",
      adminMembershipId: "membership-1",
      initialCardId: "legacy-card-1",
      initialCardSlug: "legacy-card-slug",
      credentialDelivery: {
        account: "admin@atlas.example",
        temporaryPassword: "one-time-password",
        expiresAt: "2026-08-30T10:02:00Z",
        shownOnce: true,
      },
    });
    renderPage();

    await screen.findByText("尚未开通企业");
    await user.click(screen.getByRole("button", { name: "开通第一家企业" }));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).queryByLabelText("技术标识（当前接口必填）")).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText("初始密码")).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText("兼容初始名片标题（可留空）")).not.toBeInTheDocument();
    const textboxes = within(dialog).getAllByRole("textbox", { hidden: true });
    const selects = within(dialog).getAllByRole("combobox", { hidden: true });

    fireEvent.change(textboxes[0], { target: { value: "阿特拉斯材料实验室" } });
    fireEvent.change(textboxes[1], { target: { value: "阿特拉斯" } });
    await user.selectOptions(selects[0], "domestic_enterprise");
    fireEvent.change(textboxes[2], { target: { value: "91330100MA27XG019B" } });
    fireEvent.change(textboxes[3], { target: { value: "先进制造" } });
    fireEvent.change(textboxes[4], { target: { value: "admin@atlas.example" } });
    fireEvent.change(textboxes[5], { target: { value: "陈管理员" } });
    await user.selectOptions(selects[1], "professional");
    await user.click(within(dialog).getByRole("button", { name: "确认开通" }));

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create.mock.calls[0][0]).toMatchObject({
      legalName: "阿特拉斯材料实验室",
      shortName: "阿特拉斯",
      subjectType: "domestic_enterprise",
      socialCreditCode: "91330100MA27XG019B",
      industry: "先进制造",
      adminAccount: "admin@atlas.example",
      adminDisplayName: "陈管理员",
      defaultPlanCode: "professional",
    });
    expect(await screen.findByText("一次性管理员凭据")).toBeInTheDocument();
    expect(screen.getByText("0 张")).toBeInTheDocument();
    expect(screen.getByText(/默认套餐 professional；一次性密码有效至/)).toBeInTheDocument();
  });
});

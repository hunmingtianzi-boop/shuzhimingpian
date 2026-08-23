import { FluentProvider } from "@fluentui/react-components";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PlatformOnboardingSession } from "../api/types";
import { adminLightTheme } from "../theme";
import {
  PlatformOnboardingPage,
  type PlatformOnboardingPageProps,
} from "./PlatformOnboardingPage";

const reviewSession: PlatformOnboardingSession = {
  id: "onboarding-session-7",
  displayName: "阿特拉斯资料建企",
  status: "review",
  tenantSlug: "atlas-labs",
  tenantName: "",
  version: 7,
  importBatchIds: ["batch-1"],
  suggestions: [
    {
      field: "company_name",
      value: "阿特拉斯材料实验室",
      confidence: 0.91,
      generationVersion: 3,
      sources: [
        {
          importItemId: "item-1",
          documentId: "draft-1",
          fileName: "企业介绍.pdf",
          excerpt: "阿特拉斯材料实验室专注复合材料研发。",
        },
      ],
    },
  ],
  businessProfile: [],
  createdAt: "2026-07-15T12:00:00Z",
  updatedAt: "2026-07-15T12:05:00Z",
  temporaryCredentialResetAvailable: false,
};

function buildProps(
  overrides: Partial<PlatformOnboardingPageProps> = {},
): PlatformOnboardingPageProps {
  return {
    session: reviewSession,
    importItems: [{ id: "item-1", fileName: "企业介绍.pdf", status: "completed" }],
    adminSummary: { account: "admin@atlas.example", displayName: "陈管理员" },
    llmAvailability: "ready",
    onStart: vi.fn().mockResolvedValue(undefined),
    onUpload: vi.fn().mockResolvedValue(undefined),
    onGenerate: vi.fn().mockResolvedValue(undefined),
    onConfirm: vi.fn().mockResolvedValue(undefined),
    onCancel: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

function renderPage(props: PlatformOnboardingPageProps) {
  return render(
    <FluentProvider theme={adminLightTheme}>
      <PlatformOnboardingPage {...props} />
    </FluentProvider>,
  );
}

async function enterReview(user: ReturnType<typeof userEvent.setup>) {
  if (!screen.queryByRole("heading", { name: "人工复核与确认" })) {
    await user.click(screen.getByRole("button", { name: /人工复核与确认/ }));
  }
  await screen.findByRole("heading", { name: "人工复核与确认" });
}

async function confirmIdentityGate(user: ReturnType<typeof userEvent.setup>) {
  await user.click(
    screen.getByRole("checkbox", { name: "我已逐项复核企业身份与对外展示信息" }),
  );
  await user.click(
    screen.getByRole("checkbox", { name: "我已核对管理员账号与交付对象" }),
  );
}

afterEach(() => {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1024 });
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: undefined,
  });
});

describe("PlatformOnboardingPage", () => {
  it("starts onboarding from identity fields and maps them into the legacy start payload", async () => {
    const user = userEvent.setup();
    const onStart = vi.fn().mockResolvedValue(undefined);
    renderPage(buildProps({ session: undefined, onStart }));

    expect(screen.queryByLabelText("租户标识")).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: /企业正式名称/ }), "阿特拉斯材料实验室");
    await user.type(screen.getByRole("textbox", { name: /企业简称/ }), "阿特拉斯");
    await user.type(screen.getByRole("textbox", { name: /统一社会信用代码/ }), "91330100MA27XG019B");
    await user.type(screen.getByRole("textbox", { name: /管理员账号/ }), "admin@atlas.example");
    await user.type(screen.getByRole("textbox", { name: /管理员姓名/ }), "陈管理员");
    await user.click(screen.getByRole("button", { name: "进入资料导入" }));

    await waitFor(() => expect(onStart).toHaveBeenCalledTimes(1));
    expect(onStart).toHaveBeenCalledWith({
      displayName: "阿特拉斯",
      adminAccount: "admin@atlas.example",
      adminDisplayName: "陈管理员",
      legalName: "阿特拉斯材料实验室",
      shortName: "阿特拉斯",
      subjectType: "domestic_enterprise",
      socialCreditCode: "91330100MA27XG019B",
      industry: undefined,
    });
  });

  it("uses identity fields in review, hides initial-card editing, and submits a legacy-compatible confirm payload", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    renderPage(
      buildProps({
        initialReview: {
          legalName: "阿特拉斯材料实验室",
          shortName: "阿特拉斯",
          subjectType: "domestic_enterprise",
          socialCreditCode: "91330100MA27XG019B",
        },
        onConfirm,
      }),
    );

    await enterReview(user);
    expect(screen.getByRole("textbox", { name: /企业正式名称/ })).toHaveValue("阿特拉斯材料实验室");
    expect(screen.queryByText("初始草稿名片")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", { name: "我已核对初始名片，并确认保持草稿" }),
    ).not.toBeInTheDocument();

    await confirmIdentityGate(user);
    await user.click(screen.getByRole("button", { name: "确认并激活企业" }));

    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onConfirm).toHaveBeenCalledWith(
      reviewSession.id,
      expect.objectContaining({
        expectedVersion: 7,
        legalName: "阿特拉斯材料实验室",
        shortName: "阿特拉斯",
        subjectType: "domestic_enterprise",
        socialCreditCode: "91330100MA27XG019B",
        industry: undefined,
      }),
    );
  });

  it("shows zero-card completion and only delivers admin access after confirmation", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    renderPage(
      buildProps({
        session: {
          ...reviewSession,
          status: "confirmed",
          confirmedEnterprise: {
            tenantId: "tenant-1",
            tenantSlug: "atlas-labs",
            tenantName: "阿特拉斯",
            companyId: "company-1",
            companyName: "阿特拉斯材料实验室",
            status: "active",
            adminUserId: "user-1",
            adminMembershipId: "membership-1",
            initialCardId: "legacy-card-1",
            initialCardSlug: "legacy-card-slug",
            createdAt: "2026-07-15T12:10:00Z",
          },
          credentialDelivery: {
            account: "admin@atlas.example",
            temporaryPassword: "one-time-password",
            expiresAt: "2026-07-22T12:30:00Z",
            shownOnce: true,
          },
        },
      }),
    );

    expect(await screen.findByRole("heading", { name: "企业已由服务端确认激活" })).toBeInTheDocument();
    expect(screen.getByText(/零名片起步/)).toBeInTheDocument();
    expect(screen.getByText("当前没有公开名片网址；企业管理员登录后创建并发布名片，才会生成对外访问链接。")).toBeInTheDocument();
    expect(screen.queryByLabelText("企业名片固定网址")).not.toBeInTheDocument();
    expect(screen.getByText("0 张")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "复制企业管理后台网址" }));
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/`);
  });

  it("keeps primary review actions reachable at 390px", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    window.dispatchEvent(new Event("resize"));
    const user = userEvent.setup();
    renderPage(
      buildProps({
        initialReview: {
          legalName: "阿特拉斯材料实验室",
          shortName: "阿特拉斯",
          subjectType: "domestic_enterprise",
          socialCreditCode: "91330100MA27XG019B",
        },
      }),
    );

    await enterReview(user);
    expect(screen.getByLabelText("开通会话主操作")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "取消会话" })).toBeVisible();
    expect(screen.getByRole("button", { name: "确认并激活企业" })).toBeVisible();
  });
});

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
  it("shows all candidate sources and filters candidates by uploaded file", async () => {
    const user = userEvent.setup();
    renderPage(buildProps({
      importItems: [
        { id: "item-1", fileName: "企业介绍.pdf", status: "completed" },
        { id: "item-2", fileName: "产品手册.docx", status: "completed" },
        { id: "item-3", fileName: "商会接口报告.pdf", status: "completed" },
      ],
      session: {
        ...reviewSession,
        contentReview: {
          id: "review-multi-source",
          batchId: "batch-2",
          status: "review",
          provider: "deepseek",
          model: "flash",
          attempts: 1,
          counts: { pending_review: 2 },
          stage: "completed",
          progressCurrent: 2,
          progressTotal: 2,
          candidates: [
            {
              id: "candidate-1",
              runId: "run-1",
              category: "enterprise_profile",
              payload: { field: "summary", value: "企业介绍" },
              sourceId: "item-1",
              sourceText: "企业介绍原文",
              confidence: 0.9,
              status: "pending_review",
              version: 1,
            },
            {
              id: "candidate-2",
              runId: "run-2",
              category: "products",
              payload: { name: "复合材料产品", summary: "产品介绍" },
              sourceId: "item-2",
              sourceText: "产品手册原文",
              confidence: 0.88,
              status: "pending_review",
              version: 1,
            },
          ],
        },
      },
    }));

    await user.click(screen.getByRole("tab", { name: "按资料查看" }));
    expect(screen.getByRole("button", { name: /全部资料\s*2/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /企业介绍\.pdf\s*1/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /产品手册\.docx\s*1/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /商会接口报告\.pdf\s*0\s*未形成候选/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /产品手册\.docx\s*1/ }));
    expect(screen.getByText("复合材料产品")).toBeInTheDocument();
    expect(screen.queryByText("企业介绍原文")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /商会接口报告\.pdf\s*0\s*未形成候选/ }));
    expect(screen.getByText("这份资料暂未形成候选")).toBeInTheDocument();
    expect(screen.queryByText("产品手册原文")).not.toBeInTheDocument();
  });

  it("distinguishes useful candidates from an unclassified fallback", async () => {
    const user = userEvent.setup();
    renderPage(buildProps({
      session: {
        ...reviewSession,
        contentReview: {
          id: "review-unclassified",
          batchId: "batch-1",
          status: "review",
          provider: "deepseek",
          model: "flash",
          attempts: 1,
          counts: { unclassified: 1 },
          stage: "completed",
          progressCurrent: 1,
          progressTotal: 1,
          candidates: [
            {
              id: "candidate-unclassified",
              runId: "run-1",
              category: "unclassified",
              payload: { text: "待人工识别的资料" },
              sourceId: "item-1",
              sourceText: "待人工识别的资料",
              confidence: 0,
              status: "pending_review",
              version: 1,
            },
          ],
        },
      },
    }));

    await user.click(screen.getByRole("tab", { name: "按资料查看" }));
    expect(
      screen.getByRole("button", { name: /企业介绍\.pdf\s*1\s*1 条待分类 · 识别不足/ }),
    ).toBeInTheDocument();
  });

  it("renders editable cross-source candidates with evidence and draft action", async () => {
    const user = userEvent.setup();
    const onAcceptCandidate = vi.fn().mockResolvedValue(undefined);
    renderPage(buildProps({
      onAcceptCandidate,
      importItems: [
        { id: "item-1", fileName: "材料说明.pdf", status: "completed" },
        { id: "item-2", fileName: "协作机制.pdf", status: "completed" },
      ],
      session: {
        ...reviewSession,
        synthesisStatus: "ready",
        synthesisVersion: 2,
        businessProfile: [],
        contentReview: {
          id: "review-synthesis",
          batchId: "batch-1",
          status: "review",
          provider: "deepseek",
          model: "flash",
          attempts: 1,
          counts: { pending_review: 1 },
          stage: "completed",
          progressCurrent: 2,
          progressTotal: 2,
          candidates: [{
            id: "merged-candidate-1",
            runId: "run-1",
            category: "products",
            payload: {
              name: "机器人蛋糕协作系统",
              category: "智能制造",
              summary: "跨资料摘要",
              detail: "共同补充后的完整内容",
              audience: "食品工厂",
              price_boundary: "",
            },
            sourceId: "synthesis:onboarding-session-7:2",
            sourceText: "材料说明.pdf：提供机器人躯体材料\n协作机制.pdf：补充共同协作机制",
            confidence: 0.88,
            status: "pending_review",
            version: 1,
          }],
        },
      },
    }));

    expect(screen.getByRole("heading", { name: "共同补充后的知识候选" })).toBeInTheDocument();
    expect(screen.getByText(/已联合分析 2\/2 份资料/)).toBeInTheDocument();
    expect(screen.getByText(/引用 2 份资料/)).toBeInTheDocument();
    expect(screen.getByText("条由多份资料共同补充")).toBeInTheDocument();
    expect(screen.getByDisplayValue("机器人蛋糕协作系统")).toBeInTheDocument();
    expect(screen.getByText(/材料说明\.pdf：提供机器人躯体材料/)).toBeInTheDocument();
    expect(screen.queryByText("阿特拉斯材料实验室")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认并写入草稿" }));
    await waitFor(() => expect(onAcceptCandidate).toHaveBeenCalled());
  });

  it("automatically synthesizes settled sources and keeps source review available", async () => {
    const onSynthesize = vi.fn().mockResolvedValue(undefined);
    renderPage(buildProps({
      onSynthesize,
      session: {
        ...reviewSession,
        synthesisStatus: "pending",
        synthesisVersion: 0,
        suggestions: [],
        businessProfile: [],
        contentReview: {
          id: "review-complete-1",
          batchId: "batch-1",
          status: "review",
          provider: "deepseek",
          model: "deepseek-v4-flash",
          attempts: 1,
          counts: { pending_review: 1 },
          stage: "completed",
          stageMessage: "已完成 1 份资料分析，共生成 1 条候选",
          progressCurrent: 1,
          progressTotal: 1,
          candidates: [{
            id: "candidate-auto-1",
            runId: "run-auto-1",
            category: "products",
            payload: { name: "复合材料", summary: "材料说明", detail: "完整说明" },
            sourceId: "item-1",
            sourceText: "原文证据",
            confidence: 0.9,
            status: "pending_review",
            version: 1,
          }],
        },
      },
    }));

    await waitFor(() => expect(onSynthesize).toHaveBeenCalledWith(reviewSession.id, reviewSession.version));
    expect(screen.getByRole("tab", { name: "综合归纳（推荐）" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "按资料查看" })).toBeInTheDocument();
  });

  it("does not synthesize a stale completed review while newly attached sources are processing", async () => {
    const onSynthesize = vi.fn().mockResolvedValue(undefined);
    renderPage(buildProps({
      onSynthesize,
      session: {
        ...reviewSession,
        status: "processing",
        synthesisStatus: "pending",
        synthesisVersion: 0,
        contentReview: {
          id: "review-from-previous-imports",
          batchId: "batch-1",
          status: "review",
          provider: "deepseek",
          model: "deepseek-v4-flash",
          attempts: 1,
          counts: { pending_review: 1 },
          stage: "completed",
          stageMessage: "已完成旧资料分析，共生成 1 条候选",
          progressCurrent: 1,
          progressTotal: 1,
          candidates: [],
        },
      },
    }));

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(onSynthesize).not.toHaveBeenCalled();
  });

  it("shows the real analysis failure message and keeps retry available", async () => {
    renderPage(buildProps({
      session: {
        ...reviewSession,
        status: "manual_required",
        contentReview: {
          id: "review-failed-1",
          batchId: "batch-1",
          status: "manual_required",
          provider: "deepseek",
          model: "deepseek-v4-flash",
          attempts: 1,
          failureCode: "classification_internal_error",
          counts: {},
          stage: "failed",
          stageMessage: "智能整理未完成，可以安全重试",
          progressCurrent: 1,
          progressTotal: 1,
          candidates: [],
        },
      },
    }));

    expect(screen.getByText("智能分析未完成")).toBeInTheDocument();
    expect(screen.getByText("智能整理未完成，可以安全重试")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新智能分析" })).toBeEnabled();
    expect(screen.queryByText("分析完成，等待复核")).not.toBeInTheDocument();
  });

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

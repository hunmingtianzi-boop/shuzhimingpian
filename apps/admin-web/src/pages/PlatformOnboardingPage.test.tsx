import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PlatformOnboardingSession } from "../api/types";
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
  businessProfile: [
    {
      field: "business_positioning",
      value: "面向先进制造企业的复合材料研发服务商",
      confidence: 0.88,
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
  createdAt: "2026-07-15T12:00:00Z",
  updatedAt: "2026-07-15T12:05:00Z",
  temporaryCredentialResetAvailable: false,
};

const reviewCandidate = {
  id: "candidate-1",
  runId: "run-1",
  category: "products" as const,
  payload: {
    name: "材料检测平台",
    category: "检测服务",
    summary: "复合材料检测",
    detail: "提供研发验证服务",
    audience: "先进制造企业",
    price_boundary: "按项目报价",
  },
  sourceId: "source-1",
  sourceText: "平台为制造企业提供材料检测服务。",
  confidence: 0.91,
  status: "pending_review" as const,
  version: 1,
};

function props(overrides: Partial<PlatformOnboardingPageProps> = {}): PlatformOnboardingPageProps {
  return {
    session: reviewSession,
    importItems: [
      { id: "item-1", fileName: "企业介绍.pdf", status: "completed" },
    ],
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

async function fillConfirmationGate(user: ReturnType<typeof userEvent.setup>) {
  if (!screen.queryByRole("heading", { name: "人工复核与确认" })) {
    await user.click(
      screen.getByRole("button", { name: /人工复核与确认/ }),
    );
    await screen.findByRole("heading", { name: "人工复核与确认" });
  }
  await user.click(screen.getByRole("checkbox", { name: "我已逐项复核企业信息" }));
  await user.click(
    screen.getByRole("checkbox", { name: "我已核对管理员账号与交付对象" }),
  );
  await user.click(
    screen.getByRole("checkbox", { name: "我已核对初始名片，并确认保持草稿" }),
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
  it("opens retained task history and refreshes the latest name after a rename conflict", async () => {
    const user = userEvent.setup();
    const onOpenSession = vi.fn();
    const onRefresh = vi.fn();
    const onRename = vi.fn().mockRejectedValue({ status: 409, code: "VERSION_CONFLICT" });
    const expired = {
      ...reviewSession,
      id: "expired-task",
      displayName: "旧客户建企",
      status: "expired" as const,
      expiresAt: "2026-07-16T12:00:00Z",
    };
    render(
      <PlatformOnboardingPage
        {...props({
          sessions: [reviewSession, expired],
          onOpenSession,
          onRefresh,
          onRename,
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: /旧客户建企/ }));
    expect(onOpenSession).toHaveBeenCalledWith("expired-task");
    expect(screen.getByText("已过期")).toBeInTheDocument();

    const name = screen.getByLabelText("任务名称");
    await user.clear(name);
    await user.type(name, "阿特拉斯华东建企");
    await user.click(screen.getByRole("button", { name: "保存名称" }));

    await waitFor(() =>
      expect(onRename).toHaveBeenCalledWith(
        reviewSession.id,
        reviewSession.version,
        "阿特拉斯华东建企",
      ),
    );
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("会话版本冲突")).toBeInTheDocument();
  });

  it("selects only complete pending candidates as drafts and summarizes the final choice", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const session: PlatformOnboardingSession = {
      ...reviewSession,
      contentReview: {
        id: "run-1",
        batchId: "batch-1",
        status: "review" as const,
        provider: "deepseek",
        model: "flash",
        attempts: 1,
        counts: { products: 1, unclassified: 1, faqs: 1 },
        candidates: [
          reviewCandidate,
          {
            ...reviewCandidate,
            id: "candidate-unclassified",
            category: "unclassified" as const,
            payload: { text: "待判断内容", reason: "缺少上下文" },
          },
          {
            ...reviewCandidate,
            id: "candidate-ignored",
            category: "faqs" as const,
            payload: { question: "是否支持试用？", answer: "请联系企业顾问。" },
            status: "ignored" as const,
          },
        ],
      },
    };
    render(
      <PlatformOnboardingPage
        {...props({
          session,
          initialReview: {
            tenantName: "阿特拉斯租户",
            companyName: "阿特拉斯材料实验室",
            initialCardDisplayName: "陈工程师",
          },
          onConfirm,
        })}
      />,
    );

    expect(await screen.findByRole("checkbox", { name: "创建为草稿" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: /人工复核与确认/ }));
    const summary = screen.getByLabelText("候选导入确认摘要");
    expect(summary).toHaveTextContent("创建为草稿 1 条");
    expect(summary).toHaveTextContent("本次不创建 1 条");
    expect(summary).toHaveTextContent("已忽略 1 条");

    await fillConfirmationGate(user);
    await user.click(screen.getByRole("button", { name: "确认并激活企业" }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onConfirm).toHaveBeenCalledWith(
      session.id,
      expect.objectContaining({
        candidateSelections: [
          { id: reviewCandidate.id, expectedVersion: 1, applyFields: [] },
        ],
      }),
    );
  });

  it("resets fields when reclassifying and supports explicitly ignoring a candidate", async () => {
    const user = userEvent.setup();
    const onIgnoreCandidate = vi.fn().mockResolvedValue(undefined);
    render(
      <PlatformOnboardingPage
        {...props({
          session: {
            ...reviewSession,
            contentReview: {
              id: "run-1",
              batchId: "batch-1",
              status: "review",
              provider: "deepseek",
              model: "flash",
              attempts: 1,
              counts: { products: 1 },
              candidates: [reviewCandidate],
            },
          },
          onUpdateCandidate: vi.fn().mockResolvedValue(undefined),
          onIgnoreCandidate,
        })}
      />,
    );

    await user.selectOptions(screen.getByLabelText("候选分类"), "faqs");
    expect(screen.getByLabelText("问题")).toHaveValue("");
    expect(screen.getByLabelText("答案")).toHaveValue("");
    expect(screen.queryByLabelText("适用对象")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "忽略此候选" }));
    await waitFor(() => expect(onIgnoreCandidate).toHaveBeenCalledWith(reviewSession.id, expect.objectContaining({ id: "candidate-1" })));
  });

  it("renders localized review status labels", () => {
    render(<PlatformOnboardingPage {...props({
      session: {
        ...reviewSession,
        contentReview: {
          id: "run-1",
          batchId: "batch-1",
          status: "review",
          provider: "deepseek",
          model: "flash",
          attempts: 1,
          counts: { products: 1 },
          candidates: [
            { ...reviewCandidate, status: "ignored" },
          ],
        },
      },
    })} />);

    expect(screen.getByText("已忽略")).toBeInTheDocument();
  });

  it("keeps parsed drafts usable when LLM is unavailable and uploads only to the server session", async () => {
    const user = userEvent.setup();
    const onUpload = vi.fn().mockResolvedValue(undefined);
    render(
      <PlatformOnboardingPage
        {...props({
          session: { ...reviewSession, status: "manual_required", suggestions: [] },
          llmAvailability: "unavailable",
          onUpload,
        })}
      />,
    );

    expect(screen.getByText("LLM 当前不可用，已切换为人工填写")).toBeInTheDocument();
    expect(screen.getByText(/已成功解析的资料草稿不会回滚/)).toBeInTheDocument();
    expect(screen.getByText("当前使用人工填写")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始智能分析" })).toBeDisabled();

    const file = new File(["company profile"], "补充资料.txt", { type: "text/plain" });
    await user.upload(screen.getByLabelText("选择建企资料"), file);
    await user.click(screen.getByRole("button", { name: "上传并解析（1）" }));

    await waitFor(() => expect(onUpload).toHaveBeenCalledTimes(1));
    expect(onUpload).toHaveBeenCalledWith(reviewSession.id, [file]);
    expect(JSON.stringify(onUpload.mock.calls[0])).not.toMatch(/tenantId|companyId/);
  });

  it("shows source evidence and never applies a suggestion until the user chooses it", async () => {
    const user = userEvent.setup();
    render(<PlatformOnboardingPage {...props()} />);

    await user.click(screen.getByRole("button", { name: /人工复核与确认/ }));
    const companyInput = await screen.findByLabelText("企业名称");
    expect(companyInput).toHaveValue("");
    await user.click(screen.getByRole("button", { name: /资料与智能候选/ }));
    const suggestion = screen.getByLabelText("企业名称建议");
    expect(within(suggestion).getByText("阿特拉斯材料实验室专注复合材料研发。")).toBeInTheDocument();
    expect(within(suggestion).getByText("导入项：item-1")).toBeInTheDocument();
    expect(within(suggestion).getByText("高置信 · 生成版本 3")).toBeInTheDocument();
    await user.click(within(suggestion).getByRole("button", { name: "采用建议" }));
    await user.click(screen.getByRole("button", { name: /人工复核与确认/ }));
    expect(screen.getByLabelText("企业名称")).toHaveValue("阿特拉斯材料实验室");
  });

  it("blocks analysis and confirmation while a real import item is pending, then unlocks", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <PlatformOnboardingPage
        {...props({
          session: {
            ...reviewSession,
            status: "processing",
            suggestions: [],
            businessProfile: [],
          },
          importItems: [
            { id: "item-1", fileName: "企业介绍.pdf", status: "processing" },
          ],
          initialReview: {
            tenantName: "阿特拉斯租户",
            companyName: "阿特拉斯材料实验室",
            initialCardDisplayName: "陈工程师",
          },
        })}
      />,
    );

    expect(screen.getByRole("button", { name: "开始智能分析" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /人工复核与确认/ })).toBeDisabled();
    expect(screen.getByRole("region", { name: "资料分析进度" })).toHaveTextContent(
      "正在处理",
    );

    rerender(
      <PlatformOnboardingPage
        {...props({
          session: {
            ...reviewSession,
            status: "processing",
            suggestions: [],
            businessProfile: [],
          },
          importItems: [
            { id: "item-1", fileName: "企业介绍.pdf", status: "completed" },
          ],
          initialReview: {
            tenantName: "阿特拉斯租户",
            companyName: "阿特拉斯材料实验室",
            initialCardDisplayName: "陈工程师",
          },
        })}
      />,
    );

    expect(screen.getByText("1/1 个文件已处理")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始智能分析" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /人工复核与确认/ }));
    await fillConfirmationGate(user);
    expect(screen.getByRole("button", { name: "确认并激活企业" })).toBeEnabled();
  });

  it("shows a sourced business profile without applying it to public fields", () => {
    render(<PlatformOnboardingPage {...props()} />);
    expect(screen.getByRole("heading", { name: "企业业务画像（待审核）" })).toBeInTheDocument();
    expect(screen.getByText("面向先进制造企业的复合材料研发服务商")).toBeInTheDocument();
    expect(screen.getByLabelText("业务定位建议")).not.toHaveTextContent("采用建议");
    expect(screen.getByRole("region", { name: "资料分析进度" })).toHaveTextContent(
      "分析完成，等待复核",
    );
    expect(screen.queryByText("服务端会话")).not.toBeInTheDocument();
    expect(screen.queryByText("当前版本")).not.toBeInTheDocument();
    expect(screen.getByText("查看处理编号")).toBeInTheDocument();
  });

  it("shows truthful analysis feedback while the generation request is pending", async () => {
    const user = userEvent.setup();
    let finish!: () => void;
    const onGenerate = vi.fn(
      () => new Promise<void>((resolve) => {
        finish = resolve;
      }),
    );
    render(
      <PlatformOnboardingPage
        {...props({
          session: { ...reviewSession, suggestions: [], businessProfile: [] },
          onGenerate,
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "开始智能分析" }));
    expect(screen.getByRole("button", { name: "正在分析企业资料" })).toBeDisabled();
    expect(screen.getByRole("region", { name: "资料分析进度" })).toHaveTextContent(
      "正在识别业务定位、产品服务、客户与资料缺口",
    );
    finish();
    await waitFor(() => expect(onGenerate).toHaveBeenCalledWith(reviewSession.id, reviewSession.version));
  });

  it("offers a clear next step after a company is confirmed", async () => {
    const user = userEvent.setup();
    const onStartAnother = vi.fn();
    const onOpenEnterprises = vi.fn();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(
      <PlatformOnboardingPage
        {...props({
          session: {
            ...reviewSession,
            status: "confirmed",
            confirmedEnterprise: {
              tenantId: "tenant-1",
              tenantSlug: "atlas-labs",
              tenantName: "阿特拉斯租户",
              companyId: "company-1",
              companyName: "阿特拉斯材料实验室",
              status: "active",
              adminUserId: "user-1",
              adminMembershipId: "membership-1",
              initialCardId: "card-1",
              initialCardSlug: "atlas-card",
              createdAt: "2026-07-15T12:10:00Z",
            },
          },
          onRefresh: vi.fn(),
          onStartAnother,
          onOpenEnterprises,
        })}
      />,
    );

    expect(screen.getByRole("button", { name: "刷新结果" })).toBeInTheDocument();
    const cardUrl = `${window.location.origin}/c/atlas-card`;
    expect(screen.getByLabelText("企业名片固定网址")).toHaveValue(cardUrl);
    expect(screen.getByText("草稿暂不可访问，企业管理员发布后生效")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "打开企业名片网址" })).not.toBeInTheDocument();
    const adminLink = screen.getByRole("link", { name: "打开企业管理后台" });
    expect(adminLink).toHaveAttribute("target", "_blank");
    expect(adminLink).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByLabelText("企业管理后台")).toHaveValue(
      `${window.location.origin}/`,
    );
    await user.click(screen.getByRole("button", { name: "复制企业名片网址" }));
    expect(writeText).toHaveBeenCalledWith(cardUrl);
    expect(screen.getByText("企业名片网址已复制。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "复制企业管理后台网址" }));
    expect(writeText).toHaveBeenLastCalledWith(`${window.location.origin}/`);
    expect(screen.getByText("企业管理后台网址已复制。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "继续开通新企业" }));
    expect(onStartAnother).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "前往企业中心" }));
    expect(onOpenEnterprises).toHaveBeenCalledTimes(1);
  });

  it("confirms temporary password regeneration and renders the returned password once with its expiry", async () => {
    const user = userEvent.setup();
    const completed: PlatformOnboardingSession = {
      ...reviewSession,
      status: "confirmed",
      version: 8,
      temporaryCredentialResetAvailable: true,
      confirmedEnterprise: {
        tenantId: "tenant-1",
        tenantSlug: "atlas-labs",
        tenantName: "阿特拉斯租户",
        companyId: "company-1",
        companyName: "阿特拉斯材料实验室",
        status: "active",
        adminUserId: "user-1",
        adminMembershipId: "membership-1",
        initialCardId: "card-1",
        initialCardSlug: "atlas-card",
        createdAt: "2026-07-15T12:10:00Z",
      },
    };
    const regenerated: PlatformOnboardingSession = {
      ...completed,
      version: 9,
      credentialDelivery: {
        account: "admin@atlas.example",
        temporaryPassword: "new-one-time-password",
        expiresAt: "2026-07-22T12:30:00Z",
        shownOnce: true,
      },
    };
    const onRegenerateTemporaryCredential = vi.fn().mockResolvedValue(regenerated);
    render(
      <PlatformOnboardingPage
        {...props({
          session: completed,
          onRegenerateTemporaryCredential,
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "重新生成临时密码" }));
    expect(screen.getByText(/旧临时密码会立即失效/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认重新生成" }));

    await waitFor(() =>
      expect(onRegenerateTemporaryCredential).toHaveBeenCalledWith(completed.id, 8),
    );
    expect(await screen.findByLabelText("一次性临时密码")).toHaveValue(
      "new-one-time-password",
    );
    expect(screen.getByText(/有效至/)).toBeInTheDocument();
  });

  it("keeps the confirmed result visible as soon as confirmation resolves, without waiting for a parent rerender", async () => {
    const user = userEvent.setup();
    const confirmed: PlatformOnboardingSession = {
      ...reviewSession,
      status: "confirmed",
      version: 8,
      confirmedEnterprise: {
        tenantId: "tenant-1",
        tenantSlug: "atlas-labs",
        tenantName: "阿特拉斯租户",
        companyId: "company-1",
        companyName: "阿特拉斯材料实验室",
        status: "active",
        adminUserId: "user-1",
        adminMembershipId: "membership-1",
        initialCardId: "card-1",
        initialCardSlug: "atlas-card",
        createdAt: "2026-07-15T12:10:00Z",
      },
    };
    const onConfirm = vi.fn().mockResolvedValue(confirmed);
    const pageProps = props({
      initialReview: {
        tenantName: "阿特拉斯租户",
        companyName: "阿特拉斯材料实验室",
        initialCardDisplayName: "陈工程师",
      },
      onConfirm,
    });
    const view = render(<PlatformOnboardingPage {...pageProps} />);

    await fillConfirmationGate(user);
    await waitFor(() => expect(screen.getByLabelText("租户名称")).toHaveValue("阿特拉斯租户"));
    await user.click(screen.getByRole("button", { name: "确认并激活企业" }));

    expect(await screen.findByRole("heading", { name: "企业已由服务端确认激活" })).toBeInTheDocument();
    expect(screen.getByLabelText("企业名片固定网址")).toHaveValue(
      `${window.location.origin}/c/atlas-card`,
    );
    expect(screen.queryByRole("heading", { name: "人工复核与确认" })).not.toBeInTheDocument();

    view.rerender(<PlatformOnboardingPage {...pageProps} />);
    expect(screen.getByRole("heading", { name: "企业已由服务端确认激活" })).toBeInTheDocument();
  });

  it("requires explicit enterprise, admin and draft-card review and submits expectedVersion", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(
      <PlatformOnboardingPage
        {...props({
          initialReview: {
            tenantName: "阿特拉斯租户",
            companyName: "阿特拉斯材料实验室",
            initialCardDisplayName: "陈工程师",
          },
          onConfirm,
        })}
      />,
    );

    await fillConfirmationGate(user);
    const confirm = screen.getByRole("button", { name: "确认并激活企业" });
    await waitFor(() => expect(screen.getByLabelText("租户名称")).toHaveValue("阿特拉斯租户"));
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onConfirm).toHaveBeenCalledWith(
      reviewSession.id,
      expect.objectContaining({
        expectedVersion: 7,
        tenantName: "阿特拉斯租户",
        companyName: "阿特拉斯材料实验室",
        initialCardDisplayName: "陈工程师",
      }),
    );
  });

  it("keeps review open on a version conflict and requires a cancel reason", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockRejectedValue({ status: 409, code: "VERSION_CONFLICT" });
    const onCancel = vi.fn().mockResolvedValue(undefined);
    render(
      <PlatformOnboardingPage
        {...props({
          initialReview: {
            tenantName: "阿特拉斯租户",
            companyName: "阿特拉斯材料实验室",
            initialCardDisplayName: "陈工程师",
          },
          onConfirm,
          onCancel,
        })}
      />,
    );

    await fillConfirmationGate(user);
    await waitFor(() => expect(screen.getByLabelText("企业名称")).toHaveValue("阿特拉斯材料实验室"));
    await user.click(screen.getByRole("button", { name: "确认并激活企业" }));
    expect(await screen.findByText("会话版本冲突")).toBeInTheDocument();
    expect(screen.getByText(/请刷新后重新复核/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "人工复核与确认" })).toBeInTheDocument();

    const cancelOpener = screen.getByRole("button", { name: "取消会话" });
    fireEvent.click(cancelOpener);
    const cancelTitle = await screen.findByText("取消资料辅助建企会话");
    const dialog = cancelTitle.closest('[role="dialog"]');
    expect(dialog).not.toBeNull();
    const cancelConfirm = within(dialog as HTMLElement)
      .getByText("确认取消会话")
      .closest("button") as HTMLButtonElement;
    expect(cancelConfirm).toBeDisabled();
    fireEvent.change(within(dialog as HTMLElement).getByLabelText("取消原因"), {
      target: { value: "wrong-customer-document" },
    });
    expect(cancelConfirm).toBeEnabled();
    await user.click(cancelConfirm);
    await waitFor(() =>
      expect(onCancel).toHaveBeenCalledWith(reviewSession.id, "wrong-customer-document", 7),
    );
    await waitFor(() => expect(cancelOpener).toHaveFocus());
  });

  it("does not mislabel business conflicts as a version conflict", async () => {
    const user = userEvent.setup();
    const onStart = vi.fn().mockRejectedValue({
      status: 409,
      code: "ACCOUNT_CONFLICT",
      message: "管理员账号已绑定其他企业。",
    });
    render(<PlatformOnboardingPage {...props({ session: undefined, onStart })} />);

    await user.type(screen.getByLabelText(/租户标识/), "conflict-company");
    await user.type(screen.getByLabelText(/租户名称/), "冲突企业");
    await user.type(screen.getByLabelText(/管理员账号/), "admin@example.com");
    await user.type(screen.getByLabelText(/管理员姓名/), "管理员");
    await user.click(screen.getByRole("button", { name: "进入资料导入" }));

    expect(await screen.findByText("操作未完成")).toBeInTheDocument();
    expect(screen.queryByText("会话版本冲突")).not.toBeInTheDocument();
    expect(screen.getByText("管理员账号已绑定其他企业。")).toBeInTheDocument();
  });

  it("retains named landmarks and reachable primary actions at a 390px viewport", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    window.dispatchEvent(new Event("resize"));
    render(
      <PlatformOnboardingPage
        {...props({
          session: { ...reviewSession, status: "manual_required", suggestions: [] },
          llmAvailability: "failed",
        })}
      />,
    );

    expect(screen.getByRole("navigation", { name: "资料辅助建企步骤" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "资料分析与业务归纳" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "人工复核与确认" })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /人工复核与确认/ }));
    expect(screen.getByRole("heading", { name: "人工复核与确认" })).toBeInTheDocument();
    expect(screen.getByLabelText("开通会话主操作")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "取消会话" })).toBeVisible();
    expect(screen.getByRole("button", { name: "确认并激活企业" })).toBeVisible();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { platformApi } from "../api/platformApi";
import type { PlatformOnboardingSession } from "../api/types";
import { rememberPlatformOnboardingTask } from "../utils/platformOnboardingTask";
import { PlatformOnboardingTaskDock } from "./PlatformOnboardingTaskDock";

const failedSession: PlatformOnboardingSession = {
  id: "onboarding-failed-1",
  displayName: "机器人蛋糕公司资料建企",
  status: "manual_required",
  tenantSlug: "robot-cake",
  version: 3,
  importBatchIds: ["batch-1"],
  suggestions: [],
  businessProfile: [],
  contentReview: {
    id: "review-1",
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
    startedAt: "2026-08-25T10:00:00Z",
    completedAt: "2026-08-25T10:00:06Z",
  },
  temporaryCredentialResetAvailable: false,
  createdAt: "2026-08-25T09:59:00Z",
  updatedAt: "2026-08-25T10:00:06Z",
};

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  window.history.replaceState({}, "", "/");
});

beforeEach(() => {
  vi.spyOn(platformApi, "getOnboardingImports").mockResolvedValue({
    sessionId: failedSession.id,
    settled: true,
    items: [
      { id: "source-1", fileName: "资料一.pdf", sourceType: "PDF", status: "completed", createdAt: "2026-08-25T10:00:00Z" },
      { id: "source-2", fileName: "资料二.docx", sourceType: "DOCX", status: "completed", createdAt: "2026-08-25T10:00:00Z" },
      { id: "source-3", fileName: "资料三.txt", sourceType: "TXT", status: "completed", createdAt: "2026-08-25T10:00:00Z" },
    ],
  });
});

describe("PlatformOnboardingTaskDock", () => {
  it("reports a failed analysis as actionable failure instead of success", async () => {
    vi.spyOn(platformApi, "getOnboarding").mockResolvedValue(failedSession);
    rememberPlatformOnboardingTask(failedSession.id, failedSession.displayName);
    const user = userEvent.setup();

    render(<PlatformOnboardingTaskDock />);

    const trigger = await screen.findByRole("button", { name: /分析未完成/ });
    expect(trigger.closest("aside")).toHaveAttribute("data-state", "failure");
    expect(screen.queryByText("分析完成")).not.toBeInTheDocument();

    await user.hover(trigger);
    expect(screen.getByText("智能整理未完成，可以安全重试")).toBeInTheDocument();
    expect(screen.getAllByText("任务需要处理")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "返回处理" })).toBeInTheDocument();
  });

  it("labels completed manual-review sessions without pretending they succeeded", async () => {
    vi.spyOn(platformApi, "getOnboarding").mockResolvedValue({
      ...failedSession,
      contentReview: {
        ...failedSession.contentReview!,
        stage: "completed",
        stageMessage: "候选等待确认",
      },
    });
    rememberPlatformOnboardingTask(failedSession.id, failedSession.displayName);

    render(<PlatformOnboardingTaskDock />);

    expect(await screen.findByRole("button", { name: /需要人工处理/ })).toBeInTheDocument();
    expect(screen.getByText("未形成可自动确认的候选，请返回任务补充或重新分析")).toBeInTheDocument();
    expect(screen.queryByText("分析完成")).not.toBeInTheDocument();
  });

  it("keeps reporting progress while cross-source synthesis is running", async () => {
    vi.spyOn(platformApi, "getOnboarding").mockResolvedValue({
      ...failedSession,
      status: "review",
      synthesisStatus: "processing",
      synthesisStartedAt: new Date().toISOString(),
      contentReview: {
        ...failedSession.contentReview!,
        status: "review",
        stage: "completed",
        stageMessage: "候选等待确认",
      },
    });
    rememberPlatformOnboardingTask(failedSession.id, failedSession.displayName);

    render(<PlatformOnboardingTaskDock />);

    const trigger = await screen.findByRole("button", { name: /正在综合全部资料/ });
    expect(trigger.closest("aside")).toHaveAttribute("data-state", "running");
    expect(screen.getByText("正在对照全部资料，合并同一事项并保留来源、冲突和待补信息")).toBeInTheDocument();
    expect(screen.getByText("正在合并相同知识")).toBeInTheDocument();
    expect(screen.getByText("正在读取并分析资料")).toBeInTheDocument();
    expect(screen.queryByText(failedSession.displayName)).not.toBeInTheDocument();
    expect(screen.queryByText("分析完成")).not.toBeInTheDocument();
  });

  it("includes persisted cross-source candidates in the displayed total", async () => {
    vi.spyOn(platformApi, "getOnboarding").mockResolvedValue({
      ...failedSession,
      status: "review",
      synthesisStatus: "ready",
      synthesisStartedAt: "2026-08-25T10:00:10Z",
      synthesisCompletedAt: "2026-08-25T10:00:17Z",
      contentReview: {
        ...failedSession.contentReview!,
        status: "review",
        stage: "completed",
        counts: { faq: 2 },
        candidates: [
          ...failedSession.contentReview!.candidates,
          ...Array.from({ length: 3 }, (_, index) => ({
            id: `candidate-${index}`,
            runId: "review-1",
            category: "faqs" as const,
            payload: { question: `问题 ${index}`, answer: `答案 ${index}` },
            sourceId: index === 2 ? "synthesis:onboarding-failed-1:2" : `source-${index}`,
            sourceText: `证据 ${index}`,
            confidence: 0.9,
            status: "pending_review" as const,
            version: 1,
          })),
        ],
      },
    });
    rememberPlatformOnboardingTask(failedSession.id, failedSession.displayName);

    render(<PlatformOnboardingTaskDock />);

    expect(await screen.findByRole("button", { name: /分析完成\s*3 条候选/ })).toBeInTheDocument();
    expect(screen.getByText("7 秒")).toBeInTheDocument();
    expect(screen.getByText("已完成 3 份资料分析")).toBeInTheDocument();
  });
});

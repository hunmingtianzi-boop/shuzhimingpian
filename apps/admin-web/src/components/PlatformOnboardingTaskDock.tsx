import { useCallback, useEffect, useMemo, useState } from "react";

import { platformApi } from "../api/platformApi";
import type { PlatformOnboardingSession } from "../api/types";
import { APP_PATHS, appHref } from "../routing";
import {
  clearRememberedPlatformOnboardingTask,
  PLATFORM_ONBOARDING_TASK_EVENT,
  readRememberedPlatformOnboardingTask,
} from "../utils/platformOnboardingTask";
import { BackgroundTaskDock } from "./BackgroundTaskDock";

const stageLabels = {
  queued: "准备分析资料",
  discovering: "识别各份资料",
  enriching: "整理资料候选",
  validating: "核对来源与冲突",
  finalizing: "生成分析结果",
  completed: "候选等待确认",
  failed: "任务需要处理",
} as const;

const stageProgress = {
  queued: 0.08,
  discovering: 0.24,
  enriching: 0.52,
  validating: 0.76,
  finalizing: 0.92,
  completed: 1,
  failed: 1,
} as const;

function stageMessage(stage: keyof typeof stageProgress, sourceCount: number): string {
  switch (stage) {
    case "discovering": return `正在读取 ${sourceCount} 份资料`;
    case "enriching": return "正在识别各份资料中的业务、案例和问答";
    case "validating": return "正在核对资料来源与内容冲突";
    case "finalizing": return "正在生成逐份候选";
    case "completed": return `已完成 ${sourceCount} 份资料分析`;
    case "failed": return "智能分析未完成，可以安全重试";
    default: return `准备分析 ${sourceCount} 份资料`;
  }
}

function elapsedLabel(session: PlatformOnboardingSession, fallbackStartedAt: string, now: number): string {
  const review = session.contentReview;
  const requestedAt = Date.parse(fallbackStartedAt);
  const reviewStartedAt = review?.startedAt ? Date.parse(review.startedAt) : requestedAt;
  const synthesisStartedAt = session.synthesisStartedAt ? Date.parse(session.synthesisStartedAt) : reviewStartedAt;
  const started = session.synthesisStartedAt
    ? synthesisStartedAt
    : Math.max(requestedAt, reviewStartedAt);
  const ended = session.synthesisStatus === "processing"
    ? now
    : session.synthesisCompletedAt
      ? Date.parse(session.synthesisCompletedAt)
      : review?.completedAt ? Date.parse(review.completedAt) : now;
  const seconds = Math.max(0, Math.round((ended - started) / 1000));
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} 分 ${seconds % 60} 秒`;
}

export function PlatformOnboardingTaskDock() {
  const [session, setSession] = useState<PlatformOnboardingSession>();
  const [sourceCount, setSourceCount] = useState(0);
  const [startedAt, setStartedAt] = useState<string>();
  const [now, setNow] = useState(() => Date.now());

  const refresh = useCallback(async () => {
    const remembered = readRememberedPlatformOnboardingTask();
    if (!remembered) {
      setSession(undefined);
      setSourceCount(0);
      setStartedAt(undefined);
      return;
    }
    setStartedAt(remembered.startedAt);
    try {
      const [nextSession, imports] = await Promise.all([
        platformApi.getOnboarding(remembered.sessionId),
        platformApi.getOnboardingImports(remembered.sessionId),
      ]);
      setSession(nextSession);
      setSourceCount(imports.items.length);
    } catch {
      clearRememberedPlatformOnboardingTask();
      setSession(undefined);
      setSourceCount(0);
    }
  }, []);

  useEffect(() => {
    void refresh();
    window.addEventListener(PLATFORM_ONBOARDING_TASK_EVENT, refresh);
    return () => window.removeEventListener(PLATFORM_ONBOARDING_TASK_EVENT, refresh);
  }, [refresh]);

  const processing = session?.contentReview?.status === "processing"
    || session?.synthesisStatus === "processing"
    || !session?.contentReview;
  useEffect(() => {
    if (!session || !processing) return undefined;
    const timer = window.setInterval(() => {
      void refresh();
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [processing, refresh, session?.id]);

  useEffect(() => {
    if (!session || !processing) return undefined;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [processing, session?.id]);

  const candidateCount = useMemo(
    () => Math.max(
      Object.values(session?.contentReview?.counts ?? {}).reduce((sum, value) => sum + value, 0),
      session?.contentReview?.candidates.length ?? 0,
    ),
    [session?.contentReview?.candidates.length, session?.contentReview?.counts],
  );
  if (!session || !startedAt) return null;

  const review = session.contentReview;
  const stage = review?.stage ?? "queued";
  const failed = review?.stage === "failed";
  const synthesisFailed = session.synthesisStatus === "failed";
  const synthesizing = session.synthesisStatus === "processing";
  const manualRequired = review?.status === "manual_required" && !failed;
  const needsAttention = failed || synthesisFailed || manualRequired;
  const succeeded = review?.stage === "completed"
    && review?.status === "review"
    && session.synthesisStatus === "ready";
  const backendStageMessage = review?.stageMessage?.trim();
  const usableBackendStageMessage = backendStageMessage
    && (review?.status === "processing"
      || review?.stage === "failed"
      || (review?.stage === "completed" && backendStageMessage.startsWith("已完成")))
    ? backendStageMessage
    : undefined;
  const resolvedStageLabel = failed || synthesisFailed
    ? stageLabels.failed
    : synthesizing
      ? "正在合并相同知识"
    : manualRequired
      ? "需人工补充"
      : stageLabels[stage];
  const resolvedStageMessage = failed || synthesisFailed
    ? session.synthesisFailureCode ?? review?.stageMessage ?? "智能整理未完成，可以安全重试"
    : synthesizing
      ? "正在对照全部资料，合并同一事项并保留来源、冲突和待补信息"
    : manualRequired
      ? "未形成可自动确认的候选，请返回任务补充或重新分析"
      : usableBackendStageMessage
        ?? stageMessage(stage, sourceCount || session.importBatchIds.length);
  const progress = synthesizing ? 0.94 : stageProgress[stage];
  const openResult = () => {
    const target = appHref(APP_PATHS.platformOnboarding);
    window.history.pushState({}, "", target);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  return <BackgroundTaskDock
    ariaLabel="建企资料智能分析任务"
    state={needsAttention ? "failure" : succeeded ? "success" : "running"}
    title={failed || synthesisFailed
      ? "分析未完成"
      : synthesizing
        ? "正在综合全部资料"
        : manualRequired
          ? "需要人工处理"
          : succeeded
            ? "分析完成"
            : stageLabels[stage]}
    subtitle={needsAttention
      ? session.displayName
      : candidateCount > 0
        ? `${candidateCount} 条候选已生成`
        : "正在读取并分析资料"}
    stageLabel={resolvedStageLabel}
    stageMessage={resolvedStageMessage}
    elapsedLabel={elapsedLabel(session, startedAt, now)}
    candidateLabel={`${candidateCount} 条`}
    progress={progress}
    actionLabel={needsAttention ? "返回处理" : succeeded ? "查看分析结果" : "返回建企任务"}
    onOpen={openResult}
    onClose={() => {
      clearRememberedPlatformOnboardingTask();
      setSession(undefined);
    }}
  />;
}

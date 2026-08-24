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
  queued: "等待后台处理",
  discovering: "识别候选目录",
  enriching: "补全候选字段",
  validating: "核对来源证据",
  finalizing: "整理最终结果",
  completed: "候选等待确认",
  failed: "任务需要处理",
} as const;

function elapsedLabel(session: PlatformOnboardingSession, fallbackStartedAt: string, now: number): string {
  const review = session.contentReview;
  const started = Date.parse(review?.startedAt ?? fallbackStartedAt);
  const ended = review?.completedAt ? Date.parse(review.completedAt) : now;
  const seconds = Math.max(0, Math.round((ended - started) / 1000));
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} 分 ${seconds % 60} 秒`;
}

export function PlatformOnboardingTaskDock() {
  const [session, setSession] = useState<PlatformOnboardingSession>();
  const [startedAt, setStartedAt] = useState<string>();
  const [now, setNow] = useState(() => Date.now());

  const refresh = useCallback(async () => {
    const remembered = readRememberedPlatformOnboardingTask();
    if (!remembered) {
      setSession(undefined);
      setStartedAt(undefined);
      return;
    }
    setStartedAt(remembered.startedAt);
    try {
      setSession(await platformApi.getOnboarding(remembered.sessionId));
    } catch {
      clearRememberedPlatformOnboardingTask();
      setSession(undefined);
    }
  }, []);

  useEffect(() => {
    void refresh();
    window.addEventListener(PLATFORM_ONBOARDING_TASK_EVENT, refresh);
    return () => window.removeEventListener(PLATFORM_ONBOARDING_TASK_EVENT, refresh);
  }, [refresh]);

  const processing = session?.contentReview?.status === "processing" || !session?.contentReview;
  useEffect(() => {
    if (!session || !processing) return undefined;
    const timer = window.setInterval(() => {
      setNow(Date.now());
      void refresh();
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [processing, refresh, session]);

  const candidateCount = useMemo(
    () => Object.values(session?.contentReview?.counts ?? {}).reduce((sum, value) => sum + value, 0),
    [session?.contentReview?.counts],
  );
  if (!session || !startedAt) return null;

  const review = session.contentReview;
  const stage = review?.stage ?? "queued";
  const finished = Boolean(review && review.status !== "processing");
  const progress = review && review.progressTotal > 0
    ? review.progressCurrent / review.progressTotal
    : undefined;
  const openResult = () => {
    const target = appHref(APP_PATHS.platformOnboarding);
    window.history.pushState({}, "", target);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  return <BackgroundTaskDock
    ariaLabel="建企资料智能分析任务"
    finished={finished}
    title={finished ? "分析完成" : stageLabels[stage]}
    subtitle={candidateCount > 0 ? `${candidateCount} 条候选` : session.displayName}
    stageLabel={stageLabels[stage]}
    stageMessage={review?.stageMessage ?? stageLabels[stage]}
    elapsedLabel={elapsedLabel(session, startedAt, now)}
    candidateLabel={`${candidateCount} 条`}
    progress={progress}
    actionLabel={finished ? "查看分析结果" : "返回建企任务"}
    onOpen={openResult}
    onClose={() => {
      clearRememberedPlatformOnboardingTask();
      setSession(undefined);
    }}
  />;
}

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  contentImportsApi,
  type ContentImportRun,
} from "../api/knowledgeImportsApi";
import { APP_PATHS, appHref } from "../routing";
import {
  clearRememberedContentImportTask,
  CONTENT_IMPORT_TASK_EVENT,
  readRememberedContentImportTask,
  rememberContentImportTask,
} from "../utils/contentImportTask";
import { BackgroundTaskDock } from "./BackgroundTaskDock";

const stageLabels: Record<ContentImportRun["stage"], string> = {
  queued: "等待后台处理",
  discovering: "识别候选目录",
  enriching: "补全候选字段",
  validating: "核对来源证据",
  finalizing: "整理最终结果",
  completed: "候选等待审核",
  failed: "任务需要处理",
};

function elapsedLabel(run: ContentImportRun, now: number): string {
  const started = Date.parse(run.startedAt ?? run.createdAt);
  const ended = run.completedAt ? Date.parse(run.completedAt) : now;
  const seconds = Math.max(0, Math.round((ended - started) / 1000));
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} 分 ${seconds % 60} 秒`;
}

export function ContentImportTaskDock() {
  const [run, setRun] = useState<ContentImportRun>();
  const [now, setNow] = useState(() => Date.now());

  const refresh = useCallback(async () => {
    const remembered = readRememberedContentImportTask();
    try {
      if (remembered) {
        setRun(await contentImportsApi.get(remembered.runId));
        return;
      }
      const processing = (await contentImportsApi.list()).find(
        (item) => item.status === "processing",
      );
      if (processing) {
        rememberContentImportTask(processing.id, processing.batchId);
        setRun(processing);
      } else {
        setRun(undefined);
      }
    } catch {
      clearRememberedContentImportTask();
      setRun(undefined);
    }
  }, []);

  useEffect(() => {
    void refresh();
    window.addEventListener(CONTENT_IMPORT_TASK_EVENT, refresh);
    return () => window.removeEventListener(CONTENT_IMPORT_TASK_EVENT, refresh);
  }, [refresh]);

  useEffect(() => {
    if (!run || run.status !== "processing") return undefined;
    const timer = window.setInterval(() => {
      setNow(Date.now());
      void refresh();
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [refresh, run]);

  const candidateCount = useMemo(
    () => Object.values(run?.counts ?? {}).reduce((sum, value) => sum + value, 0),
    [run?.counts],
  );
  if (!run) return null;

  const finished = run.status !== "processing";
  const progress = run.progressTotal > 0
    ? run.progressCurrent / run.progressTotal
    : undefined;
  const openResult = () => {
    const target = `${appHref(APP_PATHS.imports)}?run=${encodeURIComponent(run.id)}`;
    window.history.pushState({}, "", target);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  return <BackgroundTaskDock
    ariaLabel="资料智能整理任务"
    state={finished ? "success" : "running"}
    title={finished ? "整理完成" : stageLabels[run.stage]}
    subtitle={candidateCount > 0 ? `${candidateCount} 条候选` : "资料智能整理"}
    stageLabel={stageLabels[run.stage]}
    stageMessage={run.stageMessage ?? stageLabels[run.stage]}
    elapsedLabel={elapsedLabel(run, now)}
    candidateLabel={`${candidateCount} 条`}
    progress={progress}
    actionLabel={finished ? "查看整理结果" : "返回任务页面"}
    onOpen={openResult}
    onClose={() => {
      clearRememberedContentImportTask();
      setRun(undefined);
    }}
  />;
}

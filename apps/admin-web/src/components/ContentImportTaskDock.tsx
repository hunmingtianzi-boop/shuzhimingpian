import { Button, ProgressBar } from "@fluentui/react-components";
import {
  CheckmarkCircle24Regular,
  Dismiss20Regular,
  DocumentArrowUp24Regular,
  Open20Regular,
} from "@fluentui/react-icons";
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
  const [expanded, setExpanded] = useState(false);
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

  return (
    <aside
      className={`content-import-task-dock ${expanded ? "is-expanded" : ""}`}
      data-state={finished ? "finished" : "running"}
      aria-label="资料智能整理任务"
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
      onFocus={() => setExpanded(true)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setExpanded(false);
      }}
    >
      <button
        type="button"
        className="content-import-task-dock-trigger"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        <span className="content-import-task-dock-icon" aria-hidden="true">
          {finished ? <CheckmarkCircle24Regular /> : <DocumentArrowUp24Regular />}
        </span>
        <span className="content-import-task-dock-trigger-copy">
          <strong>{finished ? "整理完成" : stageLabels[run.stage]}</strong>
          <small>{candidateCount > 0 ? `${candidateCount} 条候选` : "资料智能整理"}</small>
        </span>
      </button>
      <div className="content-import-task-dock-detail" aria-live="polite">
        <div className="content-import-task-dock-heading">
          <div>
            <span>{finished ? "任务结果" : "正在后台处理"}</span>
            <strong>{run.stageMessage ?? stageLabels[run.stage]}</strong>
          </div>
          {finished && (
            <Button
              appearance="subtle"
              size="small"
              icon={<Dismiss20Regular />}
              aria-label="关闭任务浮窗"
              onClick={() => {
                clearRememberedContentImportTask();
                setRun(undefined);
              }}
            />
          )}
        </div>
        <ProgressBar value={progress} max={1} thickness="medium" />
        <dl className="content-import-task-dock-facts">
          <div><dt>阶段</dt><dd>{stageLabels[run.stage]}</dd></div>
          <div><dt>耗时</dt><dd>{elapsedLabel(run, now)}</dd></div>
          <div><dt>候选</dt><dd>{candidateCount} 条</dd></div>
        </dl>
        <Button
          appearance={finished ? "primary" : "secondary"}
          icon={<Open20Regular />}
          onClick={openResult}
        >
          {finished ? "查看整理结果" : "返回任务页面"}
        </Button>
      </div>
    </aside>
  );
}

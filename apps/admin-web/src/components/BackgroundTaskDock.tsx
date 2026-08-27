import { Button, ProgressBar } from "@fluentui/react-components";
import {
  CheckmarkCircle24Regular,
  Dismiss20Regular,
  DocumentArrowUp24Regular,
  ErrorCircle24Regular,
  Open20Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

export type BackgroundTaskDockProps = {
  ariaLabel: string;
  state: "running" | "success" | "failure";
  title: string;
  subtitle: string;
  stageLabel: string;
  stageMessage: string;
  elapsedLabel: string;
  candidateLabel: string;
  progress?: number;
  actionLabel: string;
  onOpen: () => void;
  onClose?: () => void;
};

export function BackgroundTaskDock({
  ariaLabel,
  state,
  title,
  subtitle,
  stageLabel,
  stageMessage,
  elapsedLabel,
  candidateLabel,
  progress,
  actionLabel,
  onOpen,
  onClose,
}: BackgroundTaskDockProps) {
  const [expanded, setExpanded] = useState(false);
  const finished = state !== "running";

  return (
    <aside
      className={`content-import-task-dock ${expanded ? "is-expanded" : ""}`}
      data-state={state}
      aria-label={ariaLabel}
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
          {state === "failure"
            ? <ErrorCircle24Regular />
            : state === "success"
              ? <CheckmarkCircle24Regular />
              : <DocumentArrowUp24Regular />}
        </span>
        <span className="content-import-task-dock-trigger-copy">
          <strong>{title}</strong>
          <small>{subtitle}</small>
        </span>
      </button>
      <div className="content-import-task-dock-detail" aria-live="polite">
        <div className="content-import-task-dock-heading">
          <div>
            <span>{state === "failure" ? "任务需要处理" : finished ? "任务结果" : "正在后台处理"}</span>
            <strong>{stageMessage}</strong>
          </div>
          {finished && onClose && (
            <Button
              appearance="subtle"
              size="small"
              icon={<Dismiss20Regular />}
              aria-label="关闭任务浮窗"
              onClick={onClose}
            />
          )}
        </div>
        <ProgressBar value={progress} max={1} thickness="medium" />
        <dl className="content-import-task-dock-facts">
          <div><dt>阶段</dt><dd>{stageLabel}</dd></div>
          <div><dt>耗时</dt><dd>{elapsedLabel}</dd></div>
          <div><dt>候选</dt><dd>{candidateLabel}</dd></div>
        </dl>
        <Button
          appearance={finished ? "primary" : "secondary"}
          icon={<Open20Regular />}
          onClick={onOpen}
        >
          {actionLabel}
        </Button>
      </div>
    </aside>
  );
}

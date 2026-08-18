import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { contentImportsApi, type ContentImportRun } from "../api/knowledgeImportsApi";
import { rememberContentImportTask } from "../utils/contentImportTask";
import { ContentImportTaskDock } from "./ContentImportTaskDock";

const processingRun: ContentImportRun = {
  id: "run-1",
  batchId: "batch-1",
  status: "processing",
  provider: "deepseek",
  model: "deepseek-v4-flash",
  attempts: 0,
  counts: { products: 3 },
  stage: "enriching",
  stageMessage: "已发现 3 条候选，正在补全字段",
  progressCurrent: 1,
  progressTotal: 3,
  jobAttempts: 1,
  candidates: [],
  startedAt: "2026-08-18T16:00:00Z",
  createdAt: "2026-08-18T16:00:00Z",
  updatedAt: "2026-08-18T16:00:10Z",
};

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("ContentImportTaskDock", () => {
  it("shows cross-page progress and returns to the exact import run", async () => {
    vi.spyOn(contentImportsApi, "get").mockResolvedValue(processingRun);
    rememberContentImportTask(processingRun.id, processingRun.batchId);
    const user = userEvent.setup();

    render(<ContentImportTaskDock />);

    const trigger = await screen.findByRole("button", { name: /补全候选字段/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.hover(trigger);
    expect(screen.getByText("已发现 3 条候选，正在补全字段")).toBeInTheDocument();
    expect(screen.getByText("3 条", { selector: "dd" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "返回任务页面" }));
    await waitFor(() => expect(window.location.pathname).toBe("/imports"));
    expect(window.location.search).toBe("?run=run-1");
    expect(window.localStorage.getItem("cf-content-import-active-task")).toContain("run-1");
  });
});

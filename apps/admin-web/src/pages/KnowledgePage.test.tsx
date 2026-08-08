import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import { scheduledPublicationsApi } from "../api/scheduledPublicationsApi";
import type { KnowledgeDocument } from "../api/types";
import { adminLightTheme } from "../theme";
import { hasPublishableDraft, KnowledgePage } from "./KnowledgePage";

function documentWith(
  status: string,
  reviewStatus?: string,
): KnowledgeDocument {
  return {
    id: "knowledge-1",
    title: "企业知识",
    status,
    version: 2,
    latestVersion: reviewStatus
      ? {
          id: "version-1",
          versionNumber: 2,
          reviewStatus,
          chunkCount: 1,
          indexedChunkCount: 0,
        }
      : undefined,
  };
}

describe("hasPublishableDraft", () => {
  it("allows a new draft to be published", () => {
    expect(hasPublishableDraft(documentWith("draft", "draft"))).toBe(true);
  });

  it("allows a pending draft on an already published document", () => {
    expect(hasPublishableDraft(documentWith("published", "draft"))).toBe(true);
  });

  it("does not offer publication without a draft version", () => {
    expect(hasPublishableDraft(documentWith("draft"))).toBe(false);
    expect(hasPublishableDraft(documentWith("published", "approved"))).toBe(false);
  });
});

describe("KnowledgePage scheduled publication", () => {
  beforeEach(() => {
    vi.spyOn(adminApi, "listKnowledgeDocuments").mockResolvedValue([
      documentWith("draft", "draft"),
    ]);
    vi.spyOn(scheduledPublicationsApi, "list").mockResolvedValue([]);
  });

  afterEach(() => vi.restoreAllMocks());

  it("offers scheduling for the selected draft version", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(scheduledPublicationsApi, "create").mockResolvedValue({
      id: "schedule-1",
      resourceType: "knowledge_document",
      resourceId: "knowledge-1",
      targetVersion: 1,
      scheduledBy: "user-1",
      knowledgeVersionId: "version-1",
      scheduledAt: "2099-01-01T01:00:00Z",
      status: "pending",
      attempts: 0,
      maxAttempts: 5,
      nextAttemptAt: "2099-01-01T01:00:00Z",
      version: 1,
    });
    render(
      <FluentProvider theme={adminLightTheme}>
        <KnowledgePage />
      </FluentProvider>,
    );

    await screen.findByText("企业知识");
    await user.click(screen.getByRole("button", { name: "定时发布" }));
    fireEvent.change(screen.getByLabelText(/发布时间/), {
      target: { value: "2099-01-01T09:00" },
    });
    await user.click(screen.getByRole("button", { name: "确认定时发布" }));

    await waitFor(() => expect(create).toHaveBeenCalledWith(expect.objectContaining({
      targetType: "knowledge_document",
      targetId: "knowledge-1",
      knowledgeVersionId: "version-1",
      version: 2,
    })));
  });

  it("shows an active schedule and cancels it", async () => {
    const user = userEvent.setup();
    vi.mocked(scheduledPublicationsApi.list).mockResolvedValue([{
      id: "schedule-2",
      resourceType: "knowledge_document",
      resourceId: "knowledge-1",
      targetVersion: 2,
      scheduledBy: "user-1",
      scheduledAt: "2099-01-01T01:00:00Z",
      status: "pending",
      attempts: 0,
      maxAttempts: 5,
      nextAttemptAt: "2099-01-01T01:00:00Z",
      version: 3,
    }]);
    const cancel = vi.spyOn(scheduledPublicationsApi, "cancel").mockResolvedValue(undefined);
    render(
      <FluentProvider theme={adminLightTheme}>
        <KnowledgePage />
      </FluentProvider>,
    );

    await screen.findByText(/计划发布/);
    expect(screen.queryByRole("button", { name: "发布" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "取消定时" }));
    await user.click(screen.getByRole("button", { name: "确认取消定时" }));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith("schedule-2", 3));
  });

  it("deletes a knowledge document only after destructive confirmation", async () => {
    const user = userEvent.setup();
    const remove = vi.spyOn(adminApi, "deleteKnowledgeDocument").mockResolvedValue(undefined);
    render(
      <FluentProvider theme={adminLightTheme}>
        <KnowledgePage />
      </FluentProvider>,
    );

    await screen.findByText("企业知识");
    await user.click(screen.getByRole("button", { name: "删除" }));
    expect(remove).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() => expect(remove).toHaveBeenCalledWith("knowledge-1", 2));
    expect(await screen.findByText(/AI 将不再检索该内容/)).toBeInTheDocument();
  });
});

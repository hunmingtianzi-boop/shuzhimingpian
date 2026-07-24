import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { ForbiddenTopic } from "../api/types";
import { adminLightTheme } from "../theme";
import { ForbiddenTopicsPage } from "./ForbiddenTopicsPage";

const topic: ForbiddenTopic = {
  id: "topic-1",
  topic: "价格承诺",
  matchTerms: ["最低价", "保证优惠"],
  action: "refuse",
  safeResponse: "",
  isActive: true,
  version: 4,
  updatedAt: "2026-07-11T00:00:00Z",
};

function renderPage() {
  return render(
    <FluentProvider theme={adminLightTheme}>
      <ForbiddenTopicsPage />
    </FluentProvider>,
  );
}

describe("ForbiddenTopicsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("confirms deactivation and sends the current version", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listForbiddenTopics").mockResolvedValue([topic]);
    const toggle = vi
      .spyOn(adminApi, "setForbiddenTopicActive")
      .mockResolvedValue({ ...topic, isActive: false, version: 5 });
    renderPage();

    await screen.findByText("价格承诺");
    await user.click(screen.getByRole("button", { name: "停用" }));
    expect(toggle).not.toHaveBeenCalled();
    const deactivateDialog = await screen.findByRole("dialog", {
      name: "确认停用禁答主题",
    });
    await user.click(
      within(deactivateDialog).getByRole("button", { name: "确认停用" }),
    );

    await waitFor(() =>
      expect(toggle).toHaveBeenCalledWith("topic-1", 4, false),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "确认停用禁答主题" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("requires confirmation before deleting a rule", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listForbiddenTopics").mockResolvedValue([topic]);
    const remove = vi
      .spyOn(adminApi, "deleteForbiddenTopic")
      .mockResolvedValue(undefined);
    renderPage();

    await screen.findByText("价格承诺");
    await user.click(screen.getByRole("button", { name: "删除" }));
    expect(remove).not.toHaveBeenCalled();
    const deleteDialog = await screen.findByRole("dialog", {
      name: "确认删除禁答主题",
    });
    await user.click(
      within(deleteDialog).getByRole("button", { name: "确认删除" }),
    );

    await waitFor(() => expect(remove).toHaveBeenCalledWith("topic-1", 4));
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "确认删除禁答主题" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("shows the shared permission state and hides creation actions", async () => {
    vi.spyOn(adminApi, "listForbiddenTopics").mockRejectedValue(
      new ApiError("没有权限", { code: "FORBIDDEN", status: 403 }),
    );
    renderPage();

    expect(await screen.findByText("没有访问权限")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "新建禁答主题" }),
    ).not.toBeInTheDocument();
  });

  it("edits a rule and preserves its optimistic version", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listForbiddenTopics").mockResolvedValue([topic]);
    const update = vi
      .spyOn(adminApi, "updateForbiddenTopic")
      .mockResolvedValue({ ...topic, topic: "报价边界", version: 5 });
    renderPage();

    await screen.findByText("价格承诺");
    await user.click(screen.getByRole("button", { name: "编辑" }));
    const editor = await screen.findByRole("dialog", { name: "编辑禁答主题" });
    const topicName = await within(editor).findByRole("textbox", {
      name: /主题名称/,
    });
    fireEvent.change(topicName, { target: { value: "报价边界" } });
    await user.click(
      within(editor).getByRole("button", { name: "保存禁答主题" }),
    );

    await waitFor(() => expect(update).toHaveBeenCalled());
    expect(update.mock.calls[0][0]).toBe("topic-1");
    expect(update.mock.calls[0][1]).toBe(4);
    expect(update.mock.calls[0][2]).toMatchObject({ topic: "报价边界" });
  });
});

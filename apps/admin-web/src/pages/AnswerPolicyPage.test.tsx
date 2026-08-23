import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import type { CompanyAnswerPolicy } from "../api/types";
import { AnswerPolicyPage } from "./AnswerPolicyPage";

vi.mock("../api/adminApi", () => ({
  adminApi: {
    getAnswerPolicy: vi.fn(),
    updateAnswerPolicy: vi.fn(),
  },
}));

const policy: CompanyAnswerPolicy = {
  aiOffTopicAnswerMode: "limited",
  aiOffTopicQuestionLimit: 3,
  version: 7,
  updatedAt: "2026-08-15T10:00:00Z",
};

function renderPage() {
  return render(
    <FluentProvider theme={webLightTheme}>
      <AnswerPolicyPage />
    </FluentProvider>,
  );
}

describe("AnswerPolicyPage", () => {
  beforeEach(() => {
    vi.mocked(adminApi.getAnswerPolicy).mockReset().mockResolvedValue(policy);
    vi.mocked(adminApi.updateAnswerPolicy).mockReset().mockResolvedValue(policy);
  });

  it("saves the enterprise-owned off-topic answer limit", async () => {
    const user = userEvent.setup();
    renderPage();

    const slider = await screen.findByRole("slider", { name: "无关问题回答上限" });
    fireEvent.change(slider, { target: { value: "5" } });
    expect(screen.getByText("每段对话最多回答 5 个无关问题")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "保存回答策略" }));

    await waitFor(() => {
      expect(adminApi.updateAnswerPolicy).toHaveBeenCalledWith(
        expect.objectContaining({
          aiOffTopicAnswerMode: "limited",
          aiOffTopicQuestionLimit: 5,
          version: 7,
        }),
      );
    });
  });

  it("offers both completely blocked and completely allowed endpoints", async () => {
    const user = userEvent.setup();
    renderPage();

    const blocked = await screen.findByRole("radio", {
      name: "完全不回答——从第 1 个企业无关问题起拒答",
    });
    await user.click(blocked);
    expect(blocked).toBeChecked();
    expect(screen.queryByRole("slider", { name: "无关问题回答上限" })).not.toBeInTheDocument();

    const unlimited = screen.getByRole("radio", {
      name: "完全允许——不按次数限制普通无关问题",
    });
    await user.click(unlimited);
    expect(unlimited).toBeChecked();

    await user.click(screen.getByRole("button", { name: "保存回答策略" }));
    await waitFor(() => {
      expect(adminApi.updateAnswerPolicy).toHaveBeenCalledWith(
        expect.objectContaining({ aiOffTopicAnswerMode: "unlimited" }),
      );
    });
  });
});

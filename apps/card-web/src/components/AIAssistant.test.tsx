import "@testing-library/jest-dom/vitest";

import { createRef } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AssistantStreamEvent } from "../lib/assistantApi";
import { templateTenant } from "../tenants/template/tenant";
import { AIAssistant, type AIAssistantHandle } from "./AIAssistant";

const streamMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/assistantApi", async () => {
  const actual = await vi.importActual<typeof import("../lib/assistantApi")>(
    "../lib/assistantApi",
  );
  return {
    ...actual,
    isAssistantApiConfigured: () => true,
    createAssistantIdempotencyKey: () => "message-key-0001",
    streamAssistantMessage: streamMock,
  };
});

describe("AIAssistant lead handoff", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    );
    streamMock.mockReset().mockImplementation(async ({ onEvent }: {
      onEvent: (event: AssistantStreamEvent) => void;
    }) => {
      onEvent({
        type: "completed",
        messageId: "message-1",
        finishReason: "stop",
        leadPrompt: true,
      });
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("closes the assistant before opening the lead form requested by the stream", async () => {
    const onLeadPrompt = vi.fn();
    render(
      <AIAssistant
        config={templateTenant.assistant}
        cardSlug="tenant-a"
        onLeadPrompt={onLeadPrompt}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: templateTenant.assistant.launcherAriaLabel }),
    );
    fireEvent.change(screen.getByLabelText(templateTenant.assistant.labels.input), {
      target: { value: "请联系我" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: templateTenant.assistant.labels.send }),
    );

    await waitFor(() => expect(onLeadPrompt).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("submits a recommended question when opened through the public card", async () => {
    const ref = createRef<AIAssistantHandle>();
    render(
      <AIAssistant
        ref={ref}
        config={templateTenant.assistant}
        cardSlug="tenant-a"
      />,
    );

    act(() => ref.current?.openWithQuestion("企业主要做什么？"));

    await waitFor(() =>
      expect(streamMock).toHaveBeenCalledWith(
        expect.objectContaining({
          cardSlug: "tenant-a",
          content: "企业主要做什么？",
        }),
      ),
    );
  });

  it("renders a whitelisted related business action after the answer and opens its target", async () => {
    streamMock.mockImplementation(async ({ onEvent }: {
      onEvent: (event: AssistantStreamEvent) => void;
    }) => {
      onEvent({ type: "delta", text: "AI 场景服务从需求诊断和原型验证开始。" });
      onEvent({
        type: "completed",
        messageId: "message-1",
        finishReason: "stop",
        leadPrompt: false,
      });
    });
    const onOpenRelatedSection = vi.fn();
    render(
      <AIAssistant
        config={templateTenant.assistant}
        cardSlug="tenant-a"
        relatedSections={[
          {
            id: "product:ai-scenario-service",
            targetId: "detail:product:ai-scenario-service",
            title: "AI 场景服务",
            description: "从需求诊断到原型验证。",
            keywords: ["AI 场景服务", "需求诊断", "原型验证"],
          },
        ]}
        onOpenRelatedSection={onOpenRelatedSection}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: templateTenant.assistant.launcherAriaLabel }),
    );
    fireEvent.change(screen.getByLabelText(templateTenant.assistant.labels.input), {
      target: { value: "你们有哪些 AI 服务？" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: templateTenant.assistant.labels.send }),
    );

    const relatedAction = await screen.findByRole("button", {
      name: "查看相关内容：AI 场景服务",
    });
    fireEvent.click(relatedAction);

    await waitFor(() => expect(onOpenRelatedSection).toHaveBeenCalledWith(
      "detail:product:ai-scenario-service",
    ));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("blocks two submissions dispatched before React can render the loading state", async () => {
    let finishStream: (() => void) | undefined;
    streamMock.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          finishStream = resolve;
        }),
    );
    render(<AIAssistant config={templateTenant.assistant} cardSlug="tenant-a" />);

    fireEvent.click(
      screen.getByRole("button", { name: templateTenant.assistant.launcherAriaLabel }),
    );
    const input = screen.getByLabelText(templateTenant.assistant.labels.input);
    fireEvent.change(input, { target: { value: "企业有什么商业模式？" } });
    const form = input.closest("form");
    expect(form).not.toBeNull();

    act(() => {
      form!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      form!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(streamMock).toHaveBeenCalledTimes(1);
    await act(async () => finishStream?.());
  });

  it("keeps the page width stable while the assistant locks scrolling", async () => {
    const originalInnerWidth = window.innerWidth;
    const originalClientWidth = document.documentElement.clientWidth;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1200 });
    Object.defineProperty(document.documentElement, "clientWidth", {
      configurable: true,
      value: 1184,
    });

    render(
      <AIAssistant config={templateTenant.assistant} cardSlug="tenant-a" />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: templateTenant.assistant.launcherAriaLabel }),
    );
    expect(document.body.style.overflow).toBe("hidden");
    expect(document.body.style.paddingRight).toBe("16px");

    fireEvent.click(
      screen.getByRole("button", { name: templateTenant.assistant.labels.closeButton }),
    );
    expect(document.body.style.overflow).toBe("hidden");
    expect(document.body.style.paddingRight).toBe("16px");
    await waitFor(() => expect(document.body.style.overflow).toBe(""));
    expect(document.body.style.paddingRight).toBe("");

    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: originalInnerWidth,
    });
    Object.defineProperty(document.documentElement, "clientWidth", {
      configurable: true,
      value: originalClientWidth,
    });
  });
});

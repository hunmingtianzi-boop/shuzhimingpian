import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode, useEffect, useRef } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { PublicCardData } from "../lib/publicCardApi";
import { templateTenant } from "../tenants/template/tenant";
import {
  DeferredAIAssistant,
  type AIAssistantHandle,
} from "./DeferredAIAssistant";
import { DeferredPublicExperience } from "./DeferredPublicExperience";

vi.mock("motion/react", async () => {
  const actual = await vi.importActual<typeof import("motion/react")>("motion/react");
  return { ...actual, useReducedMotion: () => true };
});

vi.mock("../lib/publicExperienceApi", async () => {
  const actual = await vi.importActual<typeof import("../lib/publicExperienceApi")>(
    "../lib/publicExperienceApi",
  );
  return { ...actual, isPublicExperienceConfigured: () => false };
});

vi.mock("../lib/assistantApi", async () => {
  const actual = await vi.importActual<typeof import("../lib/assistantApi")>(
    "../lib/assistantApi",
  );
  return { ...actual, isAssistantApiConfigured: () => false };
});

const card: PublicCardData = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "tenant-a",
  display_name: "示例企业",
  title: "示例企业名片",
  contact_fields: [],
  company: {
    id: "22222222-2222-2222-2222-222222222222",
    name: "示例企业",
    summary: "可信企业服务。",
  },
  featured_products: [],
  featured_cases: [],
  faq_items: [],
  ai_assistant: {
    available: false,
    display_name: "示例助手",
    disclosure: "回答由 AI 生成",
    welcome_message: "你好",
    suggested_questions: [],
  },
  policy_versions: {
    privacy: "privacy-v1",
    chat_notice: "chat-v1",
    lead_consent: "lead-v1",
    profile_personalization: "profile-v1",
  },
};

type ObserverCallback = IntersectionObserverCallback;
let observerCallbacks: ObserverCallback[] = [];

class TestIntersectionObserver {
  readonly root = null;
  readonly rootMargin = "0px";
  readonly thresholds = [0];

  constructor(callback: ObserverCallback) {
    observerCallbacks.push(callback);
  }

  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}

function InitialQuestionHarness() {
  const ref = useRef<AIAssistantHandle>(null);
  const question = templateTenant.assistant.knowledgeBase[0].shortQuestion;

  useEffect(() => {
    ref.current?.openWithQuestion(question);
  }, [question]);

  return (
    <DeferredAIAssistant
      ref={ref}
      config={templateTenant.assistant}
      cardSlug="tenant-a"
    />
  );
}

describe("deferred first-screen boundaries", () => {
  beforeAll(async () => {
    await Promise.all([import("./PublicExperience"), import("./AIAssistant")]);
  });

  beforeEach(() => {
    observerCallbacks = [];
    vi.stubGlobal("IntersectionObserver", TestIntersectionObserver);
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("keeps the catalog shell lightweight until it approaches the viewport", async () => {
    render(<DeferredPublicExperience card={card} onAssistant={vi.fn()} />);

    expect(screen.getByText("继续浏览后加载产品与案例")).toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(observerCallbacks).toHaveLength(1);

    await act(async () => {
      observerCallbacks[0](
        [{ isIntersecting: true } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      );
    });

    expect(await screen.findByRole("tab", { name: /^产品与服务/ })).toBeInTheDocument();
  });

  it("loads interaction-only panels on demand and preserves their accessible dialogs", async () => {
    render(
      <>
        <DeferredPublicExperience card={card} onAssistant={vi.fn()} />
        <DeferredAIAssistant config={templateTenant.assistant} cardSlug="tenant-a" />
      </>,
    );

    fireEvent.click(screen.getByRole("button", { name: "分享名片" }));
    const shareDialog = await screen.findByRole("dialog", { name: "扫码或复制链接" });
    expect(shareDialog).toBeInTheDocument();
    fireEvent.click(within(shareDialog).getByRole("button", { name: "关闭" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "扫码或复制链接" }),
      ).not.toBeInTheDocument(),
    );

    fireEvent.click(
      screen.getByRole("button", { name: templateTenant.assistant.launcherAriaLabel }),
    );
    expect(
      await screen.findByRole("dialog", { name: templateTenant.assistant.title }),
    ).toBeInTheDocument();
  });

  it("preserves an initial recommended question through a StrictMode lazy mount", async () => {
    render(
      <StrictMode>
        <InitialQuestionHarness />
      </StrictMode>,
    );

    expect(
      (await screen.findAllByText(templateTenant.assistant.knowledgeBase[0].shortQuestion)).length,
    ).toBeGreaterThan(0);
    expect(
      await screen.findByText(templateTenant.assistant.knowledgeBase[0].answer),
    ).toBeInTheDocument();
  });
});

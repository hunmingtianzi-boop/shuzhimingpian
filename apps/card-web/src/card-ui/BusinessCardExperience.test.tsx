import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PublicCardData } from "../lib/publicCardApi";
import { getAssistantSessionStorageKey } from "../lib/assistantApi";
import { mergePublishedCard } from "../lib/publicCard";
import * as publicExperienceApi from "../lib/publicExperienceApi";
import { templateTenant } from "../tenants/template/tenant";
import { tuotuTenant } from "../tenants/tuotu/tenant";
import { BusinessCardExperience } from "./BusinessCardExperience";

const noop = () => undefined;

const publishedOwnerCard: PublicCardData = {
  id: "card-1",
  slug: "tuotu-owner",
  card_kind: "employee",
  display_name: "公开负责人",
  title: "生态合作负责人",
  avatar_url: "https://assets.example.test/owner.webp",
  contact_fields: [],
  company: {
    id: "company-1",
    name: "拓浙 AI 集团",
    summary: "青年 AI 人才与产业场景共创。",
  },
  featured_products: [],
  featured_cases: [],
  faq_items: [],
  ai_assistant: {
    available: false,
    display_name: "资料助手",
    disclosure: "回答由 AI 生成",
    welcome_message: "你好，我可以介绍企业公开资料。",
    suggested_questions: [],
  },
  policy_versions: {
    privacy: "privacy-v1",
    chat_notice: "chat-v1",
    lead_consent: "lead-v1",
    profile_personalization: "profile-v1",
  },
};

function renderExperience(card?: PublicCardData) {
  return render(
    <BusinessCardExperience
      tenant={tuotuTenant}
      card={card}
      assistantEnabled={false}
      onLead={noop}
      onPrivacy={noop}
      onProfile={noop}
      onShare={noop}
    />,
  );
}

function mockPublishedExperience() {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1");
  vi.spyOn(publicExperienceApi, "fetchPublicCatalog").mockResolvedValue({
    products: [{
      slug: "published-service",
      name: "后台发布服务",
      category: "企业服务",
      summary: "由后台发布并进入企业名片的服务摘要。",
      detail: "服务详情。",
      sortOrder: 1,
      publishedAt: "2026-07-19T00:00:00Z",
    }],
    cases: [{
      slug: "published-case",
      title: "后台发布案例",
      industry: "人工智能",
      background: "后台案例背景。",
      solution: "后台案例方案。",
      result: "后台案例结果。",
      imageUrl: "https://assets.example.test/published-case.webp",
      sortOrder: 1,
      publishedAt: "2026-07-19T00:00:00Z",
    }],
  });
  vi.spyOn(publicExperienceApi, "fetchPublicRecommendations").mockResolvedValue([{
    resourceType: "product",
    resourceId: "product-1",
    title: "后台智能推荐",
    summary: "来自公开推荐接口。",
    url: "/c/tuotu/products/published-service",
    reason: "与企业公开内容相关。",
    evidence: {
      sourceType: "product",
      sourceId: "product-1",
      sourceVersion: 1,
      title: "后台发布服务",
      excerpt: "由后台发布并进入企业名片的服务摘要。",
    },
  }]);
}

describe("new visitor card UI", () => {
  const originalScrollIntoView = Object.getOwnPropertyDescriptor(
    HTMLElement.prototype,
    "scrollIntoView",
  );

  beforeEach(() => {
    window.history.replaceState({}, "", "/c/tuotu");
    window.sessionStorage.clear();
    vi.stubGlobal("scrollTo", vi.fn());
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    );
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    if (originalScrollIntoView) {
      Object.defineProperty(
        HTMLElement.prototype,
        "scrollIntoView",
        originalScrollIntoView,
      );
    } else {
      delete (HTMLElement.prototype as Partial<HTMLElement>).scrollIntoView;
    }
  });

  it("uses the personal view by default and keeps tab state in browser history", () => {
    renderExperience();

    expect(screen.getByRole("heading", { name: "负责人姓名" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "名片导航" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "企业" }));
    expect(window.location.search).toBe("?view=enterprise");
    expect(screen.getByRole("heading", { name: "让真实问题成为成长现场" })).toBeInTheDocument();

    act(() => {
      window.history.replaceState({}, "", "/c/tuotu");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByRole("heading", { name: "负责人姓名" })).toBeInTheDocument();
  });

  it("uses the same three-page template for newly published enterprises without a custom tenant", () => {
    const newEnterpriseCard: PublicCardData = {
      ...publishedOwnerCard,
      slug: "new-enterprise",
      card_kind: "enterprise",
      display_name: "新企业",
      title: "企业官方名片",
      avatar_url: undefined,
      company: {
        ...publishedOwnerCard.company,
        id: "company-new",
        name: "新企业",
        summary: "后台发布的新企业简介。",
      },
    };
    const generatedTenant = mergePublishedCard(
      newEnterpriseCard,
      undefined,
      templateTenant,
    );

    render(
      <BusinessCardExperience
        tenant={generatedTenant}
        card={newEnterpriseCard}
        assistantEnabled={false}
        onLead={noop}
        onPrivacy={noop}
        onProfile={noop}
        onShare={noop}
      />,
    );

    expect(screen.getByRole("heading", { name: "个人姓名" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "名片导航" })).toHaveTextContent("个人企业AI 助手");

    fireEvent.click(screen.getByRole("button", { name: "企业" }));
    expect(screen.getByText("后台发布的新企业简介。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /企业资料展示/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "AI 助手" }));
    expect(screen.getByRole("heading", { name: "资料助手" })).toBeInTheDocument();
  });

  it("keeps legacy owner links on the personal view and marks placeholder biography content as demo data", () => {
    window.history.replaceState({}, "", "/c/tuotu?view=owner");
    renderExperience();

    expect(screen.getAllByText("演示资料，待替换").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("公司名称 A")).toBeInTheDocument();
    expect(screen.getByText("20XX - 至今")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "联系本人" })).toBeInTheDocument();
  });

  it("lets real public owner fields override demo identity while preserving the demo biography warning", () => {
    window.history.replaceState({}, "", "/c/tuotu?view=owner");
    renderExperience(publishedOwnerCard);

    expect(screen.getByRole("heading", { name: "公开负责人" })).toBeInTheDocument();
    expect(screen.getByText("生态合作负责人")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "公开负责人头像" })).toHaveAttribute(
      "src",
      "https://assets.example.test/owner.webp",
    );
    expect(screen.getAllByText("演示资料，待替换").length).toBeGreaterThanOrEqual(2);
  });

  it("answers a sourced quick question in static mode and keeps the conversation across tabs", async () => {
    window.history.replaceState({}, "", "/c/tuotu?view=assistant");
    renderExperience();

    fireEvent.click(screen.getByRole("button", { name: /集团主要做什么/ }));
    await waitFor(() => expect(screen.getByText(/核心定位/)).toBeInTheDocument());
    expect(screen.getByText(/业务梳理讨论智能纪要/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "个人" }));
    fireEvent.click(screen.getByRole("button", { name: "AI 助手" }));

    expect(screen.getByText(/核心定位/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新开始" })).toBeInTheDocument();
  });

  it("keeps the referenced topic for pronoun-style follow-ups in static fallback mode", async () => {
    window.history.replaceState({}, "", "/c/tuotu?view=assistant");
    renderExperience();

    fireEvent.click(screen.getByRole("button", { name: /浙客松/ }));
    await waitFor(() =>
      expect(screen.getAllByText(/面向真实场景的 AI 创新赛事/)).toHaveLength(1),
    );

    fireEvent.change(screen.getByRole("textbox", { name: "向 AI 助手提问" }), {
      target: { value: "那怎么参与？" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));

    await waitFor(() =>
      expect(screen.getAllByText(/面向真实场景的 AI 创新赛事/)).toHaveLength(2),
    );
  });

  it("submits manual questions and exposes the three sourced recommendation entries", async () => {
    window.history.replaceState({}, "", "/c/tuotu?view=assistant");
    renderExperience();

    expect(screen.getByRole("button", { name: /AI 人才与项目孵化/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /浙客松/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /AI 场景服务了解从需求诊断/ })).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "向 AI 助手提问" }), {
      target: { value: "企业如何合作？" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));

    await waitFor(() => expect(screen.getByText(/合作方式/)).toBeInTheDocument());
  });

  it("surfaces a matching enterprise section below an answer and opens its exact target", async () => {
    window.history.replaceState({}, "", "/c/tuotu?view=assistant");
    renderExperience();

    fireEvent.change(screen.getByRole("textbox", { name: "向 AI 助手提问" }), {
      target: { value: "AI 场景服务包括哪些内容？" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));

    const sectionLink = await screen.findByRole("button", {
      name: "查看企业板块：AI 场景服务",
    });
    fireEvent.click(sectionLink);

    const params = new URLSearchParams(window.location.search);
    expect(params.get("view")).toBe("enterprise");
    expect(params.get("section")).toBe("enterprise-solution-2");
    const target = document.getElementById("enterprise-solution-2");
    expect(target).toBeInTheDocument();
    expect(target).toHaveClass("is-ai-focused");
    expect(target).toHaveFocus();
    expect(target?.scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "center",
    });

    act(() => {
      window.history.replaceState({}, "", "/c/tuotu?view=assistant");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByText(/服务范围/)).toBeInTheDocument();
  });

  it("clears both the visible chat and server conversation when restarting", async () => {
    window.history.replaceState({}, "", "/c/tuotu?view=assistant");
    const sessionKey = getAssistantSessionStorageKey("tuotu");
    const visibleHistoryKey = sessionKey + ":visible-messages";
    window.sessionStorage.setItem(
      sessionKey,
      JSON.stringify({
        token: "visitor-token",
        expiresAt: "2099-01-01T00:00:00Z",
        privacyVersion: "privacy-v1",
        chatNoticeVersion: "chat-v1",
        conversationId: "conversation-old",
      }),
    );
    renderExperience();

    fireEvent.click(screen.getByRole("button", { name: /集团主要做什么/ }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "重新开始" })).toBeInTheDocument(),
    );
    expect(window.sessionStorage.getItem(visibleHistoryKey)).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "重新开始" }));

    expect(window.sessionStorage.getItem(sessionKey)).toBeNull();
    expect(window.sessionStorage.getItem(visibleHistoryKey)).toBeNull();
    expect(
      screen.queryByRole("button", { name: "重新开始" }),
    ).not.toBeInTheDocument();
  });

  it("keeps the reviewed tuotu homepage while applying published AI settings and recommendations", async () => {
    mockPublishedExperience();
    const enterpriseCard: PublicCardData = {
      ...publishedOwnerCard,
      slug: "tuotu",
      card_kind: "enterprise",
      display_name: "拓浙 AI 集团",
      title: "企业官方名片",
      company: {
        ...publishedOwnerCard.company,
        summary: "后台维护的企业简介。",
      },
      ai_assistant: {
        ...publishedOwnerCard.ai_assistant,
        display_name: "拓浙接待助手",
        disclosure: "后台配置的 AI 内容说明。",
        welcome_message: "后台配置的欢迎语。",
        suggested_questions: ["后台配置的问题？"],
      },
    };

    renderExperience(enterpriseCard);

    fireEvent.click(screen.getByRole("button", { name: "AI 助手" }));
    expect(screen.getByRole("heading", { name: "拓浙接待助手" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "后台配置的问题？" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /后台智能推荐/ })).toBeInTheDocument();
    expect(screen.getByText("后台配置的 AI 内容说明。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "企业" }));

    expect(screen.getByText(
      "连接青年 AI 人才、高校创新资源与产业场景，让学习、项目、赛事与应用落地彼此接力。",
    )).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /AI 人才与项目孵化/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /AI 创新赛事/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /AI 场景服务/ })).toBeInTheDocument();
    expect(screen.getByText("首届浙客松 AI 创新实践")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "首届浙客松参与者集体合影" })).toBeInTheDocument();
    expect(screen.getByText("截至 2026.07")).toBeInTheDocument();
    expect(screen.queryByText("后台维护的企业简介。")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /后台发布服务/ })).not.toBeInTheDocument();
    expect(screen.queryByText("后台发布案例")).not.toBeInTheDocument();
  });

  it("replaces the generic template homepage with published catalog content", async () => {
    mockPublishedExperience();
    const genericCard: PublicCardData = {
      ...publishedOwnerCard,
      slug: "new-enterprise",
      card_kind: "enterprise",
      display_name: "新企业",
      title: "企业官方名片",
      company: {
        ...publishedOwnerCard.company,
        id: "company-new",
        name: "新企业",
        summary: "后台维护的新企业简介。",
      },
      ai_assistant: {
        ...publishedOwnerCard.ai_assistant,
        display_name: "新企业接待助手",
      },
    };
    const generatedTenant = mergePublishedCard(genericCard, undefined, templateTenant);

    render(
      <BusinessCardExperience
        tenant={generatedTenant}
        card={genericCard}
        assistantEnabled={false}
        onLead={noop}
        onPrivacy={noop}
        onProfile={noop}
        onShare={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "企业" }));

    expect(screen.getByText("后台维护的新企业简介。")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /后台发布服务/ })).toBeInTheDocument();
    expect(screen.getByText("后台发布案例")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "后台发布案例案例图片" })).toHaveAttribute(
      "src",
      "https://assets.example.test/published-case.webp",
    );
    expect(screen.queryByRole("button", { name: /企业资料展示/ })).not.toBeInTheDocument();
    expect(screen.queryByText("企业案例待发布")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "AI 助手" }));
    expect(await screen.findByRole("button", { name: /后台智能推荐/ })).toBeInTheDocument();
  });
});

import "@testing-library/jest-dom/vitest";

import { createRef } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { AssistantApiError } from "./lib/assistantApi";
import type { PublicCardData } from "./lib/publicCardApi";
import * as publicExperienceApi from "./lib/publicExperienceApi";
import {
  BusinessCardPrototypeApp,
  type BusinessCardPrototypeAppHandle,
} from "./prototype/BusinessCardPrototypeApp";
import { blankEnterpriseTenant } from "./tenants/blank/tenant";
import { templateTenant } from "./tenants/template/tenant";

const publishedCard: PublicCardData = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "example",
  display_name: "示例顾问",
  title: "解决方案顾问",
  contact_fields: [],
  company: {
    id: "22222222-2222-2222-2222-222222222222",
    name: "示例企业",
    summary: "可信企业服务。",
    website: "https://example.cn",
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

describe("BusinessCardPrototypeApp", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/c/template");
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("uses the imported card prototype shell and keeps real actions wired", () => {
    const onAssistant = vi.fn();
    const onLead = vi.fn();
    const onShare = vi.fn();

    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        onAssistant={onAssistant}
        onLead={onLead}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={onShare}
      />,
    );

    expect(screen.getByRole("heading", { name: templateTenant.brand.shortName })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "业务介绍" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "名片导航" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "发起合作" }));
    fireEvent.click(screen.getByRole("button", { name: "分享名片" }));
    fireEvent.click(screen.getByRole("button", { name: new RegExp(templateTenant.assistant.knowledgeBase[0].shortQuestion) }));

    expect(onLead).toHaveBeenCalledOnce();
    expect(onShare).toHaveBeenCalledOnce();
    expect(onAssistant).toHaveBeenCalledWith(templateTenant.assistant.knowledgeBase[0].shortQuestion);

    fireEvent.click(screen.getByRole("button", { name: new RegExp(templateTenant.brand.name) }));
    expect(screen.getByRole("heading", { name: "企业介绍" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "名片导航" })).toBeInTheDocument();
  });

  it("renders a standalone employee card without the legacy bottom navigation and links to its company card", () => {
    window.history.replaceState({}, "", "/c/xusongbo?mock-card=employee");
    const standaloneEmployeeCard: PublicCardData = {
      ...publishedCard,
      slug: "xusongbo",
      card_kind: "employee",
      company: {
        ...publishedCard.company,
        official_card_slug: "tuotu",
      },
    };

    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        card={standaloneEmployeeCard}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    expect(screen.queryByRole("navigation", { name: "名片导航" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "切换到企业名片" })).toHaveAttribute(
      "href",
      "/c/tuotu?mock-card=enterprise&from_employee=xusongbo",
    );
    expect(screen.getByRole("link", { name: /示例企业/ })).toHaveAttribute(
      "href",
      "/c/tuotu?mock-card=enterprise&from_employee=xusongbo",
    );
    expect(screen.getByRole("button", { name: "发起合作" })).toBeInTheDocument();
  });

  it("renders a standalone enterprise card as its own page without employee routing", () => {
    window.history.replaceState({}, "", "/c/tuotu?mock-card=enterprise&from_employee=xusongbo");
    const standaloneEnterpriseCard: PublicCardData = {
      ...publishedCard,
      card_kind: "enterprise",
      display_name: "示例企业",
      title: "企业官方名片",
      company: {
        ...publishedCard.company,
        official_card_slug: "tuotu",
      },
    };

    const enterpriseRender = render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        card={standaloneEnterpriseCard}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    expect(screen.getByText("企业官方名片")).toBeInTheDocument();
    expect(screen.queryByText("可以为你对接的人")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "名片导航" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "返回" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "切换到员工名片" })).toHaveAttribute(
      "href",
      "/c/xusongbo?mock-card=employee",
    );
    expect(screen.getByRole("navigation", { name: "企业名片内容导航" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "概览" })).toHaveAttribute("aria-current", "location");
    fireEvent.click(screen.getByRole("button", { name: "介绍" }));
    expect(screen.getByRole("button", { name: "介绍" })).toHaveAttribute("aria-current", "location");
    expect(screen.getByRole("button", { name: "提交合作需求" })).toBeInTheDocument();

    enterpriseRender.unmount();
    window.history.replaceState({}, "", "/c/tuotu?mock-card=enterprise");
    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        card={standaloneEnterpriseCard}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "返回" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "切换到员工名片" })).not.toBeInTheDocument();
  });

  it("renders reusable product, case and FAQ showcase layouts from variable content", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1");
    window.history.replaceState({}, "", "/c/example");
    const products: publicExperienceApi.PublicProduct[] = [
      {
        slug: "data-service",
        name: "数据服务",
        category: "企业服务",
        summary: "帮助企业整理数据并形成可执行的经营分析。",
        detail: "从数据盘点、指标设计到分析看板逐步交付。",
        audience: "成长型企业",
        priceBoundary: "按项目范围评估",
        sortOrder: 1,
        publishedAt: "2026-07-17T00:00:00Z",
      },
      {
        slug: "talent-program",
        name: "人才共创计划",
        category: "人才服务",
        summary: "围绕真实问题组织跨学科团队完成项目验证。",
        detail: "通过训练、组队和项目复盘沉淀能力。",
        sortOrder: 2,
        publishedAt: "2026-07-17T00:00:00Z",
      },
    ];
    const cases: publicExperienceApi.PublicCaseStudy[] = [
      {
        slug: "retail-growth",
        title: "零售经营增长案例",
        industry: "零售",
        background: "客户需要统一经营数据。",
        solution: "建设统一数据看板。",
        result: "关键决策效率得到提升。",
        sortOrder: 1,
        publishedAt: "2026-07-17T00:00:00Z",
      },
      {
        slug: "education-project",
        title: "青年项目实践案例",
        industry: "教育",
        background: "实践机会缺少连续路径。",
        solution: "组织分层训练和真实项目。",
        result: "参与者形成可复用的项目作品。",
        sortOrder: 2,
        publishedAt: "2026-07-17T00:00:00Z",
      },
    ];
    vi.spyOn(publicExperienceApi, "fetchPublicCatalog").mockResolvedValue({ products, cases });
    vi.spyOn(publicExperienceApi, "fetchPublicRecommendations").mockResolvedValue([]);
    const richCard: PublicCardData = {
      ...publishedCard,
      card_kind: "enterprise",
      faq_items: [
        { id: "faq-1", question: "为什么选择我们？", answer: "因为方案来自已发布资料与真实项目。", source_label: "企业公开资料" },
        { id: "faq-2", question: "如何开始合作？", answer: "先提交业务需求，再确认范围与交付方式。", source_label: "合作流程说明" },
      ],
    };

    const { container } = render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        card={richCard}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    await screen.findByText("数据服务");
    expect(container.querySelectorAll(".bp-product-showcase-item")).toHaveLength(2);
    expect(container.querySelectorAll(".bp-case-showcase-item")).toHaveLength(2);
    expect(container.querySelectorAll(".bp-faq-showcase article")).toHaveLength(2);
    expect(screen.getByText("客户需要统一经营数据。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /如何开始合作/ }));
    expect(screen.getByText("先提交业务需求，再确认范围与交付方式。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /数据服务/ }));
    expect(screen.getByText("从数据盘点、指标设计到分析看板逐步交付。")).toBeInTheDocument();
    expect(screen.getByText("成长型企业")).toBeInTheDocument();
  });

  it("keeps the primary navigation available and follows browser history", () => {
    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "业务" }));
    expect(screen.getByRole("heading", { name: "从产品、案例和业务方向开始" })).toBeInTheDocument();
    expect(new URL(window.location.href).searchParams.get("view")).toBe("square");

    window.history.replaceState({}, "", "/c/template?view=me");
    fireEvent.popState(window);
    expect(screen.getByText("我的名片关系")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "名片" }));
    expect(screen.getByRole("heading", { name: templateTenant.brand.shortName })).toBeInTheDocument();
    expect(new URL(window.location.href).searchParams.has("view")).toBe(false);
  });

  it("uses browser history for an internal company-page return without creating a loop", () => {
    const back = vi.spyOn(window.history, "back").mockImplementation(() => undefined);
    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: templateTenant.brand.name }),
    );
    expect(new URL(window.location.href).searchParams.get("view")).toBe("company");
    fireEvent.click(screen.getByRole("button", { name: "返回" }));

    expect(back).toHaveBeenCalledOnce();
  });

  it("replaces a directly opened company view with the card instead of adding history", () => {
    window.history.replaceState({}, "", "/c/template?view=company");
    const historyLength = window.history.length;
    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "返回" }));

    expect(screen.getByRole("heading", { name: templateTenant.brand.shortName })).toBeInTheDocument();
    expect(new URL(window.location.href).searchParams.has("view")).toBe(false);
    expect(window.history.length).toBe(historyLength);
  });

  it("exposes privacy and profile controls without fake visitor login", () => {
    window.history.replaceState({}, "", "/c/template?view=me");
    const onPrivacy = vi.fn();
    const onProfile = vi.fn();

    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        card={publishedCard}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={onPrivacy}
        onProfile={onProfile}
        onShare={vi.fn()}
      />,
    );

    expect(screen.queryByText("微信授权登录")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /长期访客画像授权/ }));
    fireEvent.click(screen.getByRole("button", { name: /个人信息权利/ }));

    expect(onProfile).toHaveBeenCalledOnce();
    expect(onPrivacy).toHaveBeenCalledOnce();
  });

  it("respects a disabled AI assistant and preserves the published website", () => {
    window.history.replaceState({}, "", "/c/example?view=me");
    const onAssistant = vi.fn();

    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        card={publishedCard}
        onAssistant={onAssistant}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    expect(screen.getByRole("link", { name: /示例企业官网/ })).toHaveAttribute(
      "href",
      "https://example.cn/",
    );
    fireEvent.click(screen.getByRole("button", { name: "名片" }));
    expect(screen.getByText("企业尚未开放 AI 问答，请先通过合作需求与企业联系。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始咨询" })).not.toBeInTheDocument();
    expect(onAssistant).not.toHaveBeenCalled();
  });

  it("opens an explainable product recommendation even when AI is disabled and restores it from the URL", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1");
    const product: publicExperienceApi.PublicProduct = {
      slug: "verified-service",
      name: "可信企业服务",
      category: "企业服务",
      summary: "来自已发布目录的服务。",
      detail: "这是可直接打开的已发布产品详情。",
      sortOrder: 1,
      publishedAt: "2026-07-16T09:00:00Z",
    };
    vi.spyOn(publicExperienceApi, "fetchPublicCatalog").mockResolvedValue({
      products: [product],
      cases: [],
    });
    vi.spyOn(publicExperienceApi, "fetchPublicRecommendations").mockResolvedValue([
      {
        resourceType: "product",
        resourceId: "product-1",
        title: product.name,
        summary: product.summary,
        url: `/products/${product.slug}`,
        reason: "与当前企业需求相关",
        evidence: {
          sourceType: "product",
          sourceId: "product-1",
          title: product.name,
          excerpt: "来源于已发布产品说明",
        },
      },
    ]);
    window.history.replaceState({}, "", "/c/example?view=square");

    const firstRender = render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        card={publishedCard}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    fireEvent.click(
      await screen.findByRole("button", { name: /与当前企业需求相关/ }),
    );
    expect(await screen.findByText(product.detail)).toBeInTheDocument();
    expect(new URL(window.location.href).searchParams.get("detail")).toBe(
      `product:${product.slug}`,
    );

    firstRender.unmount();
    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        card={publishedCard}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );
    expect(await screen.findByText(product.detail)).toBeInTheDocument();

    window.history.replaceState({}, "", "/c/example?view=square");
    fireEvent.popState(window);
    expect(
      await screen.findByRole("heading", {
        name: "从产品、案例和业务方向开始",
      }),
    ).toBeInTheDocument();

    window.history.replaceState(
      {},
      "",
      `/c/example?view=square&detail=product:${product.slug}`,
    );
    fireEvent.popState(window);
    expect(await screen.findByText(product.detail)).toBeInTheDocument();
  });

  it("shows a clear state when a detail link no longer exists", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1");
    vi.spyOn(publicExperienceApi, "fetchPublicCatalog").mockResolvedValue({
      products: [],
      cases: [],
    });
    vi.spyOn(publicExperienceApi, "fetchPublicRecommendations").mockResolvedValue([]);
    vi.spyOn(publicExperienceApi, "fetchPublicProduct").mockRejectedValue(
      new AssistantApiError("内容不存在", { code: "NOT_FOUND", status: 404 }),
    );
    window.history.replaceState(
      {},
      "",
      "/c/example?view=square&detail=product:removed-service",
    );

    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        card={publishedCard}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    expect(await screen.findByText("该内容不存在或已下线")).toBeInTheDocument();
    expect(new URL(window.location.href).searchParams.get("detail")).toBe(
      "product:removed-service",
    );
  });

  it("loads a valid deep-linked product even when it is outside the first catalog page", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1");
    const archivedFromCatalog: publicExperienceApi.PublicProduct = {
      slug: "page-two-service",
      name: "第二页企业服务",
      category: "企业服务",
      summary: "不在目录首屏，但仍处于发布状态。",
      detail: "详情接口返回的当前已发布内容。",
      sortOrder: 51,
      publishedAt: "2026-07-17T00:00:00Z",
    };
    vi.spyOn(publicExperienceApi, "fetchPublicCatalog").mockResolvedValue({
      products: [],
      cases: [],
    });
    vi.spyOn(publicExperienceApi, "fetchPublicRecommendations").mockResolvedValue([]);
    const detailRequest = vi
      .spyOn(publicExperienceApi, "fetchPublicProduct")
      .mockResolvedValue(archivedFromCatalog);
    window.history.replaceState(
      {},
      "",
      "/c/example?view=square&detail=product:page-two-service",
    );

    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        card={publishedCard}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    expect(await screen.findByText(archivedFromCatalog.detail)).toBeInTheDocument();
    expect(detailRequest).toHaveBeenCalledWith(
      publishedCard.slug,
      archivedFromCatalog.slug,
      expect.any(AbortSignal),
    );
  });

  it("registers published catalog entries for AI answers and opens their detail target", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1");
    const product: publicExperienceApi.PublicProduct = {
      slug: "ai-scenario-service",
      name: "AI 场景服务",
      category: "企业服务",
      summary: "从需求诊断到原型验证。",
      detail: "围绕真实业务问题推进方案设计与定制开发。",
      sortOrder: 1,
      publishedAt: "2026-07-21T00:00:00Z",
    };
    vi.spyOn(publicExperienceApi, "fetchPublicCatalog").mockResolvedValue({
      products: [product],
      cases: [],
    });
    vi.spyOn(publicExperienceApi, "fetchPublicRecommendations").mockResolvedValue([]);
    const relatedSections = vi.fn();
    const ref = createRef<BusinessCardPrototypeAppHandle>();

    render(
      <BusinessCardPrototypeApp
        ref={ref}
        tenant={templateTenant}
        card={publishedCard}
        onAssistant={vi.fn()}
        onAssistantRelatedSectionsChange={relatedSections}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    await waitFor(() => expect(relatedSections).toHaveBeenLastCalledWith([
      expect.objectContaining({
        id: `product:${product.slug}`,
        targetId: `detail:product:${product.slug}`,
        title: product.name,
      }),
    ]));
    act(() => ref.current?.openAssistantTarget(`detail:product:${product.slug}`));

    expect(await screen.findByText(product.detail)).toBeInTheDocument();
    expect(new URL(window.location.href).searchParams.get("detail")).toBe(
      `product:${product.slug}`,
    );
  });

  it("copies non-link contact details when the secure Clipboard API is unavailable", async () => {
    window.history.replaceState({}, "", "/c/example?view=me");
    const clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, "clipboard");
    const execCommandDescriptor = Object.getOwnPropertyDescriptor(document, "execCommand");
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn(() => true),
    });

    try {
      render(
        <BusinessCardPrototypeApp
          tenant={templateTenant}
          card={{
            ...publishedCard,
            contact_fields: [{ label: "微信", value: "example-wechat" }],
          }}
          onAssistant={vi.fn()}
          onLead={vi.fn()}
          onPrivacy={vi.fn()}
          onProfile={vi.fn()}
          onShare={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByRole("button", { name: /微信/ }));
      await waitFor(() => expect(screen.getByText("已复制")).toBeInTheDocument());
      expect(document.execCommand).toHaveBeenCalledWith("copy");
    } finally {
      if (clipboardDescriptor) Object.defineProperty(navigator, "clipboard", clipboardDescriptor);
      else Reflect.deleteProperty(navigator, "clipboard");
      if (execCommandDescriptor) Object.defineProperty(document, "execCommand", execCommandDescriptor);
      else Reflect.deleteProperty(document, "execCommand");
    }
  });

  it("keeps a direct AI entry when no suggested questions are configured", () => {
    const onAssistant = vi.fn();
    const tenantWithoutQuestions = {
      ...templateTenant,
      assistant: {
        ...templateTenant.assistant,
        quickQuestionIds: [],
        knowledgeBase: [],
      },
    };

    render(
      <BusinessCardPrototypeApp
        tenant={tenantWithoutQuestions}
        onAssistant={onAssistant}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /开始咨询/ }));
    expect(onAssistant).toHaveBeenCalledWith();
  });

  it("shows a result when static sharing falls back to legacy copy", async () => {
    window.history.replaceState({}, "", "/c/blank-enterprise");
    const shareDescriptor = Object.getOwnPropertyDescriptor(navigator, "share");
    const clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, "clipboard");
    const execCommandDescriptor = Object.getOwnPropertyDescriptor(document, "execCommand");
    Object.defineProperty(navigator, "share", { configurable: true, value: undefined });
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn(() => true),
    });

    try {
      render(<App tenant={blankEnterpriseTenant} />);
      fireEvent.click(screen.getByRole("button", { name: "分享名片" }));
      await waitFor(() => {
        expect(screen.getByRole("status")).toHaveTextContent("名片链接已复制");
      });
    } finally {
      if (shareDescriptor) Object.defineProperty(navigator, "share", shareDescriptor);
      else Reflect.deleteProperty(navigator, "share");
      if (clipboardDescriptor) Object.defineProperty(navigator, "clipboard", clipboardDescriptor);
      else Reflect.deleteProperty(navigator, "clipboard");
      if (execCommandDescriptor) Object.defineProperty(document, "execCommand", execCommandDescriptor);
      else Reflect.deleteProperty(document, "execCommand");
    }
  });

  it("reuses the QR and URL share panel for a standalone mock card", async () => {
    window.history.replaceState({}, "", "/c/xusongbo?mock-card=employee");

    render(<App tenant={templateTenant} />);
    fireEvent.click(screen.getByRole("button", { name: "分享名片" }));

    expect(
      await screen.findByRole("heading", { name: "扫码或复制链接" }),
    ).toBeInTheDocument();
    expect(screen.getByText("分享员工名片")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /名片二维码/ })).toBeInTheDocument();
    expect(screen.getByText("http://localhost:3000/c/xusongbo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制链接" })).toBeInTheDocument();
  });

  it("opens the published live assistant from the replacement mobile shell", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1");
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline in test"));
    window.history.replaceState({}, "", "/c/tuotu");

    render(
      <App
        tenant={templateTenant}
        publishedCard={{
          ...publishedCard,
          slug: "tuotu",
          ai_assistant: {
            ...publishedCard.ai_assistant,
            available: true,
            display_name: "正式企业 AI 助手",
          },
        }}
      />,
    );

    await screen.findByRole("button", { name: templateTenant.assistant.launcherAriaLabel });
    fireEvent.click(
      screen.getByRole("button", {
        name: new RegExp(templateTenant.assistant.knowledgeBase[0].shortQuestion),
      }),
    );

    expect(
      await screen.findByRole(
        "heading",
        { name: templateTenant.assistant.title },
        { timeout: 15_000 },
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("在线")).toBeInTheDocument();
    expect(screen.queryByText("资料模式")).not.toBeInTheDocument();
  }, 20_000);

  it("renders a usable blank enterprise without pretending content is published", () => {
    window.history.replaceState({}, "", "/c/blank-enterprise");
    const onAssistant = vi.fn();
    const onLead = vi.fn();

    render(
      <BusinessCardPrototypeApp
        tenant={blankEnterpriseTenant}
        onAssistant={onAssistant}
        onLead={onLead}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    expect(screen.getByText("空白模板")).toBeInTheDocument();
    expect(screen.getByText("尚未录入企业资料")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "开始配置企业" })).toHaveAttribute(
      "href",
      "/admin/platform/onboarding",
    );
    expect(screen.queryByText("已发布")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始咨询" })).not.toBeInTheDocument();
    expect(onAssistant).not.toHaveBeenCalled();
    expect(onLead).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: /企业名称待录入/ }),
    );
    expect(screen.getByText("企业介绍待录入")).toBeInTheDocument();
    expect(screen.getByText("产品与服务待录入")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "业务" }));
    expect(screen.getByText("产品与案例尚未录入")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "我的" }));
    expect(screen.getByRole("heading", { name: "空白企业模板" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /开始配置企业/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /长期访客画像授权/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /个人信息权利/ })).not.toBeInTheDocument();
  });
});

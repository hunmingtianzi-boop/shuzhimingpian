import { describe, expect, it } from "vitest";

import { templateTenant } from "../tenants/template/tenant";
import { tuotuTenant } from "../tenants/tuotu/tenant";
import { mergePublishedCard, type PublicCardData } from "./publicCard";
import { validateTenantConfig } from "./validateTenantConfig";

const card: PublicCardData = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "example-company",
  display_name: "示例企业",
  title: "示例企业资料中心",
  contact_fields: [],
  company: {
    id: "22222222-2222-2222-2222-222222222222",
    name: "示例企业",
    summary: "面向企业客户提供可信的数据服务。",
    industry: "企业服务",
    website: "https://example.com",
  },
  featured_products: [{ title: "数据服务", description: "帮助企业整理业务数据。" }],
  featured_cases: [],
  faq_items: [
    {
      id: "faq-service",
      question: "可以提供哪些服务？",
      answer: "当前公开资料包含数据整理服务。",
      source_label: "企业资料",
    },
  ],
  ai_assistant: {
    available: true,
    display_name: "示例企业 AI 助手",
    disclosure: "回答由 AI 基于企业已发布资料生成。",
    welcome_message: "你好，我可以介绍示例企业。",
    suggested_questions: ["可以提供哪些服务？"],
  },
  policy_versions: {
    privacy: "privacy-v1",
    chat_notice: "chat-v1",
    lead_consent: "lead-v1",
    profile_personalization: "profile-v1",
  },
};

describe("mergePublishedCard", () => {
  it("projects the bound employee business summary into the public hero", () => {
    const employeeCard: PublicCardData = {
      ...card,
      card_kind: "employee",
      display_name: "林顾问",
      title: "解决方案顾问",
      business_summary: "帮助制造企业梳理数智化落地路径。",
    };

    const tenant = mergePublishedCard(employeeCard, undefined, templateTenant);

    expect(tenant.hero.titleLines).toEqual(["林顾问", "解决方案顾问"]);
    expect(tenant.hero.summary).toBe("帮助制造企业梳理数智化落地路径。");
    expect(tenant.seo.description).toBe("帮助制造企业梳理数智化落地路径。");
  });

  it("builds a safe runtime layout for a database-only tenant", () => {
    const tenant = mergePublishedCard(card, undefined, templateTenant);

    expect(tenant.id).toBe("example-company");
    expect(tenant.brand.name).toBe("示例企业");
    expect(tenant.sections.map((section) => section.type)).toEqual([
      "feature-grid",
      "faq",
      "closing",
    ]);
    expect(tenant.assistant.knowledgeBase[0]?.id).toBe("faq-service");
    expect(tenant.assistant.quickQuestionIds).toEqual(["faq-service"]);
    expect(validateTenantConfig(tenant)).toEqual({ valid: true, errors: [] });
  });

  it("preserves a registered layout while replacing published FAQ content", () => {
    const tenant = mergePublishedCard(card, templateTenant);
    const faq = tenant.sections.find((section) => section.type === "faq");

    expect(tenant.sections).toHaveLength(templateTenant.sections.length);
    expect(faq?.type === "faq" ? faq.itemIds : []).toEqual(["faq-service"]);
    expect(tenant.hero).toEqual(templateTenant.hero);
    expect(tenant.seo).toEqual(templateTenant.seo);
    expect(tenant.footer).toEqual(templateTenant.footer);
  });

  it("keeps a curated tenant narrative while mapping namespaced knowledge IDs", () => {
    const publishedTuotu: PublicCardData = {
      ...card,
      slug: "tuotu",
      title: "拓浙 AI 集团",
      company: {
        ...card.company,
        name: "拓浙 AI 集团",
        summary: "数据库中的简短摘要不应覆盖策划完成的首屏。",
        website: undefined,
      },
      faq_items: [
        {
          id: "faq-overview",
          question: "拓浙 AI 集团主要做什么？",
          answer: "公开介绍。",
          source_label: "集团资料",
        },
        {
          id: "faq-service",
          question: "AI 场景服务包括哪些内容？",
          answer: "服务介绍。",
          source_label: "集团资料",
        },
      ],
      ai_assistant: {
        ...card.ai_assistant,
        display_name: "拓浙 AI 集团资料助手",
        suggested_questions: ["拓浙 AI 集团主要做什么？"],
      },
    };

    const tenant = mergePublishedCard(publishedTuotu, tuotuTenant);
    const faq = tenant.sections.find((section) => section.type === "faq");

    expect(tenant.hero).toEqual(tuotuTenant.hero);
    expect(tenant.seo).toEqual(tuotuTenant.seo);
    expect(tenant.brand.name).toBe("拓浙 AI 集团");
    expect(faq?.type === "faq" ? faq.itemIds : []).toEqual([
      "faq-overview",
      "faq-service",
    ]);
    expect(tenant.assistant.quickQuestionIds).toEqual([
      "faq-overview",
      "faq-service",
    ]);
    expect(validateTenantConfig(tenant)).toEqual({ valid: true, errors: [] });
  });
});

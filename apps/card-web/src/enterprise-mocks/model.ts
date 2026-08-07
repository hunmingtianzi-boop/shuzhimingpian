import { useEffect, useMemo, useState } from "react";

import type { EnterpriseCardConfig } from "../domain/card";
import type { PublicCardData } from "../lib/publicCardApi";
import {
  fetchPublicCatalog,
  type PublicCatalog,
} from "../lib/publicExperienceApi";

export type EnterpriseMockLayout = "summary" | "accordion" | "intent";

export type EnterpriseMockBusiness = {
  id: string;
  eyebrow: string;
  title: string;
  summary: string;
  detail: string;
  audience: string;
};

export type EnterpriseMockCase = {
  id: string;
  title: string;
  summary: string;
  result: string;
};

export type EnterpriseMockFaq = {
  id: string;
  question: string;
  answer: string;
  source: string;
};

export type EnterpriseMockIntent = {
  id: "talent" | "activity" | "enterprise";
  eyebrow: string;
  title: string;
  description: string;
  assistantQuestion: string;
};

export type EnterpriseMockContent = {
  companyName: string;
  companySummary: string;
  descriptor: string;
  logoUrl: string;
  logoAlt: string;
  websiteUrl: string;
  publishedLabel: string;
  businesses: EnterpriseMockBusiness[];
  cases: EnterpriseMockCase[];
  faqs: EnterpriseMockFaq[];
  intents: EnterpriseMockIntent[];
  metrics: Array<{ value: string; label: string; note: string }>;
  sourceLabel: string;
};

export type EnterpriseMockVariantProps = {
  content: EnterpriseMockContent;
  onAssistant: (question?: string) => void;
  onLead: () => void;
};

const mockLayouts = new Set<EnterpriseMockLayout>([
  "summary",
  "accordion",
  "intent",
]);

export function resolveEnterpriseMockLayout(search: string) {
  const candidate = new URLSearchParams(search).get("mock-layout");
  return mockLayouts.has(candidate as EnterpriseMockLayout)
    ? (candidate as EnterpriseMockLayout)
    : undefined;
}

function valueFromRecord(
  record: Record<string, string>,
  keys: string[],
  fallback: string,
) {
  for (const key of keys) {
    const value = record[key]?.trim();
    if (value) return value;
  }
  return fallback;
}

function buildContent(
  tenant: EnterpriseCardConfig,
  card: PublicCardData | undefined,
  catalog: PublicCatalog | undefined,
): EnterpriseMockContent {
  const featureSection = tenant.sections.find(
    (section) => section.type === "feature-grid",
  );
  const evidenceSection = tenant.sections.find(
    (section) => section.type === "evidence",
  );

  const tenantBusinesses = featureSection?.businesses ?? [];
  const featuredProducts = card?.featured_products ?? [];
  const businesses: EnterpriseMockBusiness[] = catalog?.products.length
    ? catalog.products.map((item) => ({
        id: item.slug,
        eyebrow: item.category || "产品与服务",
        title: item.name,
        summary: item.summary,
        detail: item.detail,
        audience: item.audience || "适合希望推进真实 AI 项目的团队",
      }))
    : featuredProducts.length
      ? featuredProducts.map((item, index) => ({
          id: valueFromRecord(item, ["slug", "id"], `featured-${index}`),
          eyebrow: valueFromRecord(item, ["category", "type"], "产品与服务"),
          title: valueFromRecord(item, ["name", "title", "label"], `业务 ${index + 1}`),
          summary: valueFromRecord(item, ["summary", "description", "value"], "了解这项业务的服务范围与合作方式。"),
          detail: valueFromRecord(item, ["detail", "description", "summary"], "具体范围、周期和交付方式需结合实际需求确认。"),
          audience: valueFromRecord(item, ["audience", "target"], "适合希望推进真实 AI 项目的团队"),
        }))
      : tenantBusinesses.map((item, index) => ({
          id: `tenant-business-${index}`,
          eyebrow: item.eyebrow,
          title: item.title,
          summary: item.description,
          detail: item.points.join("、"),
          audience: item.status,
        }));

  const featuredCases = card?.featured_cases ?? [];
  const cases: EnterpriseMockCase[] = catalog?.cases.length
    ? catalog.cases.map((item) => ({
        id: item.slug,
        title: item.title,
        summary: item.solution,
        result: item.result,
      }))
    : featuredCases.length
      ? featuredCases.map((item, index) => ({
          id: valueFromRecord(item, ["slug", "id"], `featured-case-${index}`),
          title: valueFromRecord(item, ["title", "name", "label"], `案例 ${index + 1}`),
          summary: valueFromRecord(item, ["summary", "solution", "description"], "围绕真实场景完成需求梳理与联合验证。"),
          result: valueFromRecord(item, ["result", "outcome", "value"], "形成可复盘的阶段成果。"),
        }))
      : evidenceSection
        ? [{
            id: evidenceSection.id,
            title: evidenceSection.heading,
            summary: evidenceSection.description,
            result: evidenceSection.metricDescription,
          }]
        : [];

  const faqs: EnterpriseMockFaq[] = card?.faq_items.length
    ? card.faq_items.map((item) => ({
        id: item.id,
        question: item.question,
        answer: item.answer,
        source: item.source_label,
      }))
    : tenant.assistant.knowledgeBase.map((item) => ({
        id: item.id,
        question: item.question,
        answer: item.answer.replace(/\*\*/g, "").replace(/\n[-\d.]\s*/g, " "),
        source: item.source,
      }));

  return {
    companyName: card?.company.name || tenant.brand.name,
    companySummary: card?.company.summary || tenant.hero.summary,
    descriptor:
      [card?.company.industry, card?.company.region].filter(Boolean).join(" · ") ||
      tenant.brand.headerDescriptor,
    logoUrl: card?.company.logo_url || tenant.brand.logo.src,
    logoAlt: tenant.brand.logo.alt,
    websiteUrl: card?.company.website || tenant.brand.officialAction.target,
    publishedLabel: card ? "资料已发布" : "本地品牌资料",
    businesses,
    cases,
    faqs,
    intents: [
      {
        id: "talent",
        eyebrow: "我是学生或青年人才",
        title: "加入学习与项目",
        description: "找到适合自己的训练、组队与真实项目入口。",
        assistantQuestion: "学生可以如何加入并获得成长？",
      },
      {
        id: "activity",
        eyebrow: "我关注活动与赛事",
        title: "了解浙客松",
        description: "查看活动方式、参与路径与成果展示边界。",
        assistantQuestion: "浙客松是什么，如何参与？",
      },
      {
        id: "enterprise",
        eyebrow: "我是企业或合作伙伴",
        title: "发起场景共创",
        description: "从具体问题出发，评估原型、项目与人才合作。",
        assistantQuestion: "企业可以怎样与拓浙 AI 集团合作？",
      },
    ],
    metrics: tenant.hero.metrics,
    sourceLabel: "内容来自 2026 年 7 月整合材料，合作范围以双方确认结果为准。",
  };
}

export function useEnterpriseMockContent(
  tenant: EnterpriseCardConfig,
  card?: PublicCardData,
) {
  const [catalog, setCatalog] = useState<PublicCatalog>();

  useEffect(() => {
    if (!card?.slug) return;
    const controller = new AbortController();
    void fetchPublicCatalog(card.slug, controller.signal)
      .then(setCatalog)
      .catch(() => {
        // A mock must stay reviewable even when the local API is unavailable.
      });
    return () => controller.abort();
  }, [card?.slug]);

  return useMemo(
    () => buildContent(tenant, card, catalog),
    [tenant, card, catalog],
  );
}

import type {
  BusinessItem,
  EnterpriseCardConfig,
  EnterpriseCardSection,
  KnowledgeItem,
} from "../domain/card";
import type { PublicCardData } from "./publicCardApi";
import { resolvePublicResourceUrl } from "./publicResourceUrl";

export { fetchPublicCard } from "./publicCardApi";
export type { PublicCardData } from "./publicCardApi";

function toKnowledgeItems(card: PublicCardData): KnowledgeItem[] {
  return card.faq_items.map((item) => ({
    id: item.id,
    question: item.question,
    shortQuestion: item.question.length > 18 ? `${item.question.slice(0, 17)}…` : item.question,
    answer: item.answer,
    keywords: [item.question, ...item.question.split(/[，。？?、\s]+/)].filter(Boolean),
    source: item.source_label,
  }));
}

function productBusinesses(card: PublicCardData): BusinessItem[] {
  const products = card.featured_products.slice(0, 3).map((item) => ({
    icon: "globe",
    eyebrow: "产品与服务",
    title: item.title || "企业服务",
    description: item.description || "详情请咨询企业工作人员。",
    status: "已发布",
    points: ["企业公开资料", "详情以官方确认为准"],
  }));
  const cases = card.featured_cases.slice(0, Math.max(0, 4 - products.length)).map((item) => ({
    icon: "book",
    eyebrow: "公开案例",
    title: item.title || "企业案例",
    description: item.description || "案例内容已经企业审核后公开。",
    status: "已审核",
    points: [item.industry || "公开案例", "内容已经企业审核"],
  }));
  const businesses = [...products, ...cases];
  if (!businesses.length) {
    businesses.push(
    {
      icon: "buildings",
      eyebrow: card.company.industry || "企业介绍",
      title: card.company.name,
      description: card.company.summary || "企业资料正在完善，请通过官方渠道确认详情。",
      status: "已发布",
      points: [card.company.region || "企业公开资料", card.company.website || "官方渠道待完善"],
    },
    );
  }
  if (businesses.length < 2) {
    businesses.push({
      icon: "book",
      eyebrow: "企业知识库",
      title: card.ai_assistant.display_name,
      description: "资料助手只根据企业审核并发布的知识回答问题。",
      status: card.ai_assistant.available ? "在线" : "待配置",
      points: [`${card.faq_items.length} 条公开知识`, "无依据问题不会猜测"],
    });
  }
  return businesses;
}

function dynamicSections(
  card: PublicCardData,
  knowledge: KnowledgeItem[],
  base: EnterpriseCardConfig,
): EnterpriseCardSection[] {
  const feature: EnterpriseCardSection = {
    type: "feature-grid",
    id: "business",
    navLabel: "企业",
    showInNav: true,
    heading: "了解企业与业务",
    description: "以下内容来自企业当前已发布资料。",
    businesses: productBusinesses(card),
  };
  const faq: EnterpriseCardSection = {
    type: "faq",
    id: "faq",
    navLabel: "FAQ",
    showInNav: knowledge.length > 0,
    heading: "常见问题",
    description: "回答来自企业审核并发布的知识资料。",
    itemIds: knowledge.map((item) => item.id),
  };
  const closing: EnterpriseCardSection = {
    type: "closing",
    id: "closing",
    navLabel: "联系",
    showInNav: false,
    heading: "需要进一步了解？",
    description: "可以向资料助手提问，或前往企业官方渠道确认。",
    art: base.hero.art,
    actions: card.company.website
      ? [{ kind: "external", label: "访问企业官网", target: card.company.website }]
      : [{ kind: "assistant", label: "向资料助手提问", target: knowledge[0]?.question ?? "请介绍一下这家企业" }],
  };
  return knowledge.length ? [feature, faq, closing] : [feature, closing];
}

export function mergePublishedCard(
  card: PublicCardData,
  staticTenant?: EnterpriseCardConfig,
  fallbackTenant?: EnterpriseCardConfig,
): EnterpriseCardConfig {
  const base = staticTenant ?? fallbackTenant;
  if (!base) throw new Error("A base tenant is required to render a published card");
  const knowledge = toKnowledgeItems(card);
  const faqIds = knowledge.map((item) => item.id);
  const logoSrc = resolvePublicResourceUrl(card.company.logo_url || card.avatar_url) || base.brand.logo.src;
  const website =
    card.company.website ||
    (staticTenant
      ? base.brand.officialAction.target
      : `${globalThis.location?.origin ?? "http://localhost"}/c/${card.slug}`);
  const shortName = card.company.name.length > 10 ? card.company.name.slice(0, 10) : card.company.name;

  if (staticTenant) {
    const dynamicIds = new Set(faqIds);
    const staticKnowledge = new Map(
      base.assistant.knowledgeBase.map((item) => [item.id, item]),
    );
    const resolvePublishedKnowledgeId = (id: string) => {
      if (dynamicIds.has(id)) return id;
      const namespacedId = `faq-${id}`;
      if (dynamicIds.has(namespacedId)) return namespacedId;
      const question = staticKnowledge.get(id)?.question;
      return question
        ? knowledge.find((item) => item.question === question)?.id
        : undefined;
    };
    const mapPublishedIds = (ids: string[]) =>
      ids
        .map(resolvePublishedKnowledgeId)
        .filter((id): id is string => Boolean(id))
        .filter((id, index, values) => values.indexOf(id) === index);
    const sections = base.sections.map((section) => {
      if (section.type !== "faq" || !faqIds.length) return section;
      const curatedIds = mapPublishedIds(section.itemIds);
      return {
        ...section,
        itemIds: curatedIds.length ? curatedIds : faqIds.slice(0, 6),
      };
    });
    const suggestedIds = card.ai_assistant.suggested_questions
      .map((question) => knowledge.find((item) => item.question === question)?.id)
      .filter((id): id is string => Boolean(id));
    const quickQuestionIds = [
      ...mapPublishedIds(base.assistant.quickQuestionIds),
      ...suggestedIds,
      ...faqIds,
    ]
      .filter((id, index, values) => values.indexOf(id) === index)
      .slice(0, 3);

    return {
      ...base,
      id: card.slug,
      version: `${base.version}:db`,
      brand: {
        ...base.brand,
        logo:
          logoSrc === base.brand.logo.src
            ? base.brand.logo
            : { ...base.brand.logo, src: logoSrc, alt: `${base.brand.name}标识` },
        officialAction: { ...base.brand.officialAction, target: website },
      },
      sections,
      assistant: {
        ...base.assistant,
        title: card.ai_assistant.display_name,
        status: card.ai_assistant.available ? "在线" : "待配置",
        subtitle: "企业知识库 · 实时 AI 回答",
        launcherAriaLabel: `打开${card.ai_assistant.display_name}`,
        quickQuestionIds,
        knowledgeBase: knowledge.length ? knowledge : base.assistant.knowledgeBase,
      },
    };
  }

  const sections = dynamicSections(card, knowledge, base);
  const isEmployeeCard = card.card_kind === "employee";
  const publicSummary = isEmployeeCard
    ? card.business_summary || card.company.summary
    : card.company.summary;

  return {
    ...base,
    id: card.slug,
    version: `${base.version}:db`,
    seo: {
      title: `${card.title} | 数智名片`,
      description: publicSummary || `${card.company.name}企业数智名片`,
    },
    brand: {
      ...base.brand,
      name: card.company.name,
      shortName,
      tagline: card.title,
      headerDescriptor: card.company.industry || "企业数智名片",
      logo: { ...base.brand.logo, src: logoSrc, alt: `${card.company.name}标识` },
      homeAriaLabel: `返回${card.company.name}首页`,
      officialAction: { kind: "external", label: "官网", target: website },
    },
    hero: {
      ...base.hero,
      kicker: card.company.industry || "企业数智名片",
      titleLines: isEmployeeCard
        ? [card.display_name, card.title]
        : [card.company.name, card.title === card.company.name ? "企业数智名片" : card.title],
      summary: publicSummary || "企业资料正在完善，请以正式发布内容为准。",
      actions: knowledge.length
        ? [{ kind: "assistant", label: "向资料助手提问", target: knowledge[0].question }]
        : card.company.website
          ? [{ kind: "external", label: "访问企业官网", target: card.company.website }]
          : [{ kind: "anchor", label: "查看企业资料", target: "#business" }],
      metrics: [
        { value: `${knowledge.length} 条`, label: "公开知识", note: "企业审核后发布" },
        {
          value: `${card.featured_products.length} 项`,
          label: "产品与服务",
          note: "来自当前企业资料",
        },
        {
          value: `${card.featured_cases.length} 项`,
          label: "公开案例",
          note: "仅展示获准内容",
        },
        {
          value: card.ai_assistant.available ? "在线" : "待配置",
          label: "资料助手",
          note: "基于已发布知识回答",
        },
      ],
    },
    sections,
    assistant: {
      ...base.assistant,
      title: card.ai_assistant.display_name,
      status: card.ai_assistant.available ? "在线" : "待配置",
      subtitle: "企业知识库 · 实时 AI 回答",
      launcherAriaLabel: `打开${card.ai_assistant.display_name}`,
      launcherKicker: "资料内回答",
      initialMessage: {
        text: card.ai_assistant.welcome_message,
        source: "企业已发布知识库",
      },
      quickQuestionIds: card.ai_assistant.suggested_questions
        .map((question) => knowledge.find((item) => item.question === question)?.id)
        .filter((id): id is string => Boolean(id))
        .concat(faqIds)
        .filter((id, index, values) => values.indexOf(id) === index)
        .slice(0, 3),
      disclaimer: card.ai_assistant.disclosure,
      knowledgeBase: knowledge.length ? knowledge : base.assistant.knowledgeBase,
      fallback: {
        answer: "当前已发布资料没有覆盖这个问题，请联系企业工作人员确认。",
        source: "企业已发布知识库",
      },
    },
    footer: {
      ...base.footer,
      brandNote: `${card.company.name}企业数智名片`,
      disclaimer: card.ai_assistant.disclosure,
    },
  };
}

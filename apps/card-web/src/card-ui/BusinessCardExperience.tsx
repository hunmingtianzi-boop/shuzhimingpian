import {
  ArrowRight,
  Briefcase,
  Buildings,
  ChatCircleDots,
  Handshake,
  PaperPlaneTilt,
  Path,
  Robot,
  ShareNetwork,
  ShieldCheck,
  Target,
  User,
  X,
} from "@phosphor-icons/react";
import { useReducedMotion } from "motion/react";
import {
  type CSSProperties,
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";

import type {
  CardCaseStudy,
  CardPresentation,
  CardSolution,
  EnterpriseCardConfig,
  OwnerPresentation,
  ResponsiveMediaAsset,
} from "../domain/card";
import type { PublicCardData } from "../lib/publicCardApi";
import {
  fetchPublicCatalog,
  fetchPublicRecommendations,
  isPublicExperienceConfigured,
  type PublicCatalog,
  type PublicRecommendation,
} from "../lib/publicExperienceApi";
import {
  AssistantPage,
  type AssistantRelatedSection,
  type PendingAssistantQuestion,
} from "./AssistantPage";

import "./card-ui.css";

type CardView = "personal" | "enterprise" | "assistant";

type EnterpriseSectionFocus = {
  id: string;
  requestId: number;
};

export type BusinessCardExperienceHandle = {
  openAssistant: (question?: string) => void;
};

function readView(search: string): CardView {
  const value = new URLSearchParams(search).get("view");
  if (value === "enterprise" || value === "assistant") return value;
  // `owner` is the legacy personal-page route and remains readable for shared links.
  return "personal";
}

function readEnterpriseSection(search: string) {
  const value = new URLSearchParams(search).get("section")?.trim();
  return value?.startsWith("enterprise-") ? value : undefined;
}

function sectionKeywords(...values: Array<string | undefined>) {
  return values.flatMap((value) => {
    const trimmed = value?.trim();
    if (!trimmed) return [];
    return [
      trimmed,
      ...trimmed
        .split(/[\s，。！？、,.!?：:；;（）()【】\[\]\/|与和及]+/)
        .map((part) => part.trim())
        .filter((part) => part.length >= 2),
    ];
  });
}

function ResponsiveImage({
  asset,
  className,
  eager = false,
}: {
  asset: ResponsiveMediaAsset;
  className?: string;
  eager?: boolean;
}) {
  return (
    <img
      className={className}
      src={asset.src}
      srcSet={asset.srcSet}
      sizes={asset.sizes}
      width={asset.width}
      height={asset.height}
      alt={asset.alt}
      loading={eager ? "eager" : "lazy"}
      fetchPriority={eager ? "high" : "auto"}
      decoding="async"
    />
  );
}

function fallbackSolutions(tenant: EnterpriseCardConfig): CardSolution[] {
  const businessSection = tenant.sections.find((section) => section.type === "feature-grid");
  if (businessSection?.type === "feature-grid") {
    return businessSection.businesses.slice(0, 3).map((item, index) => ({
      id: `solution-${index}`,
      title: item.title,
      description: item.description,
    }));
  }
  return [
    { id: "overview", title: "企业能力", description: tenant.hero.summary },
    { id: "service", title: "解决方案", description: "围绕真实业务问题形成可执行的协作方案。" },
    { id: "cooperation", title: "合作共创", description: "连接资源、项目与团队，持续推进价值落地。" },
  ];
}

function fallbackOwner(tenant: EnterpriseCardConfig): OwnerPresentation {
  return {
    demoLabel: "演示资料，待替换",
    name: "负责人姓名",
    role: "创始人 / 总经理",
    summary: `负责${tenant.brand.name}的战略规划、业务协作与项目推进。`,
    valueProposition: "以长期价值为核心，与优秀伙伴共同推动真实问题获得持续解决。",
    capabilities: ["战略规划", "资源整合", "商务合作"],
    experiences: [
      { period: "20XX - 至今", organization: "公司名称 A", role: "创始人 / 总经理", description: "负责公司战略、运营与重点项目推进。" },
      { period: "20XX - 20XX", organization: "公司名称 B", role: "联合创始人 / 副总裁", description: "负责业务建设、资源协同与市场拓展。" },
      { period: "20XX - 20XX", organization: "公司名称 C", role: "高级经理", description: "参与关键项目与团队协作。" },
    ],
    portrait: tenant.hero.art,
  };
}

function fallbackCase(tenant: EnterpriseCardConfig): CardCaseStudy {
  return {
    title: tenant.sections.find((section) => section.type === "evidence")?.heading ?? "企业实践案例",
    category: "公开案例",
    description: tenant.hero.summary,
    detail: tenant.footer.disclaimer,
    visual: tenant.hero.art,
  };
}

function resolvePresentation(tenant: EnterpriseCardConfig): CardPresentation {
  return (
    tenant.presentation ?? {
      heroVisual: tenant.hero.art,
      heroSummary: tenant.hero.summary,
      solutions: fallbackSolutions(tenant),
      caseStudy: fallbackCase(tenant),
      owner: fallbackOwner(tenant),
      assistantVisual: tenant.brand.logo,
      assistantRecommendations: tenant.assistant.knowledgeBase.slice(0, 3).map((item) => ({
        title: item.shortQuestion,
        description: item.question,
        question: item.question,
      })),
    }
  );
}

function publishedItems(items: Array<Record<string, string>>, prefix: string): CardSolution[] {
  return items.flatMap((item, index) => {
    const title = item.title?.trim();
    if (!title) return [];
    return [{
      id: `${prefix}-${index}`,
      title,
      description: item.description?.trim() || "查看企业已发布业务资料。",
    }];
  });
}

function publishedCase(
  card: PublicCardData,
  presentation: CardPresentation,
  catalog?: PublicCatalog,
): CardCaseStudy | undefined {
  const record = catalog?.cases[0];
  if (record) {
    return {
      title: record.title,
      category: record.industry || "公开案例",
      description: record.background,
      detail: [record.background, record.solution, record.result].filter(Boolean).join(" "),
      visual: record.imageUrl
        ? {
            ...presentation.caseStudy.visual,
            src: record.imageUrl,
            srcSet: undefined,
            sizes: undefined,
            alt: `${record.title}案例图片`,
          }
        : presentation.caseStudy.visual,
    };
  }
  const featured = card.featured_cases.find((item) => item.title?.trim());
  if (!featured) return undefined;
  return {
    ...presentation.caseStudy,
    title: featured.title.trim(),
    category: featured.industry?.trim() || "公开案例",
    description: featured.description?.trim() || card.company.summary,
    detail: featured.description?.trim() || presentation.caseStudy.detail,
  };
}

function mergePublishedPresentation(
  base: CardPresentation,
  card?: PublicCardData,
  catalog?: PublicCatalog,
  recommendations?: PublicRecommendation[],
): CardPresentation {
  if (!card) return base;
  const keepsCuratedHomepage = base.homepageContentMode === "curated";
  const catalogSolutions = catalog?.products.map((product) => ({
    id: product.slug,
    title: product.name,
    description: product.summary,
  })) ?? [];
  const featuredSolutions = publishedItems(card.featured_products, "featured-product");
  const publishedSolutions = catalogSolutions.length ? catalogSolutions : featuredSolutions;
  const publishedRecommendations = (recommendations ?? []).map((item) => ({
    title: item.title,
    description: item.summary,
    question: `请介绍一下${item.title}`,
  }));
  return {
    ...base,
    heroSummary: keepsCuratedHomepage
      ? base.heroSummary
      : card.company.summary || base.heroSummary,
    solutions: keepsCuratedHomepage
      ? base.solutions
      : publishedSolutions.length
        ? publishedSolutions.slice(0, 3)
        : base.solutions,
    caseStudy: keepsCuratedHomepage
      ? base.caseStudy
      : publishedCase(card, base, catalog) ?? base.caseStudy,
    assistantRecommendations: publishedRecommendations.length
      ? publishedRecommendations.slice(0, 3)
      : base.assistantRecommendations,
  };
}

function BrandHeader({
  name,
  logo,
  descriptor,
  onShare,
}: {
  name: string;
  logo: ResponsiveMediaAsset;
  descriptor: string;
  onShare: () => void;
}) {
  return (
    <header className="tz-brand-header">
      <div className="tz-brand-lockup">
        <img src={logo.src} width={logo.width} height={logo.height} alt={logo.alt} />
        <div>
          <strong>{name}</strong>
          <span>{descriptor}</span>
        </div>
      </div>
      <button type="button" onClick={onShare} aria-label="分享名片">
        <ShareNetwork weight="bold" aria-hidden="true" />
      </button>
    </header>
  );
}

function EnterprisePage({
  tenant,
  card,
  presentation,
  onAssistant,
  onLead,
  onShare,
  onPrivacy,
  onProfile,
  focusedSection,
}: {
  tenant: EnterpriseCardConfig;
  card?: PublicCardData;
  presentation: CardPresentation;
  onAssistant: (question?: string) => void;
  onLead: () => void;
  onShare: () => void;
  onPrivacy: () => void;
  onProfile: () => void;
  focusedSection?: EnterpriseSectionFocus;
}) {
  const [caseOpen, setCaseOpen] = useState(false);
  const reducedMotion = useReducedMotion();
  const companyName = card?.company.name || tenant.brand.name;
  const logo: ResponsiveMediaAsset = {
    ...tenant.brand.logo,
    src: card?.company.logo_url || tenant.brand.logo.src,
    alt: `${companyName}品牌标识`,
  };
  const metrics = tenant.hero.metrics.slice(0, 3);
  const metricsNote = tenant.id === "tuotu" ? "截至 2026.07" : "已发布资料";

  useEffect(() => {
    if (!focusedSection) return undefined;
    let secondFrame = 0;
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => {
        const target = document.getElementById(focusedSection.id);
        if (!target) return;
        target.scrollIntoView({
          behavior: reducedMotion ? "auto" : "smooth",
          block: "center",
        });
        target.focus({ preventScroll: true });
      });
    });
    return () => {
      window.cancelAnimationFrame(firstFrame);
      if (secondFrame) window.cancelAnimationFrame(secondFrame);
    };
  }, [focusedSection, reducedMotion]);

  return (
    <main className="tz-page tz-enterprise-page" id="enterprise-view">
      <BrandHeader
        name={companyName}
        logo={logo}
        descriptor={tenant.brand.tagline || "数智企业名片"}
        onShare={onShare}
      />

      <section
        id="enterprise-overview"
        className={`tz-enterprise-hero ${focusedSection?.id === "enterprise-overview" ? "is-ai-focused" : ""}`}
        aria-labelledby="enterprise-hero-title"
        tabIndex={-1}
      >
        <ResponsiveImage asset={presentation.heroVisual} className="tz-enterprise-hero-image" eager />
        <div className="tz-enterprise-hero-overlay" />
        <div className="tz-enterprise-hero-content">
          <h1 id="enterprise-hero-title">
            {tenant.hero.titleLines.map((line) => <span key={line}>{line}</span>)}
          </h1>
          <p>{presentation.heroSummary || card?.company.summary || tenant.hero.summary}</p>
          <div className="tz-hero-actions">
            <button type="button" className="tz-primary-action" onClick={() => onAssistant()}>
              <ChatCircleDots weight="fill" aria-hidden="true" />与 AI 对话
            </button>
            <button type="button" className="tz-secondary-action" onClick={onLead}>
              <Handshake weight="duotone" aria-hidden="true" />发起合作
            </button>
          </div>
        </div>
      </section>

      <section
        id="enterprise-proof"
        className={`tz-proof-strip ${focusedSection?.id === "enterprise-proof" ? "is-ai-focused" : ""}`}
        aria-labelledby="proof-title"
        tabIndex={-1}
      >
        <div className="tz-proof-heading">
          <strong id="proof-title">阶段成果</strong>
          <span>{metricsNote}</span>
        </div>
        <div className="tz-metric-rail">
          {metrics.map((metric) => (
            <article key={metric.label}>
              <strong>{metric.value}</strong>
              <span>{metric.label}</span>
            </article>
          ))}
        </div>
      </section>

      <section
        id="enterprise-solutions"
        className={`tz-capability-list ${focusedSection?.id === "enterprise-solutions" ? "is-ai-focused" : ""}`}
        aria-labelledby="solutions-title"
        tabIndex={-1}
      >
        <h2 id="solutions-title">三大业务</h2>
        <div className="tz-capability-rows">
          {presentation.solutions.slice(0, 3).map((solution, index) => (
            <button
              id={`enterprise-solution-${index}`}
              className={focusedSection?.id === `enterprise-solution-${index}` ? "is-ai-focused" : undefined}
              key={solution.id}
              type="button"
              onClick={() => onAssistant(`请介绍${solution.title}`)}
            >
              <strong>{solution.title}</strong>
            </button>
          ))}
        </div>
      </section>

      <button
        id="enterprise-case"
        type="button"
        className={`tz-featured-case ${focusedSection?.id === "enterprise-case" ? "is-ai-focused" : ""}`}
        aria-haspopup="dialog"
        onClick={() => setCaseOpen(true)}
      >
        <ResponsiveImage asset={presentation.caseStudy.visual} className="tz-featured-case-image" />
        <span className="tz-featured-case-copy">
          <small>代表案例</small>
          <strong>{presentation.caseStudy.title}</strong>
          <i>{presentation.caseStudy.description}</i>
        </span>
        <ArrowRight aria-hidden="true" />
      </button>

      <footer className="tz-card-footer">
        <div><ShieldCheck weight="duotone" aria-hidden="true" /><span>{tenant.footer.disclaimer}</span></div>
        <nav aria-label="隐私与资料说明">
          <button type="button" onClick={onPrivacy}>隐私说明</button>
          <i />
          <button type="button" onClick={onProfile}>资料与授权</button>
        </nav>
      </footer>

      {caseOpen && (
        <div className="tz-case-modal" role="dialog" aria-modal="true" aria-labelledby="case-dialog-title">
          <div className="tz-case-modal-card">
            <button type="button" className="tz-case-modal-close" onClick={() => setCaseOpen(false)} aria-label="关闭案例详情">
              <X weight="bold" aria-hidden="true" />
            </button>
            <ResponsiveImage asset={presentation.caseStudy.visual} className="tz-case-modal-image" />
            <span>{presentation.caseStudy.category}</span>
            <h2 id="case-dialog-title">{presentation.caseStudy.title}</h2>
            <p>{presentation.caseStudy.detail}</p>
          </div>
        </div>
      )}
    </main>
  );
}

function PersonalPage({
  tenant,
  card,
  presentation,
  onLead,
  onShare,
}: {
  tenant: EnterpriseCardConfig;
  card?: PublicCardData;
  presentation: CardPresentation;
  onLead: () => void;
  onShare: () => void;
}) {
  const companyName = card?.company.name || tenant.brand.name;
  const hasRealOwner = Boolean(
    card && card.card_kind !== "enterprise" && card.display_name !== card.company.name,
  );
  const owner = presentation.owner;
  const ownerName = hasRealOwner ? card!.display_name : owner.name;
  const ownerRole = hasRealOwner && card?.title ? card.title : owner.role;
  const portrait = card?.avatar_url
    ? { ...owner.portrait, src: card.avatar_url, srcSet: undefined, alt: `${ownerName}头像` }
    : owner.portrait;
  const logo: ResponsiveMediaAsset = {
    ...tenant.brand.logo,
    src: card?.company.logo_url || tenant.brand.logo.src,
    alt: `${companyName}品牌标识`,
  };
  const capabilityIcons = [Path, Target, Handshake];

  return (
    <main className="tz-page tz-owner-page" id="personal-view">
      <BrandHeader
        name={companyName}
        logo={logo}
        descriptor={tenant.brand.tagline || "数智企业名片"}
        onShare={onShare}
      />

      <section className="tz-owner-profile" aria-labelledby="owner-name">
        <div className="tz-owner-portrait-wrap">
          <ResponsiveImage asset={portrait} className="tz-owner-portrait" eager />
          <span>{owner.demoLabel}</span>
        </div>
        <div className="tz-owner-identity">
          <small>{hasRealOwner ? "公开名片资料" : "个人演示名片"}</small>
          <h1 id="owner-name">{ownerName}</h1>
          <p>{ownerRole}</p>
          <div className="tz-owner-rule" />
          <blockquote>“{owner.valueProposition}”</blockquote>
        </div>
        <p className="tz-owner-summary">{owner.summary}</p>
        <div className="tz-capabilities" aria-label="核心能力">
          {owner.capabilities.slice(0, 3).map((capability, index) => {
            const Icon = capabilityIcons[index] ?? Target;
            return <span key={capability}><Icon weight="duotone" aria-hidden="true" />{capability}</span>;
          })}
        </div>
      </section>

      <section className="tz-panel tz-owner-experience" aria-labelledby="experience-title">
        <div className="tz-section-title">
          <div><h2 id="experience-title">职业经历</h2></div>
          <small>{owner.demoLabel}</small>
        </div>
        <div className="tz-timeline">
          {owner.experiences.slice(0, 3).map((experience) => (
            <article key={`${experience.period}-${experience.organization}`}>
              <i />
              <span>{experience.period}</span>
              <h3>{experience.organization}<small>{experience.role}</small></h3>
              <p>{experience.description}</p>
            </article>
          ))}
        </div>
      </section>

      <button className="tz-contact-owner" type="button" onClick={onLead}>
        <PaperPlaneTilt weight="fill" aria-hidden="true" />联系本人
      </button>
      <p className="tz-owner-note">联系请求将进入企业合作留资流程，不直接公开个人联系方式。</p>
    </main>
  );
}

function BottomNavigation({ view, onChange }: { view: CardView; onChange: (view: CardView) => void }) {
  const tabs = [
    { id: "personal" as const, label: "个人", Icon: User },
    { id: "enterprise" as const, label: "企业", Icon: Buildings },
    { id: "assistant" as const, label: "AI 助手", Icon: Robot },
  ];
  return (
    <nav className="tz-bottom-nav" aria-label="名片导航">
      {tabs.map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          className={view === id ? "is-active" : undefined}
          aria-current={view === id ? "page" : undefined}
          onClick={() => onChange(id)}
        >
          <span><Icon weight={view === id ? "fill" : "duotone"} aria-hidden="true" /></span>
          {label}
        </button>
      ))}
    </nav>
  );
}

export const BusinessCardExperience = forwardRef<
  BusinessCardExperienceHandle,
  {
    tenant: EnterpriseCardConfig;
    card?: PublicCardData;
    assistantEnabled: boolean;
    onLead: () => void;
    onPrivacy: () => void;
    onProfile: () => void;
    onShare: () => void;
  }
>(function BusinessCardExperience(
  { tenant, card, assistantEnabled, onLead, onPrivacy, onProfile, onShare },
  ref,
) {
  const [view, setView] = useState<CardView>(() => readView(window.location.search));
  const sectionRequestId = useRef(0);
  const [focusedSection, setFocusedSection] = useState<EnterpriseSectionFocus | undefined>(() => {
    const id = readEnterpriseSection(window.location.search);
    return id ? { id, requestId: 0 } : undefined;
  });
  const [pendingQuestion, setPendingQuestion] = useState<PendingAssistantQuestion>();
  const pendingQuestionId = useRef(0);
  const reducedMotion = useReducedMotion();
  const basePresentation = useMemo(() => resolvePresentation(tenant), [tenant]);
  const [publishedCatalog, setPublishedCatalog] = useState<PublicCatalog>();
  const [publishedRecommendations, setPublishedRecommendations] = useState<PublicRecommendation[]>();
  const presentation = useMemo(
    () => mergePublishedPresentation(
      basePresentation,
      card,
      publishedCatalog,
      publishedRecommendations,
    ),
    [basePresentation, card, publishedCatalog, publishedRecommendations],
  );
  const relatedSections = useMemo<AssistantRelatedSection[]>(() => {
    const companyName = card?.company.name || tenant.brand.name;
    const metrics = tenant.hero.metrics.slice(0, 3);
    return [
      {
        id: "overview",
        targetId: "enterprise-overview",
        title: `${companyName}企业介绍`,
        description: presentation.heroSummary || tenant.hero.summary,
        keywords: sectionKeywords(
          companyName,
          tenant.hero.titleLines.join(""),
          presentation.heroSummary,
        ),
      },
      {
        id: "proof",
        targetId: "enterprise-proof",
        title: "阶段成果",
        description: metrics.map((metric) => `${metric.label} ${metric.value}`).join(" · "),
        keywords: sectionKeywords(
          "阶段成果",
          "阶段数据",
          "规模数据",
          ...metrics.flatMap((metric) => [metric.label, metric.value]),
        ),
      },
      ...presentation.solutions.slice(0, 3).map((solution, index) => ({
        id: `solution:${solution.id}`,
        targetId: `enterprise-solution-${index}`,
        title: solution.title,
        description: solution.description,
        keywords: sectionKeywords(solution.title, solution.description),
      })),
      {
        id: "case",
        targetId: "enterprise-case",
        title: presentation.caseStudy.title,
        description: presentation.caseStudy.description,
        keywords: sectionKeywords(
          presentation.caseStudy.title,
          presentation.caseStudy.category,
          presentation.caseStudy.description,
          "代表案例",
          "成功案例",
        ),
      },
      {
        id: "cooperation",
        targetId: "enterprise-overview",
        title: "合作入口",
        description: "查看合作方向并发起联系。",
        keywords: sectionKeywords("企业合作", "合作方式", "发起合作", "商务合作", "项目合作"),
      },
    ];
  }, [card?.company.name, presentation, tenant.brand.name, tenant.hero]);

  useEffect(() => {
    setPublishedCatalog(undefined);
    setPublishedRecommendations(undefined);
    if (!card || card.card_kind === "employee" || !isPublicExperienceConfigured()) return undefined;
    const controller = new AbortController();
    void Promise.allSettled([
      fetchPublicCatalog(card.slug, controller.signal),
      fetchPublicRecommendations(card.slug, controller.signal),
    ]).then(([catalogResult, recommendationResult]) => {
      if (controller.signal.aborted) return;
      if (catalogResult.status === "fulfilled") setPublishedCatalog(catalogResult.value);
      if (recommendationResult.status === "fulfilled") {
        setPublishedRecommendations(recommendationResult.value);
      }
    });
    return () => controller.abort();
  }, [card?.card_kind, card?.slug]);

  useEffect(() => {
    const onPopState = () => {
      const nextView = readView(window.location.search);
      const sectionId = readEnterpriseSection(window.location.search);
      setView(nextView);
      if (nextView === "enterprise" && sectionId) {
        sectionRequestId.current += 1;
        setFocusedSection({ id: sectionId, requestId: sectionRequestId.current });
      } else {
        setFocusedSection(undefined);
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = "dark";
    document.documentElement.style.colorScheme = "dark";
    document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute("content", "#030b19");

    const hero = presentation.heroVisual;
    let preload = document.head.querySelector<HTMLLinkElement>('link[data-card-ui-asset="hero"]');
    if (!preload) {
      preload = document.createElement("link");
      preload.rel = "preload";
      preload.as = "image";
      preload.dataset.cardUiAsset = "hero";
      document.head.append(preload);
    }
    preload.href = hero.src;
    if (hero.srcSet) preload.imageSrcset = hero.srcSet;
    if (hero.sizes) preload.imageSizes = hero.sizes;
  }, [presentation.heroVisual]);

  const changeView = useCallback(
    (
      nextView: CardView,
      options?: { replace?: boolean; question?: string; sectionId?: string },
    ) => {
      if (options?.question?.trim()) {
        pendingQuestionId.current += 1;
        setPendingQuestion({ id: pendingQuestionId.current, text: options.question.trim() });
      }
      const url = new URL(window.location.href);
      if (nextView === "personal") url.searchParams.delete("view");
      else url.searchParams.set("view", nextView);
      if (nextView === "enterprise" && options?.sectionId) {
        url.searchParams.set("section", options.sectionId);
        sectionRequestId.current += 1;
        setFocusedSection({
          id: options.sectionId,
          requestId: sectionRequestId.current,
        });
      } else {
        url.searchParams.delete("section");
        setFocusedSection(undefined);
      }
      const nextUrl = `${url.pathname}${url.search}${url.hash}`;
      const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      if (options?.replace) window.history.replaceState({ cardView: nextView }, "", nextUrl);
      else if (nextUrl !== currentUrl) window.history.pushState({ cardView: nextView }, "", nextUrl);
      setView(nextView);
      if (!options?.sectionId) {
        if (!reducedMotion) window.scrollTo({ top: 0, behavior: "smooth" });
        else window.scrollTo(0, 0);
      }
    },
    [reducedMotion],
  );

  const openAssistant = useCallback(
    (question?: string) => changeView("assistant", { question }),
    [changeView],
  );

  const openEnterpriseSection = useCallback(
    (sectionId: string) => changeView("enterprise", { sectionId }),
    [changeView],
  );

  useImperativeHandle(ref, () => ({ openAssistant }), [openAssistant]);

  const darkTheme = tenant.theme.dark;
  const stageStyle = {
    "--tz-bg": darkTheme.background,
    "--tz-bg-deep": darkTheme.background,
    "--tz-surface": darkTheme.surface,
    "--tz-surface-strong": darkTheme.surfaceRaised,
    "--tz-surface-soft": darkTheme.surfaceMuted,
    "--tz-line": darkTheme.line,
    "--tz-line-strong": darkTheme.lineStrong,
    "--tz-blue": darkTheme.accent,
    "--tz-blue-bright": darkTheme.accentStrong,
    "--tz-blue-soft": darkTheme.accentSoft,
    "--tz-on-action": tenant.theme.onAction,
    "--tz-text": darkTheme.text,
    "--tz-text-soft": darkTheme.textSoft,
    "--tz-text-faint": darkTheme.textFaint,
  } as CSSProperties;

  return (
    <div className="tz-stage" data-tenant={tenant.id} style={stageStyle}>
      <div className="tz-card-shell">
        <div className={`tz-view-layer ${view === "personal" ? "is-active" : ""}`} hidden={view !== "personal"}>
          <PersonalPage
            tenant={tenant}
            card={card}
            presentation={presentation}
            onLead={onLead}
            onShare={onShare}
          />
        </div>
        <div className={`tz-view-layer ${view === "enterprise" ? "is-active" : ""}`} hidden={view !== "enterprise"}>
          <EnterprisePage
            tenant={tenant}
            card={card}
            presentation={presentation}
            onAssistant={openAssistant}
            onLead={onLead}
            onShare={onShare}
            onPrivacy={onPrivacy}
            onProfile={onProfile}
            focusedSection={focusedSection}
          />
        </div>
        <div className={`tz-view-layer ${view === "assistant" ? "is-active" : ""}`} hidden={view !== "assistant"}>
          <AssistantPage
            config={tenant.assistant}
            cardSlug={card?.slug ?? tenant.id}
            assistantVisual={presentation.assistantVisual}
            recommendations={presentation.assistantRecommendations}
            questionIds={presentation.assistantQuestionIds}
            welcomeMessage={card?.ai_assistant.welcome_message}
            displayName={card?.ai_assistant.display_name}
            disclosure={card?.ai_assistant.disclosure}
            suggestedQuestions={card?.ai_assistant.suggested_questions}
            liveAvailable={assistantEnabled}
            pendingQuestion={pendingQuestion}
            isActive={view === "assistant"}
            onLead={onLead}
            relatedSections={relatedSections}
            onOpenEnterpriseSection={openEnterpriseSection}
          />
        </div>
      </div>
      <BottomNavigation view={view} onChange={changeView} />
    </div>
  );
});

import {
  ArrowLeftIcon,
  BookmarkSimpleIcon,
  BuildingsIcon,
  CaretRightIcon,
  ChatCircleDotsIcon,
  HandshakeIcon,
  IdentificationCardIcon,
  PaperPlaneTiltIcon,
  SealCheckIcon,
  ShareNetworkIcon,
  SparkleIcon,
  SquaresFourIcon,
  UserCircleIcon,
} from "@phosphor-icons/react";
import type { CardPageIdentity } from "@cf/card-page-renderer";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { EnterpriseCardConfig } from "../domain/card";
import { AssistantApiError } from "../lib/assistantApi";
import type { AssistantRelatedSection } from "../lib/assistantRelatedSections";
import type { AnalyticsPage } from "../lib/visitAnalytics";
import { copyText } from "../lib/clipboard";
import type { PublicCardData, PublicEnterpriseTemplateBlock } from "../lib/publicCardApi";
import { EnterpriseTemplateBlocks } from "../components/EnterpriseTemplateBlocks";
import { resolvePublicResourceUrl } from "../lib/publicResourceUrl";
import {
  fetchPublicCaseStudy,
  fetchPublicCatalog,
  fetchPublicProduct,
  fetchPublicRecommendations,
  isPublicExperienceConfigured,
  safeContactHref,
  type PublicCaseStudy,
  type PublicCatalog,
  type PublicProduct,
  type PublicRecommendation,
} from "../lib/publicExperienceApi";

import "./prototype.css";
import "./prototype-overrides.css";
import "./integration.css";

type View = "card" | "company" | "square" | "me" | "detail";
type BaseView = Exclude<View, "detail">;
type SquareFilter = "全部" | "产品" | "案例";
type DetailTarget =
  | { kind: "product"; item: PublicProduct; from: BaseView }
  | { kind: "case"; item: PublicCaseStudy; from: BaseView };
type DetailInput =
  | { kind: "product"; item: PublicProduct }
  | { kind: "case"; item: PublicCaseStudy };
type DetailHistoryTarget = {
  kind: DetailInput["kind"];
  slug: string;
  from: BaseView;
};
type DetailRoute = Pick<DetailHistoryTarget, "kind" | "slug">;
type PrototypeHistoryState =
  | { bpView: BaseView; from?: BaseView }
  | { bpView: "detail"; detail: DetailHistoryTarget };

type CardSwitchTarget = {
  href: string;
  kind: "employee" | "enterprise";
  label: string;
  ariaLabel: string;
};

type CompanySectionId = "overview" | "intro" | "business" | "cases" | "trust" | "faq" | "ai";
const companySectionAnalyticsLabels: Record<CompanySectionId, string> = {
  overview: "企业概览",
  intro: "企业介绍",
  business: "业务与产品",
  cases: "案例",
  trust: "信任信息",
  faq: "常见问题",
  ai: "AI 接待入口",
};

export type BusinessCardPrototypeAppHandle = {
  openAssistantTarget: (targetId: string) => void;
};

type BusinessCardPrototypeAppProps = {
  tenant: EnterpriseCardConfig;
  card?: PublicCardData;
  onAssistant: (question?: string) => void;
  onAssistantRelatedSectionsChange?: (sections: AssistantRelatedSection[]) => void;
  onAnalyticsPageChange?: (page: AnalyticsPage) => void;
  onLead: () => void;
  onPrivacy: () => void;
  onProfile: () => void;
  onShare: () => void;
};

const companySectionDefinitions: ReadonlyArray<{ id: CompanySectionId; label: string }> = [
  { id: "overview", label: "概览" },
  { id: "intro", label: "介绍" },
  { id: "business", label: "业务" },
  { id: "cases", label: "案例" },
  { id: "trust", label: "资料" },
  { id: "faq", label: "问答" },
  { id: "ai", label: "AI" },
];

type CatalogState =
  | { status: "idle" | "loading" }
  | { status: "ready"; data: PublicCatalog }
  | { status: "error"; message: string };
type DetailLookupState =
  | { status: "idle" }
  | { status: "loading"; key: string }
  | { status: "missing"; key: string }
  | { status: "error"; key: string; message: string };

const publicViews: BaseView[] = ["card", "company", "square", "me"];

function isBaseView(value: unknown): value is BaseView {
  return typeof value === "string" && publicViews.includes(value as BaseView);
}

function initialBaseView(): BaseView {
  const candidate = new URLSearchParams(window.location.search).get("view");
  return isBaseView(candidate) ? candidate : "card";
}

function scrollPageToTop() {
  const frame = document.querySelector<HTMLElement>(".bp-phone-frame");
  if (typeof frame?.scrollTo === "function") {
    frame.scrollTo({ top: 0, behavior: "auto" });
  }
  document.documentElement.scrollTop = 0;
  document.body.scrollTop = 0;
}

function initials(value: string) {
  const normalized = value.trim();
  if (!normalized) return "名";
  return Array.from(normalized).slice(-2).join("");
}

function recordLabel(record: Record<string, string>) {
  return (
    record.name ||
    record.title ||
    record.label ||
    record.summary ||
    record.value ||
    ""
  ).trim();
}

function createStandaloneDefaultBlocks({
  kind,
  positioning,
  intro,
  assistantTitle,
  assistantBody,
}: {
  kind: "employee" | "enterprise";
  positioning: string;
  intro: string;
  assistantTitle: string;
  assistantBody: string;
}): PublicEnterpriseTemplateBlock[] {
  return [
    {
      id: `default-${kind}-identity`,
      type: "identity",
      title: "基础名片",
      visible: true,
      directory_enabled: false,
      sort_order: 0,
    },
    {
      id: `default-${kind}-overview`,
      type: "rich_text",
      title: "概览",
      body: positioning,
      visible: true,
      directory_enabled: true,
      sort_order: 10,
    },
    {
      id: `default-${kind}-intro`,
      type: "rich_text",
      title: kind === "employee" ? "个人介绍" : "企业介绍",
      body: intro,
      visible: true,
      directory_enabled: true,
      sort_order: 20,
    },
    {
      id: `default-${kind}-business`,
      type: "business_collection",
      title: "核心业务",
      visible: true,
      directory_enabled: true,
      sort_order: 30,
    },
    {
      id: `default-${kind}-cases`,
      type: "case_collection",
      title: "代表案例",
      visible: true,
      directory_enabled: true,
      sort_order: 40,
    },
    {
      id: `default-${kind}-trust`,
      type: "trust_panel",
      title: "企业资料",
      visible: true,
      directory_enabled: true,
      sort_order: 50,
    },
    {
      id: `default-${kind}-faq`,
      type: "faq",
      title: "常见问题",
      visible: true,
      directory_enabled: true,
      sort_order: 60,
      faq_mode: "all_published",
    },
    {
      id: `default-${kind}-ai`,
      type: "ai_assistant",
      title: assistantTitle,
      body: assistantBody,
      visible: true,
      directory_enabled: true,
      sort_order: 70,
    },
  ];
}

function completeStandaloneTemplateBlocks(
  publishedBlocks: PublicEnterpriseTemplateBlock[],
  defaultBlocks: PublicEnterpriseTemplateBlock[],
) {
  if (publishedBlocks.some((block) => block.type === "identity")) {
    return publishedBlocks;
  }
  if (!publishedBlocks.length) return defaultBlocks;

  const identity = defaultBlocks.find((block) => block.type === "identity");
  const publishedTypes = new Set(publishedBlocks.map((block) => block.type));
  const publishedTitles = new Set(
    publishedBlocks.map((block) => block.title?.trim()).filter(Boolean),
  );
  const firstOrder = publishedBlocks[0]?.sort_order ?? 0;
  const lastOrder = publishedBlocks.reduce(
    (maximum, block) => Math.max(maximum, block.sort_order ?? 0),
    firstOrder,
  );
  const appendedDefaults = defaultBlocks.filter((block) => {
    if (block.type === "identity") return false;
    if (block.type === "rich_text") return !publishedTitles.has(block.title?.trim());
    return !publishedTypes.has(block.type);
  }).map((block, index) => ({
    ...block,
    sort_order: lastOrder + (index + 1) * 10,
  }));

  return [
    ...(identity ? [{ ...identity, sort_order: firstOrder - 10 }] : []),
    ...publishedBlocks,
    ...appendedDefaults,
  ];
}

function detailRouteFromLocation() {
  const raw = new URLSearchParams(window.location.search).get("detail");
  const [kind, ...slugParts] = raw?.split(":") ?? [];
  const slug = slugParts.join(":").trim();
  if ((kind === "product" || kind === "case") && slug) {
    return { kind, slug } as const;
  }
  return undefined;
}

function publicCardHref(slug: string, fromEmployeeSlug?: string) {
  const url = new URL(window.location.href);
  const encodedSlug = encodeURIComponent(slug);
  url.pathname = /(?:^|\/)c\/[^/]+/i.test(url.pathname)
    ? url.pathname.replace(/((?:^|\/)c\/)[^/]+/i, `$1${encodedSlug}`)
    : `/c/${encodedSlug}`;
  const isMock = url.searchParams.has("mock-card");
  url.search = "";
  if (isMock) url.searchParams.set("mock-card", "enterprise");
  if (fromEmployeeSlug) url.searchParams.set("from_employee", fromEmployeeSlug);
  return `${url.pathname}${url.search}`;
}

function employeeCardHref(slug: string) {
  const url = new URL(window.location.href);
  const encodedSlug = encodeURIComponent(slug);
  url.pathname = /(?:^|\/)c\/[^/]+/i.test(url.pathname)
    ? url.pathname.replace(/((?:^|\/)c\/)[^/]+/i, `$1${encodedSlug}`)
    : `/c/${encodedSlug}`;
  const isMock = url.searchParams.has("mock-card");
  url.search = "";
  if (isMock) url.searchParams.set("mock-card", "employee");
  return `${url.pathname}${url.search}`;
}

function recommendationSlug(item: PublicRecommendation) {
  try {
    const segments = new URL(item.url, window.location.origin).pathname
      .split("/")
      .filter(Boolean);
    return decodeURIComponent(segments.at(-1) ?? "");
  } catch {
    return "";
  }
}

function Arrow() {
  return <CaretRightIcon aria-hidden="true" size={17} weight="bold" />;
}

function Avatar({ label, src, small = false }: { label: string; src?: string; small?: boolean }) {
  if (src) {
    return (
      <img
        className={`bp-avatar${small ? " bp-avatar-small" : ""}`}
        src={src}
        alt={`${label}的职业头像`}
      />
    );
  }
  return (
    <span
      className={`bp-avatar bp-avatar-fallback${small ? " bp-avatar-small" : ""}`}
      aria-label={`${label}的姓名缩写`}
    >
      {initials(label)}
    </span>
  );
}

function AppHeader({
  back,
  switchTarget,
  title,
  onShare,
}: {
  back?: () => void;
  switchTarget?: CardSwitchTarget;
  title?: string;
  onShare?: () => void;
}) {
  return (
    <header className={`bp-topbar${title ? "" : " bp-card-topbar"}${switchTarget ? " bp-switch-topbar" : ""}`}>
      {switchTarget ? (
        <a className="bp-card-switch" href={switchTarget.href} aria-label={switchTarget.ariaLabel}>
          {switchTarget.kind === "enterprise" ? (
            <BuildingsIcon size={16} weight="fill" />
          ) : (
            <IdentificationCardIcon size={16} weight="fill" />
          )}
          <span>{switchTarget.label}</span>
        </a>
      ) : back ? (
        <button type="button" onClick={back} aria-label="返回">
          <ArrowLeftIcon size={26} />
        </button>
      ) : (
        <span className="bp-topbar-spacer" aria-hidden="true" />
      )}
      <strong>{title ?? ""}</strong>
      {onShare ? (
        <button type="button" onClick={onShare} aria-label="分享名片">
          <ShareNetworkIcon size={24} />
          {!title && !switchTarget && <small>分享</small>}
        </button>
      ) : (
        <span className="bp-topbar-spacer" aria-hidden="true" />
      )}
    </header>
  );
}

function Section({
  title,
  children,
  action,
  sectionId,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  sectionId?: CompanySectionId;
}) {
  return (
    <section
      className={`bp-section${sectionId ? " bp-company-scroll-section" : ""}`}
      id={sectionId ? `bp-company-section-${sectionId}` : undefined}
      data-company-section={sectionId}
    >
      <div className="bp-section-title">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

type ProductShowcaseItem = {
  key: string;
  category: string;
  title: string;
  description: string;
  meta?: string;
  disabled?: boolean;
  onOpen: () => void;
};

function ProductShowcase({ items }: { items: ProductShowcaseItem[] }) {
  return (
    <div className="bp-product-showcase">
      {items.map((item, index) => (
        <button
          className="bp-product-showcase-item"
          type="button"
          key={item.key}
          disabled={item.disabled}
          onClick={item.onOpen}
        >
          <span className="bp-showcase-number" aria-hidden="true">
            {String(index + 1).padStart(2, "0")}
          </span>
          <small>{item.category}</small>
          <strong>{item.title}</strong>
          <p>{item.description}</p>
          {item.meta && <em>{item.meta}</em>}
          <span className="bp-showcase-link">查看详情 <Arrow /></span>
        </button>
      ))}
    </div>
  );
}

function CaseShowcase({
  items,
  onOpen,
}: {
  items: PublicCaseStudy[];
  onOpen: (item: PublicCaseStudy) => void;
}) {
  return (
    <div className="bp-case-showcase">
      {items.map((item, index) => (
        <button
          className={`bp-case-showcase-item${index === 0 ? " featured" : ""}`}
          type="button"
          key={item.slug}
          onClick={() => onOpen(item)}
        >
          <span className="bp-case-showcase-meta">
            <b>CASE {String(index + 1).padStart(2, "0")}</b>
            <small>{item.industry || "公开案例"}</small>
          </span>
          <strong>{item.title}</strong>
          {index === 0 && (
            <span className="bp-case-showcase-brief">
              <span><small>项目背景</small><p>{item.background}</p></span>
              <span><small>解决方案</small><p>{item.solution}</p></span>
            </span>
          )}
          <span className="bp-case-showcase-result">
            <small>项目结果</small>
            <p>{item.result}</p>
          </span>
          <span className="bp-showcase-link">查看完整案例 <Arrow /></span>
        </button>
      ))}
    </div>
  );
}

function FaqShowcase({
  items,
  openFaq,
  onToggle,
  onAssistant,
  assistantAvailable,
}: {
  items: PublicCardData["faq_items"];
  openFaq: string | null;
  onToggle: (id: string) => void;
  onAssistant: (question: string) => void;
  assistantAvailable: boolean;
}) {
  return (
    <div className="bp-faq-showcase">
      {items.map((faq, index) => {
        const isOpen = openFaq === faq.id;
        return (
          <article className={isOpen ? "open" : ""} key={faq.id}>
            <button
              type="button"
              aria-expanded={isOpen}
              onClick={() => onToggle(faq.id)}
            >
              <span className="bp-faq-number" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <strong>{faq.question}</strong>
              <span className="bp-faq-toggle" aria-hidden="true">{isOpen ? "−" : "+"}</span>
            </button>
            {isOpen && (
              <div className="bp-faq-answer">
                <p>{faq.answer}</p>
                <footer>
                  <small>资料来源：{faq.source_label}</small>
                  {assistantAvailable && (
                    <button type="button" onClick={() => onAssistant(faq.question)}>
                      继续问 AI <Arrow />
                    </button>
                  )}
                </footer>
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}

function NavIcon({ view, active }: { view: View; active: boolean }) {
  const props = { size: 22, weight: active ? "fill" : "regular" } as const;
  if (view === "card") return <IdentificationCardIcon {...props} />;
  if (view === "square") return <SquaresFourIcon {...props} />;
  if (view === "company") return <BuildingsIcon {...props} />;
  return <UserCircleIcon {...props} />;
}

function LoadingRows({ label }: { label: string }) {
  return (
    <div className="bp-resource-state" role="status">
      <span />
      <span />
      <p>正在加载{label}</p>
    </div>
  );
}

export const BusinessCardPrototypeApp = forwardRef<
  BusinessCardPrototypeAppHandle,
  BusinessCardPrototypeAppProps
>(function BusinessCardPrototypeApp({
  tenant,
  card,
  onAssistant,
  onAssistantRelatedSectionsChange,
  onAnalyticsPageChange,
  onLead,
  onPrivacy,
  onProfile,
  onShare,
}: BusinessCardPrototypeAppProps, ref) {
  const standaloneKind = card?.card_kind;
  const isStandaloneCard = standaloneKind === "employee" || standaloneKind === "enterprise";
  const standaloneRoot: BaseView = standaloneKind === "enterprise" ? "company" : "card";
  const defaultBaseView: BaseView = isStandaloneCard ? standaloneRoot : "card";
  const initialCardView = () => {
    if (detailRouteFromLocation()) return "detail" as const;
    if (!isStandaloneCard) return initialBaseView();
    return new URLSearchParams(window.location.search).get("view") === "square"
      ? "square"
      : standaloneRoot;
  };
  const [view, setView] = useState<View>(initialCardView);
  const [detail, setDetail] = useState<DetailTarget | null>(null);
  const [detailLookup, setDetailLookup] = useState<DetailLookupState>({ status: "idle" });
  const [locationRevision, setLocationRevision] = useState(0);
  const [catalog, setCatalog] = useState<CatalogState>({ status: "idle" });
  const [recommendations, setRecommendations] = useState<PublicRecommendation[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<SquareFilter>("全部");
  const [copyFeedback, setCopyFeedback] = useState<{
    key: string;
    status: "copied" | "failed";
  } | null>(null);
  const [openFaq, setOpenFaq] = useState<string | null>(card?.faq_items[0]?.id ?? null);
  const storageKey = `cf-card-saved:${card?.slug ?? tenant.id}`;
  const [saved, setSaved] = useState(() => {
    try {
      return window.localStorage.getItem(storageKey) === "1";
    } catch {
      return false;
    }
  });
  const [activeCompanySection, setActiveCompanySection] = useState<CompanySectionId>("overview");
  const companySectionNavRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setOpenFaq(card?.faq_items[0]?.id ?? null);
  }, [card?.faq_items]);

  useEffect(() => {
    const handlePopState = (event: PopStateEvent) => {
      const state = event.state as PrototypeHistoryState | null;
      if (state?.bpView === "detail" && state.detail) {
        setDetail(null);
        setView("detail");
      } else {
        setDetail(null);
        setView(
          isBaseView(state?.bpView)
            ? state.bpView
            : initialCardView(),
        );
      }
      setLocationRevision((current) => current + 1);
      scrollPageToTop();
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [isStandaloneCard, standaloneRoot]);

  useEffect(() => {
    if (!card || !isPublicExperienceConfigured()) {
      setCatalog({ status: "idle" });
      setRecommendations([]);
      return undefined;
    }
    const controller = new AbortController();
    setCatalog({ status: "loading" });
    void fetchPublicCatalog(card.slug, controller.signal)
      .then((data) => setCatalog({ status: "ready", data }))
      .catch(() => {
        if (!controller.signal.aborted) {
          setCatalog({ status: "error", message: "业务资料暂时无法加载，请稍后重试。" });
        }
      });
    void fetchPublicRecommendations(card.slug, controller.signal)
      .then(setRecommendations)
      .catch(() => {
        if (!controller.signal.aborted) setRecommendations([]);
      });
    return () => controller.abort();
  }, [card]);

  const tenantBusinesses = useMemo(
    () => tenant.sections.find((section) => section.type === "feature-grid")?.businesses ?? [],
    [tenant.sections],
  );
  const products = catalog.status === "ready" ? catalog.data.products : [];
  const cases = catalog.status === "ready" ? catalog.data.cases : [];
  const requestedDetail = detailRouteFromLocation();

  useEffect(() => {
    const route = detailRouteFromLocation();
    if (!route) {
      setDetailLookup({ status: "idle" });
      if (view === "detail") {
        setDetail(null);
        setView(defaultBaseView);
      }
      return;
    }
    setView("detail");
    if (catalog.status !== "ready") {
      setDetail(null);
      setDetailLookup({ status: "idle" });
      return;
    }
    const item = route.kind === "product"
      ? catalog.data.products.find((candidate) => candidate.slug === route.slug)
      : catalog.data.cases.find((candidate) => candidate.slug === route.slug);
    const historyState = window.history.state as PrototypeHistoryState | null;
    const from = historyState?.bpView === "detail" &&
      historyState.detail.kind === route.kind &&
      historyState.detail.slug === route.slug
      ? historyState.detail.from
      : defaultBaseView;
    if (item) {
      setDetailLookup({ status: "idle" });
      setDetail(
        route.kind === "product"
          ? { kind: "product", item: item as PublicProduct, from }
          : { kind: "case", item: item as PublicCaseStudy, from },
      );
      scrollPageToTop();
      return;
    }
    if (!card?.slug) {
      setDetail(null);
      setDetailLookup({ status: "missing", key: `${route.kind}:${route.slug}` });
      return;
    }

    const controller = new AbortController();
    const key = `${route.kind}:${route.slug}`;
    setDetail(null);
    setDetailLookup({ status: "loading", key });
    const request = route.kind === "product"
      ? fetchPublicProduct(card.slug, route.slug, controller.signal)
      : fetchPublicCaseStudy(card.slug, route.slug, controller.signal);
    void request
      .then((resolved) => {
        setDetailLookup({ status: "idle" });
        setDetail(
          route.kind === "product"
            ? { kind: "product", item: resolved as PublicProduct, from }
            : { kind: "case", item: resolved as PublicCaseStudy, from },
        );
        scrollPageToTop();
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof AssistantApiError && error.status === 404) {
          setDetailLookup({ status: "missing", key });
          return;
        }
        setDetailLookup({
          status: "error",
          key,
          message: "详情暂时无法加载，请稍后重试。",
        });
      });
    return () => controller.abort();
  }, [card?.slug, catalog, defaultBaseView, locationRevision, view]);
  const isBlankTemplate = Boolean(tenant.isBlankTemplate && !card);
  const isPublished = Boolean(card);
  const companyName = card?.company.name ?? tenant.brand.name;
  const companySummary = card?.company.summary || tenant.hero.summary;
  const displayName = card?.display_name ?? tenant.brand.shortName;
  const title = card?.title ?? tenant.brand.headerDescriptor;
  const avatar = isBlankTemplate ? undefined : resolvePublicResourceUrl(card?.avatar_url);
  const companyLogo = isBlankTemplate
    ? undefined
    : resolvePublicResourceUrl(card?.company.logo_url) || tenant.brand.logo.src;
  const assistantName = card?.ai_assistant.display_name ?? tenant.assistant.title;
  const assistantAvailable =
    !isBlankTemplate && (card?.ai_assistant.available ?? true);
  const tenantQuestions = tenant.assistant.quickQuestionIds.flatMap((id) => {
    const item = tenant.assistant.knowledgeBase.find((candidate) => candidate.id === id);
    return item ? [item.shortQuestion || item.question] : [];
  });
  const suggestedQuestions: string[] = (
    card?.ai_assistant.suggested_questions.length
      ? card.ai_assistant.suggested_questions
      : tenantQuestions
  ).slice(0, 3);
  const featuredLabels = (card?.featured_products ?? []).map(recordLabel).filter(Boolean);
  const tags = [...featuredLabels, ...tenantBusinesses.map((item) => item.title)]
    .filter((value, index, all) => all.indexOf(value) === index)
    .slice(0, 3);
  const introParagraphs = [companySummary, ...tenantBusinesses.map((item) => item.description)]
    .filter(Boolean)
    .slice(0, 4);
  const representativeCase = cases[0];
  const representativeProduct = products[0];
  const contactFields = card?.contact_fields.filter((item) => item.label && item.value) ?? [];
  const websiteHref = isBlankTemplate
    ? undefined
    : card?.company.website
      ? safeContactHref({ href: card.company.website })
      : safeContactHref({ href: tenant.brand.officialAction.target });
  const websiteLabel = card?.company.website
    ? `${companyName}官网`
    : tenant.brand.officialAction.label;
  const adminHref =
    import.meta.env.VITE_ADMIN_BASE_URL?.trim() || `${import.meta.env.BASE_URL}admin/`;
  const onboardingHref = `${adminHref.replace(/\/*$/, "/")}platform/onboarding`;
  const officialCompanyHref = card?.company.official_card_slug
    ? publicCardHref(
      card.company.official_card_slug,
      standaloneKind === "employee" ? card.slug : undefined,
    )
    : undefined;
  const employeeReturnSlug = standaloneKind === "enterprise"
    ? new URLSearchParams(window.location.search).get("from_employee")
    : undefined;
  const employeeReturnHref = employeeReturnSlug
    ? employeeCardHref(employeeReturnSlug)
    : undefined;

  const go = (next: BaseView) => {
    if (next === view && detail === null) return;
    const from = view === "detail" ? detail?.from ?? defaultBaseView : view;
    setDetail(null);
    setView(next);
    const url = new URL(window.location.href);
    url.searchParams.delete("detail");
    if (next === defaultBaseView) url.searchParams.delete("view");
    else url.searchParams.set("view", next);
    window.history.pushState({ bpView: next, from }, "", url);
    scrollPageToTop();
  };

  const replaceWithView = (next: BaseView) => {
    setDetail(null);
    setView(next);
    const url = new URL(window.location.href);
    url.searchParams.delete("detail");
    if (next === defaultBaseView) url.searchParams.delete("view");
    else url.searchParams.set("view", next);
    window.history.replaceState({ bpView: next }, "", url);
    scrollPageToTop();
  };

  const replaceWithCard = () => replaceWithView("card");

  const returnFromCompany = () => {
    const state = window.history.state as PrototypeHistoryState | null;
    if (state?.bpView === "company" && state.from) {
      window.history.back();
      return;
    }
    replaceWithCard();
  };

  const openDetail = (target: DetailInput) => {
    const from: BaseView = view === "detail"
      ? detail?.from ?? defaultBaseView
      : view;
    const nextDetail: DetailTarget = target.kind === "product"
      ? { kind: "product", item: target.item, from }
      : { kind: "case", item: target.item, from };
    setDetail(nextDetail);
    setDetailLookup({ status: "idle" });
    const url = new URL(window.location.href);
    url.searchParams.set("detail", `${target.kind}:${target.item.slug}`);
    window.history.pushState(
      {
        bpView: "detail",
        detail: { kind: target.kind, slug: target.item.slug, from },
      } satisfies PrototypeHistoryState,
      "",
      url,
    );
    setView("detail");
    scrollPageToTop();
  };

  const openDetailRoute = (route: DetailRoute) => {
    const from: BaseView = view === "detail"
      ? detail?.from ?? defaultBaseView
      : view;
    setDetail(null);
    setDetailLookup({ status: "idle" });
    const url = new URL(window.location.href);
    url.searchParams.set("detail", `${route.kind}:${route.slug}`);
    window.history.pushState(
      { bpView: "detail", detail: { ...route, from } } satisfies PrototypeHistoryState,
      "",
      url,
    );
    setView("detail");
    setLocationRevision((current) => current + 1);
    scrollPageToTop();
  };

  const returnFromDetail = () => {
    const state = window.history.state as PrototypeHistoryState | null;
    if (state?.bpView === "detail") {
      window.history.back();
      return;
    }
    replaceWithView(detail?.from ?? defaultBaseView);
  };

  const copyContact = async (key: string, value: string) => {
    try {
      await copyText(value);
      setCopyFeedback({ key, status: "copied" });
    } catch {
      setCopyFeedback({ key, status: "failed" });
    }
  };

  const toggleSaved = () => {
    const next = !saved;
    setSaved(next);
    try {
      if (next) window.localStorage.setItem(storageKey, "1");
      else window.localStorage.removeItem(storageKey);
    } catch {
      // The visual state remains useful when storage is unavailable.
    }
  };

  const normalizedQuery = query.trim().toLocaleLowerCase("zh-CN");
  const visibleProducts = products.filter((item) => {
    if (filter === "案例") return false;
    return !normalizedQuery || `${item.name}${item.category ?? ""}${item.summary}`.toLocaleLowerCase("zh-CN").includes(normalizedQuery);
  });
  const visibleCases = cases.filter((item) => {
    if (filter === "产品") return false;
    return !normalizedQuery || `${item.title}${item.industry ?? ""}${item.background}${item.result}`.toLocaleLowerCase("zh-CN").includes(normalizedQuery);
  });

  const recommendationTarget = (item: PublicRecommendation): DetailInput | undefined => {
    const slug = recommendationSlug(item);
    if (item.resourceType === "product") {
      const product = products.find((candidate) => candidate.slug === slug)
        ?? products.find((candidate) => candidate.name === item.title);
      return product ? { kind: "product", item: product } : undefined;
    }
    if (item.resourceType === "case_study") {
      const caseStudy = cases.find((candidate) => candidate.slug === slug)
        ?? cases.find((candidate) => candidate.title === item.title);
      return caseStudy ? { kind: "case", item: caseStudy } : undefined;
    }
    return undefined;
  };

  const recommendationRoute = (item: PublicRecommendation): DetailRoute | undefined => {
    const slug = recommendationSlug(item);
    if (!slug) return undefined;
    if (item.resourceType === "product") return { kind: "product", slug };
    if (item.resourceType === "case_study") return { kind: "case", slug };
    return undefined;
  };

  const companyProductItems: ProductShowcaseItem[] = (
    products.length
      ? products.slice(0, 4).map((item) => ({
          key: item.slug,
          category: item.category || "产品与服务",
          title: item.name,
          description: item.summary,
          meta: item.audience ? `适用对象：${item.audience}` : undefined,
          onOpen: () => openDetail({ kind: "product", item }),
        }))
      : tenantBusinesses.slice(0, 4).map((item) => ({
          key: item.title,
          category: item.eyebrow || "业务方向",
          title: item.title,
          description: item.description,
          meta: item.points[0] || item.status || undefined,
          disabled: !assistantAvailable,
          onOpen: () => onAssistant(`请介绍${item.title}`),
        }))
  );

  const assistantRelatedSections = useMemo<AssistantRelatedSection[]>(() => {
    if (catalog.status === "ready") {
      return [
        ...catalog.data.products.map((item) => ({
          id: `product:${item.slug}`,
          targetId: `detail:product:${item.slug}`,
          title: item.name,
          description: item.summary,
          keywords: [
            item.name,
            item.category,
            item.summary,
            item.detail,
            item.audience,
          ].filter((value): value is string => Boolean(value?.trim())),
        })),
        ...catalog.data.cases.map((item) => ({
          id: `case:${item.slug}`,
          targetId: `detail:case:${item.slug}`,
          title: item.title,
          description: item.result,
          keywords: [
            item.title,
            item.industry,
            item.background,
            item.solution,
            item.result,
            "代表案例",
            "成功案例",
          ].filter((value): value is string => Boolean(value?.trim())),
        })),
      ];
    }

    return tenantBusinesses.map((item, index) => ({
      id: `business:${index}`,
      targetId: "company:business",
      title: item.title,
      description: item.description,
      keywords: [item.title, item.description, ...item.points]
        .filter((value): value is string => Boolean(value?.trim())),
    }));
  }, [catalog, tenantBusinesses]);

  useEffect(() => {
    onAssistantRelatedSectionsChange?.(assistantRelatedSections);
  }, [assistantRelatedSections, onAssistantRelatedSectionsChange]);

  const isStandaloneEnterprise = isStandaloneCard && standaloneKind === "enterprise";
  const isStandaloneEmployee = isStandaloneCard && standaloneKind === "employee";
  const companyNavigationItems = companySectionDefinitions;
  const publishedTemplateBlocks = (card?.enterprise_template?.blocks ?? [])
    .slice()
    .sort((left, right) => (left.sort_order ?? 0) - (right.sort_order ?? 0));
  const visibleTemplateBlocks = publishedTemplateBlocks.filter(
    (block) => block.type === "identity" || block.visible !== false,
  );
  const standaloneTemplateKind = isStandaloneEmployee ? "employee" : "enterprise";
  const standaloneDefaultBlocks = createStandaloneDefaultBlocks({
    kind: standaloneTemplateKind,
    positioning: isStandaloneEmployee
      ? card?.business_summary || companySummary
      : tenant.hero.summary,
    intro: isStandaloneEmployee
      ? card?.business_summary || companySummary
      : companySummary,
    assistantTitle: isStandaloneEmployee ? `${displayName}的 AI 助手` : assistantName,
    assistantBody: card?.ai_assistant.welcome_message
      || "基于已发布资料介绍业务，并协助整理合作需求。",
  });
  const effectiveTemplateBlocks = isStandaloneCard
    ? completeStandaloneTemplateBlocks(publishedTemplateBlocks, standaloneDefaultBlocks)
    : publishedTemplateBlocks;
  const hasComposableStandalonePage = isStandaloneCard;
  const hasComposableEnterprisePage = isStandaloneEnterprise;
  const hasComposableEmployeePage = isStandaloneEmployee;
  const templateIntroBlock = visibleTemplateBlocks.find(
    (block) => block.type === "rich_text" && block.title?.trim() === "企业介绍",
  );
  const templateAiBlock = visibleTemplateBlocks.find((block) => block.type === "ai_assistant");
  const templateFeatureBlocks = visibleTemplateBlocks.filter(
    (block) => block !== templateIntroBlock && ["rich_text", "image_gallery", "video_link"].includes(block.type),
  );
  const templateCaseBlocks = visibleTemplateBlocks.filter((block) => block.type === "case_collection");
  const templateFaqBlocks = visibleTemplateBlocks.filter((block) => block.type === "faq");
  const templateCtaBlocks = visibleTemplateBlocks.filter((block) => block.type === "cta");
  const companyNavigationKey = companyNavigationItems.map(({ id }) => id).join(",");

  useEffect(() => {
    if (!onAnalyticsPageChange) return;
    if (view === "detail") {
      const route = detail
        ? { kind: detail.kind, slug: detail.item.slug, title: detail.kind === "product" ? detail.item.name : detail.item.title }
        : requestedDetail
          ? { ...requestedDetail, title: requestedDetail.slug }
          : undefined;
      if (route) {
        onAnalyticsPageChange({
          key: `detail:${route.kind}:${route.slug}`,
          title: route.title,
          objectType: route.kind,
          objectId: route.slug,
        });
        return;
      }
    }
    if (view === "company") {
      onAnalyticsPageChange({
        key: `company:${activeCompanySection}`,
        title: `企业页·${companySectionAnalyticsLabels[activeCompanySection]}`,
        objectType: "card",
        objectId: `company:${activeCompanySection}`,
      });
      return;
    }
    const labels: Record<BaseView, string> = {
      card: "个人名片",
      company: "企业主页",
      square: "业务广场",
      me: "访客中心",
    };
    onAnalyticsPageChange({
      key: view,
      title: labels[view as BaseView] ?? view,
      objectType: "card",
      objectId: view,
    });
  }, [
    activeCompanySection,
    detail,
    onAnalyticsPageChange,
    requestedDetail?.kind,
    requestedDetail?.slug,
    view,
  ]);
  const composedIdentity: CardPageIdentity = isStandaloneEmployee
    ? {
        kind: "employee",
        name: displayName,
        headline: title,
        summary: card?.business_summary || undefined,
        imageUrl: avatar,
        companyName,
        verificationLabel: isPublished ? "已发布" : "本地展示",
        positioning: card?.business_summary || companySummary,
        tags,
      }
    : {
        kind: "enterprise",
        name: companyName,
        headline: card?.company.industry || undefined,
        summary: companySummary,
        imageUrl: companyLogo,
        verificationLabel: isPublished ? "资料已发布" : "本地展示",
        positioning: tenant.hero.summary,
        meta: [card?.company.industry, card?.company.region]
          .filter((value): value is string => Boolean(value)),
        tags,
      };

  useEffect(() => {
    if (!isStandaloneEnterprise || view !== "company") return;

    let frameId = 0;
    const updateActiveSection = () => {
      const sections = companyNavigationItems
        .map(({ id }) => document.getElementById(`bp-company-section-${id}`))
        .filter((section): section is HTMLElement => Boolean(section));
      if (!sections.length || !sections.some((section) => section.getBoundingClientRect().height > 0)) return;

      const threshold = 68 + 52 + 20;
      let next = sections[0].dataset.companySection as CompanySectionId;
      for (const section of sections) {
        if (section.getBoundingClientRect().top <= threshold) {
          next = section.dataset.companySection as CompanySectionId;
        }
      }

      const scrollTop = window.scrollY || document.documentElement.scrollTop;
      const scrollHeight = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
      if (scrollTop + window.innerHeight >= scrollHeight - 8) {
        next = sections.at(-1)?.dataset.companySection as CompanySectionId;
      }
      setActiveCompanySection((current) => current === next ? current : next);
    };
    const scheduleUpdate = () => {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(updateActiveSection);
    };

    setActiveCompanySection("overview");
    scheduleUpdate();
    window.addEventListener("scroll", scheduleUpdate, { passive: true });
    window.addEventListener("resize", scheduleUpdate);
    return () => {
      window.cancelAnimationFrame(frameId);
      window.removeEventListener("scroll", scheduleUpdate);
      window.removeEventListener("resize", scheduleUpdate);
    };
  }, [companyNavigationKey, isStandaloneEnterprise, view]);

  useEffect(() => {
    if (!isStandaloneEnterprise) return;
    const nav = companySectionNavRef.current;
    const activeTab = nav?.querySelector<HTMLElement>(`[data-company-target="${activeCompanySection}"]`);
    if (!nav || !activeTab || typeof nav.scrollTo !== "function") return;
    const left = activeTab.offsetLeft - (nav.clientWidth - activeTab.offsetWidth) / 2;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    nav.scrollTo({ left, behavior: reducedMotion ? "auto" : "smooth" });
  }, [activeCompanySection, isStandaloneEnterprise]);

  const scrollToCompanySection = (sectionId: CompanySectionId) => {
    setActiveCompanySection(sectionId);
    const target = document.getElementById(`bp-company-section-${sectionId}`);
    if (!target || target.getBoundingClientRect().height <= 0) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const top = window.scrollY + target.getBoundingClientRect().top - (68 + 52 + 18);
    window.scrollTo({ top: Math.max(0, top), behavior: reducedMotion ? "auto" : "smooth" });
  };

  useImperativeHandle(ref, () => ({
    openAssistantTarget: (targetId: string) => {
      const [scope, kindOrSection, ...remainder] = targetId.split(":");
      if (scope === "detail" && (kindOrSection === "product" || kindOrSection === "case")) {
        const slug = remainder.join(":").trim();
        if (!slug) return;
        const target = kindOrSection === "product"
          ? products.find((item) => item.slug === slug)
          : cases.find((item) => item.slug === slug);
        if (target) {
          openDetail(
            kindOrSection === "product"
              ? { kind: "product", item: target as PublicProduct }
              : { kind: "case", item: target as PublicCaseStudy },
          );
        } else {
          openDetailRoute({ kind: kindOrSection, slug });
        }
        return;
      }

      if (scope === "company" && companySectionDefinitions.some(({ id }) => id === kindOrSection)) {
        const sectionId = kindOrSection as CompanySectionId;
        go("company");
        window.requestAnimationFrame(() => {
          window.requestAnimationFrame(() => scrollToCompanySection(sectionId));
        });
      }
    },
  }));

  const bottom = (
    <nav className="bp-bottom-nav" aria-label="名片导航">
      {([
        ["名片", "card"],
        ["业务", "square"],
        ["企业", "company"],
        ["我的", "me"],
      ] as Array<[string, BaseView]>).map(([label, target]) => (
        <button
          key={target}
          className={view === target ? "active" : ""}
          type="button"
          onClick={() => go(target)}
        >
          <span><NavIcon view={target} active={view === target} /></span>
          <small>{label}</small>
        </button>
      ))}
    </nav>
  );

  const composedTemplatePage = hasComposableStandalonePage ? (
    <EnterpriseTemplateBlocks
      blocks={effectiveTemplateBlocks}
      pageBackground={card?.enterprise_template?.page_background}
      pageTextTone={card?.enterprise_template?.page_text_tone}
      directory={{
        ariaLabel: isStandaloneEmployee ? "员工名片内容导航" : "企业名片内容导航",
      }}
      identityData={composedIdentity}
      products={products}
      cases={cases}
      faqItems={card?.faq_items ?? []}
      onOpenProduct={(slug) => openDetailRoute({ kind: "product", slug })}
      onOpenCase={(slug) => openDetailRoute({ kind: "case", slug })}
      onAssistant={assistantAvailable ? (question) => onAssistant(question) : undefined}
    />
  ) : null;

  const cardPage = (
    <>
      <AppHeader
        switchTarget={standaloneKind === "employee" && officialCompanyHref ? {
          href: officialCompanyHref,
          kind: "enterprise",
          label: "切换企业",
          ariaLabel: "切换到企业名片",
        } : undefined}
        onShare={onShare}
      />
      <main className="bp-page bp-card-page">
        {hasComposableEmployeePage ? composedTemplatePage : (
          <>
        <div className="bp-person-head">
          {avatar ? (
            <img className="bp-portrait" src={avatar} alt={`${displayName}的职业头像`} />
          ) : (
            <span className="bp-portrait bp-portrait-fallback" aria-label={`${displayName}的姓名缩写`}>
              {initials(displayName)}
            </span>
          )}
          <div>
            <div className="bp-name-line">
              <h1>{displayName}</h1>
              <b className={!isPublished ? "bp-template-badge" : undefined}>
                {isBlankTemplate ? "空白模板" : isPublished ? <><SealCheckIcon size={17} weight="fill" /> 已发布</> : "本地展示"}
              </b>
            </div>
            <p>{title}</p>
            {isStandaloneCard ? (
              officialCompanyHref ? (
                <a className="bp-affiliation" href={officialCompanyHref}>
                  <BuildingsIcon size={18} weight="fill" /> {companyName} <Arrow />
                </a>
              ) : (
                <span className="bp-affiliation bp-affiliation-disabled">
                  <BuildingsIcon size={18} weight="fill" /> {companyName}<small>企业名片暂未发布</small>
                </span>
              )
            ) : (
              <button className="bp-affiliation" type="button" onClick={() => go("company")}>
                <BuildingsIcon size={18} weight="fill" /> {companyName} <Arrow />
              </button>
            )}
            <div className="bp-tags">
              {tags.map((tag) => <span key={tag}>{tag}</span>)}
            </div>
          </div>
        </div>

        <section className="bp-card-intro">
          <div className="bp-card-panel-title"><h2>业务介绍</h2></div>
          <div className="bp-intro">
            {isBlankTemplate ? (
              <div className="bp-template-empty">
                <strong>尚未录入企业资料</strong>
                <p>导入甲方主体、品牌、业务、案例和联系资料后，此处会自动生成可审核的企业介绍。</p>
                <a href={onboardingHref}>进入后台开始配置 <Arrow /></a>
              </div>
            ) : (
              <>
                {introParagraphs.map((paragraph, index) => <p key={`${index}-${paragraph}`}>{paragraph}</p>)}
                <button type="button" className="bp-text-button" onClick={() => go(isStandaloneCard ? "square" : "company")}>
                  {isStandaloneCard ? "查看全部业务" : "查看企业详情"} <Arrow />
                </button>
              </>
            )}
          </div>
        </section>

        {representativeCase ? (
          <button
            type="button"
            className="bp-case bp-card-case"
            onClick={() => openDetail({ kind: "case", item: representativeCase })}
          >
            <div className="bp-case-copy">
              <small>代表案例</small>
              <strong>{representativeCase.title}</strong>
              <span>{representativeCase.result}</span>
            </div>
            <i><span>▰</span></i><em>查看案例 <Arrow /></em>
          </button>
        ) : representativeProduct ? (
          <button
            type="button"
            className="bp-case bp-card-case"
            onClick={() => openDetail({ kind: "product", item: representativeProduct })}
          >
            <div className="bp-case-copy">
              <small>核心业务</small>
              <strong>{representativeProduct.name}</strong>
              <span>{representativeProduct.summary}</span>
            </div>
            <i><span>▰</span></i><em>查看详情 <Arrow /></em>
          </button>
        ) : null}

        <section className="bp-ai-card">
          <div><i>AI</i><span><strong>{assistantName}</strong><small>{assistantAvailable ? isPublished ? "基于已发布资料" : "基于本地展示资料" : "暂未开放"}</small></span></div>
          <p>{isBlankTemplate ? "上传并审核企业知识资料后，AI 才会基于已发布内容回答，不会使用模板猜测企业事实。" : assistantAvailable ? (card?.ai_assistant.disclosure || "回答会引用企业已发布知识，重要事项请与企业进一步确认。") : "企业尚未开放 AI 问答，请先通过合作需求与企业联系。"}</p>
          {assistantAvailable && suggestedQuestions.map((question, index) => (
            <button type="button" key={question} onClick={() => onAssistant(question)}>
              {index === 0 ? <SparkleIcon size={18} weight="fill" /> : <span aria-hidden="true">●</span>}
              {question} <Arrow />
            </button>
          ))}
          {assistantAvailable && !suggestedQuestions.length && (
            <button type="button" onClick={() => onAssistant()}>
              <ChatCircleDotsIcon size={18} /> 开始咨询 <Arrow />
            </button>
          )}
          {isBlankTemplate && <a className="bp-template-link" href={onboardingHref}>配置企业知识库 <Arrow /></a>}
        </section>
          </>
        )}
        {isStandaloneCard && (
          <div className="bp-standalone-utilities">
            <button type="button" onClick={toggleSaved}>{saved ? "取消保存" : "保存名片"}</button>
            <button type="button" onClick={onPrivacy}>隐私与个人信息</button>
          </div>
        )}
      </main>
      {isStandaloneCard ? <div className="bp-sticky-actions bp-standalone-action-bar" aria-label="名片主要操作">
        <button className="primary" type="button" disabled={!assistantAvailable} onClick={() => onAssistant()}>问 AI</button>
        <button type="button" onClick={onLead}>发起合作</button>
      </div> : <div className="bp-sticky-actions bp-card-actions">
        {isBlankTemplate ? <>
          <button type="button" onClick={onShare}><ShareNetworkIcon size={22} /> 分享模板</button>
          <a className="primary" href={onboardingHref}>开始配置企业</a>
        </> : <>
          <button type="button" onClick={toggleSaved} aria-pressed={saved}>
            <BookmarkSimpleIcon size={22} weight={saved ? "fill" : "regular"} />
            {saved ? "本机已保存" : "保存到本机"}
          </button>
          <button className="primary" type="button" onClick={onLead}>
            <HandshakeIcon size={22} /> 发起合作
          </button>
        </>}
      </div>}
      {!isStandaloneCard && bottom}
    </>
  );

  const companyPage = (
    <>
      <AppHeader
        back={isStandaloneCard ? undefined : returnFromCompany}
        switchTarget={isStandaloneCard && employeeReturnHref ? {
          href: employeeReturnHref,
          kind: "employee",
          label: "切换员工",
          ariaLabel: "切换到员工名片",
        } : undefined}
        title={isStandaloneCard ? "企业官方名片" : `来自${displayName}的名片`}
        onShare={onShare}
      />
      <main className="bp-page bp-company-page">
        {!hasComposableEnterprisePage && <div className="bp-company-head">
          {companyLogo ? <img src={companyLogo} alt={`${companyName}标识`} /> : <i>◈</i>}
          <div>
            <div className="bp-name-line"><h1>{companyName}</h1><b>{isBlankTemplate ? "待配置" : isPublished ? "✓ 资料已发布" : "本地展示"}</b></div>
            <p>{companySummary}</p>
            <small className="bp-company-meta">
              {[card?.company.industry, card?.company.region].filter(Boolean).join(" · ") || tenant.brand.headerDescriptor}
            </small>
            <div className="bp-tags">{tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
          </div>
        </div>}

        {isStandaloneEnterprise && !hasComposableEnterprisePage && (
          <nav ref={companySectionNavRef} className="bp-company-section-nav" aria-label="企业名片内容导航">
            {companyNavigationItems.map(({ id, label }) => (
              <button
                key={id}
                className="bp-company-section-tab"
                type="button"
                data-company-target={id}
                aria-controls={`bp-company-section-${id}`}
                aria-current={activeCompanySection === id ? "location" : undefined}
                onClick={() => scrollToCompanySection(id)}
              >
                {label}
              </button>
            ))}
          </nav>
        )}

        {!hasComposableEnterprisePage && <section
          className={`bp-company-position${isStandaloneEnterprise ? " bp-company-scroll-section" : ""}`}
          id={isStandaloneEnterprise ? "bp-company-section-overview" : undefined}
          data-company-section={isStandaloneEnterprise ? "overview" : undefined}
        >
          <small>{isBlankTemplate ? "配置提示" : "我们能帮助你"}</small>
          <strong>{isBlankTemplate ? "录入品牌定位和核心价值后，此处会生成企业对外主张。" : tenant.hero.summary}</strong>
        </section>}

        {hasComposableEnterprisePage && composedTemplatePage}

        {!hasComposableEnterprisePage && (
          <>
        <Section title="企业介绍" sectionId={isStandaloneEnterprise ? "intro" : undefined}>
          {isBlankTemplate ? <div className="bp-empty-state bp-inline-empty"><strong>企业介绍待录入</strong><p>支持从企业简介、官网文本或审核后的文档生成。</p><a href={onboardingHref}>录入企业资料</a></div> : <div className="bp-intro"><p>{companySummary}</p>{templateIntroBlock?.body && templateIntroBlock.body.trim().length >= 24 && templateIntroBlock.body !== companySummary ? <p>{templateIntroBlock.body}</p> : null}</div>}
        </Section>

        {isStandaloneEnterprise && templateFeatureBlocks.length > 0 && (
          <EnterpriseTemplateBlocks
            blocks={templateFeatureBlocks}
            onOpenCase={(slug) => openDetailRoute({ kind: "case", slug })}
          />
        )}

        <Section
          title="核心业务"
          sectionId={isStandaloneEnterprise ? "business" : undefined}
          action={products.length > 4 ? <button className="bp-text-button" type="button" onClick={() => go("square")}>查看全部</button> : undefined}
        >
          {catalog.status === "loading" ? <LoadingRows label="业务资料" /> : (
            companyProductItems.length ? <ProductShowcase items={companyProductItems} /> : <div className="bp-empty-state bp-inline-empty"><strong>产品与服务待录入</strong><p>添加业务名称、适用客户、价值说明和服务边界后即可展示。</p><a href={onboardingHref}>添加业务资料</a></div>
          )}
        </Section>

        <Section
          title="代表案例"
          sectionId={isStandaloneEnterprise ? "cases" : undefined}
          action={cases.length > 3 ? <button className="bp-text-button" type="button" onClick={() => go("square")}>查看全部</button> : undefined}
        >
          {cases.length > 0 ? (
            <CaseShowcase
              items={cases.slice(0, 3)}
              onOpen={(item) => openDetail({ kind: "case", item })}
            />
          ) : (
            <div className="bp-empty-state bp-inline-empty">
              <strong>代表案例待补充</strong>
              <p>案例经企业确认公开范围后会显示在这里。</p>
            </div>
          )}
        </Section>

        {isStandaloneEnterprise && templateCaseBlocks.length > 0 && (
          <EnterpriseTemplateBlocks
            blocks={templateCaseBlocks}
            onOpenCase={(slug) => openDetailRoute({ kind: "case", slug })}
          />
        )}

        <Section title="企业资料" sectionId={isStandaloneEnterprise ? "trust" : undefined}>
          {isBlankTemplate ? <div className="bp-empty-state bp-inline-empty"><strong>可信资料待审核</strong><p>主体信息、资质、案例授权和公开范围须确认后才会显示。</p><a href={onboardingHref}>进入资料审核</a></div> : <div className="bp-trust">
            <span>✓ 企业公开资料</span><span>✓ AI 引用可追溯</span>
            {(card?.company.industry || card?.company.region) && <span>{[card.company.industry, card.company.region].filter(Boolean).join(" · ")}</span>}
            {websiteHref && <a className="bp-trust-link" href={websiteHref} target="_blank" rel="noreferrer">访问企业官网 <Arrow /></a>}
          </div>}
        </Section>

        {!isStandaloneCard && <Section title="可以为你对接的人">
          {isBlankTemplate ? <div className="bp-empty-state bp-inline-empty"><strong>名片持有人待录入</strong><p>添加姓名、职务、头像和经授权的联系渠道。</p><a href={onboardingHref}>配置名片成员</a></div> : <div className="bp-people">
            <button type="button" onClick={() => go("card")}>
              <Avatar small label={displayName} src={avatar} />
              <span><strong>{displayName}　{title}</strong><small>{companyName}</small></span><Arrow />
            </button>
          </div>}
        </Section>}

        <Section title="常见问题" sectionId={isStandaloneEnterprise ? "faq" : undefined}>
          {card?.faq_items.length ? (
            <FaqShowcase
              items={card.faq_items}
              openFaq={openFaq}
              onToggle={(id) => setOpenFaq(openFaq === id ? null : id)}
              onAssistant={onAssistant}
              assistantAvailable={assistantAvailable}
            />
          ) : (
            <div className="bp-empty-state bp-inline-empty">
              <strong>常见问题待补充</strong>
              <p>企业确认问答口径后会显示在这里。</p>
            </div>
          )}
        </Section>

        {isStandaloneEnterprise && templateFaqBlocks.length > 0 && (
          <EnterpriseTemplateBlocks blocks={templateFaqBlocks} />
        )}

        {isStandaloneEnterprise && templateCtaBlocks.length > 0 && (
          <EnterpriseTemplateBlocks blocks={templateCtaBlocks} />
        )}

        <section
          className={`bp-ai-card bp-company-ai${isStandaloneEnterprise ? " bp-company-scroll-section" : ""}`}
          id={isStandaloneEnterprise ? "bp-company-section-ai" : undefined}
          data-company-section={isStandaloneEnterprise ? "ai" : undefined}
        >
          <div><i>AI</i><span><strong>{assistantName}</strong><small>{assistantAvailable ? isPublished ? "基于已发布资料" : "基于本地展示资料" : "暂未开放"}</small></span></div>
          <p>{isBlankTemplate ? "知识资料尚未录入；完成解析、预览和发布后才会开放问答。" : assistantAvailable ? (templateAiBlock?.body || card?.ai_assistant.welcome_message || "我可以介绍企业能力、解释常见问题，并帮助整理合作需求。") : "企业尚未开放 AI 问答，可提交合作需求等待人工联系。"}</p>
          {assistantAvailable && <button type="button" onClick={() => onAssistant()}>咨询适合我们的解决方案 <Arrow /></button>}
          {isBlankTemplate && <a className="bp-template-link" href={onboardingHref}>配置企业知识库 <Arrow /></a>}
        </section>
          </>
        )}
        {isStandaloneCard && (
          <div className="bp-standalone-utilities">
            <button type="button" onClick={toggleSaved}>{saved ? "取消保存" : "保存企业名片"}</button>
            <button type="button" onClick={onPrivacy}>隐私与个人信息</button>
          </div>
        )}
      </main>
      {isStandaloneCard ? <div className="bp-sticky-actions bp-standalone-action-bar" aria-label="企业名片主要操作">
        <button className="primary" type="button" disabled={!assistantAvailable} onClick={() => onAssistant()}>咨询 AI</button>
        <button type="button" onClick={onLead}>提交合作需求</button>
      </div> : <div className="bp-sticky-actions bp-company-actions">
        {isBlankTemplate ? <>
          <button type="button" onClick={onShare}>分享空白模板</button>
          <a className="primary" href={onboardingHref}>开始配置企业</a>
        </> : <>
          <button type="button" onClick={toggleSaved}>{saved ? "✓ 本机已保存企业名片" : "⌑ 保存到本机"}</button>
          <button className="primary" type="button" onClick={onLead}>⌁ 发起合作</button>
        </>}
      </div>}
      {!isStandaloneCard && bottom}
    </>
  );

  const squarePage = (
    <>
      <AppHeader back={isStandaloneCard ? () => replaceWithView(standaloneRoot) : undefined} title="业务广场" onShare={onShare} />
      <main className="bp-page">
        <div className="bp-square-hero">
          <p>真实公开资料</p><h1>从产品、案例和业务方向开始</h1>
          <small>所有内容均来自企业当前已发布资料；不会展示未公开内容。</small>
          <label className="bp-search">⌕ <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="搜索产品、案例或业务方向" placeholder="搜索产品、案例或业务方向" /></label>
        </div>
        <Section title="内容类型">
          <div className="bp-filter">
            {(["全部", "产品", "案例"] as SquareFilter[]).map((item) => <button className={filter === item ? "active" : ""} type="button" key={item} onClick={() => setFilter(item)}>{item}</button>)}
          </div>
        </Section>

        {catalog.status === "loading" ? <LoadingRows label="公开内容" /> : catalog.status === "idle" ? (
          <div className="bp-empty-state"><strong>{isBlankTemplate ? "产品与案例尚未录入" : "暂无已发布的业务内容"}</strong><p>{isBlankTemplate ? "导入甲方产品、服务与获授权案例后，这里会形成可检索的业务广场。" : "当前静态页面尚未连接企业业务目录。"}</p>{isBlankTemplate && <a href={onboardingHref}>添加企业业务资料</a>}</div>
        ) : catalog.status === "error" ? (
          <div className="bp-empty-state" role="alert"><strong>暂时无法读取业务资料</strong><p>{catalog.message}</p>{assistantAvailable && <button type="button" onClick={() => onAssistant("请介绍目前已发布的业务资料")}>改为向 AI 了解</button>}</div>
        ) : (
          <>
            {visibleProducts.length > 0 && <Section title="产品与服务"><div className="bp-list">{visibleProducts.map((product) => <button type="button" key={product.slug} onClick={() => openDetail({ kind: "product", item: product })}><i>◇</i><span><strong>{product.name}</strong><small>{product.category || "产品与服务"} · {product.summary}</small></span><Arrow /></button>)}</div></Section>}
            {visibleCases.length > 0 && <Section title="公开案例"><div className="bp-list">{visibleCases.map((item) => <button type="button" key={item.slug} onClick={() => openDetail({ kind: "case", item })}><i>▦</i><span><strong>{item.title}</strong><small>{item.industry || "公开案例"} · {item.result}</small></span><Arrow /></button>)}</div></Section>}
            {!visibleProducts.length && !visibleCases.length && <div className="bp-empty-state"><strong>没有找到匹配内容</strong><p>{assistantAvailable ? "可以换一个关键词，或直接向 AI 助手提问。" : "可以换一个关键词，或提交合作需求等待人工联系。"}</p>{assistantAvailable && <button type="button" onClick={() => onAssistant(query || "请介绍企业当前业务")}>向 AI 提问</button>}</div>}
          </>
        )}

        {recommendations.length > 0 && <Section title="可解释推荐"><div className="bp-list">{recommendations.map((item) => {
          const target = recommendationTarget(item);
          const route = recommendationRoute(item);
          const canOpen = Boolean(target || route);
          return <button type="button" key={`${item.resourceType}-${item.resourceId}`} disabled={!canOpen && !assistantAvailable} onClick={() => target ? openDetail(target) : route ? openDetailRoute(route) : onAssistant(`请介绍${item.title}`)}><span><strong>{item.title}</strong><small>{item.reason} · 依据：{item.evidence.excerpt} · {canOpen ? "打开已发布详情" : "向 AI 了解"}</small></span><Arrow /></button>;
        })}</div></Section>}
      </main>
      {!isStandaloneCard && bottom}
    </>
  );

  const mePage = (
    <>
      <AppHeader title="我的名片关系" onShare={onShare} />
      <main className="bp-page">
        <div className="bp-me-head"><Avatar label={isBlankTemplate ? "＋" : displayName} src={avatar} /><div><h1>{isBlankTemplate ? "空白企业模板" : saved ? "已保存这张名片" : "尚未保存名片"}</h1><p>{isBlankTemplate ? "等待装入甲方企业资料" : `${companyName} · ${displayName}`}</p></div></div>
        <Section title="名片操作"><div className="bp-list">
          {!isBlankTemplate && <button type="button" onClick={toggleSaved}><span className="bp-list-icon"><BookmarkSimpleIcon size={19} weight={saved ? "fill" : "regular"} /></span><span><strong>{saved ? "取消保存" : "保存到本设备"}</strong><small>仅保存在当前浏览器，不会上传通讯录</small></span><Arrow /></button>}
          <button type="button" onClick={onShare}><span className="bp-list-icon"><ShareNetworkIcon size={19} /></span><span><strong>分享名片</strong><small>生成二维码或复制当前公开链接</small></span><Arrow /></button>
          {isBlankTemplate ? <a className="bp-list-link" href={onboardingHref}><span className="bp-list-icon"><BuildingsIcon size={19} /></span><span><strong>开始配置企业</strong><small>录入甲方资料并生成可审核预览</small></span><Arrow /></a> : <button type="button" onClick={onLead}><span className="bp-list-icon"><PaperPlaneTiltIcon size={19} /></span><span><strong>提交合作需求</strong><small>提交前会单独征得联系授权</small></span><Arrow /></button>}
        </div></Section>

        <Section title="官方联系方式"><div className="bp-list">
          {websiteHref && <a className="bp-list-link" href={websiteHref} target="_blank" rel="noreferrer"><span className="bp-list-icon"><BuildingsIcon size={19} /></span><span><strong>{websiteLabel}</strong><small>{websiteHref}</small></span><Arrow /></a>}
          {contactFields.map((field, index) => {
            const href = safeContactHref(field);
            const key = `${field.label}-${index}`;
            const feedback = copyFeedback?.key === key
              ? copyFeedback.status === "copied" ? "已复制" : "复制失败，请长按内容复制"
              : field.value;
            const content = <><span className="bp-list-icon"><ChatCircleDotsIcon size={19} /></span><span><strong>{field.label}</strong><small aria-live="polite">{feedback}</small></span><Arrow /></>;
            return href ? <a className="bp-list-link" href={href} key={key}>{content}</a> : <button type="button" key={key} onClick={() => void copyContact(key, field.value)}>{content}</button>;
          })}
          {!websiteHref && !contactFields.length && <p className="bp-page-note">企业暂未发布直接联系方式，可以提交合作需求等待联系。</p>}
        </div></Section>

        {card ? <Section title="隐私与授权"><div className="bp-list">
          <button type="button" onClick={onProfile}><span className="bp-list-icon"><IdentificationCardIcon size={19} /></span><span><strong>长期访客画像授权</strong><small>自主开启或撤回个性化关联</small></span><Arrow /></button>
          <button type="button" onClick={onPrivacy}><span className="bp-list-icon"><UserCircleIcon size={19} /></span><span><strong>个人信息权利</strong><small>访问、更正、删除数据或撤回授权</small></span><Arrow /></button>
        </div></Section> : !isBlankTemplate ? <Section title="隐私与授权"><p className="bp-page-note">当前为离线展示，公开名片服务恢复后可管理画像授权与个人信息权利。</p></Section> : null}

        <Section title="企业入口"><a className="bp-company-reco" href={isBlankTemplate ? onboardingHref : adminHref}>{companyLogo ? <img src={companyLogo} alt="" /> : <i aria-hidden="true">＋</i>}<span><strong>{isBlankTemplate ? "进入资料辅助建企" : "进入企业管理后台"}</strong><small>{isBlankTemplate ? "录入并审核甲方企业资料" : "仅企业员工和管理员可以登录"}</small></span><Arrow /></a></Section>
      </main>
      {bottom}
    </>
  );

  const detailPage = detail ? (
    <>
      <AppHeader back={returnFromDetail} title={detail.kind === "product" ? "产品与服务" : "公开案例"} onShare={onShare} />
      <main className="bp-page bp-detail-page">
        <p className="bp-detail-eyebrow">{detail.kind === "product" ? detail.item.category || "产品与服务" : detail.item.industry || "公开案例"}</p>
        <h1>{detail.kind === "product" ? detail.item.name : detail.item.title}</h1>
        {detail.item.imageUrl && <img className="bp-detail-image" src={detail.item.imageUrl} alt="" />}
        {detail.kind === "product" ? <>
          <p className="bp-detail-lede">{detail.item.summary}</p>
          <div className="bp-product-detail-poster">
            <article className="wide"><span>01</span><div><small>详细说明</small><p>{detail.item.detail}</p></div></article>
            {detail.item.audience && <article><span>02</span><div><small>适用对象</small><p>{detail.item.audience}</p></div></article>}
            {detail.item.priceBoundary && <article><span>03</span><div><small>服务边界</small><p>{detail.item.priceBoundary}</p></div></article>}
          </div>
        </> : <>
          <div className="bp-case-story">
            {[
              ["01", "项目背景", detail.item.background],
              ["02", "解决方案", detail.item.solution],
              ["03", "项目结果", detail.item.result],
            ].map(([number, label, content], index) => (
              <article className={index === 2 ? "result" : ""} key={label}>
                <span>{number}</span><div><small>{label}</small><p>{content}</p></div>
              </article>
            ))}
          </div>
        </>}
        {assistantAvailable && <section className="bp-ai-card"><div><i>AI</i><span><strong>{assistantName}</strong><small>继续了解</small></span></div><button type="button" onClick={() => onAssistant(`请详细介绍${detail.kind === "product" ? detail.item.name : detail.item.title}`)}>向 AI 继续提问 <Arrow /></button></section>}
      </main>
      <div className="bp-sticky-actions bp-detail-actions"><button type="button" onClick={returnFromDetail}>返回</button><button className="primary" type="button" onClick={onLead}>留下合作需求</button></div>
    </>
  ) : requestedDetail ? (
    <>
      <AppHeader
        back={returnFromDetail}
        title={requestedDetail.kind === "product" ? "产品与服务" : "公开案例"}
        onShare={onShare}
      />
      <main className="bp-page bp-detail-page">
        {catalog.status === "loading" || (catalog.status === "ready" && (detailLookup.status === "idle" || detailLookup.status === "loading")) ? (
          <LoadingRows label="详情" />
        ) : catalog.status === "error" ? (
          <div className="bp-empty-state" role="alert">
            <strong>详情暂时无法加载</strong>
            <p>{catalog.message}</p>
            <button type="button" onClick={() => replaceWithView("square")}>返回业务广场</button>
          </div>
        ) : detailLookup.status === "error" ? (
          <div className="bp-empty-state" role="alert">
            <strong>详情暂时无法加载</strong>
            <p>{detailLookup.message}</p>
            <button type="button" onClick={() => replaceWithView("square")}>返回业务广场</button>
          </div>
        ) : catalog.status === "ready" && detailLookup.status === "missing" ? (
          <div className="bp-empty-state" role="alert">
            <strong>该内容不存在或已下线</strong>
            <p>链接对应的公开内容已更新，请返回业务广场查看当前已发布资料。</p>
            <button type="button" onClick={() => replaceWithView("square")}>返回业务广场</button>
          </div>
        ) : (
          <div className="bp-empty-state" role="alert">
            <strong>当前无法读取详情</strong>
            <p>公开业务目录尚未连接，请稍后重试或返回名片首页。</p>
            <button type="button" onClick={() => replaceWithView("card")}>返回名片</button>
          </div>
        )}
      </main>
    </>
  ) : null;

  const page = view === "card" ? cardPage : view === "company" ? companyPage : view === "square" ? squarePage : view === "me" ? mePage : detailPage ?? squarePage;

  return <div className={`bp-app bp-live-app bp-view-${view}${isStandaloneCard ? " bp-standalone-card" : ""}`}><div className="bp-phone-frame">{page}</div></div>;
});

import {
  ArrowRight,
  Briefcase,
  Buildings,
  CheckCircle,
  CopySimple,
  EnvelopeSimple,
  PaperPlaneTilt,
  Phone,
  QrCode,
  ShareNetwork,
  ShieldCheck,
  SpinnerGap,
  WechatLogo,
  X,
} from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  forwardRef,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PropsWithChildren,
  useCallback,
  useEffect,
  useId,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  AssistantApiError,
  getActiveAssistantConversationId,
  type PublicPolicyVersions,
} from "../lib/assistantApi";
import { lockBodyScroll } from "../lib/bodyScrollLock";
import { fetchPublicCard, type PublicCardData } from "../lib/publicCardApi";
import {
  canonicalShareUrl,
  createPublicIdempotencyKey,
  fetchPublicCaseStudy,
  fetchPublicCatalog,
  fetchPublicProduct,
  fetchPublicRecommendations,
  isPublicExperienceConfigured,
  safeContactHref,
  setProfilePersonalizationConsent,
  submitPrivacyRequest,
  submitPublicLead,
  type PrivacyRequestType,
  type PublicCaseStudy,
  type PublicCatalog,
  type PublicProduct,
  type PublicRecommendation,
} from "../lib/publicExperienceApi";
import {
  readProfileLinkToken,
  readProfileRevokePending,
} from "../lib/profileLink";
import { encodeQrMatrix, qrPathData } from "../lib/qrCode";

type DialogState =
  | { type: "lead" }
  | { type: "privacy" }
  | { type: "profile" }
  | { type: "share" }
  | { type: "product"; item: PublicProduct }
  | { type: "case"; item: PublicCaseStudy }
  | null;

type AsyncState<T> =
  | { status: "idle" | "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; message: string };

type LeadFields = {
  name: string;
  mobile: string;
  email: string;
  wechat: string;
  companyName: string;
  demand: string;
  consent: boolean;
};

type PrivacyFields = {
  requestType: PrivacyRequestType;
  consentScope: "chat_notice" | "lead_contact";
  note: string;
};

export type PublicExperienceHandle = {
  openLead: () => void;
  openPrivacy: () => void;
  openProfile: () => void;
  openShare: () => void;
};

function policyVersions(card: PublicCardData): PublicPolicyVersions {
  return {
    privacy: card.policy_versions.privacy,
    chatNotice: card.policy_versions.chat_notice,
    leadConsent: card.policy_versions.lead_consent,
    profilePersonalization: card.policy_versions.profile_personalization,
  };
}

function publicErrorMessage(error: unknown, fallback: string) {
  if (!(error instanceof AssistantApiError)) return fallback;
  if (error.code === "POLICY_VERSION_MISMATCH") {
    return "授权告知已更新，请重新确认后再提交。";
  }
  if (error.code === "IDEMPOTENCY_IN_PROGRESS") {
    return "请求正在处理中，请稍候再试，不会重复创建记录。";
  }
  if (error.code === "IDEMPOTENCY_CONFLICT") {
    return "本次提交信息已变化，请重新确认后再试。";
  }
  if (error.status === 429) return "当前提交较多，请稍后再试。";
  if (error.status === 401 || error.status === 403) {
    return "访客会话未能恢复，请刷新页面后再试。";
  }
  if (error.code === "NETWORK_ERROR" || (error.status ?? 0) >= 500) {
    return "服务暂时不可用，请检查网络后重试。";
  }
  return error.message || fallback;
}

function copyText(value: string) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(value);
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand?.("copy") ?? false;
  textarea.remove();
  return copied ? Promise.resolve() : Promise.reject(new Error("copy failed"));
}

function ModalShell({
  title,
  eyebrow,
  wide = false,
  onClose,
  children,
}: PropsWithChildren<{
  title: string;
  eyebrow: string;
  wide?: boolean;
  onClose: () => void;
}>) {
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const shouldReduceMotion = useReducedMotion();
  const titleId = `public-dialog-${useId().replace(/:/g, "")}`;

  useEffect(() => {
    previousFocus.current = document.activeElement as HTMLElement | null;
    const focusTimer = window.setTimeout(() => {
      const firstField = panelRef.current?.querySelector<HTMLElement>(
        "input:not([disabled]), select:not([disabled]), textarea:not([disabled])",
      );
      (firstField ?? closeRef.current)?.focus();
    }, 40);
    const handleKeys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", handleKeys);
    return () => {
      window.clearTimeout(focusTimer);
      window.removeEventListener("keydown", handleKeys);
      window.setTimeout(() => previousFocus.current?.focus(), 0);
    };
  }, [onClose]);

  return (
    <>
      <motion.button
        className="public-dialog-backdrop"
        type="button"
        aria-label="关闭弹窗"
        onClick={onClose}
        initial={shouldReduceMotion ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={shouldReduceMotion ? undefined : { opacity: 0 }}
      />
      <motion.section
        ref={panelRef}
        className={`public-dialog${wide ? " public-dialog-wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        initial={shouldReduceMotion ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={shouldReduceMotion ? undefined : { opacity: 0 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
      >
        <header className="public-dialog-header">
          <div>
            <p>{eyebrow}</p>
            <h2 id={titleId}>{title}</h2>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="关闭">
            <X size={20} aria-hidden="true" />
          </button>
        </header>
        <div className="public-dialog-body">{children}</div>
      </motion.section>
    </>
  );
}

function CatalogLoading() {
  return (
    <div className="catalog-loading" aria-label="正在加载产品与案例">
      {[0, 1, 2].map((item) => (
        <span key={item} />
      ))}
    </div>
  );
}

function DetailContent({
  dialog,
  detail,
  retry,
  onAssistant,
  onLead,
}: {
  dialog: Exclude<DialogState, null | { type: "lead" | "privacy" | "profile" | "share" }>;
  detail: AsyncState<PublicProduct | PublicCaseStudy>;
  retry: () => void;
  onAssistant: (question: string) => void;
  onLead: () => void;
}) {
  const item = detail.status === "ready" ? detail.data : dialog.item;
  const isProduct = dialog.type === "product";
  const product = isProduct ? (item as PublicProduct) : undefined;
  const caseStudy = !isProduct ? (item as PublicCaseStudy) : undefined;

  return (
    <div className="catalog-detail">
      {item.imageUrl && (
        <img
          src={item.imageUrl}
          alt=""
          width="960"
          height="560"
          loading="lazy"
          decoding="async"
        />
      )}
      {detail.status === "loading" && (
        <p className="inline-status" role="status">
          <SpinnerGap className="spin" size={18} aria-hidden="true" />
          正在读取最新详情
        </p>
      )}
      {detail.status === "error" && (
        <div className="inline-error" role="alert">
          <p>{detail.message}</p>
          <button type="button" onClick={retry}>
            重试
          </button>
        </div>
      )}

      {product ? (
        <>
          <p className="catalog-detail-summary">{product.summary}</p>
          <div className="catalog-detail-copy">
            <h3>服务详情</h3>
            <p>{product.detail}</p>
          </div>
          {(product.audience || product.priceBoundary) && (
            <dl className="catalog-detail-meta">
              {product.audience && (
                <div>
                  <dt>适用对象</dt>
                  <dd>{product.audience}</dd>
                </div>
              )}
              {product.priceBoundary && (
                <div>
                  <dt>合作边界</dt>
                  <dd>{product.priceBoundary}</dd>
                </div>
              )}
            </dl>
          )}
        </>
      ) : (
        caseStudy && (
          <div className="catalog-case-story">
            {[
              ["项目背景", caseStudy.background],
              ["解决方案", caseStudy.solution],
              ["项目成果", caseStudy.result],
            ].map(([label, value]) => (
              <section key={label}>
                <h3>{label}</h3>
                <p>{value}</p>
              </section>
            ))}
          </div>
        )
      )}

      <div className="dialog-actions">
        <button
          className="button button-primary"
          type="button"
          onClick={() => {
            onAssistant(
              isProduct
                ? `请详细介绍${product?.name ?? "这个产品"}`
                : `请详细介绍${caseStudy?.title ?? "这个案例"}`,
            );
          }}
        >
          向 AI 继续了解
          <ArrowRight size={17} aria-hidden="true" />
        </button>
        <button className="button button-secondary" type="button" onClick={onLead}>
          留下合作需求
        </button>
      </div>
    </div>
  );
}

export const PublicExperience = forwardRef<
  PublicExperienceHandle,
  {
    card: PublicCardData;
    controllerOnly?: boolean;
    onAssistant: (question: string) => void;
  }
>(function PublicExperience({ card, controllerOnly = false, onAssistant }, ref) {
  const configured = isPublicExperienceConfigured();
  const [catalog, setCatalog] = useState<AsyncState<PublicCatalog>>({ status: "idle" });
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [recommendations, setRecommendations] = useState<AsyncState<PublicRecommendation[]>>({ status: "idle" });
  const [activeTab, setActiveTab] = useState<"products" | "cases">("products");
  const [dialog, setDialog] = useState<DialogState>(null);
  const [detail, setDetail] = useState<AsyncState<PublicProduct | PublicCaseStudy>>({
    status: "idle",
  });
  const [policies, setPolicies] = useState(() => policyVersions(card));
  const [contactStatus, setContactStatus] = useState("");
  const detailController = useRef<AbortController | null>(null);
  const scrollUnlockRef = useRef<(() => void) | null>(null);
  const dialogOpenRef = useRef(Boolean(dialog));
  dialogOpenRef.current = Boolean(dialog);

  const releaseScrollLock = useCallback(() => {
    scrollUnlockRef.current?.();
    scrollUnlockRef.current = null;
  }, []);

  useLayoutEffect(() => {
    if (dialog && !scrollUnlockRef.current) {
      scrollUnlockRef.current = lockBodyScroll();
    }
  }, [dialog]);

  useEffect(() => setPolicies(policyVersions(card)), [card]);
  useEffect(
    () => () => {
      detailController.current?.abort();
      releaseScrollLock();
    },
    [releaseScrollLock],
  );

  const closeDialog = useCallback(() => {
    detailController.current?.abort();
    detailController.current = null;
    setDialog(null);
  }, []);
  const openLead = useCallback(() => {
    detailController.current?.abort();
    detailController.current = null;
    setDialog({ type: "lead" });
  }, []);
  const openShare = useCallback(() => {
    detailController.current?.abort();
    detailController.current = null;
    setDialog({ type: "share" });
  }, []);
  const openPrivacy = useCallback(() => {
    detailController.current?.abort();
    detailController.current = null;
    setDialog({ type: "privacy" });
  }, []);
  const openProfile = useCallback(() => {
    detailController.current?.abort();
    detailController.current = null;
    setDialog({ type: "profile" });
  }, []);
  useImperativeHandle(
    ref,
    () => ({ openLead, openPrivacy, openProfile, openShare }),
    [openLead, openPrivacy, openProfile, openShare],
  );

  useEffect(() => {
    if (!configured || controllerOnly) return undefined;
    const controller = new AbortController();
    setCatalog({ status: "loading" });
    void fetchPublicCatalog(card.slug, controller.signal)
      .then((data) => {
        setCatalog({ status: "ready", data });
        if (!data.products.length && data.cases.length) setActiveTab("cases");
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setCatalog({
          status: "error",
          message: publicErrorMessage(error, "产品与案例暂时无法加载。"),
        });
      });
    return () => controller.abort();
  }, [card.slug, catalogAttempt, configured, controllerOnly]);

  useEffect(() => {
    if (!configured || controllerOnly) return undefined;
    const controller = new AbortController();
    setRecommendations({ status: "loading" });
    void fetchPublicRecommendations(card.slug, controller.signal)
      .then((data) => setRecommendations({ status: "ready", data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setRecommendations({
          status: "error",
          message: publicErrorMessage(error, "推荐内容暂时无法加载。"),
        });
      });
    return () => controller.abort();
  }, [card.slug, configured, controllerOnly]);

  const loadDetail = useCallback(
    (target: Exclude<DialogState, null | { type: "lead" | "privacy" | "profile" | "share" }>) => {
      detailController.current?.abort();
      const controller = new AbortController();
      detailController.current = controller;
      setDetail({ status: "loading" });
      const request =
        target.type === "product"
          ? fetchPublicProduct(card.slug, target.item.slug, controller.signal)
          : fetchPublicCaseStudy(card.slug, target.item.slug, controller.signal);
      void request
        .then((data) => setDetail({ status: "ready", data }))
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          setDetail({
            status: "error",
            message: publicErrorMessage(error, "详情暂时无法加载。"),
          });
        })
        .finally(() => {
          if (detailController.current === controller) detailController.current = null;
        });
      return controller;
    },
    [card.slug],
  );

  const openDetail = useCallback(
    (target: Exclude<DialogState, null | { type: "lead" | "privacy" | "profile" | "share" }>) => {
      setDialog(target);
      loadDetail(target);
    },
    [loadDetail],
  );

  const refreshPolicies = useCallback(async () => {
    const latest = await fetchPublicCard(card.slug);
    if (!latest) throw new Error("card unavailable");
    const next = policyVersions(latest);
    setPolicies(next);
    return next;
  }, [card.slug]);

  const contactFields = card.contact_fields.filter((field) => field.label && field.value);
  const products = catalog.status === "ready" ? catalog.data.products : [];
  const cases = catalog.status === "ready" ? catalog.data.cases : [];
  const activeItems = activeTab === "products" ? products : cases;
  const openRecommendation = (recommendation: PublicRecommendation) => {
    if (recommendation.resourceType === "product") {
      const product = products.find((item) => recommendation.url.endsWith(`/${item.slug}`));
      if (product) return openDetail({ type: "product", item: product });
    }
    if (recommendation.resourceType === "case_study") {
      const caseStudy = cases.find((item) => recommendation.url.endsWith(`/${item.slug}`));
      if (caseStudy) return openDetail({ type: "case", item: caseStudy });
    }
    onAssistant(`请介绍一下${recommendation.title}`);
  };
  const handleTabKey = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    let nextTab: "products" | "cases" | undefined;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      nextTab = activeTab === "products" ? "cases" : "products";
    } else if (event.key === "Home") {
      nextTab = "products";
    } else if (event.key === "End") {
      nextTab = "cases";
    }
    if (!nextTab) return;
    event.preventDefault();
    setActiveTab(nextTab);
    window.requestAnimationFrame(() => {
      document.getElementById(`catalog-tab-${nextTab}`)?.focus();
    });
  };

  return (
    <>
      {!controllerOnly && <section className="section public-experience" id="catalog" aria-labelledby="catalog-title">
        <div className="page-width">
          <div className="public-experience-heading">
            <div className="section-heading">
              <p className="section-eyebrow">已发布业务资料</p>
              <h2 id="catalog-title">
                产品、案例与<br className="catalog-title-break" />下一步合作
              </h2>
              <p className="section-description">
                查看企业当前公开内容，也可以直接咨询、分享或提交合作需求。
              </p>
            </div>
            <div className="public-quick-actions">
              <button className="button button-secondary" type="button" onClick={openShare}>
                <ShareNetwork size={18} aria-hidden="true" />
                分享名片
              </button>
              <button className="button button-primary" type="button" onClick={openLead}>
                <PaperPlaneTilt size={18} aria-hidden="true" />
                留下需求
              </button>
            </div>
          </div>

          <div className="catalog-tabs" role="tablist" aria-label="公开业务资料">
            <button
              type="button"
              role="tab"
              id="catalog-tab-products"
              aria-selected={activeTab === "products"}
              aria-controls="catalog-panel"
              tabIndex={activeTab === "products" ? 0 : -1}
              onClick={() => setActiveTab("products")}
              onKeyDown={handleTabKey}
            >
              <Briefcase size={18} aria-hidden="true" />
              产品与服务
              {catalog.status === "ready" && <span>{products.length}</span>}
            </button>
            <button
              type="button"
              role="tab"
              id="catalog-tab-cases"
              aria-selected={activeTab === "cases"}
              aria-controls="catalog-panel"
              tabIndex={activeTab === "cases" ? 0 : -1}
              onClick={() => setActiveTab("cases")}
              onKeyDown={handleTabKey}
            >
              <Buildings size={18} aria-hidden="true" />
              公开案例
              {catalog.status === "ready" && <span>{cases.length}</span>}
            </button>
          </div>

          <div
            className="catalog-panel"
            id="catalog-panel"
            role="tabpanel"
            aria-labelledby={
              activeTab === "products" ? "catalog-tab-products" : "catalog-tab-cases"
            }
          >
            {!configured ? (
              <div className="catalog-empty">
                <ShieldCheck size={26} aria-hidden="true" />
                <h3>公开资料接口尚未配置</h3>
                <p>仍可使用页面现有介绍与本地资料助手。</p>
              </div>
            ) : catalog.status === "idle" || catalog.status === "loading" ? (
              <CatalogLoading />
            ) : catalog.status === "error" ? (
              <div className="catalog-empty catalog-error" role="alert">
                <ShieldCheck size={26} aria-hidden="true" />
                <h3>暂时没有读取到业务资料</h3>
                <p>{catalog.message}</p>
                <button type="button" onClick={() => setCatalogAttempt((value) => value + 1)}>
                  重新加载
                </button>
              </div>
            ) : activeItems.length === 0 ? (
              <div className="catalog-empty">
                {activeTab === "products" ? (
                  <Briefcase size={26} aria-hidden="true" />
                ) : (
                  <Buildings size={26} aria-hidden="true" />
                )}
                <h3>{activeTab === "products" ? "产品资料正在准备" : "案例资料正在准备"}</h3>
                <p>企业尚未发布这一类内容，可以先向 AI 助手了解。</p>
                <button type="button" onClick={() => onAssistant("请介绍一下目前已发布的业务资料") }>
                  向 AI 了解
                </button>
              </div>
            ) : (
              <div className="catalog-list">
                {activeTab === "products"
                  ? products.map((product, index) => (
                      <button
                        className="catalog-item"
                        type="button"
                        key={product.slug}
                        onClick={() => openDetail({ type: "product", item: product })}
                      >
                        <span className="catalog-index">{String(index + 1).padStart(2, "0")}</span>
                        <span className="catalog-item-copy">
                          <small>{product.category || "产品与服务"}</small>
                          <strong>{product.name}</strong>
                          <span>{product.summary}</span>
                        </span>
                        <ArrowRight size={20} aria-hidden="true" />
                      </button>
                    ))
                  : cases.map((caseStudy, index) => (
                      <button
                        className="catalog-item"
                        type="button"
                        key={caseStudy.slug}
                        onClick={() => openDetail({ type: "case", item: caseStudy })}
                      >
                        <span className="catalog-index">{String(index + 1).padStart(2, "0")}</span>
                        <span className="catalog-item-copy">
                          <small>{caseStudy.industry || "公开案例"}</small>
                          <strong>{caseStudy.title}</strong>
                          <span>{caseStudy.background}</span>
                        </span>
                        <ArrowRight size={20} aria-hidden="true" />
                      </button>
                    ))}
              </div>
            )}
          </div>

          {recommendations.status === "ready" && recommendations.data.length > 0 && (
            <aside className="public-recommendations" aria-labelledby="recommendations-title">
              <div>
                <p className="section-eyebrow">公开内容推荐</p>
                <h3 id="recommendations-title">或许对你有帮助</h3>
                <p>推荐理由和依据均来自企业当前公开内容，不使用或展示个人画像。</p>
              </div>
              <div className="public-recommendation-list">
                {recommendations.data.map((recommendation) => (
                  <button
                    type="button"
                    key={`${recommendation.resourceType}-${recommendation.resourceId}`}
                    onClick={() => openRecommendation(recommendation)}
                  >
                    <span>
                      <small>{recommendation.reason}</small>
                      <strong>{recommendation.title}</strong>
                      <em>依据：{recommendation.evidence.excerpt}</em>
                    </span>
                    <ArrowRight size={18} aria-hidden="true" />
                  </button>
                ))}
              </div>
            </aside>
          )}
          {recommendations.status === "error" && (
            <p className="public-recommendations-unavailable" role="status">推荐内容暂时不可用，仍可浏览已发布资料或向 AI 助手提问。</p>
          )}

          <div className="contact-ledger" id="contact">
            <div className="contact-intro">
              <p className="section-eyebrow">官方联系方式</p>
              <h3>选择合适的方式继续沟通</h3>
              <p>仅使用企业当前公开的联系方式。提交需求前会单独征得授权。</p>
            </div>
            <div className="contact-fields" aria-live="polite">
              {contactFields.length ? (
                contactFields.map((field, index) => {
                  const href = safeContactHref(field);
                  const Icon = /mail|邮箱/i.test(`${field.label}${href}`)
                    ? EnvelopeSimple
                    : /微信|wechat/i.test(`${field.label}${href}`)
                      ? WechatLogo
                      : Phone;
                  const content = (
                    <>
                      <Icon size={20} aria-hidden="true" />
                      <span>
                        <small>{field.label}</small>
                        <strong>{field.value}</strong>
                      </span>
                      {href ? <ArrowRight size={17} aria-hidden="true" /> : <CopySimple size={17} aria-hidden="true" />}
                    </>
                  );
                  return href ? (
                    <a
                      key={`${field.label}-${index}`}
                      href={href}
                      target={/^https?:/i.test(href) ? "_blank" : undefined}
                      rel={/^https?:/i.test(href) ? "noreferrer" : undefined}
                    >
                      {content}
                    </a>
                  ) : (
                    <button
                      key={`${field.label}-${index}`}
                      type="button"
                      onClick={() => {
                        void copyText(field.value)
                          .then(() => setContactStatus(`${field.label}已复制`))
                          .catch(() => setContactStatus("复制失败，请长按内容复制"));
                      }}
                    >
                      {content}
                    </button>
                  );
                })
              ) : (
                <p className="contact-empty">企业暂未发布直接联系方式，可以提交需求等待联系。</p>
              )}
              {contactStatus && <p className="sr-only">{contactStatus}</p>}
            </div>
            <button className="privacy-entry" type="button" onClick={() => setDialog({ type: "privacy" })}>
              <ShieldCheck size={17} aria-hidden="true" />
              访问、更正、删除数据或撤回授权
              <ArrowRight size={16} aria-hidden="true" />
            </button>
            <ProfilePersonalizationControl
              cardSlug={card.slug}
              companyId={card.company.id}
              policies={policies}
              refreshPolicies={refreshPolicies}
              configured={configured}
            />
          </div>
        </div>
      </section>}

      <AnimatePresence
        onExitComplete={() => {
          if (!dialogOpenRef.current) releaseScrollLock();
        }}
      >
        {dialog?.type === "lead" && (
          <ModalShell eyebrow="主动联系授权" title="留下合作需求" onClose={closeDialog}>
            <LeadForm
              cardSlug={card.slug}
              policies={policies}
              refreshPolicies={refreshPolicies}
              onClose={closeDialog}
            />
          </ModalShell>
        )}
        {dialog?.type === "privacy" && (
          <ModalShell eyebrow="个人信息权利" title="提交隐私请求" onClose={closeDialog}>
            <PrivacyForm
              cardSlug={card.slug}
              policies={policies}
              refreshPolicies={refreshPolicies}
              onClose={closeDialog}
            />
          </ModalShell>
        )}
        {dialog?.type === "profile" && (
          <ModalShell eyebrow="长期访客画像" title="个性化授权" onClose={closeDialog}>
            <ProfilePersonalizationControl
              cardSlug={card.slug}
              companyId={card.company.id}
              policies={policies}
              refreshPolicies={refreshPolicies}
              configured={configured}
            />
          </ModalShell>
        )}
        {dialog?.type === "share" && (
          <ModalShell
            eyebrow={card.card_kind === "employee" ? "分享员工名片" : "分享企业名片"}
            title="扫码或复制链接"
            onClose={closeDialog}
          >
            <SharePanel card={card} />
          </ModalShell>
        )}
        {(dialog?.type === "product" || dialog?.type === "case") && (
          <ModalShell
            eyebrow={dialog.type === "product" ? dialog.item.category || "产品与服务" : dialog.item.industry || "公开案例"}
            title={dialog.type === "product" ? dialog.item.name : dialog.item.title}
            wide
            onClose={closeDialog}
          >
            <DetailContent
              dialog={dialog}
              detail={detail}
              retry={() => loadDetail(dialog)}
              onAssistant={(question) => {
                closeDialog();
                onAssistant(question);
              }}
              onLead={openLead}
            />
          </ModalShell>
        )}
      </AnimatePresence>
    </>
  );
});

function ProfilePersonalizationControl({
  cardSlug,
  companyId,
  policies,
  refreshPolicies,
  configured,
}: {
  cardSlug: string;
  companyId: string;
  policies: PublicPolicyVersions;
  refreshPolicies: () => Promise<PublicPolicyVersions>;
  configured: boolean;
}) {
  const [enabled, setEnabled] = useState(() => Boolean(readProfileLinkToken(companyId)));
  const [status, setStatus] = useState<
    | { type: "idle" | "submitting" | "revoke-pending" }
    | { type: "success" | "error"; message: string }
  >(() => readProfileRevokePending(companyId) ? { type: "revoke-pending" } : { type: "idle" });
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    setEnabled(Boolean(readProfileLinkToken(companyId)));
    setStatus(
      readProfileRevokePending(companyId)
        ? { type: "revoke-pending" }
        : { type: "idle" },
    );
  }, [companyId]);
  useEffect(() => () => controller.current?.abort(), []);

  const updateConsent = async () => {
    if (status.type === "submitting") return;
    const granted = status.type === "revoke-pending" ? false : !enabled;
    if (!granted) setEnabled(false);
    setStatus({ type: "submitting" });
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    try {
      await setProfilePersonalizationConsent({
        cardSlug,
        companyId,
        policyVersions: policies,
        granted,
        idempotencyKey: createPublicIdempotencyKey(),
        signal: nextController.signal,
      });
      setEnabled(granted);
      setStatus({
        type: "success",
        message: granted
          ? "已开启。之后访问本企业的名片时可继续使用已形成的兴趣偏好。"
          : "已撤回并删除本设备上的长期关联信息。",
      });
    } catch (error) {
      if (nextController.signal.aborted) return;
      if (error instanceof AssistantApiError && error.code === "POLICY_VERSION_MISMATCH") {
        try {
          await refreshPolicies();
        } catch {
          // The next explicit action will try fetching the latest policy again.
        }
      }
      if (
        !granted ||
        (error instanceof AssistantApiError && error.code === "PROFILE_REVOKE_PENDING")
      ) {
        setEnabled(false);
        setStatus({
          type: "revoke-pending",
        });
      } else {
        setStatus({
          type: "error",
          message: publicErrorMessage(error, "开启失败，请稍后重试。"),
        });
      }
    } finally {
      if (controller.current === nextController) controller.current = null;
    }
  };

  const revokePending = status.type === "revoke-pending";
  return (
    <aside className="profile-personalization" aria-labelledby="profile-personalization-title">
      <div>
        <span className="profile-personalization-icon" aria-hidden="true">
          <ShieldCheck size={19} weight="duotone" />
        </span>
        <div>
          <h3 id="profile-personalization-title">仅在本企业内记住兴趣</h3>
          <p>
            开启后，本企业可在你下次访问时延续兴趣偏好；不会跨企业关联，默认不开启，且可随时撤回。
          </p>
          <small>授权版本：{policies.profilePersonalization}</small>
        </div>
      </div>
      <button
        className={`button ${enabled ? "button-secondary" : "button-primary"}`}
        type="button"
        disabled={!configured || status.type === "submitting"}
        aria-pressed={enabled}
        onClick={() => void updateConsent()}
      >
        {status.type === "submitting" ? (
          <><SpinnerGap className="spin" size={17} aria-hidden="true" />正在处理</>
        ) : revokePending ? (
          "重试完成撤回"
        ) : enabled ? (
          "撤回并停止记住"
        ) : (
          "同意并开启"
        )}
      </button>
      {!configured && <p className="profile-personalization-status">公开服务未配置，当前无法开启。</p>}
      {revokePending && (
        <p className="profile-personalization-status profile-personalization-warning" role="alert">
          本设备未保存长期关联信息，但服务器可能仍处于开启状态；请联网后重试完成撤回。
        </p>
      )}
      {(status.type === "success" || status.type === "error") && (
        <p
          className={`profile-personalization-status${status.type === "error" ? " profile-personalization-warning" : ""}`}
          role={status.type === "error" ? "alert" : "status"}
        >
          {status.message}
        </p>
      )}
    </aside>
  );
}

function LeadForm({
  cardSlug,
  policies,
  refreshPolicies,
  onClose,
}: {
  cardSlug: string;
  policies: PublicPolicyVersions;
  refreshPolicies: () => Promise<PublicPolicyVersions>;
  onClose: () => void;
}) {
  const [fields, setFields] = useState<LeadFields>({
    name: "",
    mobile: "",
    email: "",
    wechat: "",
    companyName: "",
    demand: "",
    consent: false,
  });
  const [status, setStatus] = useState<
    | { type: "idle" | "submitting" }
    | { type: "error"; message: string; policyStale?: boolean }
    | { type: "success"; id: string }
  >({ type: "idle" });
  const keys = useRef<{
    fingerprint: string;
    consent: string;
    lead: string;
  } | null>(null);
  const pending = useRef(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  const update = (name: keyof LeadFields, value: string | boolean) => {
    setFields((current) => ({ ...current, [name]: value }));
    if (status.type !== "submitting") setStatus({ type: "idle" });
    keys.current = null;
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (pending.current || status.type === "success") return;
    if (!fields.name.trim() || !fields.demand.trim()) {
      setStatus({ type: "error", message: "请填写姓名和合作需求。" });
      return;
    }
    if (![fields.mobile, fields.email, fields.wechat].some((value) => value.trim())) {
      setStatus({ type: "error", message: "请至少填写手机、邮箱或微信中的一项。" });
      return;
    }
    if (!fields.consent) {
      setStatus({ type: "error", message: "请先确认留资授权告知。" });
      return;
    }

    pending.current = true;
    setStatus({ type: "submitting" });
    const fingerprint = JSON.stringify({ ...fields, policy: policies.leadConsent });
    try {
      if (!keys.current || keys.current.fingerprint !== fingerprint) {
        keys.current = {
          fingerprint,
          consent: createPublicIdempotencyKey(),
          lead: createPublicIdempotencyKey(),
        };
      }
      controller.current = new AbortController();
      const result = await submitPublicLead({
        cardSlug,
        policyVersions: policies,
        input: {
          conversationId: getActiveAssistantConversationId(cardSlug),
          name: fields.name,
          mobile: fields.mobile,
          email: fields.email,
          wechat: fields.wechat,
          companyName: fields.companyName,
          demand: fields.demand,
        },
        consentIdempotencyKey: keys.current.consent,
        leadIdempotencyKey: keys.current.lead,
        signal: controller.current.signal,
      });
      setStatus({ type: "success", id: result.id });
    } catch (error) {
      if (controller.current?.signal.aborted) return;
      if (error instanceof AssistantApiError && error.code === "POLICY_VERSION_MISMATCH") {
        try {
          await refreshPolicies();
        } catch {
          // The explicit stale-policy state still prevents an accidental resubmission.
        }
        keys.current = null;
        setFields((current) => ({ ...current, consent: false }));
        setStatus({
          type: "error",
          policyStale: true,
          message: "授权告知已更新，请阅读并重新勾选后提交。",
        });
      } else {
        setStatus({
          type: "error",
          message: publicErrorMessage(error, "需求提交失败，请稍后重试。"),
        });
      }
    } finally {
      pending.current = false;
      controller.current = null;
    }
  };

  if (status.type === "success") {
    return (
      <div className="form-success" role="status">
        <CheckCircle size={40} weight="duotone" aria-hidden="true" />
        <h3>需求已安全提交</h3>
        <p>企业工作人员可以在后台查看并跟进，本页面不会公开你的联系方式。</p>
        <small>受理编号 {status.id}</small>
        <button className="button button-primary" type="button" onClick={onClose}>
          完成
        </button>
      </div>
    );
  }

  return (
    <form className="public-form" onSubmit={submit} noValidate>
      <div className="form-row form-row-two">
        <label>
          <span>姓名 *</span>
          <input
            name="name"
            autoComplete="name"
            maxLength={120}
            value={fields.name}
            onChange={(event) => update("name", event.target.value)}
            required
          />
        </label>
        <label>
          <span>公司或组织</span>
          <input
            name="organization"
            autoComplete="organization"
            maxLength={200}
            value={fields.companyName}
            onChange={(event) => update("companyName", event.target.value)}
          />
        </label>
      </div>
      <fieldset>
        <legend>至少填写一种联系方式 *</legend>
        <div className="form-row form-row-three">
          <label>
            <span><Phone size={15} aria-hidden="true" />手机</span>
            <input
              name="mobile"
              type="tel"
              autoComplete="tel"
              maxLength={40}
              value={fields.mobile}
              onChange={(event) => update("mobile", event.target.value)}
            />
          </label>
          <label>
            <span><EnvelopeSimple size={15} aria-hidden="true" />邮箱</span>
            <input
              name="email"
              type="email"
              autoComplete="email"
              maxLength={254}
              value={fields.email}
              onChange={(event) => update("email", event.target.value)}
            />
          </label>
          <label>
            <span><WechatLogo size={15} aria-hidden="true" />微信</span>
            <input
              name="wechat"
              autoComplete="off"
              maxLength={100}
              value={fields.wechat}
              onChange={(event) => update("wechat", event.target.value)}
            />
          </label>
        </div>
      </fieldset>
      <label>
        <span>合作需求 *</span>
        <textarea
          name="demand"
          rows={5}
          maxLength={4000}
          placeholder="请简要说明希望解决的问题、合作方向或期望时间"
          value={fields.demand}
          onChange={(event) => update("demand", event.target.value)}
          required
        />
      </label>
      <label className="consent-check">
        <input
          type="checkbox"
          checked={fields.consent}
          onChange={(event) => update("consent", event.target.checked)}
        />
        <span>
          我同意企业为联系和跟进本次需求而处理上述信息。授权版本：
          <strong>{policies.leadConsent}</strong>
        </span>
      </label>
      {status.type === "error" && (
        <div className={`form-error${status.policyStale ? " form-policy-stale" : ""}`} role="alert">
          <ShieldCheck size={18} aria-hidden="true" />
          <span>{status.message}</span>
        </div>
      )}
      <button
        className="button button-primary form-submit"
        type="submit"
        disabled={status.type === "submitting"}
      >
        {status.type === "submitting" ? (
          <><SpinnerGap className="spin" size={18} aria-hidden="true" />正在安全提交</>
        ) : (
          <><PaperPlaneTilt size={18} aria-hidden="true" />确认授权并提交</>
        )}
      </button>
    </form>
  );
}

function PrivacyForm({
  cardSlug,
  policies,
  refreshPolicies,
  onClose,
}: {
  cardSlug: string;
  policies: PublicPolicyVersions;
  refreshPolicies: () => Promise<PublicPolicyVersions>;
  onClose: () => void;
}) {
  const [fields, setFields] = useState<PrivacyFields>({
    requestType: "access",
    consentScope: "lead_contact",
    note: "",
  });
  const [status, setStatus] = useState<
    | { type: "idle" | "submitting" }
    | { type: "error"; message: string }
    | { type: "success"; id: string }
  >({ type: "idle" });
  const key = useRef<{ fingerprint: string; value: string } | null>(null);
  const pending = useRef(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (pending.current || status.type === "success") return;
    pending.current = true;
    setStatus({ type: "submitting" });
    const fingerprint = JSON.stringify(fields);
    try {
      if (!key.current || key.current.fingerprint !== fingerprint) {
        key.current = { fingerprint, value: createPublicIdempotencyKey() };
      }
      controller.current = new AbortController();
      const result = await submitPrivacyRequest({
        cardSlug,
        policyVersions: policies,
        input: fields,
        idempotencyKey: key.current.value,
        signal: controller.current.signal,
      });
      setStatus({ type: "success", id: result.id });
    } catch (error) {
      if (controller.current?.signal.aborted) return;
      if (error instanceof AssistantApiError && error.code === "POLICY_VERSION_MISMATCH") {
        try {
          await refreshPolicies();
        } catch {
          // A retry will request the latest version again.
        }
        key.current = null;
      }
      setStatus({
        type: "error",
        message: publicErrorMessage(error, "隐私请求提交失败，请稍后重试。"),
      });
    } finally {
      pending.current = false;
      controller.current = null;
    }
  };

  if (status.type === "success") {
    return (
      <div className="form-success" role="status">
        <CheckCircle size={40} weight="duotone" aria-hidden="true" />
        <h3>隐私请求已受理</h3>
        <p>企业将按照请求类型核验并处理，请保存下方受理编号。</p>
        <small>受理编号 {status.id}</small>
        <button className="button button-primary" type="button" onClick={onClose}>
          完成
        </button>
      </div>
    );
  }

  return (
    <form className="public-form" onSubmit={submit}>
      <label>
        <span>请求类型</span>
        <select
          value={fields.requestType}
          onChange={(event) => {
            setFields((current) => ({
              ...current,
              requestType: event.target.value as PrivacyRequestType,
            }));
            key.current = null;
            setStatus({ type: "idle" });
          }}
        >
          <option value="access">访问我的数据</option>
          <option value="correction">更正我的数据</option>
          <option value="deletion">删除我的数据</option>
          <option value="withdraw_consent">撤回授权</option>
        </select>
      </label>
      {fields.requestType === "withdraw_consent" && (
        <label>
          <span>撤回范围</span>
          <select
            value={fields.consentScope}
            onChange={(event) => {
              setFields((current) => ({
                ...current,
                consentScope: event.target.value as PrivacyFields["consentScope"],
              }));
              key.current = null;
            }}
          >
            <option value="lead_contact">联系与需求跟进授权</option>
            <option value="chat_notice">AI 对话告知授权</option>
          </select>
        </label>
      )}
      <label>
        <span>补充说明</span>
        <textarea
          rows={5}
          maxLength={4000}
          placeholder="可填写需要处理的数据范围或其他说明"
          value={fields.note}
          onChange={(event) => {
            setFields((current) => ({ ...current, note: event.target.value }));
            key.current = null;
            setStatus({ type: "idle" });
          }}
        />
      </label>
      <p className="form-note">
        请求与当前匿名访客会话关联。为保护数据安全，企业可能需要进一步核验身份。
      </p>
      {status.type === "error" && (
        <div className="form-error" role="alert">
          <ShieldCheck size={18} aria-hidden="true" />
          <span>{status.message}</span>
        </div>
      )}
      <button
        className="button button-primary form-submit"
        type="submit"
        disabled={status.type === "submitting"}
      >
        {status.type === "submitting" ? (
          <><SpinnerGap className="spin" size={18} aria-hidden="true" />正在提交</>
        ) : (
          <><ShieldCheck size={18} aria-hidden="true" />提交隐私请求</>
        )}
      </button>
    </form>
  );
}

function SharePanel({ card }: { card: PublicCardData }) {
  const shareUrl = useMemo(() => canonicalShareUrl(window.location), []);
  const [status, setStatus] = useState("");
  const canUseNativeShare = typeof navigator.share === "function";
  const qr = useMemo(() => {
    try {
      const matrix = encodeQrMatrix(shareUrl);
      return {
        path: qrPathData(matrix),
        size: matrix.length + 8,
      };
    } catch {
      return undefined;
    }
  }, [shareUrl]);

  const copy = () => {
    void copyText(shareUrl)
      .then(() => setStatus("链接已复制"))
      .catch(() => setStatus("复制失败，请长按链接复制"));
  };

  const share = () => {
    if (!canUseNativeShare) {
      copy();
      return;
    }
    void navigator
      .share({ title: card.title, text: card.company.summary, url: shareUrl })
      .then(() => setStatus("分享面板已打开"))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        copy();
      });
  };

  return (
    <div className="share-panel">
      <div className="qr-surface">
        {qr ? (
          <svg
            viewBox={`0 0 ${qr.size} ${qr.size}`}
            role="img"
            aria-label={`${card.company.name}名片二维码`}
            shapeRendering="crispEdges"
          >
            <title>{card.company.name}名片二维码</title>
            <rect width={qr.size} height={qr.size} fill="#ffffff" />
            <path d={qr.path} fill="#071017" />
          </svg>
        ) : (
          <div className="qr-unavailable">
            <QrCode size={36} aria-hidden="true" />
            <span>链接较长，请复制后分享</span>
          </div>
        )}
      </div>
      <div className="share-copy">
        <QrCode size={24} weight="duotone" aria-hidden="true" />
        <h3>让对方扫码打开</h3>
        <p>二维码在浏览器本地生成，不会把名片链接发送给第三方服务。</p>
        <code>{shareUrl}</code>
      </div>
      <div className="dialog-actions">
        <button className="button button-primary" type="button" onClick={share}>
          <ShareNetwork size={18} aria-hidden="true" />
          {canUseNativeShare ? "系统分享" : "复制分享链接"}
        </button>
        <button className="button button-secondary" type="button" onClick={copy}>
          <CopySimple size={18} aria-hidden="true" />
          复制链接
        </button>
      </div>
      <p className="share-status" aria-live="polite">{status}</p>
    </div>
  );
}

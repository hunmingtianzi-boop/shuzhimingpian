import {
  ArrowLeft,
  ArrowRight,
  Buildings,
  CalendarDots,
  CheckCircle,
  GraduationCap,
  Sparkle,
} from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  EnterpriseMockBusiness,
  EnterpriseMockFaq,
  EnterpriseMockIntent,
  EnterpriseMockVariantProps,
} from "./model";
import "./intent-enterprise-mock.css";

type IntentId = EnterpriseMockIntent["id"];

const intentMeta: Record<
  IntentId,
  {
    route: string;
    shortLabel: string;
    resultTitle: string;
    resultDescription: string;
    primaryAction: string;
    businessLabel: string;
    faqLabel: string;
    keywords: string[];
    icon: typeof GraduationCap;
  }
> = {
  talent: {
    route: "01",
    shortLabel: "青年人才",
    resultTitle: "找到一条真实的成长路径",
    resultDescription: "先看适合你的学习、组队和项目机会，再向 AI 接待员询问具体参与条件。",
    primaryAction: "咨询参与方式",
    businessLabel: "为你优先展示",
    faqLabel: "青年人才常问",
    keywords: ["人才", "学生", "青年", "学习", "训练", "成长", "就业", "组队", "项目"],
    icon: GraduationCap,
  },
  activity: {
    route: "02",
    shortLabel: "活动赛事",
    resultTitle: "快速判断活动是否适合你",
    resultDescription: "先了解活动形式、参与路径与成果边界，再决定报名、观摩或联合发起。",
    primaryAction: "询问活动详情",
    businessLabel: "活动相关内容",
    faqLabel: "参与者常问",
    keywords: ["活动", "赛事", "浙客松", "比赛", "训练营", "路演", "参与", "报名"],
    icon: CalendarDots,
  },
  enterprise: {
    route: "03",
    shortLabel: "企业合作",
    resultTitle: "从一个具体业务问题开始",
    resultDescription: "先看可落地的共创方式和相近实践，再提交需求，由团队继续对接。",
    primaryAction: "提交合作需求",
    businessLabel: "合作能力优先级",
    faqLabel: "合作方常问",
    keywords: ["企业", "合作", "场景", "共创", "落地", "开发", "咨询", "交付", "服务"],
    icon: Buildings,
  },
};

function rankByIntent<T>(
  items: T[],
  intentId: IntentId,
  getText: (item: T) => string,
) {
  const keywords = intentMeta[intentId].keywords;
  return items
    .map((item, index) => {
      const text = getText(item).toLowerCase();
      const score = keywords.reduce(
        (total, keyword) => total + (text.includes(keyword) ? 1 : 0),
        0,
      );
      return { item, index, score };
    })
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map(({ item }) => item);
}

function businessText(item: EnterpriseMockBusiness) {
  return [item.eyebrow, item.title, item.summary, item.detail, item.audience].join(" ");
}

function faqText(item: EnterpriseMockFaq) {
  return [item.question, item.answer].join(" ");
}

export function IntentEnterpriseMock({
  content,
  onAssistant,
  onLead,
}: EnterpriseMockVariantProps) {
  const [selectedIntent, setSelectedIntent] = useState<IntentId | null>(null);
  const landingTitleRef = useRef<HTMLHeadingElement>(null);
  const resultTitleRef = useRef<HTMLHeadingElement>(null);

  const selected = useMemo(
    () => content.intents.find((intent) => intent.id === selectedIntent),
    [content.intents, selectedIntent],
  );

  const rankedBusinesses = useMemo(
    () =>
      selectedIntent
        ? rankByIntent(content.businesses, selectedIntent, businessText)
        : content.businesses,
    [content.businesses, selectedIntent],
  );

  const rankedFaqs = useMemo(
    () =>
      selectedIntent
        ? rankByIntent(content.faqs, selectedIntent, faqText)
        : content.faqs,
    [content.faqs, selectedIntent],
  );

  useEffect(() => {
    if (selectedIntent) {
      resultTitleRef.current?.focus();
    }
  }, [selectedIntent]);

  function returnToIntentChoice() {
    setSelectedIntent(null);
    requestAnimationFrame(() => landingTitleRef.current?.focus());
  }

  if (!selected || !selectedIntent) {
    return (
      <main className="em-site em-intent em-intent--landing">
        <header className="emi-header" aria-label="企业名片页眉">
          <a className="emi-brand" href={content.websiteUrl} target="_blank" rel="noreferrer">
            <img src={content.logoUrl} alt={content.logoAlt} />
            <span>
              <strong>{content.companyName}</strong>
              <small>{content.descriptor}</small>
            </span>
          </a>
          <span className="emi-verified"><CheckCircle weight="fill" /> 资料已核验</span>
        </header>

        <div className="emi-landing-layout">
          <section className="emi-intro" aria-labelledby="emi-landing-title">
            <p className="emi-kicker">企业官方数智名片</p>
            <h1 id="emi-landing-title" ref={landingTitleRef} tabIndex={-1}>
              你今天想从这里
              <span>找到什么？</span>
            </h1>
            <p className="emi-intro-copy">
              选择你的来访目的，我们只把此刻相关的业务、案例和问题排到前面。
            </p>
            <div className="emi-company-note">
              <span>{content.companyName}</span>
              <p>{content.companySummary}</p>
            </div>
          </section>

          <nav className="emi-route-board" aria-label="选择来访目的">
            <p className="emi-route-board__label">选择一条访问路线</p>
            {content.intents.map((intent) => {
              const meta = intentMeta[intent.id];
              const Icon = meta.icon;
              return (
                <button
                  className="emi-route"
                  key={intent.id}
                  type="button"
                  onClick={() => setSelectedIntent(intent.id)}
                >
                  <span className="emi-route__number">{meta.route}</span>
                  <span className="emi-route__content">
                    <span className="emi-route__eyebrow"><Icon aria-hidden="true" /> {intent.eyebrow}</span>
                    <strong>{intent.title}</strong>
                    <small>{intent.description}</small>
                  </span>
                  <ArrowRight className="emi-route__arrow" aria-hidden="true" />
                </button>
              );
            })}
            <button
              className="emi-ask-direct"
              type="button"
              onClick={() => onAssistant("请先介绍一下你们，并帮我判断应该从哪里开始了解。")}
            >
              <Sparkle weight="fill" aria-hidden="true" />
              不确定？让 AI 接待员帮你判断
            </button>
          </nav>
        </div>

        <footer className="emi-landing-footer">
          <span>{content.publishedLabel}</span>
          <span>内容有来源 · AI 回答受控</span>
        </footer>
      </main>
    );
  }

  const meta = intentMeta[selectedIntent];
  const SelectedIcon = meta.icon;
  const topBusinesses = rankedBusinesses.slice(0, 3);
  const topFaqs = rankedFaqs.slice(0, 3);
  const featuredCase = content.cases[0];

  return (
    <main className={`em-site em-intent em-intent--result emi-theme-${selectedIntent}`}>
      <header className="emi-result-header">
        <button className="emi-back" type="button" onClick={returnToIntentChoice}>
          <ArrowLeft aria-hidden="true" />
          重新选择
        </button>
        <a className="emi-result-brand" href={content.websiteUrl} target="_blank" rel="noreferrer">
          <img src={content.logoUrl} alt="" />
          <span>{content.companyName}</span>
        </a>
      </header>

      <nav className="emi-switcher" aria-label="切换来访目的">
        {content.intents.map((intent) => (
          <button
            key={intent.id}
            type="button"
            aria-pressed={intent.id === selectedIntent}
            onClick={() => setSelectedIntent(intent.id)}
          >
            <span>{intentMeta[intent.id].route}</span>
            {intentMeta[intent.id].shortLabel}
          </button>
        ))}
      </nav>

      <section className="emi-result-hero" aria-labelledby="emi-result-title">
        <div className="emi-result-hero__route" aria-hidden="true">
          <SelectedIcon />
          <span>ROUTE {meta.route}</span>
        </div>
        <div className="emi-result-hero__copy">
          <p>{selected.eyebrow}</p>
          <h1 id="emi-result-title" ref={resultTitleRef} tabIndex={-1}>{meta.resultTitle}</h1>
          <span>{meta.resultDescription}</span>
        </div>
        <div className="emi-result-hero__actions">
          {selectedIntent === "enterprise" ? (
            <button className="emi-action emi-action--light" type="button" onClick={onLead}>
              {meta.primaryAction}<ArrowRight aria-hidden="true" />
            </button>
          ) : (
            <button
              className="emi-action emi-action--light"
              type="button"
              onClick={() => onAssistant(selected.assistantQuestion)}
            >
              {meta.primaryAction}<ArrowRight aria-hidden="true" />
            </button>
          )}
          <button
            className="emi-action emi-action--quiet"
            type="button"
            onClick={() => onAssistant(selected.assistantQuestion)}
          >
            问 AI 接待员
          </button>
        </div>
      </section>

      <div className="emi-result-body">
        <section className="emi-priority" aria-labelledby="emi-business-title">
          <div className="emi-section-heading">
            <p>{meta.businessLabel}</p>
            <h2 id="emi-business-title">先看这三项</h2>
            <span>内容顺序已按你的目的调整</span>
          </div>
          <div className="emi-business-list">
            {topBusinesses.map((business, index) => (
              <article className={index === 0 ? "emi-business emi-business--first" : "emi-business"} key={business.id}>
                <span className="emi-business__index">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <p>{business.eyebrow}</p>
                  <h3>{business.title}</h3>
                  <span>{business.summary}</span>
                  {index === 0 && <small>适合：{business.audience}</small>}
                </div>
                <button type="button" onClick={() => onAssistant(`请详细介绍“${business.title}”。`)}>
                  了解详情<ArrowRight aria-hidden="true" />
                </button>
              </article>
            ))}
          </div>
        </section>

        {featuredCase && (
          <section className="emi-proof" aria-labelledby="emi-proof-title">
            <div className="emi-proof__eyebrow">一个可复核的实践</div>
            <h2 id="emi-proof-title">{featuredCase.title}</h2>
            <p>{featuredCase.summary}</p>
            <strong>{featuredCase.result}</strong>
          </section>
        )}

        <section className="emi-faq" aria-labelledby="emi-faq-title">
          <div className="emi-section-heading">
            <p>{meta.faqLabel}</p>
            <h2 id="emi-faq-title">先回答三个问题</h2>
          </div>
          <div className="emi-faq-list">
            {topFaqs.map((faq, index) => (
              <details key={faq.id} open={index === 0}>
                <summary>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  {faq.question}
                  <span className="emi-faq-toggle" aria-hidden="true">＋</span>
                </summary>
                <div>
                  <p>{faq.answer}</p>
                  <small>来源：{faq.source}</small>
                </div>
              </details>
            ))}
          </div>
          <button
            className="emi-text-action"
            type="button"
            onClick={() => onAssistant(selected.assistantQuestion)}
          >
            还有问题，直接问 AI 接待员<ArrowRight aria-hidden="true" />
          </button>
        </section>

        <section className="emi-final-action" aria-label="下一步行动">
          <p>已经找到方向？</p>
          <h2>{selectedIntent === "enterprise" ? "把具体问题交给我们继续对接。" : "现在就问清参与条件与下一步。"}</h2>
          <div>
            <button
              className="emi-action emi-action--dark"
              type="button"
              onClick={selectedIntent === "enterprise" ? onLead : () => onAssistant(selected.assistantQuestion)}
            >
              {meta.primaryAction}<ArrowRight aria-hidden="true" />
            </button>
            <button className="emi-change-route" type="button" onClick={returnToIntentChoice}>
              换一条访问路线
            </button>
          </div>
        </section>

        <footer className="emi-result-footer">
          <a href={content.websiteUrl} target="_blank" rel="noreferrer">访问企业官网</a>
          <p>{content.sourceLabel}</p>
        </footer>
      </div>
    </main>
  );
}

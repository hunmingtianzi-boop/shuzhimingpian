import {
  ArrowRight,
  ArrowUpRight,
  Briefcase,
  CalendarBlank,
  CaretDown,
  ChatCenteredDots,
  CheckCircle,
  GlobeHemisphereWest,
  UsersThree,
} from "@phosphor-icons/react";

import type { EnterpriseMockVariantProps } from "./model";
import "./summary-enterprise-mock.css";

const intentIcons = {
  talent: UsersThree,
  activity: CalendarBlank,
  enterprise: Briefcase,
} as const;

export function SummaryEnterpriseMock({
  content,
  onAssistant,
  onLead,
}: EnterpriseMockVariantProps) {
  const featuredBusinesses = content.businesses.slice(0, 3);
  const featuredCase = content.cases[0];
  const featuredFaqs = content.faqs.slice(0, 3);

  return (
    <main className="summary-mock">
      <header className="summary-mock__header">
        <a className="summary-mock__brand" href="#summary-top" aria-label={`${content.companyName}，返回顶部`}>
          <span className="summary-mock__logo-shell">
            <img src={content.logoUrl} alt={content.logoAlt} />
          </span>
          <span>
            <strong>{content.companyName}</strong>
            <small>企业官方名片</small>
          </span>
        </a>
        <span className="summary-mock__verified">
          <CheckCircle weight="fill" aria-hidden="true" />
          已认证
        </span>
      </header>

      <section className="summary-mock__hero" id="summary-top" aria-labelledby="summary-title">
        <div className="summary-mock__hero-copy">
          <p className="summary-mock__eyebrow">{content.descriptor}</p>
          <h1 id="summary-title">把 AI 能力带进真实的学习、项目与产业现场。</h1>
          <p className="summary-mock__intro">{content.companySummary}</p>
          <div className="summary-mock__actions" aria-label="主要操作">
            <button className="em-primary-action" type="button" onClick={() => onAssistant()}>
              <ChatCenteredDots weight="bold" aria-hidden="true" />
              咨询企业 AI
            </button>
            <button className="em-secondary-action" type="button" onClick={onLead}>
              提交合作需求
              <ArrowRight weight="bold" aria-hidden="true" />
            </button>
          </div>
        </div>

        <aside className="summary-mock__proof" aria-label="企业资料状态">
          <span className="summary-mock__proof-mark" aria-hidden="true">拓</span>
          <div>
            <span className="summary-mock__proof-label">可信资料</span>
            <strong>{content.publishedLabel}</strong>
            <p>{content.sourceLabel}</p>
          </div>
        </aside>
      </section>

      <section className="summary-mock__section summary-mock__intent-section" aria-labelledby="summary-intent-title">
        <div className="summary-mock__section-heading">
          <p className="summary-mock__kicker">从你的目标出发</p>
          <h2 id="summary-intent-title">你这次想了解什么？</h2>
        </div>
        <div className="summary-mock__intent-list">
          {content.intents.map((intent, index) => {
            const IntentIcon = intentIcons[intent.id];
            return (
              <button
                className="summary-mock__intent"
                type="button"
                key={intent.id}
                onClick={() => onAssistant(intent.assistantQuestion)}
              >
                <span className="summary-mock__intent-index">0{index + 1}</span>
                <span className="summary-mock__intent-icon" aria-hidden="true">
                  <IntentIcon weight="regular" />
                </span>
                <span className="summary-mock__intent-copy">
                  <small>{intent.eyebrow}</small>
                  <strong>{intent.title}</strong>
                  <span>{intent.description}</span>
                </span>
                <ArrowUpRight className="summary-mock__intent-arrow" weight="bold" aria-hidden="true" />
              </button>
            );
          })}
        </div>
      </section>

      <section className="summary-mock__section summary-mock__business" aria-labelledby="summary-business-title">
        <div className="summary-mock__section-heading summary-mock__section-heading--row">
          <div>
            <p className="summary-mock__kicker">能力概览</p>
            <h2 id="summary-business-title">核心业务</h2>
          </div>
          <span className="summary-mock__section-note">先看摘要，需要时再展开</span>
        </div>

        <div className="summary-mock__business-list">
          {featuredBusinesses.map((business, index) => (
            <details className="summary-mock__business-item" key={business.id}>
              <summary>
                <span className="summary-mock__business-number">{String(index + 1).padStart(2, "0")}</span>
                <span className="summary-mock__business-copy">
                  <small>{business.eyebrow}</small>
                  <strong>{business.title}</strong>
                  <span>{business.summary}</span>
                </span>
                <span className="summary-mock__detail-trigger">
                  详情
                  <CaretDown weight="bold" aria-hidden="true" />
                </span>
              </summary>
              <div className="summary-mock__business-detail">
                <p>{business.detail}</p>
                <span>适合：{business.audience}</span>
                <button type="button" onClick={() => onAssistant(`请介绍${business.title}的合作方式`)}>
                  就这项业务咨询 AI
                  <ArrowRight weight="bold" aria-hidden="true" />
                </button>
              </div>
            </details>
          ))}
        </div>
      </section>

      {featuredCase ? (
        <section className="summary-mock__case" aria-labelledby="summary-case-title">
          <div className="summary-mock__case-meta">
            <p className="summary-mock__kicker">代表案例</p>
            <span>01 / {String(Math.max(content.cases.length, 1)).padStart(2, "0")}</span>
          </div>
          <div className="summary-mock__case-layout">
            <h2 id="summary-case-title">{featuredCase.title}</h2>
            <div className="summary-mock__case-story">
              <p>{featuredCase.summary}</p>
              <div>
                <small>阶段成果</small>
                <strong>{featuredCase.result}</strong>
              </div>
            </div>
          </div>
        </section>
      ) : null}

      <section className="summary-mock__section summary-mock__faq" aria-labelledby="summary-faq-title">
        <div className="summary-mock__section-heading summary-mock__section-heading--row">
          <div>
            <p className="summary-mock__kicker">快速确认</p>
            <h2 id="summary-faq-title">常见问题</h2>
          </div>
          <button className="summary-mock__text-action" type="button" onClick={() => onAssistant("我还有其他问题") }>
            直接问 AI
            <ArrowUpRight weight="bold" aria-hidden="true" />
          </button>
        </div>
        <div className="summary-mock__faq-list">
          {featuredFaqs.map((faq, index) => (
            <details className="summary-mock__faq-item" key={faq.id} open={index === 0 ? true : undefined}>
              <summary>
                <span>{faq.question}</span>
                <CaretDown weight="bold" aria-hidden="true" />
              </summary>
              <div className="summary-mock__faq-answer">
                <p>{faq.answer}</p>
                <small>来源：{faq.source}</small>
              </div>
            </details>
          ))}
        </div>
      </section>

      <footer className="summary-mock__footer">
        <div className="summary-mock__footer-brand">
          <span className="summary-mock__footer-monogram">拓</span>
          <div>
            <strong>{content.companyName}</strong>
            <span>克制承诺，真实交付。</span>
          </div>
        </div>
        <a href={content.websiteUrl} target="_blank" rel="noreferrer">
          <GlobeHemisphereWest aria-hidden="true" />
          访问企业官网
          <ArrowUpRight weight="bold" aria-hidden="true" />
        </a>
        <p>{content.sourceLabel}</p>
      </footer>

      <nav className="summary-mock__mobile-action" aria-label="移动端主要操作">
        <button type="button" onClick={() => onAssistant()}>
          <ChatCenteredDots weight="bold" aria-hidden="true" />
          咨询 AI
        </button>
        <button type="button" onClick={onLead}>合作需求</button>
      </nav>
    </main>
  );
}

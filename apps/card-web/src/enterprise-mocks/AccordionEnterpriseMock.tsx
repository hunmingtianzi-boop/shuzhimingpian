import type { EnterpriseMockVariantProps } from "./model";

import "./enterprise-mock-base.css";
import "./accordion-enterprise-mock.css";

const navigation = [
  { href: "#accordion-overview", label: "概览" },
  { href: "#accordion-business", label: "业务" },
  { href: "#accordion-cases", label: "案例" },
  { href: "#accordion-faq", label: "问答" },
];

export function AccordionEnterpriseMock({
  content,
  onAssistant,
  onLead,
}: EnterpriseMockVariantProps) {
  return (
    <main className="em-site em-accordion" id="accordion-overview">
      <header className="em-accordion__masthead">
        <a className="em-accordion__identity" href="#accordion-overview">
          <img
            className="em-accordion__logo"
            src={content.logoUrl}
            alt={content.logoAlt}
          />
          <span>
            <strong>{content.companyName}</strong>
            <small>企业官方名片</small>
          </span>
        </a>
        <span className="em-accordion__status">
          <span aria-hidden="true" />
          {content.publishedLabel}
        </span>
      </header>

      <section className="em-accordion__hero" aria-labelledby="accordion-title">
        <div className="em-accordion__hero-copy">
          <p className="em-accordion__kicker">企业简报 · 单页阅览</p>
          <h1 id="accordion-title">{content.companyName}</h1>
          <p className="em-accordion__descriptor">{content.descriptor}</p>
          <p className="em-accordion__summary">{content.companySummary}</p>
          <div className="em-accordion__hero-actions">
            <button
              className="em-primary-action"
              type="button"
              onClick={() => onAssistant()}
            >
              咨询企业 AI
              <span aria-hidden="true">↗</span>
            </button>
            <button
              className="em-secondary-action"
              type="button"
              onClick={onLead}
            >
              提交合作需求
            </button>
          </div>
        </div>

        <dl className="em-accordion__metrics" aria-label="企业数据概览">
          {content.metrics.slice(0, 3).map((metric) => (
            <div key={`${metric.value}-${metric.label}`}>
              <dt>{metric.label}</dt>
              <dd>{metric.value}</dd>
              <p>{metric.note}</p>
            </div>
          ))}
        </dl>
      </section>

      <nav className="em-accordion__nav" aria-label="企业页面分段导航">
        <div>
          {navigation.map((item, index) => (
            <a href={item.href} key={item.href}>
              <span aria-hidden="true">0{index + 1}</span>
              {item.label}
            </a>
          ))}
        </div>
      </nav>

      <div className="em-accordion__content">
        <section
          className="em-accordion__section"
          id="accordion-business"
          aria-labelledby="accordion-business-title"
        >
          <div className="em-accordion__section-heading">
            <div>
              <p>What we do</p>
              <h2 id="accordion-business-title">核心业务</h2>
            </div>
            <p>
              先读每项的一句话摘要，需要时再展开服务边界与适用对象。
            </p>
          </div>

          <div className="em-accordion__disclosures">
            {content.businesses.map((business, index) => (
              <details className="em-accordion__disclosure" key={business.id}>
                <summary>
                  <span className="em-accordion__index" aria-hidden="true">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="em-accordion__summary-copy">
                    <small>{business.eyebrow}</small>
                    <strong>{business.title}</strong>
                    <span>{business.summary}</span>
                  </span>
                  <span className="em-accordion__toggle" aria-hidden="true" />
                </summary>
                <div className="em-accordion__detail">
                  <p>{business.detail}</p>
                  <dl>
                    <dt>适合谁</dt>
                    <dd>{business.audience}</dd>
                  </dl>
                  <button
                    type="button"
                    onClick={() =>
                      onAssistant(`请介绍“${business.title}”的合作方式。`)
                    }
                  >
                    针对这项业务提问
                    <span aria-hidden="true">→</span>
                  </button>
                </div>
              </details>
            ))}
          </div>
        </section>

        <section
          className="em-accordion__section"
          id="accordion-cases"
          aria-labelledby="accordion-cases-title"
        >
          <div className="em-accordion__section-heading">
            <div>
              <p>Selected work</p>
              <h2 id="accordion-cases-title">代表案例</h2>
            </div>
            <p>成果先行，展开后查看对应方案与阶段结果。</p>
          </div>

          <div className="em-accordion__case-list">
            {content.cases.map((item, index) => (
              <details className="em-accordion__case" key={item.id}>
                <summary>
                  <span className="em-accordion__case-number" aria-hidden="true">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span>
                    <strong>{item.title}</strong>
                    <small>查看案例摘要</small>
                  </span>
                  <span className="em-accordion__toggle" aria-hidden="true" />
                </summary>
                <div className="em-accordion__case-detail">
                  <div>
                    <small>解决方案</small>
                    <p>{item.summary}</p>
                  </div>
                  <div>
                    <small>阶段结果</small>
                    <p>{item.result}</p>
                  </div>
                </div>
              </details>
            ))}
          </div>
        </section>

        <section
          className="em-accordion__section em-accordion__section--faq"
          id="accordion-faq"
          aria-labelledby="accordion-faq-title"
        >
          <div className="em-accordion__section-heading">
            <div>
              <p>Questions</p>
              <h2 id="accordion-faq-title">常见问题</h2>
            </div>
            <p>答案来自已发布企业资料；复杂问题可继续交给企业 AI。</p>
          </div>

          <div className="em-accordion__faq-list">
            {content.faqs.map((faq, index) => (
              <details className="em-accordion__faq" key={faq.id}>
                <summary>
                  <span aria-hidden="true">Q{String(index + 1).padStart(2, "0")}</span>
                  <strong>{faq.question}</strong>
                  <span className="em-accordion__toggle" aria-hidden="true" />
                </summary>
                <div className="em-accordion__faq-answer">
                  <p>{faq.answer}</p>
                  <small>资料来源：{faq.source}</small>
                  <button type="button" onClick={() => onAssistant(faq.question)}>
                    继续追问
                    <span aria-hidden="true">→</span>
                  </button>
                </div>
              </details>
            ))}
          </div>
        </section>

        <footer className="em-accordion__footer">
          <div>
            <strong>{content.companyName}</strong>
            <p>{content.sourceLabel}</p>
          </div>
          <a href={content.websiteUrl} target="_blank" rel="noreferrer">
            访问企业官网
            <span aria-hidden="true">↗</span>
          </a>
        </footer>
      </div>

      <aside className="em-accordion__action-bar" aria-label="企业联系操作">
        <p>
          <span>有具体问题？</span>
          AI 会根据公开资料回答
        </p>
        <div>
          <button type="button" onClick={() => onAssistant()}>
            咨询 AI
          </button>
          <button type="button" onClick={onLead}>
            提交合作需求
          </button>
        </div>
      </aside>
    </main>
  );
}

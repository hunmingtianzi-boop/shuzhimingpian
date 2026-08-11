import type { KeyboardEvent } from "react";

export type StudioCollectionItem = Record<string, unknown>;

type CollectionProps = {
  items: StudioCollectionItem[];
  layout?: string;
  onOpenItem?: (item: StudioCollectionItem) => void;
};

function activateOnKeyboard(event: KeyboardEvent<HTMLElement>, action?: () => void) {
  if (!action || (event.key !== "Enter" && event.key !== " ")) return;
  event.preventDefault();
  action();
}

export function StudioServiceCollection({ items, layout = "auto", onOpenItem }: CollectionProps) {
  if (!items.length) return <div className="empty-state"><strong>产品与服务待补充</strong><p>发布业务资料后会自动出现在这里。</p></div>;
  const density = items.length <= 1 ? "single" : items.length === 2 ? "pair" : "many";
  return <div className={`service-grid cpr-product-list cpr-product-list--${density} count-${items.length} layout-${layout}`}>
    {items.map((item, index) => {
      const open = onOpenItem ? () => onOpenItem(item) : undefined;
      const imageUrl = typeof item.imageUrl === "string" && item.imageUrl ? item.imageUrl : undefined;
      return <article className={`service-card ${imageUrl ? "has-media" : "text-only"}`} key={String(item.id || index)} role={open ? "button" : undefined} tabIndex={open ? 0 : undefined} onClick={open} onKeyDown={(event) => activateOnKeyboard(event, open)}>
        {imageUrl ? <div className="service-visual"><img src={imageUrl} alt={`${String(item.title || item.name || "业务")}展示图`}/></div> : null}
        <span className="service-index">{String(index + 1).padStart(2, "0")}</span>
        <div className="service-copy">{item.category ? <span className="service-category">{String(item.category)}</span> : null}<h3>{String(item.title || item.name || "未命名业务")}</h3>{item.summary ? <p>{String(item.summary)}</p> : null}</div>
        <span className="service-arrow" aria-label={String(item.ctaLabel || "查看业务")}>→</span>
      </article>;
    })}
  </div>;
}

export function StudioCaseCollection({ items, layout = "featured", onOpenItem }: CollectionProps) {
  if (!items.length) return <div className="empty-state"><strong>代表案例待补充</strong><p>案例确认公开范围后会显示在这里。</p></div>;
  const density = items.length <= 1 ? "single" : items.length === 2 ? "pair" : "many";
  return <div className={`case-collection cpr-case-list cpr-case-list--${density} layout-${layout}`}>
    {items.map((item, index) => {
      const metrics = Array.isArray(item.metrics) ? item.metrics as Array<{ value?: unknown; label?: unknown }> : [];
      const resultItems = metrics.length ? metrics.map((metric) => [metric.value, metric.label] as [unknown, unknown]) : [];
      const open = onOpenItem ? () => onOpenItem(item) : undefined;
      const hasImage = Boolean(item.imageUrl);
      const caseNumber = String(index + 1).padStart(2, "0");
      return <article className={`case-story ${index === 0 && items.length > 1 ? "case-story--lead" : "case-story--secondary"} ${hasImage ? "case-story--media" : "case-story--text-only"}`} key={String(item.id || index)} role={open ? "button" : undefined} tabIndex={open ? 0 : undefined} onClick={open} onKeyDown={(event) => activateOnKeyboard(event, open)}>
        {hasImage ? <div className="case-media"><img className="case-cover" src={String(item.imageUrl)} alt={`${String(item.title || "案例")}案例封面`}/><span className="case-index">{caseNumber}</span></div> : null}
        <div className="case-body">
          <div className="case-meta">{!hasImage ? <span className="case-text-index">CASE {caseNumber}</span> : null}<span className="case-chip">{String(item.industry || "公开案例")}</span>{item.clientName ? <span>{String(item.clientName)}</span> : null}</div>
          <h3>{String(item.title || "未命名案例")}</h3>
          {item.summary || item.solution ? <p>{String(item.summary || item.solution)}</p> : null}
          {resultItems.length ? <div className="case-results">{resultItems.slice(0, 3).map(([value, label], resultIndex) => <div key={resultIndex}><strong>{String(value)}</strong><span>{String(label)}</span></div>)}</div> : null}
          <button className="case-link" type="button" onClick={(event) => { event.stopPropagation(); onOpenItem?.(item); }}>{String(item.ctaLabel || "查看案例")} <span>→</span></button>
        </div>
      </article>;
    })}
  </div>;
}

export function StudioGallery({ items, layout = "mosaic", title }: { items: Array<{ id: string; imageUrl: string; title?: string; description?: string; timeLabel?: string; periodLabel?: string; badgeMode?: "title" | "time" | "period" | "custom" | "none"; badgeText?: string; altText?: string; linkUrl?: string }>; layout?: string; title: string }) {
  if (!items.length) return <div className="empty-state"><strong>展示图片待上传</strong><p>添加图片后会按数量自动编排。</p></div>;
  const density = items.length <= 1 ? "single" : items.length === 2 ? "pair" : "many";
  return <div className={`gallery-grid cpr-gallery cpr-gallery--${density} layout-${layout}`}>
    {items.map((item, index) => {
      const badge = item.badgeMode === "none" ? "" : item.badgeMode === "time" ? item.timeLabel : item.badgeMode === "period" ? item.periodLabel : item.badgeMode === "custom" ? item.badgeText : item.title;
      const figure = <figure><img src={item.imageUrl} alt={item.altText || item.title || `${title} ${index + 1}`}/>{badge ? <figcaption><span>{badge}</span></figcaption> : null}{item.description ? <p>{item.description}</p> : null}</figure>;
      return item.linkUrl ? <a className="gallery-link" href={item.linkUrl} key={item.id}>{figure}</a> : <div className="gallery-link" key={item.id}>{figure}</div>;
    })}
  </div>;
}

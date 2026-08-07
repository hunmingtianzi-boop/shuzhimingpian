import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  CardPageBlocksRenderer,
  deriveCardPageDirectory,
  orderVisibleCardPageBlocks,
} from "./CardPageBlocksRenderer";
import "./styles.css";

export type CardPageBlockType =
  | "identity"
  | "rich_text"
  | "business_collection"
  | "image_gallery"
  | "video_link"
  | "case_collection"
  | "trust_panel"
  | "faq"
  | "cta"
  | "ai_assistant";

export type CardPageIdentity = {
  kind: "enterprise" | "employee";
  name: string;
  headline?: string;
  summary?: string;
  imageUrl?: string;
  companyName?: string;
  verificationLabel?: string;
  positioning?: string;
  meta?: string[];
  tags?: string[];
};

export type CardPageProduct = {
  id: string;
  slug?: string;
  name: string;
  category?: string;
  summary?: string;
  imageUrl?: string;
};

export type CardPageCase = {
  id: string;
  slug?: string;
  title: string;
  industry?: string;
  summary?: string;
  result?: string;
  imageUrl?: string;
};

export type CardPageFaqItem = {
  id: string;
  documentId?: string;
  question: string;
  answer: string;
  sourceLabel?: string;
};

export type CardPageBlock = {
  id: string;
  type: CardPageBlockType;
  title?: string;
  body?: string;
  visible?: boolean;
  directoryEnabled?: boolean;
  sortOrder?: number;
  imageUrls?: string[];
  videoUrl?: string;
  videoCoverUrl?: string;
  productIds?: string[];
  productItems?: CardPageProduct[];
  caseIds?: string[];
  caseItems?: CardPageCase[];
  faqMode?: "all_published" | "selected";
  faqDocumentIds?: string[];
  ctaLabel?: string;
  ctaUrl?: string;
};

export type CardPageResolvedData = {
  identity?: CardPageIdentity;
  products?: CardPageProduct[];
  cases?: CardPageCase[];
  faqItems?: CardPageFaqItem[];
};

export type CardPageExperienceActions = {
  onOpenProduct?: (item: CardPageProduct) => void;
  onOpenCase?: (item: CardPageCase) => void;
  onAssistant?: (question?: string) => void;
};

export type CardPageEditorAdapter = {
  selectedBlockId?: string | null;
  onSelectBlock?: (blockId: string) => void;
  renderBlockHandle?: (block: CardPageBlock) => ReactNode;
  getBlockClassName?: (block: CardPageBlock) => string | undefined;
};

export type CardPageDirectoryOptions = {
  ariaLabel?: string;
  onNavigate?: (blockId: string) => void;
};

export type CardPageExperienceProps = {
  blocks: CardPageBlock[];
  data?: CardPageResolvedData;
  actions?: CardPageExperienceActions;
  identityContent?: ReactNode;
  directory?: boolean | CardPageDirectoryOptions;
  resolveResourceUrl?: (url: string) => string;
  editorAdapter?: CardPageEditorAdapter;
  className?: string;
};

const blockSelector = {
  getId: (block: CardPageBlock) => block.id,
  getSortOrder: (block: CardPageBlock) => block.sortOrder ?? 0,
  // Identity is a required source-projected block: it participates in ordering,
  // but a malformed/legacy snapshot must never make the card subject disappear.
  isVisible: (block: CardPageBlock) => block.type === "identity" || block.visible !== false,
};

export function safeCardPageExternalUrl(value?: string) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : undefined;
  } catch {
    return undefined;
  }
}

function quantityClass(count: number) {
  if (count <= 1) return "single";
  if (count === 2) return "pair";
  return "many";
}

function resolveReferencedItems<T extends { id: string }>(
  embedded: T[] | undefined,
  ids: string[] | undefined,
  available: T[],
) {
  if (embedded !== undefined) return embedded;
  if (!ids?.length) return available;
  const byId = new Map(available.map((item) => [item.id, item]));
  return ids.flatMap((id) => {
    const item = byId.get(id);
    return item ? [item] : [];
  });
}

export function resolveCardPageFaqItems(
  block: Pick<CardPageBlock, "faqMode" | "faqDocumentIds">,
  faqItems: CardPageFaqItem[],
) {
  if (block.faqMode !== "selected") return faqItems;
  const byDocumentId = new Map<string, CardPageFaqItem>();
  faqItems.forEach((item) => {
    byDocumentId.set(item.documentId || item.id, item);
  });
  return (block.faqDocumentIds ?? []).flatMap((documentId) => {
    const item = byDocumentId.get(documentId);
    return item ? [item] : [];
  });
}

function initials(name: string) {
  const compact = name.trim().replace(/\s+/g, "");
  return compact.slice(0, Math.min(2, compact.length)).toUpperCase() || "名片";
}

function IdentityBlock({
  identity,
  resolveResourceUrl,
}: {
  identity?: CardPageIdentity;
  resolveResourceUrl: (url: string) => string;
}) {
  if (!identity) {
    return (
      <div className="cpr-empty cpr-identity-empty">
        <strong>基础名片信息待同步</strong>
        <p>选择企业或企业员工后，这里会自动读取身份资料。</p>
      </div>
    );
  }

  const meta = (identity.meta ?? []).filter(Boolean);
  return (
    <div className={`cpr-identity cpr-identity--${identity.kind}`}>
      <div className="cpr-identity-portrait">
        {identity.imageUrl ? (
          <img
            src={resolveResourceUrl(identity.imageUrl)}
            alt={identity.kind === "employee" ? `${identity.name}的职业头像` : `${identity.name}标识`}
          />
        ) : (
          <span aria-label={`${identity.name}的名称缩写`}>{initials(identity.name)}</span>
        )}
      </div>
      <div className="cpr-identity-copy">
        <div className="cpr-identity-name-row">
          <h1>{identity.name}</h1>
          {identity.verificationLabel && <b>{identity.verificationLabel}</b>}
        </div>
        {identity.headline && <p className="cpr-identity-headline">{identity.headline}</p>}
        {identity.companyName && <p className="cpr-identity-company">{identity.companyName}</p>}
        {identity.summary && <p className="cpr-identity-summary">{identity.summary}</p>}
        {meta.length > 0 && <small className="cpr-identity-meta">{meta.join(" · ")}</small>}
        {identity.tags?.length ? (
          <div className="cpr-tags" aria-label="名片标签">
            {identity.tags.map((tag) => <span key={tag}>{tag}</span>)}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SectionHeading({ block }: { block: CardPageBlock }) {
  if (!block.title) return null;
  return (
    <div className="bp-section-title cpr-section-title">
      <h2>{block.title}</h2>
    </div>
  );
}

function isOverviewBlock(block: CardPageBlock) {
  return block.type === "rich_text" && (
    block.id === "overview"
    || block.id.endsWith("-overview")
    || block.title?.trim() === "概览"
  );
}

function directoryTitle(block: CardPageBlock) {
  const title = block.title?.trim();
  if (block.type === "rich_text") {
    if (isOverviewBlock(block)) return "概览";
    if (title === "企业介绍" || title === "个人介绍") return "介绍";
    return title;
  }
  const compactTitles: Partial<Record<CardPageBlockType, string>> = {
    identity: "名片",
    business_collection: "业务",
    image_gallery: "图片",
    video_link: "视频",
    case_collection: "案例",
    trust_panel: "资料",
    faq: "问答",
    cta: "联系",
    ai_assistant: "AI",
  };
  return compactTitles[block.type] || title;
}

function ProductCollection({
  items,
  onOpen,
  resolveResourceUrl,
}: {
  items: CardPageProduct[];
  onOpen?: (item: CardPageProduct) => void;
  resolveResourceUrl: (url: string) => string;
}) {
  if (!items.length) {
    return <div className="cpr-empty"><strong>产品与服务待补充</strong><p>发布业务资料后会自动出现在这里。</p></div>;
  }
  const size = quantityClass(items.length);
  return (
    <div className={`cpr-product-list cpr-product-list--${size}`} data-item-count={items.length}>
      {items.map((item, index) => {
        const content = (
          <>
            {item.imageUrl && <img src={resolveResourceUrl(item.imageUrl)} alt="" loading="lazy" />}
            <span className="cpr-item-index" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
            <div className="cpr-product-copy">
              <small>{item.category || "产品与服务"}</small>
              <strong>{item.name}</strong>
              {item.summary && <p>{item.summary}</p>}
              {onOpen && <span className="cpr-item-link">查看详情 <i aria-hidden="true">→</i></span>}
            </div>
          </>
        );
        return onOpen ? (
          <button className="cpr-product-item" type="button" key={item.id} onClick={() => onOpen(item)}>
            {content}
          </button>
        ) : (
          <div className="cpr-product-item" key={item.id}>{content}</div>
        );
      })}
    </div>
  );
}

function CaseCollection({
  items,
  onOpen,
  resolveResourceUrl,
}: {
  items: CardPageCase[];
  onOpen?: (item: CardPageCase) => void;
  resolveResourceUrl: (url: string) => string;
}) {
  if (!items.length) {
    return <div className="cpr-empty"><strong>代表案例待补充</strong><p>案例确认公开范围后会显示在这里。</p></div>;
  }
  const size = quantityClass(items.length);
  return (
    <div className={`cpr-case-list cpr-case-list--${size}`} data-item-count={items.length}>
      {items.map((item, index) => {
        const content = (
          <>
            {item.imageUrl && <img src={resolveResourceUrl(item.imageUrl)} alt="" loading="lazy" />}
            <span className="cpr-case-meta"><b>CASE {String(index + 1).padStart(2, "0")}</b><small>{item.industry || "公开案例"}</small></span>
            <strong>{item.title}</strong>
            {(item.summary || item.result) && <p>{item.summary || item.result}</p>}
            {onOpen && <span className="cpr-item-link">查看完整案例 <i aria-hidden="true">→</i></span>}
          </>
        );
        return onOpen ? (
          <button className="cpr-case-item" type="button" key={item.id} onClick={() => onOpen(item)}>
            {content}
          </button>
        ) : (
          <div className="cpr-case-item" key={item.id}>{content}</div>
        );
      })}
    </div>
  );
}

function Gallery({
  urls,
  title,
  resolveResourceUrl,
}: {
  urls: string[];
  title?: string;
  resolveResourceUrl: (url: string) => string;
}) {
  if (!urls.length) {
    return <div className="cpr-empty"><strong>展示图片待上传</strong><p>添加图片后会按数量自动编排。</p></div>;
  }
  return (
    <div className={`cpr-gallery cpr-gallery--${quantityClass(urls.length)}`} data-item-count={urls.length}>
      {urls.map((url, index) => (
        <figure key={`${url}-${index}`}>
          <img src={resolveResourceUrl(url)} alt={`${title || "企业展示"} ${index + 1}`} loading="lazy" />
        </figure>
      ))}
    </div>
  );
}

function FaqCollection({
  items,
  onAssistant,
}: {
  items: CardPageFaqItem[];
  onAssistant?: (question?: string) => void;
}) {
  if (!items.length) {
    return <div className="cpr-empty"><strong>常见问题待补充</strong><p>已发布且公开的知识 FAQ 会同步到这里。</p></div>;
  }
  return (
    <div className="cpr-faq-list">
      {items.map((item, index) => (
        <details key={item.id} open={index === 0}>
          <summary>
            <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
            <strong>{item.question}</strong>
            <i aria-hidden="true" />
          </summary>
          <div className="cpr-faq-answer">
            <p>{item.answer}</p>
            {(item.sourceLabel || onAssistant) && (
              <footer>
                {item.sourceLabel && <small>资料来源：{item.sourceLabel}</small>}
                {onAssistant && <button type="button" onClick={() => onAssistant(item.question)}>继续问 AI <span aria-hidden="true">→</span></button>}
              </footer>
            )}
          </div>
        </details>
      ))}
    </div>
  );
}

function renderBlockContent({
  block,
  data,
  actions,
  identityContent,
  resolveResourceUrl,
}: {
  block: CardPageBlock;
  data: CardPageResolvedData;
  actions: CardPageExperienceActions;
  identityContent?: ReactNode;
  resolveResourceUrl: (url: string) => string;
}) {
  if (block.type === "identity") {
    return identityContent ?? <IdentityBlock identity={data.identity} resolveResourceUrl={resolveResourceUrl} />;
  }

  const intro = block.body?.trim();
  if (block.type === "rich_text") {
    if (isOverviewBlock(block)) {
      const positioning = intro || data.identity?.positioning?.trim() || data.identity?.summary?.trim();
      return positioning ? (
        <div className="cpr-positioning">
          <small>我们能帮助你</small>
          <strong>{positioning}</strong>
        </div>
      ) : <div className="cpr-empty"><strong>企业定位待补充</strong></div>;
    }
    return intro ? <div className="cpr-rich-text"><p>{intro}</p></div> : <div className="cpr-empty"><strong>内容待补充</strong></div>;
  }

  if (block.type === "business_collection") {
    const items = resolveReferencedItems(block.productItems, block.productIds, data.products ?? []);
    return <>{intro && <p className="cpr-block-intro">{intro}</p>}<ProductCollection items={items} onOpen={actions.onOpenProduct} resolveResourceUrl={resolveResourceUrl} /></>;
  }

  if (block.type === "case_collection") {
    const items = resolveReferencedItems(block.caseItems, block.caseIds, data.cases ?? []);
    return <>{intro && <p className="cpr-block-intro">{intro}</p>}<CaseCollection items={items} onOpen={actions.onOpenCase} resolveResourceUrl={resolveResourceUrl} /></>;
  }

  if (block.type === "image_gallery") {
    return <>{intro && <p className="cpr-block-intro">{intro}</p>}<Gallery urls={block.imageUrls ?? []} title={block.title} resolveResourceUrl={resolveResourceUrl} /></>;
  }

  if (block.type === "video_link") {
    const url = safeCardPageExternalUrl(block.videoUrl);
    if (!url) return <div className="cpr-empty"><strong>视频待配置</strong><p>请添加安全的 HTTPS 视频地址。</p></div>;
    return (
      <a className="cpr-video" href={url} target="_blank" rel="noreferrer">
        {block.videoCoverUrl ? <img src={resolveResourceUrl(block.videoCoverUrl)} alt={`${block.title || "企业视频"}封面`} /> : <span className="cpr-video-placeholder" aria-hidden="true">▶</span>}
        <span className="cpr-video-action"><b aria-hidden="true">▶</b><strong>播放视频</strong><small>将在新窗口打开</small></span>
      </a>
    );
  }

  if (block.type === "trust_panel") {
    return (
      <div className="cpr-trust-grid">
        <span><b aria-hidden="true">✓</b> 企业公开资料</span>
        <span><b aria-hidden="true">✓</b> 发布范围已确认</span>
        <span><b aria-hidden="true">✓</b> AI 引用可追溯</span>
      </div>
    );
  }

  if (block.type === "faq") {
    const items = resolveCardPageFaqItems(block, data.faqItems ?? []);
    return <FaqCollection items={items} onAssistant={actions.onAssistant} />;
  }

  if (block.type === "ai_assistant") {
    return (
      <div className="cpr-ai-panel">
        <div className="cpr-ai-mark" aria-hidden="true">AI</div>
        <div>
          <strong>{block.title || "企业 AI 助手"}</strong>
          <p>{intro || "基于企业已审核并发布的资料，为访客介绍业务并整理合作需求。"}</p>
        </div>
        {actions.onAssistant && <button type="button" onClick={() => actions.onAssistant?.()}>开始咨询 <span aria-hidden="true">→</span></button>}
      </div>
    );
  }

  if (block.type === "cta") {
    const url = safeCardPageExternalUrl(block.ctaUrl);
    return (
      <div className="cpr-cta-panel">
        <p>{intro || "准备进一步了解？"}</p>
        {url ? <a href={url} target="_blank" rel="noreferrer">{block.ctaLabel || "了解更多"}<span aria-hidden="true">↗</span></a> : <span className="cpr-cta-disabled">行动链接待配置</span>}
      </div>
    );
  }

  return null;
}

export function CardPageExperience({
  blocks,
  data = {},
  actions = {},
  identityContent,
  directory = false,
  resolveResourceUrl = (url) => url,
  editorAdapter,
  className,
}: CardPageExperienceProps) {
  const directoryItems = useMemo(() => deriveCardPageDirectory(blocks, {
    ...blockSelector,
    getTitle: directoryTitle,
    isDirectoryEnabled: (block) => block.directoryEnabled !== false,
  }), [blocks]);
  const directoryOptions = typeof directory === "object" ? directory : undefined;
  const directoryKey = useMemo(
    () => directoryItems.map((item) => item.id).join("|"),
    [directoryItems],
  );
  const [activeDirectoryBlockId, setActiveDirectoryBlockId] = useState<string | undefined>(
    directoryItems[0]?.id,
  );
  const orderedBlocks = orderVisibleCardPageBlocks(blocks, blockSelector);
  const leadingIdentity = orderedBlocks[0]?.type === "identity" ? orderedBlocks[0] : undefined;
  const remainingBlocks = leadingIdentity
    ? blocks.filter((block) => block.id !== leadingIdentity.id)
    : blocks;

  useEffect(() => {
    if (!directoryItems.some((item) => item.id === activeDirectoryBlockId)) {
      setActiveDirectoryBlockId(directoryItems[0]?.id);
    }
  }, [activeDirectoryBlockId, directoryItems, directoryKey]);

  useEffect(() => {
    if (!directory || typeof IntersectionObserver === "undefined" || directoryItems.length === 0) {
      return undefined;
    }
    const targets = directoryItems.flatMap((item) => {
      const target = document.getElementById(`bp-template-block-${item.id}`);
      return target ? [target] : [];
    });
    if (targets.length === 0) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        const visibleEntry = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => {
            if (right.intersectionRatio !== left.intersectionRatio) {
              return right.intersectionRatio - left.intersectionRatio;
            }
            return Math.abs(left.boundingClientRect.top) - Math.abs(right.boundingClientRect.top);
          })[0];
        const blockId = visibleEntry?.target.getAttribute("data-card-page-block");
        if (blockId) setActiveDirectoryBlockId(blockId);
      },
      { rootMargin: "-126px 0px -52% 0px", threshold: [0.08, 0.3, 0.65] },
    );
    targets.forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, [directory, directoryItems, directoryKey]);

  const navigateToBlock = (blockId: string) => {
    setActiveDirectoryBlockId(blockId);
    if (directoryOptions?.onNavigate) {
      directoryOptions.onNavigate(blockId);
      return;
    }
    const target = document.getElementById(`bp-template-block-${blockId}`);
    target?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    target?.focus({ preventScroll: true });
  };

  const renderBlocks = (items: CardPageBlock[], className: string) => (
    <CardPageBlocksRenderer
      blocks={items}
      selector={blockSelector}
      className={className}
      ariaLabel={data.identity?.kind === "employee" ? "员工名片内容" : "企业名片内容"}
      blockClassName={(block) => [
        "bp-section",
        "enterprise-template-block",
        `enterprise-template-${block.type}`,
        "cpr-block",
        `cpr-block--${block.type}`,
        editorAdapter?.selectedBlockId === block.id ? "cpr-block--selected" : "",
        editorAdapter?.getBlockClassName?.(block) || "",
      ].filter(Boolean).join(" ")}
      getBlockDataType={(block) => block.type}
      renderBlock={(block) => (
        <div
          className="cpr-block-inner"
          onClick={editorAdapter?.onSelectBlock ? () => editorAdapter.onSelectBlock?.(block.id) : undefined}
        >
          {editorAdapter?.renderBlockHandle && (
            <div className="cpr-editor-affordance">{editorAdapter.renderBlockHandle(block)}</div>
          )}
          {block.type !== "identity" && block.type !== "ai_assistant" && !isOverviewBlock(block) && <SectionHeading block={block} />}
          <div className="enterprise-template-block-content cpr-block-content">
            {renderBlockContent({ block, data, actions, identityContent, resolveResourceUrl })}
          </div>
        </div>
      )}
    />
  );

  return (
    <div className={["cpr-experience", className].filter(Boolean).join(" ")} data-card-page-experience>
      {leadingIdentity && renderBlocks([leadingIdentity], "cpr-blocks cpr-blocks--leading enterprise-template-public")}
      {directory && directoryItems.length > 0 && (
        <nav className="cpr-directory" aria-label={directoryOptions?.ariaLabel || "名片内容导航"}>
          {directoryItems.map((item, index) => (
            <button
              type="button"
              key={item.id}
              aria-current={activeDirectoryBlockId === item.id ? "location" : undefined}
              onClick={() => navigateToBlock(item.id)}
            >
              <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
              {item.title}
            </button>
          ))}
        </nav>
      )}
      {renderBlocks(remainingBlocks, "cpr-blocks enterprise-template-public")}
    </div>
  );
}

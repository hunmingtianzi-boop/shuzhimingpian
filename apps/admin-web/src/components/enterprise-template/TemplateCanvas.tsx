import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  CardPageExperience,
  type CardPageBlock,
  type CardPageCase,
  type CardPageProduct,
} from "@cf/card-page-renderer";
import { memo, useState } from "react";

import type {
  CaseStudy,
  EnterpriseTemplateBlock,
  EnterpriseTemplateThemeKey,
  IdentityContactField,
  ManagedCard,
  Product,
  SelectableFaqDocument,
} from "../../api/types";
import { resolveApiResourceUrl } from "../../lib/resourceUrl";

export type TemplateCanvasProps = {
  blocks: EnterpriseTemplateBlock[];
  themeKey?: EnterpriseTemplateThemeKey;
  products: Product[];
  cases: CaseStudy[];
  faqItems: SelectableFaqDocument[];
  identity: {
    cardKind: ManagedCard["cardKind"];
    displayName: string;
    title: string;
    avatarUrl?: string;
    companyName?: string;
    summary?: string;
    positioning?: string;
    identityTitles?: string[];
    identityTags?: string[];
    identityFacts?: Array<{ label: string; value: string }>;
    contactFields?: IdentityContactField[];
  };
  selectedBlockId?: string;
  onSelectBlock: (blockId: string) => void;
  onMoveBlock: (activeId: string, overId: string) => void;
};

type DraftCanvasView =
  | { kind: "product"; item: Product }
  | { kind: "case"; item: CaseStudy }
  | { kind: "assistant"; question?: string }
  | null;

function previewContactHref(contact: IdentityContactField) {
  if (contact.href?.trim()) return contact.href.trim();
  const value = contact.value.trim();
  if (!value) return undefined;
  if (contact.kind === "phone") return `tel:${value.replace(/[^+\d]/g, "")}`;
  if (contact.kind === "email") return `mailto:${value}`;
  if (contact.kind === "location") {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(value)}`;
  }
  if (contact.kind === "website") return /^https?:\/\//i.test(value) ? value : `https://${value}`;
  return undefined;
}

function CanvasDragHandle({ block }: { block: CardPageBlock }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: block.id,
  });
  return (
    <button
      ref={setNodeRef}
      type="button"
      className={`template-canvas-drag-handle${isDragging ? " is-dragging" : ""}`}
      aria-label={`拖动${block.title || "模块"}调整位置`}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      {...attributes}
      {...listeners}
    >
      <span aria-hidden="true">⠿</span>
      拖动
    </button>
  );
}

function CanvasDetailView({
  view,
  onBack,
  onAssistant,
}: {
  view: Exclude<DraftCanvasView, null | { kind: "assistant" }>;
  onBack: () => void;
  onAssistant: (question: string) => void;
}) {
  const isProduct = view.kind === "product";
  const title = isProduct ? view.item.name : view.item.title;
  const category = isProduct ? view.item.category : view.item.industry;
  const imageUrl = resolveApiResourceUrl(view.item.imageUrl) ?? view.item.imageUrl;
  const caseStory = !isProduct ? [
    ["01", "项目背景", view.item.background],
    ["02", "解决方案", view.item.solution],
    ["03", "项目成果", view.item.result],
  ] : [];

  return (
    <article
      className="template-canvas-route template-canvas-detail"
      aria-label={isProduct ? "产品详情预览" : "案例详情预览"}
    >
      <header className="template-canvas-route-bar">
        <button type="button" onClick={onBack} aria-label="返回名片页面">
          <span aria-hidden="true">←</span>
          返回
        </button>
        <span>{isProduct ? "产品详情" : "案例详情"}</span>
      </header>

      {imageUrl ? <img className="template-canvas-detail-cover" src={imageUrl} alt={`${title}封面`} /> : null}

      <div className="template-canvas-detail-copy">
        <small>{category || (isProduct ? "产品与服务" : "公开案例")}</small>
        <h1>{title}</h1>
        {isProduct && view.item.summary ? <p>{view.item.summary}</p> : null}
        {isProduct && view.item.detail ? (
          <section>
            <span>详细介绍</span>
            <p>{view.item.detail}</p>
          </section>
        ) : null}
        {!isProduct ? (
          <div className="template-canvas-case-story">
            {caseStory.map(([number, label, content]) => (
              <article key={label}>
                <strong>{number}</strong>
                <div><span>{label}</span><p>{content || "待补充"}</p></div>
              </article>
            ))}
          </div>
        ) : null}
        <section className="template-canvas-detail-assistant">
          <div><i aria-hidden="true">AI</i><span><strong>拓浙 AI 资料助手</strong><small>继续了解</small></span></div>
          <button type="button" onClick={() => onAssistant(`请详细介绍${title}`)}>向 AI 继续提问 <span aria-hidden="true">→</span></button>
        </section>
      </div>
    </article>
  );
}

function CanvasAssistantView({
  question,
  onBack,
}: {
  question?: string;
  onBack: () => void;
}) {
  return (
    <section className="template-canvas-route template-canvas-assistant" aria-label="AI 助手预览">
      <header className="template-canvas-route-bar">
        <button type="button" onClick={onBack} aria-label="返回名片页面">
          <span aria-hidden="true">←</span>
          返回
        </button>
        <span>AI 助手</span>
      </header>
      <div className="template-canvas-assistant-copy">
        <span className="template-canvas-assistant-mark" aria-hidden="true">AI</span>
        <small>访客端交互预览</small>
        <h1>公开页将打开 AI 助手</h1>
        <p>编辑器只预览入口和跳转效果，不会在这里发起真实问答。</p>
        {question ? <blockquote>将带入问题：{question}</blockquote> : null}
      </div>
    </section>
  );
}

function TemplateCanvasComponent({
  blocks,
  themeKey = "brand",
  products,
  cases,
  faqItems,
  identity,
  selectedBlockId,
  onSelectBlock,
  onMoveBlock,
}: TemplateCanvasProps) {
  const [draftView, setDraftView] = useState<DraftCanvasView>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    if (!event.over || event.active.id === event.over.id) return;
    onMoveBlock(String(event.active.id), String(event.over.id));
  };

  const openProduct = (item: CardPageProduct) => {
    const source = products.find((product) => product.id === item.id);
    if (source) setDraftView({ kind: "product", item: source });
  };

  const openCase = (item: CardPageCase) => {
    const source = cases.find((caseStudy) => caseStudy.id === item.id);
    if (source) setDraftView({ kind: "case", item: source });
  };

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={blocks.map((block) => block.id)} strategy={verticalListSortingStrategy}>
        {draftView?.kind === "product" || draftView?.kind === "case" ? (
          <CanvasDetailView
            view={draftView}
            onBack={() => setDraftView(null)}
            onAssistant={(question) => setDraftView({ kind: "assistant", question })}
          />
        ) : draftView?.kind === "assistant" ? (
          <CanvasAssistantView question={draftView.question} onBack={() => setDraftView(null)} />
        ) : (
          <div className="template-canvas-live-page">
          <CardPageExperience
            blocks={blocks}
            className={`template-shared-card-page template-theme-${themeKey}`}
            data={{
              identity: {
                variant: "v2",
                kind: identity.cardKind,
                name: identity.displayName,
                headline: identity.positioning || identity.title,
                imageUrl: identity.avatarUrl,
                companyName: identity.cardKind === "employee" ? identity.companyName : undefined,
                verificationLabel: "企业认证",
                summary: identity.summary,
                positioning: identity.positioning,
                titles: identity.identityTitles,
                tags: identity.identityTags,
                facts: identity.identityFacts,
                contacts: identity.contactFields?.map((contact) => ({
                  id: contact.id,
                  kind: contact.kind,
                  label: contact.label,
                  value: contact.value,
                  href: previewContactHref(contact),
                })),
              },
              products: products.map((item) => ({
                id: item.id,
                slug: item.slug,
                name: item.name,
                category: item.category,
                summary: item.summary,
                imageUrl: item.imageUrl,
              })),
              cases: cases.map((item) => ({
                id: item.id,
                slug: item.slug,
                title: item.title,
                industry: item.industry,
                summary: item.solution || item.background,
                result: item.result,
                imageUrl: item.imageUrl,
              })),
              faqItems: faqItems.map((item) => ({
                id: item.id,
                documentId: item.id,
                question: item.title,
                answer: item.answer,
                sourceLabel: "企业知识 FAQ",
              })),
            }}
            actions={{
              onOpenProduct: openProduct,
              onOpenCase: openCase,
              onAssistant: (question) => setDraftView({ kind: "assistant", question }),
            }}
            shell={{
              title: identity.cardKind === "employee" ? "员工数字名片" : "企业官方名片",
              primaryAction: { label: "咨询 AI", onClick: () => setDraftView({ kind: "assistant" }) },
              secondaryAction: { label: "提交合作需求", onClick: () => undefined },
            }}
            directory={{
              ariaLabel: "企业名片内容导航预览",
              onNavigate: (blockId) => {
                onSelectBlock(blockId);
              },
            }}
            resolveResourceUrl={(url) => resolveApiResourceUrl(url) ?? url}
            editorAdapter={{
              selectedBlockId,
              onSelectBlock,
              renderBlockHandle: (block) => <CanvasDragHandle block={block} />,
            }}
          />
          </div>
        )}
      </SortableContext>
    </DndContext>
  );
}

export const TemplateCanvas = memo(TemplateCanvasComponent, (previous, next) => (
  previous.blocks === next.blocks
  && previous.themeKey === next.themeKey
  && previous.products === next.products
  && previous.cases === next.cases
  && previous.faqItems === next.faqItems
  && previous.selectedBlockId === next.selectedBlockId
  && previous.identity.cardKind === next.identity.cardKind
  && previous.identity.displayName === next.identity.displayName
  && previous.identity.title === next.identity.title
  && previous.identity.avatarUrl === next.identity.avatarUrl
  && previous.identity.companyName === next.identity.companyName
  && previous.identity.summary === next.identity.summary
  && previous.identity.positioning === next.identity.positioning
  && previous.identity.identityTitles === next.identity.identityTitles
  && previous.identity.identityTags === next.identity.identityTags
  && previous.identity.identityFacts === next.identity.identityFacts
  && previous.identity.contactFields === next.identity.contactFields
));

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
import { useState } from "react";

import type {
  CaseStudy,
  EnterpriseTemplateBlock,
  ManagedCard,
  Product,
  SelectableFaqDocument,
} from "../../api/types";
import { resolveApiResourceUrl } from "../../lib/resourceUrl";

export type TemplateCanvasProps = {
  blocks: EnterpriseTemplateBlock[];
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
}: {
  view: Exclude<DraftCanvasView, null | { kind: "assistant" }>;
  onBack: () => void;
}) {
  const isProduct = view.kind === "product";
  const title = isProduct ? view.item.name : view.item.title;
  const category = isProduct ? view.item.category : view.item.industry;
  const summary = isProduct
    ? view.item.summary
    : view.item.solution || view.item.background;
  const detail = isProduct ? view.item.detail : view.item.result;
  const imageUrl = resolveApiResourceUrl(view.item.imageUrl) ?? view.item.imageUrl;

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
        {summary ? <p>{summary}</p> : null}
        {detail ? (
          <section>
            <span>{isProduct ? "详细介绍" : "项目成效"}</span>
            <p>{detail}</p>
          </section>
        ) : null}
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

export function TemplateCanvas({
  blocks,
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
          <CanvasDetailView view={draftView} onBack={() => setDraftView(null)} />
        ) : draftView?.kind === "assistant" ? (
          <CanvasAssistantView question={draftView.question} onBack={() => setDraftView(null)} />
        ) : (
          <CardPageExperience
            blocks={blocks}
            className="template-shared-card-page"
            data={{
              identity: {
                kind: identity.cardKind,
                name: identity.displayName,
                headline: identity.title,
                imageUrl: identity.avatarUrl,
                companyName: identity.cardKind === "employee" ? identity.companyName : undefined,
                verificationLabel: "企业认证",
                summary: identity.summary,
                positioning: identity.positioning,
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
            directory={{
              ariaLabel: "企业名片内容导航预览",
              onNavigate: (blockId) => {
                onSelectBlock(blockId);
                const target = document.getElementById(`bp-template-block-${blockId}`);
                target?.scrollIntoView({ behavior: "smooth", block: "start" });
              },
            }}
            resolveResourceUrl={(url) => resolveApiResourceUrl(url) ?? url}
            editorAdapter={{
              selectedBlockId,
              onSelectBlock,
              renderBlockHandle: (block) => <CanvasDragHandle block={block} />,
            }}
          />
        )}
      </SortableContext>
    </DndContext>
  );
}

import type { ReactNode } from "react";

import { orderVisibleCardPageBlocks } from "./CardPageBlocksRenderer";
import { CardStudioSurface } from "./CardStudioSurface";
import { StudioCardPage, type StudioModule } from "./CardStudioComponents";

export type CardPageBlockType = "identity" | "rich_text" | "business_collection" | "image_gallery" | "video_link" | "case_collection" | "trust_panel" | "faq" | "cta" | "ai_assistant" | "action_collection";
export type CardPageLayoutVariant = "auto" | "list" | "grid" | "carousel" | "featured" | "mosaic" | "horizontal" | "vertical";
export type CardPageIdentityPresentation = {
  identityLayout?: "horizontal" | "vertical";
  background?: {
    assetUrl?: string;
    fit?: "cover" | "contain" | "custom";
    position?: "center" | "top" | "bottom" | "left" | "right" | "topLeft" | "topRight" | "bottomLeft" | "bottomRight" | "top_left" | "top_right" | "bottom_left" | "bottom_right";
    aspectRatio?: "auto" | "16:9" | "4:3" | "3:2" | "1:1";
    focalX?: number;
    focalY?: number;
    scale?: number;
    opacity?: number;
    overlay?: "none" | "light" | "dark" | "brand";
  };
};
export type CardPageActionTemplate = "quick" | "shortcuts" | "media" | "event" | "banner" | "articles" | "video" | "buttons";
export type CardPageActionIcon = "external" | "phone" | "mail" | "message" | "map" | "building" | "calendar" | "file" | "play";
export type CardPageActionItem = { id: string; title: string; summary?: string; label?: string; tag?: string; icon?: CardPageActionIcon; date?: string; location?: string; source?: string; status?: string; duration?: string; imageUrl?: string; targetType: "external_url" | "internal_path" | "phone" | "map"; targetValue: string; openMode?: "self" | "new_tab" };
export type CardPageGalleryItem = { id: string; imageUrl: string; title?: string; description?: string; timeLabel?: string; periodLabel?: string; badgeMode?: "title" | "time" | "period" | "custom" | "none"; badgeText?: string; altText?: string; linkUrl?: string };
export type CardPageIdentity = { variant?: "legacy" | "v2"; kind: "enterprise" | "employee"; name: string; headline?: string; titles?: string[]; summary?: string; imageUrl?: string; companyName?: string; verificationLabel?: string; positioning?: string; meta?: string[]; facts?: Array<{ label: string; value: string }>; tags?: string[]; contacts?: Array<{ id?: string; kind?: "phone" | "wechat" | "email" | "location" | "website" | "other"; label: string; value: string; href?: string }> };
export type CardPageProduct = { id: string; slug?: string; name: string; category?: string; summary?: string; imageUrl?: string; ctaLabel?: string };
export type CardPageCase = { id: string; slug?: string; title: string; industry?: string; clientName?: string; background?: string; solution?: string; summary?: string; result?: string; metrics?: Array<{ value: string; label: string }>; imageUrl?: string; ctaLabel?: string };
export type CardPageFaqItem = { id: string; documentId?: string; question: string; answer: string; sourceLabel?: string };
export type CardPageBlock = {
  id: string; type: CardPageBlockType; title?: string; body?: string; visible?: boolean; showTitle?: boolean; directoryEnabled?: boolean; sortOrder?: number;
  layoutVariant?: CardPageLayoutVariant; itemLimit?: number; presentation?: CardPageIdentityPresentation; imageUrls?: string[]; galleryItems?: CardPageGalleryItem[]; videoUrl?: string; videoCoverUrl?: string;
  productIds?: string[]; productItems?: CardPageProduct[]; productOverrides?: Array<Partial<CardPageProduct> & { id: string; title?: string }>; caseIds?: string[]; caseItems?: CardPageCase[]; caseOverrides?: Array<Partial<CardPageCase> & { id: string }>; faqMode?: "all_published" | "selected"; faqDocumentIds?: string[];
  ctaLabel?: string; ctaUrl?: string; ctaIcon?: CardPageActionIcon; actionTemplate?: CardPageActionTemplate; actionItems?: CardPageActionItem[];
};
export type CardPageResolvedData = { identity?: CardPageIdentity; products?: CardPageProduct[]; cases?: CardPageCase[]; faqItems?: CardPageFaqItem[] };
export type CardPageExperienceActions = { onOpenProduct?: (item: CardPageProduct) => void; onOpenCase?: (item: CardPageCase) => void; onAction?: (item: CardPageActionItem) => void; onAssistant?: (question?: string) => void };
export type CardPageEditorAdapter = { selectedBlockId?: string | null; onSelectBlock?: (blockId: string) => void; renderBlockHandle?: (block: CardPageBlock) => ReactNode; getBlockClassName?: (block: CardPageBlock) => string | undefined };
export type CardPageDirectoryOptions = { ariaLabel?: string; onNavigate?: (blockId: string) => void };
export type CardPageExperienceProps = {
  blocks: CardPageBlock[]; data?: CardPageResolvedData; actions?: CardPageExperienceActions; identityContent?: ReactNode; directory?: boolean | CardPageDirectoryOptions;
  resolveResourceUrl?: (url: string) => string; editorAdapter?: CardPageEditorAdapter; className?: string;
  shell?: { title?: string; onBack?: () => void; onShare?: () => void; switchTarget?: { href: string; label: string; ariaLabel: string }; contentAriaLabel?: string; primaryAction?: { label: string; onClick: () => void; disabled?: boolean }; secondaryAction?: { label: string; onClick: () => void; disabled?: boolean } };
};

const blockSelector = {
  getId: (block: CardPageBlock) => block.id,
  getSortOrder: (block: CardPageBlock) => block.sortOrder ?? 0,
  isVisible: (block: CardPageBlock) => block.type === "identity" || block.visible !== false,
};

export function safeCardPageExternalUrl(value?: string) {
  if (!value) return undefined;
  try { const url = new URL(value); return url.protocol === "https:" ? url.toString() : undefined; } catch { return undefined; }
}

export function safeCardPageVideoUrl(value?: string, resolveResourceUrl: (url: string) => string = (url) => url) {
  const resolved = value?.trim() ? resolveResourceUrl(value.trim()) : "";
  if (!resolved || /[\\\u0000-\u001f]/.test(resolved)) return undefined;
  try {
    const url = new URL(resolved, "https://card.local");
    return ["https:", "http:", "blob:"].includes(url.protocol) ? resolved : undefined;
  } catch { return undefined; }
}

export function safeCardPageActionHref(item: CardPageActionItem) {
  const value = item.targetValue.trim();
  if (!value || /[\\\u0000-\u001f]/.test(value)) return undefined;
  if (item.targetType === "external_url" || item.targetType === "map") return safeCardPageExternalUrl(value);
  if (item.targetType === "internal_path") {
    if (!value.startsWith("/") || value.startsWith("//")) return undefined;
    try { const parsed = new URL(value, "https://card.local"); return parsed.origin === "https://card.local" && !parsed.pathname.split("/").includes("..") ? `${parsed.pathname}${parsed.search}${parsed.hash}` : undefined; } catch { return undefined; }
  }
  return /^\+?[0-9][0-9() -]{4,24}$/.test(value) ? `tel:${value.replace(/[^+\d]/g, "")}` : undefined;
}

export function resolveCardPageFaqItems(block: Pick<CardPageBlock, "faqMode" | "faqDocumentIds">, faqItems: CardPageFaqItem[]) {
  if (block.faqMode !== "selected") return faqItems;
  const byDocumentId = new Map(faqItems.map((item) => [item.documentId || item.id, item]));
  return (block.faqDocumentIds || []).flatMap((id) => { const item = byDocumentId.get(id); return item ? [item] : []; });
}

function limited<T>(items: T[], limit?: number) { return limit && Number.isFinite(limit) ? items.slice(0, Math.max(1, Math.min(12, Math.floor(limit)))) : items; }
function resolved<T extends { id: string }>(embedded: T[] | undefined, ids: string[] | undefined, available: T[]) {
  if (embedded !== undefined) return embedded;
  if (!ids?.length) return available;
  const byId = new Map(available.map((item) => [item.id, item]));
  return ids.flatMap((id) => { const item = byId.get(id); return item ? [item] : []; });
}
function withOverrides<T extends { id: string }>(items: T[], overrides: Array<Partial<T> & { id: string }> | undefined) {
  const byId = new Map((overrides || []).map((item) => [item.id, item]));
  return items.map((item) => ({ ...item, ...byId.get(item.id) }));
}
function simulatorLayout(variant?: CardPageLayoutVariant, listAlias = "stack") { return ({ carousel: "rail", list: listAlias } as Record<string, string>)[variant || "auto"] || variant || "auto"; }
function isOverview(block: CardPageBlock) { return block.type === "rich_text" && (block.id === "overview" || block.id.endsWith("-overview") || block.title?.trim() === "概览"); }
function moduleTitle(block: CardPageBlock, identityKind?: CardPageIdentity["kind"]) {
  const configured = block.title?.trim();
  if (block.type === "rich_text" && identityKind === "employee" && configured === "企业介绍") return "个人介绍";
  if (block.type === "rich_text" && identityKind === "enterprise" && configured === "个人介绍") return "企业介绍";
  return configured || ({ identity: "基础名片", rich_text: "介绍", business_collection: "核心业务", image_gallery: "工作相册", video_link: "视频介绍", case_collection: "业务案例", trust_panel: "企业资料", faq: "常见问题", cta: "联系", ai_assistant: "AI 助手", action_collection: "快捷入口" } as Record<CardPageBlockType, string>)[block.type];
}
function moduleSource(block: CardPageBlock, identityKind?: CardPageIdentity["kind"]) {
  const profileSource = identityKind === "enterprise" ? "企业资料" : "员工信息";
  return ({ identity: "企业员工", rich_text: profileSource, business_collection: "业务库", image_gallery: "素材库", video_link: "素材库", case_collection: "案例库", trust_panel: "企业资料", faq: "问答库", cta: "自定义内容", ai_assistant: "企业资料", action_collection: "快捷入口" } as Record<CardPageBlockType, string>)[block.type];
}
function studioType(block: CardPageBlock): StudioModule["type"] { return isOverview(block) ? "overview" : ({ identity: "identity", rich_text: "intro", business_collection: "services", image_gallery: "gallery", video_link: "video", case_collection: "cases", trust_panel: "trust", faq: "faq", cta: "cta", ai_assistant: "ai", action_collection: "actions" } as Record<CardPageBlockType, StudioModule["type"]>)[block.type]; }
function positionValue(value?: CardPageIdentityPresentation["background"] extends infer B ? B extends { position?: infer P } ? P : never : never) { return ({ top_left: "topLeft", top_right: "topRight", bottom_left: "bottomLeft", bottom_right: "bottomRight" } as Record<string, string>)[String(value || "")] || value; }

export function adaptCardPageToStudioModel({ blocks, data = {}, resolveResourceUrl = (url) => url }: Pick<CardPageExperienceProps, "blocks" | "data" | "resolveResourceUrl">): StudioModule[] {
  return orderVisibleCardPageBlocks(blocks, blockSelector).map((block): StudioModule => {
    const base: StudioModule = { id: block.id, type: studioType(block), title: moduleTitle(block, data.identity?.kind), source: moduleSource(block, data.identity?.kind), visible: block.type === "identity" ? true : block.visible !== false, directoryEnabled: block.directoryEnabled, showTitle: block.showTitle !== false && block.type !== "identity" && !isOverview(block), layout: simulatorLayout(block.layoutVariant), body: block.body, actionTemplate: block.actionTemplate };
    if (block.type === "identity") {
      const identity = data.identity;
      base.identity = identity ? { ...identity, imageUrl: identity.imageUrl ? resolveResourceUrl(identity.imageUrl) : undefined, layout: block.presentation?.identityLayout || (block.layoutVariant === "vertical" ? "vertical" : "horizontal"), background: { imageUrl: block.presentation?.background?.assetUrl ? resolveResourceUrl(block.presentation.background.assetUrl) : undefined, fit: block.presentation?.background?.fit, position: positionValue(block.presentation?.background?.position) as string, aspectRatio: block.presentation?.background?.aspectRatio, focalX: block.presentation?.background?.focalX, focalY: block.presentation?.background?.focalY, scale: block.presentation?.background?.scale, opacity: block.presentation?.background?.opacity, overlay: block.presentation?.background?.overlay } } : undefined;
    } else if (block.type === "business_collection") {
      base.items = limited(withOverrides(resolved(block.productItems, block.productIds, data.products || []), block.productOverrides?.map((item) => ({ ...item, name: item.title || item.name }))), block.itemLimit).map((item) => ({ ...item, title: item.name, imageUrl: item.imageUrl ? resolveResourceUrl(item.imageUrl) : undefined }));
    } else if (block.type === "case_collection") {
      base.items = limited(withOverrides(resolved(block.caseItems, block.caseIds, data.cases || []), block.caseOverrides), block.itemLimit).map((item) => ({ ...item, imageUrl: item.imageUrl ? resolveResourceUrl(item.imageUrl) : undefined }));
    } else if (block.type === "image_gallery") {
      base.galleryItems = limited(block.galleryItems || (block.imageUrls || []).map((imageUrl, index) => ({ id: `legacy-${index + 1}`, imageUrl, title: block.title, badgeMode: "title" as const })), block.itemLimit).map((item) => ({ ...item, imageUrl: resolveResourceUrl(item.imageUrl) }));
      base.imageUrls = base.galleryItems.map((item) => item.imageUrl);
    } else if (block.type === "video_link") {
      base.videoUrl = safeCardPageVideoUrl(block.videoUrl, resolveResourceUrl); base.videoCoverUrl = block.videoCoverUrl ? resolveResourceUrl(block.videoCoverUrl) : undefined;
    } else if (block.type === "faq") {
      base.items = limited(resolveCardPageFaqItems(block, data.faqItems || []), block.itemLimit).map((item) => ({ ...item }));
    } else if (block.type === "action_collection") {
      base.items = limited(block.actionItems || [], block.itemLimit).flatMap((item) => { const href = safeCardPageActionHref(item); return href ? [{ ...item, href, imageUrl: item.imageUrl ? resolveResourceUrl(item.imageUrl) : undefined }] : []; });
    } else if (block.type === "cta") { base.ctaLabel = block.ctaLabel; base.ctaUrl = safeCardPageExternalUrl(block.ctaUrl); base.ctaIcon = block.ctaIcon; }
    return base;
  });
}

export function CardPageExperience({ blocks, data = {}, actions = {}, directory = false, resolveResourceUrl = (url) => url, editorAdapter, className, shell }: CardPageExperienceProps) {
  const modules = adaptCardPageToStudioModel({ blocks, data, resolveResourceUrl });
  const byId = new Map(blocks.map((block) => [block.id, block]));
  const directoryOptions = typeof directory === "object" ? directory : undefined;
  return <CardStudioSurface mode={editorAdapter ? "editor" : "public"}>
    <StudioCardPage
      modules={directory ? modules : modules.map((module) => ({ ...module, directoryEnabled: false }))}
      title={shell?.title || (data.identity?.kind === "employee" ? "员工数字名片" : "企业官方名片")}
      editor={Boolean(editorAdapter)}
      className={["card-page-experience", className].filter(Boolean).join(" ")}
      selectedModuleId={editorAdapter?.selectedBlockId}
      onSelectModule={(id) => { editorAdapter?.onSelectBlock?.(id); directoryOptions?.onNavigate?.(id); }}
      renderModuleHandle={editorAdapter?.renderBlockHandle ? (module) => { const block = byId.get(module.id); return block ? editorAdapter.renderBlockHandle?.(block) : null; } : undefined}
      onBack={shell?.onBack}
      onShare={shell?.onShare}
      switchTarget={shell?.switchTarget}
      contentAriaLabel={shell?.contentAriaLabel}
      onOpenItem={(module, item) => module.type === "services" ? actions.onOpenProduct?.(item as CardPageProduct) : module.type === "cases" ? actions.onOpenCase?.(item as CardPageCase) : undefined}
      onAction={(item) => actions.onAction?.(item as unknown as CardPageActionItem)}
      onAssistant={actions.onAssistant}
      directoryAriaLabel={directoryOptions?.ariaLabel || "名片内容导航"}
      primaryAction={shell?.primaryAction}
      secondaryAction={shell?.secondaryAction}
    />
  </CardStudioSurface>;
}

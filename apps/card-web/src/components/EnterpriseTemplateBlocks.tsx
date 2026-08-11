import {
  CardPageExperience,
  type CardPageActionItem,
  type CardPageBlock,
  type CardPageCase,
  type CardPageDirectoryOptions,
  type CardPageFaqItem,
  type CardPageIdentity,
  type CardPageProduct,
} from "@cf/card-page-renderer";
import type { ReactNode } from "react";

import type { PublicEnterpriseTemplateBlock } from "../lib/publicCardApi";
import type { PublicCaseStudy, PublicProduct } from "../lib/publicExperienceApi";
import { resolvePublicResourceUrl } from "../lib/publicResourceUrl";

function toCardPageProduct(item: PublicProduct): CardPageProduct {
  return {
    id: item.slug,
    slug: item.slug,
    name: item.name,
    category: item.category,
    summary: item.summary,
    imageUrl: item.imageUrl,
  };
}

function toCardPageCase(item: PublicCaseStudy): CardPageCase {
  return {
    id: item.slug,
    slug: item.slug,
    title: item.title,
    industry: item.industry,
    summary: item.result,
    result: item.result,
    imageUrl: item.imageUrl,
  };
}

function toCardPageFaqItem(item: {
  id: string;
  document_id?: string;
  question: string;
  answer: string;
  source_label?: string;
}): CardPageFaqItem {
  return {
    id: item.id,
    documentId: item.document_id || item.id,
    question: item.question,
    answer: item.answer,
    sourceLabel: item.source_label,
  };
}

export function toCardPageBlock(block: PublicEnterpriseTemplateBlock): CardPageBlock {
  return {
    id: block.id,
    type: block.type,
    title: block.title,
    body: block.body,
    visible: block.visible,
    showTitle: block.show_title,
    directoryEnabled: block.directory_enabled,
    sortOrder: block.sort_order,
    layoutVariant: block.layout_variant,
    itemLimit: block.item_limit,
    actionTemplate: block.action_template,
    presentation: block.presentation ? {
      identityLayout: block.presentation.identity_layout,
      background: block.presentation.background ? {
        assetUrl: block.presentation.background.asset_url,
        fit: block.presentation.background.fit,
        position: ({
          top_left: "topLeft",
          top_right: "topRight",
          bottom_left: "bottomLeft",
          bottom_right: "bottomRight",
        } as const)[block.presentation.background.position as "top_left"]
          ?? block.presentation.background.position as "center" | "top" | "bottom" | "left" | "right",
        aspectRatio: block.presentation.background.aspect_ratio,
        focalX: block.presentation.background.focal_x,
        focalY: block.presentation.background.focal_y,
        scale: block.presentation.background.scale,
        opacity: block.presentation.background.opacity,
        overlay: block.presentation.background.overlay,
      } : undefined,
    } : undefined,
    imageUrls: block.image_urls,
    galleryItems: block.gallery_items?.map((item) => ({ id: item.id, imageUrl: item.image_url, title: item.title, description: item.description, timeLabel: item.time_label, periodLabel: item.period_label, badgeMode: item.badge_mode, badgeText: item.badge_text, altText: item.alt_text, linkUrl: item.link_url })),
    videoUrl: block.video_url,
    videoCoverUrl: block.video_cover_url,
    productIds: block.product_ids,
    productItems: block.product_items?.map((item) => ({
      id: item.id,
      slug: item.slug,
      name: item.name,
      category: item.category,
      summary: item.summary,
      imageUrl: item.image_url,
      ctaLabel: item.cta_label,
    })),
    caseIds: block.case_ids,
    caseItems: block.case_items?.map((item) => ({
      id: item.id,
      slug: item.slug,
      title: item.title,
      industry: item.industry,
      clientName: item.client_name,
      background: item.background,
      solution: item.solution,
      summary: item.summary,
      result: item.result,
      metrics: item.metrics,
      imageUrl: item.image_url,
      ctaLabel: item.cta_label,
    })),
    faqMode: block.faq_mode,
    faqDocumentIds: block.faq_document_ids,
    ctaLabel: block.cta_label,
    ctaUrl: block.cta_url,
    actionItems: block.action_items?.map((item) => ({
      id: item.id,
      title: item.title,
      summary: item.summary,
      label: item.label,
      tag: item.tag,
      icon: item.icon,
      date: item.date,
      location: item.location,
      source: item.source,
      status: item.status,
      duration: item.duration,
      imageUrl: item.image_url,
      targetType: item.target_type,
      targetValue: item.target_value,
      openMode: item.open_mode,
    })),
  };
}

export function EnterpriseTemplateBlocks({
  blocks,
  themeKey = "brand",
  directory,
  identity,
  identityData,
  products = [],
  cases = [],
  faqItems = [],
  onAssistant,
  onOpenCase,
  onOpenProduct,
  onAction,
  title,
  onBack,
  onShare,
  primaryAction,
  secondaryAction,
}: {
  blocks: PublicEnterpriseTemplateBlock[];
  themeKey?: "brand" | "clean" | "warm";
  directory?: boolean | CardPageDirectoryOptions;
  identity?: ReactNode;
  identityData?: CardPageIdentity;
  products?: PublicProduct[];
  cases?: PublicCaseStudy[];
  faqItems?: Array<{
    id: string;
    document_id?: string;
    question: string;
    answer: string;
    source_label?: string;
  }>;
  onAssistant?: (question?: string) => void;
  onOpenCase?: (slug: string) => void;
  onOpenProduct?: (slug: string) => void;
  onAction?: (item: CardPageActionItem) => void;
  title?: string;
  onBack?: () => void;
  onShare?: () => void;
  primaryAction?: { label: string; onClick: () => void; disabled?: boolean };
  secondaryAction?: { label: string; onClick: () => void; disabled?: boolean };
}) {
  return (
    <CardPageExperience
      className={`public-shared-card-page template-theme-${themeKey}`}
      blocks={blocks.map(toCardPageBlock)}
      data={{
        identity: identityData,
        products: products.map(toCardPageProduct),
        cases: cases.map(toCardPageCase),
        faqItems: faqItems.map(toCardPageFaqItem),
      }}
      directory={directory}
      identityContent={identity}
      resolveResourceUrl={(url) => resolvePublicResourceUrl(url) || url}
      actions={{
        onAssistant,
        onOpenProduct: onOpenProduct
          ? (item) => item.slug && onOpenProduct(item.slug)
          : undefined,
        onOpenCase: onOpenCase
          ? (item) => item.slug && onOpenCase(item.slug)
          : undefined,
        onAction,
      }}
      shell={{ title, onBack, onShare, primaryAction, secondaryAction }}
    />
  );
}

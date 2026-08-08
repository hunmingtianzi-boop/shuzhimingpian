import {
  CardPageExperience,
  type CardPageBlock,
  type CardPageCase,
  type CardPageDirectoryOptions,
  type CardPageFaqItem,
  type CardPageIdentity,
  type CardPageProduct,
} from "@cf/card-page-renderer";
import type { ReactNode } from "react";

import type { PublicCardData, PublicEnterpriseTemplateBlock } from "../lib/publicCardApi";
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
    directoryEnabled: block.directory_enabled,
    sortOrder: block.sort_order,
    imageUrls: block.image_urls,
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
    })),
    caseIds: block.case_ids,
    caseItems: block.case_items?.map((item) => ({
      id: item.id,
      slug: item.slug,
      title: item.title,
      industry: item.industry,
      summary: item.summary,
      imageUrl: item.image_url,
    })),
    faqMode: block.faq_mode,
    faqDocumentIds: block.faq_document_ids,
    ctaLabel: block.cta_label,
    ctaUrl: block.cta_url,
    background: block.background ? {
      kind: block.background.kind,
      color: block.background.color,
      imageUrl: block.background.image_url,
      fit: block.background.fit,
      positionX: block.background.position_x,
      positionY: block.background.position_y,
      overlayColor: block.background.overlay_color,
      overlayOpacity: block.background.overlay_opacity,
    } : undefined,
    textTone: block.text_tone,
    textColor: block.text_color,
    contentImage: block.content_image ? {
      url: block.content_image.url,
      alt: block.content_image.alt,
      placement: block.content_image.placement,
      fit: block.content_image.fit,
      aspectRatio: block.content_image.aspect_ratio,
      widthPercent: block.content_image.width_percent,
      positionX: block.content_image.position_x,
      positionY: block.content_image.position_y,
    } : undefined,
    sizePreset: block.size_preset,
    paddingY: block.padding_y,
  };
}

export function EnterpriseTemplateBlocks({
  blocks,
  pageBackground,
  pageTextTone,
  directory,
  identity,
  identityData,
  products = [],
  cases = [],
  faqItems = [],
  onAssistant,
  onOpenCase,
  onOpenProduct,
}: {
  blocks: PublicEnterpriseTemplateBlock[];
  pageBackground?: NonNullable<PublicCardData["enterprise_template"]>["page_background"];
  pageTextTone?: NonNullable<PublicCardData["enterprise_template"]>["page_text_tone"];
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
}) {
  return (
    <CardPageExperience
      className="public-shared-card-page"
      blocks={blocks.map(toCardPageBlock)}
      pageBackground={pageBackground ? {
        kind: pageBackground.kind,
        color: pageBackground.color,
        imageUrl: pageBackground.image_url,
        fit: pageBackground.fit,
        positionX: pageBackground.position_x,
        positionY: pageBackground.position_y,
        overlayColor: pageBackground.overlay_color,
        overlayOpacity: pageBackground.overlay_opacity,
      } : undefined}
      pageTextTone={pageTextTone}
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
      }}
    />
  );
}

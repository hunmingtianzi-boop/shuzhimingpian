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
  };
}

export function EnterpriseTemplateBlocks({
  blocks,
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

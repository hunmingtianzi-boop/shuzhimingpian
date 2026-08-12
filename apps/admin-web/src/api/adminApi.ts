import { apiClient, ApiClient, ApiError, unwrapData } from "./client";
import type {
  AdminUser,
  CardAssetUpload,
  CardVideoAssetUpload,
  CardComposerDefault,
  EnterpriseTemplate,
  EnterpriseTemplateBlock,
  EnterpriseTemplateThemeKey,
  CardSettings,
  CardSettingsInput,
  CaseStudy,
  CaseStudyInput,
  CompanyProfile,
  CompanyProfileInput,
  ContentVisibility,
  ForbiddenAction,
  ForbiddenTopic,
  ForbiddenTopicInput,
  KnowledgeDocument,
  KnowledgeDocumentDetail,
  KnowledgeDocumentInput,
  KnowledgeVisibility,
  ManagedCard,
  ManagedCardInput,
  Product,
  ProductInput,
  SelectableFaqDocument,
  WeComCardContactWay,
} from "./types";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function optionalString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string") return value;
  }
  return "";
}

function nullableString(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function optionalNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function requireRecord(payload: unknown, label: string): JsonRecord {
  const data = unwrapData(payload);
  if (!isRecord(data)) {
    throw new ApiError(`${label}接口返回了无法识别的数据。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return data;
}

function requireNestedRecord(
  data: JsonRecord,
  field: string,
  label: string,
): JsonRecord {
  const value = data[field];
  if (!isRecord(value)) {
    throw new ApiError(`${label}缺少 ${field}。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value;
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value) {
    throw new ApiError(`${label}缺少有效字符串。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value;
}

function requireId(data: JsonRecord, label: string): string {
  return requireString(data.id, `${label} id`);
}

function normalizeCompany(payload: unknown): CompanyProfile {
  const raw = requireRecord(payload, "企业资料");
  return {
    id: typeof raw.id === "string" ? raw.id : undefined,
    name: optionalString(raw.name),
    summary: optionalString(raw.summary),
    industry: optionalString(raw.industry),
    region: optionalString(raw.region),
    website: optionalString(raw.website),
    logoUrl: optionalString(raw.logo_url),
    profilePersonalizationPolicyVersion:
      optionalString(raw.profile_personalization_policy_version) ||
      "profile-personalization-v1",
    onboardingStatus: optionalString(raw.onboarding_status) || "content_pending",
    version: optionalNumber(raw.version),
    updatedAt: optionalString(raw.updated_at) || undefined,
  };
}

function normalizeCard(payload: unknown): CardSettings {
  const raw = requireRecord(payload, "名片设置");
  const questions = Array.isArray(raw.suggested_questions)
    ? raw.suggested_questions.filter(
        (value): value is string => typeof value === "string",
      )
    : [];
  const policies = isRecord(raw.policy_versions) ? raw.policy_versions : {};
  return {
    id: typeof raw.id === "string" ? raw.id : undefined,
    displayName: optionalString(raw.display_name),
    title: optionalString(raw.title),
    slug: optionalString(raw.slug),
    avatarUrl: optionalString(raw.avatar_url),
    assistantName: optionalString(raw.assistant_name),
    welcomeMessage: optionalString(raw.welcome_message),
    suggestedQuestions: questions,
    policyVersions: {
      privacy: optionalString(policies.privacy),
      chatNotice: optionalString(policies.chat_notice),
      leadConsent: optionalString(policies.lead_consent),
    },
    status: optionalString(raw.status) || undefined,
    onboardingStatus: optionalString(raw.onboarding_status) || "content_pending",
    version: optionalNumber(raw.version),
    updatedAt: optionalString(raw.updated_at) || undefined,
  };
}

function normalizeTemplateBlock(value: unknown): EnterpriseTemplateBlock | undefined {
  if (!isRecord(value) || typeof value.id !== "string" || typeof value.type !== "string") return undefined;
  const type = value.type;
  if (![
    "identity", "rich_text", "business_collection", "image_gallery", "video_link", "case_collection", "trust_panel", "faq", "cta", "action_collection", "ai_assistant",
  ].includes(type)) return undefined;
  const strings = (raw: unknown) => Array.isArray(raw)
    ? raw.filter((item): item is string => typeof item === "string" && Boolean(item.trim()))
    : undefined;
  const presentation = isRecord(value.presentation) ? value.presentation : undefined;
  const background = presentation && isRecord(presentation.background)
    ? presentation.background
    : undefined;
  const actionItems = Array.isArray(value.action_items)
    ? value.action_items.flatMap((rawItem) => {
        if (!isRecord(rawItem) || typeof rawItem.id !== "string" || typeof rawItem.title !== "string") return [];
        const targetType = optionalString(rawItem.target_type);
        const openMode = optionalString(rawItem.open_mode);
        if (!["external_url", "internal_path", "phone", "map"].includes(targetType)) return [];
        return [{
          id: rawItem.id,
          title: rawItem.title,
          summary: optionalString(rawItem.summary) || undefined,
          label: optionalString(rawItem.label) || undefined,
          tag: optionalString(rawItem.tag) || undefined,
          icon: ["external", "building", "calendar", "file", "play"].includes(optionalString(rawItem.icon))
            ? optionalString(rawItem.icon) as NonNullable<EnterpriseTemplateBlock["actionItems"]>[number]["icon"]
            : undefined,
          date: optionalString(rawItem.date) || undefined,
          location: optionalString(rawItem.location) || undefined,
          source: optionalString(rawItem.source) || undefined,
          status: optionalString(rawItem.status) || undefined,
          duration: optionalString(rawItem.duration) || undefined,
          imageUrl: optionalString(rawItem.image_url) || undefined,
          targetType: targetType as NonNullable<EnterpriseTemplateBlock["actionItems"]>[number]["targetType"],
          targetValue: optionalString(rawItem.target_value),
          openMode: openMode === "new_tab" ? "new_tab" as const : "self" as const,
        }];
      })
    : undefined;
  const galleryItems = Array.isArray(value.gallery_items)
    ? value.gallery_items.flatMap((rawItem) => {
        if (!isRecord(rawItem) || typeof rawItem.id !== "string" || typeof rawItem.image_url !== "string") return [];
        const badgeMode = optionalString(rawItem.badge_mode);
        return [{
          id: rawItem.id,
          imageUrl: rawItem.image_url,
          title: optionalString(rawItem.title) || undefined,
          description: optionalString(rawItem.description) || undefined,
          timeLabel: optionalString(rawItem.time_label) || undefined,
          periodLabel: optionalString(rawItem.period_label) || undefined,
          badgeMode: (["title", "time", "period", "custom", "none"].includes(badgeMode) ? badgeMode : "title") as NonNullable<EnterpriseTemplateBlock["galleryItems"]>[number]["badgeMode"],
          badgeText: optionalString(rawItem.badge_text) || undefined,
          altText: optionalString(rawItem.alt_text) || undefined,
          linkUrl: optionalString(rawItem.link_url) || undefined,
        }];
      })
    : undefined;
  const normalizeOverrides = (raw: unknown, kind: "product" | "case") => Array.isArray(raw)
    ? raw.flatMap<Record<string, unknown>>((rawItem) => {
        if (!isRecord(rawItem) || typeof rawItem.id !== "string") return [];
        const base = {
          id: rawItem.id,
          title: optionalString(rawItem.title) || undefined,
          summary: optionalString(rawItem.summary) || undefined,
          imageUrl: optionalString(rawItem.image_url) || undefined,
          ctaLabel: optionalString(rawItem.cta_label) || undefined,
        };
        return kind === "product" ? [{
          ...base,
          category: optionalString(rawItem.category) || undefined,
        }] : [{
          ...base,
          industry: optionalString(rawItem.industry) || undefined,
          clientName: optionalString(rawItem.client_name) || undefined,
          background: optionalString(rawItem.background) || undefined,
          solution: optionalString(rawItem.solution) || undefined,
          result: optionalString(rawItem.result) || undefined,
          metrics: Array.isArray(rawItem.metrics) ? rawItem.metrics.flatMap((metric) => isRecord(metric) && typeof metric.value === "string" && typeof metric.label === "string" ? [{ value: metric.value, label: metric.label }] : []) : undefined,
        }];
      })
    : undefined;
  const layoutVariant = optionalString(value.layout_variant);
  const backgroundPosition = optionalString(background?.position);
  const normalizedBackgroundPosition = ({
    center: "center",
    top: "top",
    bottom: "bottom",
    left: "left",
    right: "right",
    top_left: "topLeft",
    top_right: "topRight",
    bottom_left: "bottomLeft",
    bottom_right: "bottomRight",
  } as Record<string, NonNullable<NonNullable<EnterpriseTemplateBlock["presentation"]>["background"]>["position"]>)[backgroundPosition];
  return {
    id: value.id,
    type: type as EnterpriseTemplateBlock["type"],
    visible: value.visible !== false,
    showTitle: value.show_title !== false,
    directoryEnabled: value.directory_enabled !== false,
    sortOrder: optionalNumber(value.sort_order) ?? 0,
    title: optionalString(value.title) || undefined,
    body: optionalString(value.body) || undefined,
    imageUrls: strings(value.image_urls),
    galleryItems,
    videoUrl: optionalString(value.video_url) || undefined,
    videoCoverUrl: optionalString(value.video_cover_url) || undefined,
    productIds: strings(value.product_ids),
    productOverrides: normalizeOverrides(value.product_overrides, "product") as EnterpriseTemplateBlock["productOverrides"],
    caseIds: strings(value.case_ids),
    caseOverrides: normalizeOverrides(value.case_overrides, "case") as EnterpriseTemplateBlock["caseOverrides"],
    layoutVariant: ["auto", "list", "grid", "carousel", "featured", "mosaic", "horizontal", "vertical"].includes(layoutVariant)
      ? layoutVariant as EnterpriseTemplateBlock["layoutVariant"]
      : undefined,
    itemLimit: optionalNumber(value.item_limit),
    actionTemplate: type === "action_collection" && ["shortcuts", "media", "event", "banner", "articles", "video", "buttons"].includes(optionalString(value.action_template))
      ? optionalString(value.action_template) as EnterpriseTemplateBlock["actionTemplate"]
      : undefined,
    presentation: presentation ? {
      identityLayout: presentation.identity_layout === "vertical" ? "vertical" : presentation.identity_layout === "horizontal" ? "horizontal" : undefined,
      background: background ? {
        assetUrl: optionalString(background.asset_url) || undefined,
        fit: ["cover", "contain", "custom"].includes(optionalString(background.fit))
          ? optionalString(background.fit) as NonNullable<NonNullable<EnterpriseTemplateBlock["presentation"]>["background"]>["fit"]
          : undefined,
        position: normalizedBackgroundPosition,
        aspectRatio: (["auto", "16:9", "4:3", "3:2", "1:1"] as const).includes(background.aspect_ratio as never)
          ? background.aspect_ratio as NonNullable<NonNullable<EnterpriseTemplateBlock["presentation"]>["background"]>["aspectRatio"]
          : undefined,
        focalX: optionalNumber(background.focal_x),
        focalY: optionalNumber(background.focal_y),
        scale: optionalNumber(background.scale),
        opacity: optionalNumber(background.opacity),
        overlay: ["none", "light", "dark", "brand"].includes(optionalString(background.overlay))
          ? optionalString(background.overlay) as NonNullable<NonNullable<EnterpriseTemplateBlock["presentation"]>["background"]>["overlay"]
          : undefined,
      } : undefined,
    } : undefined,
    actionItems,
    faqMode: type === "faq" && value.faq_mode === "selected" ? "selected" : type === "faq" ? "all_published" : undefined,
    faqDocumentIds: type === "faq" ? strings(value.faq_document_ids) : undefined,
    ctaLabel: optionalString(value.cta_label) || undefined,
    ctaUrl: optionalString(value.cta_url) || undefined,
  };
}

function normalizeEnterpriseTemplate(payload: unknown): EnterpriseTemplate {
  const raw = requireRecord(unwrapData(payload), "企业名片模板");
  const document = (value: unknown) => {
    const record = isRecord(value) ? value : {};
    return {
      schemaVersion: 1 as const,
      themeKey: ["brand", "clean", "warm"].includes(optionalString(record.theme_key))
        ? optionalString(record.theme_key) as EnterpriseTemplateThemeKey
        : "brand",
      blocks: Array.isArray(record.blocks)
        ? record.blocks.flatMap((item) => {
            const block = normalizeTemplateBlock(item);
            return block ? [block] : [];
          })
        : [],
    };
  };
  return {
    cardId: requireString(raw.card_id, "企业模板 card_id"),
    version: optionalNumber(raw.version) ?? 1,
    draft: document(raw.draft),
    published: isRecord(raw.published) ? document(raw.published) : undefined,
  };
}

function normalizeCardComposerDefault(payload: unknown): CardComposerDefault {
  const raw = requireRecord(unwrapData(payload), "名片默认配置");
  const cardKind = optionalString(raw.card_kind);
  if (cardKind !== "enterprise" && cardKind !== "employee") {
    throw new ApiError("名片默认配置缺少有效类型。", { code: "INVALID_API_RESPONSE" });
  }
  const document = normalizeEnterpriseTemplate({
    card_id: "default",
    version: raw.version,
    draft: raw.document,
  }).draft;
  return { cardKind, version: requireNumber(raw.version, "名片默认配置 version"), document };
}

function enterpriseTemplatePayload(
  themeKey: EnterpriseTemplateThemeKey,
  blocks: EnterpriseTemplateBlock[],
) {
  return {
    schema_version: 1,
    theme_key: themeKey,
    blocks: blocks.map((block, index) => ({
      id: block.id,
      type: block.type,
      visible: block.visible,
      show_title: block.showTitle !== false,
      directory_enabled: block.directoryEnabled !== false,
      sort_order: index,
      ...(block.title?.trim() ? { title: block.title.trim() } : {}),
      ...(block.body?.trim() ? { body: block.body.trim() } : {}),
      ...(block.imageUrls?.length ? { image_urls: block.imageUrls.map((value) => value.trim()).filter(Boolean) } : {}),
      ...(block.galleryItems?.length ? { gallery_items: block.galleryItems.map((item) => ({
        id: item.id,
        image_url: item.imageUrl.trim(),
        ...(item.title?.trim() ? { title: item.title.trim() } : {}),
        ...(item.description?.trim() ? { description: item.description.trim() } : {}),
        ...(item.timeLabel?.trim() ? { time_label: item.timeLabel.trim() } : {}),
        ...(item.periodLabel?.trim() ? { period_label: item.periodLabel.trim() } : {}),
        badge_mode: item.badgeMode,
        ...(item.badgeText?.trim() ? { badge_text: item.badgeText.trim() } : {}),
        ...(item.altText?.trim() ? { alt_text: item.altText.trim() } : {}),
        ...(item.linkUrl?.trim() ? { link_url: item.linkUrl.trim() } : {}),
      })) } : {}),
      ...(block.videoUrl?.trim() ? { video_url: block.videoUrl.trim() } : {}),
      ...(block.videoCoverUrl?.trim() ? { video_cover_url: block.videoCoverUrl.trim() } : {}),
      ...(block.productIds?.length ? { product_ids: block.productIds.map((value) => value.trim()).filter(Boolean) } : {}),
      ...(block.productOverrides?.length ? { product_overrides: block.productOverrides.map((item) => ({
        id: item.id,
        ...(item.title?.trim() ? { title: item.title.trim() } : {}),
        ...(item.category?.trim() ? { category: item.category.trim() } : {}),
        ...(item.summary?.trim() ? { summary: item.summary.trim() } : {}),
        ...(item.imageUrl?.trim() ? { image_url: item.imageUrl.trim() } : {}),
        ...(item.ctaLabel?.trim() ? { cta_label: item.ctaLabel.trim() } : {}),
      })) } : {}),
      ...(block.caseIds?.length ? { case_ids: block.caseIds.map((value) => value.trim()).filter(Boolean) } : {}),
      ...(block.caseOverrides?.length ? { case_overrides: block.caseOverrides.map((item) => ({
        id: item.id,
        ...(item.title?.trim() ? { title: item.title.trim() } : {}),
        ...(item.industry?.trim() ? { industry: item.industry.trim() } : {}),
        ...(item.clientName?.trim() ? { client_name: item.clientName.trim() } : {}),
        ...(item.background?.trim() ? { background: item.background.trim() } : {}),
        ...(item.solution?.trim() ? { solution: item.solution.trim() } : {}),
        ...(item.summary?.trim() ? { summary: item.summary.trim() } : {}),
        ...(item.result?.trim() ? { result: item.result.trim() } : {}),
        ...(item.imageUrl?.trim() ? { image_url: item.imageUrl.trim() } : {}),
        ...(item.ctaLabel?.trim() ? { cta_label: item.ctaLabel.trim() } : {}),
        ...(item.metrics?.length ? { metrics: item.metrics.filter((metric) => metric.value.trim() && metric.label.trim()).map((metric) => ({ value: metric.value.trim(), label: metric.label.trim() })) } : {}),
      })) } : {}),
      ...(block.layoutVariant ? { layout_variant: block.layoutVariant } : {}),
      ...(typeof block.itemLimit === "number" ? { item_limit: block.itemLimit } : {}),
      ...(block.actionTemplate ? { action_template: block.actionTemplate } : {}),
      ...(block.presentation ? {
        presentation: {
          ...(block.presentation.identityLayout ? { identity_layout: block.presentation.identityLayout } : {}),
          ...(block.presentation.background ? {
            background: {
              ...(block.presentation.background.assetUrl?.trim() ? { asset_url: block.presentation.background.assetUrl.trim() } : {}),
              ...(block.presentation.background.fit ? { fit: block.presentation.background.fit } : {}),
              ...(block.presentation.background.position ? {
                position: ({
                  topLeft: "top_left",
                  topRight: "top_right",
                  bottomLeft: "bottom_left",
                  bottomRight: "bottom_right",
                } as const)[block.presentation.background.position as "topLeft"] ?? block.presentation.background.position,
              } : {}),
              ...(block.presentation.background.aspectRatio ? { aspect_ratio: block.presentation.background.aspectRatio } : {}),
              ...(typeof block.presentation.background.focalX === "number" ? { focal_x: block.presentation.background.focalX } : {}),
              ...(typeof block.presentation.background.focalY === "number" ? { focal_y: block.presentation.background.focalY } : {}),
              ...(typeof block.presentation.background.scale === "number" ? { scale: block.presentation.background.scale } : {}),
              ...(typeof block.presentation.background.opacity === "number" ? { opacity: block.presentation.background.opacity } : {}),
              ...(block.presentation.background.overlay ? { overlay: block.presentation.background.overlay } : {}),
            },
          } : {}),
        },
      } : {}),
      ...(block.actionItems?.length ? {
        action_items: block.actionItems.map((item) => ({
          id: item.id,
          title: item.title.trim(),
          ...(item.summary?.trim() ? { summary: item.summary.trim() } : {}),
          ...(item.label?.trim() ? { label: item.label.trim() } : {}),
          ...(item.tag?.trim() ? { tag: item.tag.trim() } : {}),
          ...(item.icon ? { icon: item.icon } : {}),
          ...(item.date?.trim() ? { date: item.date.trim() } : {}),
          ...(item.location?.trim() ? { location: item.location.trim() } : {}),
          ...(item.source?.trim() ? { source: item.source.trim() } : {}),
          ...(item.status?.trim() ? { status: item.status.trim() } : {}),
          ...(item.duration?.trim() ? { duration: item.duration.trim() } : {}),
          ...(item.imageUrl?.trim() ? { image_url: item.imageUrl.trim() } : {}),
          target_type: item.targetType,
          target_value: item.targetType === "phone"
            ? item.targetValue.trim().replace(/^tel:/i, "")
            : item.targetValue.trim(),
          open_mode: item.openMode,
        })),
      } : {}),
      ...(block.type === "faq" ? {
        faq_mode: block.faqMode === "selected" ? "selected" : "all_published",
        ...(block.faqMode === "selected" && block.faqDocumentIds?.length
          ? { faq_document_ids: block.faqDocumentIds.map((value) => value.trim()).filter(Boolean) }
          : {}),
      } : {}),
      ...(block.ctaLabel?.trim() ? { cta_label: block.ctaLabel.trim() } : {}),
      ...(block.ctaUrl?.trim() ? { cta_url: block.ctaUrl.trim() } : {}),
    })),
  };
}

function normalizeLatestVersion(raw: unknown): KnowledgeDocument["latestVersion"] {
  if (!isRecord(raw)) return undefined;
  return {
    id: requireId(raw, "知识版本"),
    versionNumber: optionalNumber(raw.version_number) ?? 1,
    reviewStatus: optionalString(raw.review_status),
    chunkCount: optionalNumber(raw.chunk_count) ?? 0,
    indexedChunkCount: optionalNumber(raw.indexed_chunk_count) ?? 0,
    indexStatus: optionalString(raw.index_status) || undefined,
    indexErrorCode: optionalString(raw.index_error_code) || undefined,
  };
}

function normalizeDocument(raw: unknown): KnowledgeDocument {
  if (!isRecord(raw)) {
    throw new ApiError("知识列表包含无法识别的数据。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  const visibility = optionalString(raw.visibility);
  return {
    id: requireId(raw, "知识条目"),
    title: optionalString(raw.title),
    status: optionalString(raw.status) || "draft",
    sourceType: optionalString(raw.source_type) || undefined,
    visibility: (["public", "authenticated", "internal"] as string[]).includes(visibility)
      ? visibility as KnowledgeVisibility
      : undefined,
    version: optionalNumber(raw.version),
    latestVersion: normalizeLatestVersion(raw.latest_version),
    updatedAt: optionalString(raw.updated_at) || undefined,
  };
}

function normalizeDocuments(payload: unknown): KnowledgeDocument[] {
  const raw = unwrapData(payload);
  if (!Array.isArray(raw)) {
    throw new ApiError("知识列表接口返回了无法识别的数据。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  return raw.map(normalizeDocument);
}

function normalizeSelectableFaqDocuments(payload: unknown): SelectableFaqDocument[] {
  const raw = unwrapData(payload);
  if (!Array.isArray(raw)) {
    throw new ApiError("可选 FAQ 接口返回了无法识别的数据。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  return raw.map((item) => {
    const record = requireRecord(item, "可选 FAQ");
    return {
      id: requireId(record, "可选 FAQ"),
      title: requireString(record.title, "可选 FAQ title"),
      answer: requireString(record.answer, "可选 FAQ answer"),
      status: "published",
      visibility: "public",
    };
  });
}

function requireNumber(value: unknown, label: string): number {
  const normalized = optionalNumber(value);
  if (normalized === undefined) {
    throw new ApiError(`${label}缺少有效数字。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return normalized;
}

function normalizeVisibility(value: unknown, label: string): ContentVisibility {
  const visibility = optionalString(value) || "public";
  if (!(["public", "authenticated", "internal"] as string[]).includes(visibility)) {
    throw new ApiError(`${label}包含无法识别的 visibility。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return visibility as ContentVisibility;
}

function normalizeStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function normalizeList<T>(
  payload: unknown,
  label: string,
  normalizer: (value: unknown) => T,
): T[] {
  const raw = unwrapData(payload);
  if (!Array.isArray(raw)) {
    throw new ApiError(`${label}接口返回了无法识别的数据。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return raw.map(normalizer);
}

function normalizeProduct(rawValue: unknown): Product {
  if (!isRecord(rawValue)) {
    throw new ApiError("产品列表包含无法识别的数据。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  return {
    id: requireId(rawValue, "产品"),
    slug: requireString(rawValue.slug, "产品 slug"),
    name: optionalString(rawValue.name),
    category: optionalString(rawValue.category),
    summary: optionalString(rawValue.summary),
    detail: optionalString(rawValue.detail),
    audience: optionalString(rawValue.audience),
    priceBoundary: optionalString(rawValue.price_boundary),
    imageUrl: optionalString(rawValue.image_url),
    visibility: normalizeVisibility(rawValue.visibility, "产品"),
    sortOrder: optionalNumber(rawValue.sort_order) ?? 0,
    settings: isRecord(rawValue.settings) ? rawValue.settings : {},
    status: optionalString(rawValue.status) || "draft",
    version: requireNumber(rawValue.version, "产品 version"),
    publishedAt: optionalString(rawValue.published_at) || undefined,
    createdAt: optionalString(rawValue.created_at) || undefined,
    updatedAt: optionalString(rawValue.updated_at) || undefined,
  };
}

function normalizeCaseStudy(rawValue: unknown): CaseStudy {
  if (!isRecord(rawValue)) {
    throw new ApiError("案例列表包含无法识别的数据。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  return {
    id: requireId(rawValue, "案例"),
    slug: requireString(rawValue.slug, "案例 slug"),
    title: optionalString(rawValue.title),
    industry: optionalString(rawValue.industry),
    background: optionalString(rawValue.background),
    solution: optionalString(rawValue.solution),
    result: optionalString(rawValue.result),
    clientDisplayName: optionalString(rawValue.client_display_name),
    imageUrl: optionalString(rawValue.image_url),
    visibility: normalizeVisibility(rawValue.visibility, "案例"),
    sortOrder: optionalNumber(rawValue.sort_order) ?? 0,
    settings: isRecord(rawValue.settings) ? rawValue.settings : {},
    status: optionalString(rawValue.status) || "draft",
    version: requireNumber(rawValue.version, "案例 version"),
    publishedAt: optionalString(rawValue.published_at) || undefined,
    createdAt: optionalString(rawValue.created_at) || undefined,
    updatedAt: optionalString(rawValue.updated_at) || undefined,
  };
}

function normalizeForbiddenTopic(rawValue: unknown): ForbiddenTopic {
  if (!isRecord(rawValue)) {
    throw new ApiError("禁答主题列表包含无法识别的数据。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  const action = optionalString(rawValue.action) || "refuse";
  if (!("refuse handoff safe_template".split(" ") as string[]).includes(action)) {
    throw new ApiError("禁答主题包含无法识别的 action。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  return {
    id: requireId(rawValue, "禁答主题"),
    topic: optionalString(rawValue.topic),
    matchTerms: normalizeStringArray(rawValue.match_terms),
    action: action as ForbiddenAction,
    safeResponse: optionalString(rawValue.safe_response),
    isActive: rawValue.is_active !== false,
    version: requireNumber(rawValue.version, "禁答主题 version"),
    createdAt: optionalString(rawValue.created_at) || undefined,
    updatedAt: optionalString(rawValue.updated_at) || undefined,
  };
}

function normalizeManagedCard(rawValue: unknown): ManagedCard {
  if (!isRecord(rawValue)) {
    throw new ApiError("名片列表包含无法识别的数据。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  const policies = isRecord(rawValue.policy_versions)
    ? rawValue.policy_versions
    : {};
  const cardKind = optionalString(rawValue.card_kind);
  if (cardKind !== "enterprise" && cardKind !== "employee") {
    throw new ApiError("名片包含无法识别的业务类型。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  const ownerUserId = optionalString(rawValue.owner_user_id) || undefined;
  const contactFields = Array.isArray(rawValue.contact_fields)
    ? rawValue.contact_fields.flatMap((rawContact, index) => {
        if (!isRecord(rawContact)) return [];
        const label = optionalString(rawContact.label);
        const value = optionalString(rawContact.value);
        if (!label || !value) return [];
        const rawKind = optionalString(rawContact.kind) || optionalString(rawContact.type);
        const kind = (["phone", "wechat", "email", "location", "website", "other"] as const)
          .find((value) => value === rawKind) ?? "other";
        return [{
          id: optionalString(rawContact.id) || `contact-${index + 1}`,
          kind,
          label,
          value,
          href: optionalString(rawContact.href) || undefined,
        }];
      })
    : [];
  if (cardKind === "employee" && !ownerUserId) {
    throw new ApiError("员工名片缺少有效所有者。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  if (cardKind === "enterprise" && ownerUserId) {
    throw new ApiError("企业官方名片不能绑定员工所有者。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  return {
    id: requireId(rawValue, "名片"),
    cardKind,
    ownerUserId,
    slug: requireString(rawValue.slug, "名片 slug"),
    displayName: optionalString(rawValue.display_name),
    title: optionalString(rawValue.title),
    avatarUrl: optionalString(rawValue.avatar_url),
    assistantName: optionalString(rawValue.assistant_name),
    welcomeMessage: optionalString(rawValue.welcome_message),
    suggestedQuestions: normalizeStringArray(rawValue.suggested_questions),
    policyVersions: {
      privacy: optionalString(policies.privacy),
      chatNotice: optionalString(policies.chat_notice),
      leadConsent: optionalString(policies.lead_consent),
    },
    identityTitles: normalizeStringArray(rawValue.identity_titles).slice(0, 8),
    contactFields,
    employeeContactVisibility: normalizeStringArray(rawValue.employee_contact_visibility)
      .filter((value): value is "mobile" | "email" => value === "mobile" || value === "email"),
    status: optionalString(rawValue.status) || "draft",
    version: requireNumber(rawValue.version, "名片 version"),
    shareUrl: requireString(rawValue.share_url, "名片 share_url"),
    qrUrl: requireString(rawValue.qr_url, "名片 qr_url"),
    publishedAt: optionalString(rawValue.published_at) || undefined,
    createdAt: optionalString(rawValue.created_at) || undefined,
    updatedAt: optionalString(rawValue.updated_at) || undefined,
  };
}

function normalizeWeComCardContactWay(payload: unknown): WeComCardContactWay {
  const rawValue = requireRecord(payload, "企微联系入口");
  return {
    id: requireId(rawValue, "企微联系入口"),
    cardId: requireString(rawValue.card_id, "企微联系入口 card_id"),
    ownerUserId: requireString(rawValue.owner_user_id, "企微联系入口 owner_user_id"),
    qrCodeUrl: optionalString(rawValue.qr_code_url) || undefined,
    provisionedAt: requireString(rawValue.provisioned_at, "企微联系入口 provisioned_at"),
  };
}

function normalizeCardAssetUpload(rawValue: unknown): CardAssetUpload {
  const data = requireRecord(rawValue, "名片图片");
  const contentType = requireString(data.content_type, "名片图片 content_type");
  if (contentType !== "image/webp") {
    throw new ApiError("名片图片接口返回了不支持的格式。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  return {
    url: requireString(data.url, "名片图片 url"),
    contentType,
    width: requireNumber(data.width, "名片图片 width"),
    height: requireNumber(data.height, "名片图片 height"),
    sizeBytes: requireNumber(data.size_bytes, "名片图片 size_bytes"),
  };
}

function normalizeCardVideoAssetUpload(rawValue: unknown): CardVideoAssetUpload {
  const data = requireRecord(rawValue, "名片视频");
  const contentType = requireString(data.content_type, "名片视频 content_type");
  if (contentType !== "video/mp4" && contentType !== "video/webm") {
    throw new ApiError("名片视频接口返回了不支持的格式。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  return {
    url: requireString(data.url, "名片视频 url"),
    contentType,
    sizeBytes: requireNumber(data.size_bytes, "名片视频 size_bytes"),
  };
}

function normalizeKnowledgeDetail(payload: unknown): KnowledgeDocumentDetail {
  const raw = requireRecord(payload, "知识详情");
  const record = normalizeDocument(raw);
  const visibility = optionalString(raw.visibility) || "public";
  if (!(["public", "authenticated", "internal"] as string[]).includes(visibility)) {
    throw new ApiError("知识详情包含无法识别的 visibility。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  return {
    ...record,
    rawText: optionalString(raw.raw_text),
    visibility: visibility as KnowledgeVisibility,
    metadata: isRecord(raw.metadata) ? raw.metadata : {},
    editableVersionId: optionalString(raw.editable_version_id) || undefined,
  };
}

function companyPayload(input: CompanyProfileInput) {
  return {
    name: input.name.trim(),
    summary: input.summary.trim(),
    industry: nullableString(input.industry),
    region: nullableString(input.region),
    website: nullableString(input.website),
    logo_url: nullableString(input.logoUrl),
    profile_personalization_policy_version:
      input.profilePersonalizationPolicyVersion.trim(),
  };
}

function cardPayload(input: CardSettingsInput) {
  const policyVersions = Object.fromEntries(
    [
      ["privacy", input.policyVersions.privacy],
      ["chat_notice", input.policyVersions.chatNotice],
      ["lead_consent", input.policyVersions.leadConsent],
    ]
      .map(([key, value]) => [key, value.trim()] as const)
      .filter(([, value]) => value.length > 0),
  );
  return {
    slug: input.slug.trim(),
    display_name: input.displayName.trim(),
    title: input.title.trim(),
    avatar_url: nullableString(input.avatarUrl),
    assistant_name: nullableString(input.assistantName),
    welcome_message: nullableString(input.welcomeMessage),
    suggested_questions: input.suggestedQuestions
      .map((value) => value.trim())
      .filter(Boolean)
      .slice(0, 6),
    policy_versions: policyVersions,
  };
}

function knowledgeDraftPayload(input: KnowledgeDocumentInput) {
  return {
    raw_text: input.answer.trim(),
    title: input.title.trim(),
    visibility: input.visibility,
    metadata: input.metadata,
  };
}

function productPayload(input: ProductInput) {
  return {
    slug: input.slug.trim(),
    name: input.name.trim(),
    category: nullableString(input.category),
    summary: input.summary.trim(),
    detail: input.detail.trim(),
    audience: nullableString(input.audience),
    price_boundary: nullableString(input.priceBoundary),
    image_url: nullableString(input.imageUrl),
    visibility: input.visibility,
    sort_order: input.sortOrder,
    settings: input.settings,
  };
}

function caseStudyPayload(input: CaseStudyInput) {
  return {
    slug: input.slug.trim(),
    title: input.title.trim(),
    industry: nullableString(input.industry),
    background: input.background.trim(),
    solution: input.solution.trim(),
    result: input.result.trim(),
    client_display_name: nullableString(input.clientDisplayName),
    image_url: nullableString(input.imageUrl),
    visibility: input.visibility,
    sort_order: input.sortOrder,
    settings: input.settings,
  };
}

function forbiddenTopicPayload(input: ForbiddenTopicInput) {
  return {
    topic: input.topic.trim(),
    match_terms: input.matchTerms.map((value) => value.trim()).filter(Boolean),
    action: input.action,
    safe_response: nullableString(input.safeResponse),
  };
}

function managedCardPayload(input: ManagedCardInput, requireOwner: boolean) {
  const ownerUserId = input.ownerUserId?.trim();
  if (input.cardKind === "employee" && requireOwner && !ownerUserId) {
    throw new ApiError("编辑名片时必须保留有效的所有者。", {
      code: "INVALID_CARD_OWNER",
    });
  }
  const policyVersions = Object.fromEntries(
    [
      ["privacy", input.policyVersions.privacy],
      ["chat_notice", input.policyVersions.chatNotice],
      ["lead_consent", input.policyVersions.leadConsent],
    ]
      .map(([key, value]) => [key, value.trim()] as const)
      .filter(([, value]) => value.length > 0),
  );
  return {
    card_kind: input.cardKind,
    ...(input.cardKind === "employee" && ownerUserId
      ? { owner_user_id: ownerUserId }
      : {}),
    ...(!requireOwner && input.templateDocument
      ? {
          template_document: enterpriseTemplatePayload(
            input.templateDocument.themeKey,
            input.templateDocument.blocks,
          ),
        }
      : !requireOwner && input.templateSourceCardId?.trim()
        ? { template_source_card_id: input.templateSourceCardId.trim() }
        : {}),
    display_name: input.displayName.trim() || "员工名片",
    title: input.title.trim(),
    ...(input.cardKind === "enterprise"
      ? { avatar_url: nullableString(input.avatarUrl) }
      : {}),
    assistant_name: nullableString(input.assistantName),
    welcome_message: nullableString(input.welcomeMessage),
    suggested_questions: input.suggestedQuestions
      .map((value) => value.trim())
      .filter(Boolean)
      .slice(0, 6),
    identity_titles: input.identityTitles
      .map((value) => value.trim())
      .filter(Boolean)
      .slice(0, 8),
    contact_fields: input.contactFields
      .filter((field) => field.label.trim() && field.value.trim())
      .slice(0, 8)
      .map((field) => ({
        id: field.id,
        kind: field.kind,
        label: field.label.trim(),
        value: field.value.trim(),
        ...(field.href?.trim() ? { href: field.href.trim() } : {}),
      })),
    policy_versions: policyVersions,
    ...(input.cardKind === "employee"
      ? { employee_contact_visibility: input.employeeContactVisibility }
      : {}),
  };
}

export function createAdminApi(client: ApiClient) {
  return {
  async me(): Promise<AdminUser> {
    const data = requireRecord(await client.get("/auth/me"), "当前用户");
    const user = requireNestedRecord(data, "user", "当前用户");
    const membership = requireNestedRecord(data, "membership", "当前用户");
    const permissions = Array.isArray(membership.permissions)
      ? membership.permissions.filter(
          (value): value is string => typeof value === "string",
        )
      : [];
    return {
      id: requireId(user, "当前用户"),
      displayName: requireString(user.display_name, "当前用户 display_name"),
      membershipId: requireId(membership, "当前成员关系"),
      tenantId: requireString(membership.tenant_id, "tenant_id"),
      companyId: requireString(membership.company_id, "company_id"),
      role: optionalString(membership.role) || undefined,
      permissions,
    };
  },

  async getCompanyProfile(): Promise<CompanyProfile> {
    return normalizeCompany(await client.get("/admin/company/profile"));
  },

  async updateCompanyProfile(input: CompanyProfileInput): Promise<void> {
    await client.put(
      "/admin/company/profile",
      companyPayload(input),
      { version: input.version },
    );
  },

  async getCard(): Promise<CardSettings> {
    return normalizeCard(await client.get("/admin/card"));
  },

  async updateCard(input: CardSettingsInput): Promise<void> {
    await client.put("/admin/card", cardPayload(input), {
      version: input.version,
    });
  },

  async completeEnterpriseSetup(): Promise<void> {
    await client.post("/admin/setup/complete", {});
  },

  async listKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
    return normalizeDocuments(
      await client.get("/admin/knowledge/documents"),
    );
  },

  async listSelectableFaqDocuments(): Promise<SelectableFaqDocument[]> {
    return normalizeSelectableFaqDocuments(
      await client.get("/admin/knowledge/documents?selectable_faq=true"),
    );
  },

  async getKnowledgeDocument(id: string): Promise<KnowledgeDocumentDetail> {
    return normalizeKnowledgeDetail(
      await client.get(
        `/admin/knowledge/documents/${encodeURIComponent(id)}`,
      ),
    );
  },

  async createKnowledgeDocument(title: string): Promise<string> {
    const raw = requireRecord(
      await client.post("/admin/knowledge/documents", {
        title: title.trim(),
        source_type: "faq",
      }),
      "新建知识",
    );
    return requireId(raw, "新建知识");
  },

  async updateKnowledgeDocument(
    id: string,
    input: KnowledgeDocumentInput,
  ): Promise<void> {
    await client.put(
      `/admin/knowledge/documents/${encodeURIComponent(id)}`,
      knowledgeDraftPayload(input),
    );
  },

  async publishKnowledgeDocument(id: string): Promise<void> {
    await client.post(
      `/admin/knowledge/documents/${encodeURIComponent(id)}/publish`,
      {},
    );
  },

  async deleteKnowledgeDocument(id: string, version: number): Promise<void> {
    await client.delete(
      `/admin/knowledge/documents/${encodeURIComponent(id)}`,
      { version },
    );
  },

  async listProducts(): Promise<Product[]> {
    return normalizeList(
      await client.get("/admin/products?limit=100&offset=0"),
      "产品列表",
      normalizeProduct,
    );
  },

  async createProduct(input: ProductInput): Promise<Product> {
    return normalizeProduct(
      unwrapData(await client.post("/admin/products", productPayload(input))),
    );
  },

  async updateProduct(
    id: string,
    version: number,
    input: ProductInput,
  ): Promise<Product> {
    return normalizeProduct(
      unwrapData(
        await client.patch(
          `/admin/products/${encodeURIComponent(id)}`,
          productPayload(input),
          { version },
        ),
      ),
    );
  },

  async publishProduct(id: string, version: number): Promise<Product> {
    return normalizeProduct(
      unwrapData(
        await client.post(
          `/admin/products/${encodeURIComponent(id)}:publish`,
          {},
          { version },
        ),
      ),
    );
  },

  async archiveProduct(id: string, version: number): Promise<Product> {
    return normalizeProduct(
      unwrapData(
        await client.post(
          `/admin/products/${encodeURIComponent(id)}/archive`,
          {},
          { version },
        ),
      ),
    );
  },

  async deleteProduct(id: string, version: number): Promise<void> {
    await client.delete(`/admin/products/${encodeURIComponent(id)}`, { version });
  },

  async listCaseStudies(): Promise<CaseStudy[]> {
    return normalizeList(
      await client.get("/admin/cases?limit=100&offset=0"),
      "案例列表",
      normalizeCaseStudy,
    );
  },

  async createCaseStudy(input: CaseStudyInput): Promise<CaseStudy> {
    return normalizeCaseStudy(
      unwrapData(await client.post("/admin/cases", caseStudyPayload(input))),
    );
  },

  async updateCaseStudy(
    id: string,
    version: number,
    input: CaseStudyInput,
  ): Promise<CaseStudy> {
    return normalizeCaseStudy(
      unwrapData(
        await client.patch(
          `/admin/cases/${encodeURIComponent(id)}`,
          caseStudyPayload(input),
          { version },
        ),
      ),
    );
  },

  async publishCaseStudy(id: string, version: number): Promise<CaseStudy> {
    return normalizeCaseStudy(
      unwrapData(
        await client.post(
          `/admin/cases/${encodeURIComponent(id)}:publish`,
          {},
          { version },
        ),
      ),
    );
  },

  async archiveCaseStudy(id: string, version: number): Promise<CaseStudy> {
    return normalizeCaseStudy(
      unwrapData(
        await client.post(
          `/admin/case-studies/${encodeURIComponent(id)}/archive`,
          {},
          { version },
        ),
      ),
    );
  },

  async deleteCaseStudy(id: string, version: number): Promise<void> {
    await client.delete(`/admin/cases/${encodeURIComponent(id)}`, { version });
  },

  async listForbiddenTopics(): Promise<ForbiddenTopic[]> {
    return normalizeList(
      await client.get("/admin/forbidden-topics?limit=100&offset=0"),
      "禁答主题列表",
      normalizeForbiddenTopic,
    );
  },

  async createForbiddenTopic(
    input: ForbiddenTopicInput,
  ): Promise<ForbiddenTopic> {
    return normalizeForbiddenTopic(
      unwrapData(
        await client.post("/admin/forbidden-topics", {
          ...forbiddenTopicPayload(input),
          is_active: input.isActive,
        }),
      ),
    );
  },

  async updateForbiddenTopic(
    id: string,
    version: number,
    input: ForbiddenTopicInput,
  ): Promise<ForbiddenTopic> {
    return normalizeForbiddenTopic(
      unwrapData(
        await client.patch(
          `/admin/forbidden-topics/${encodeURIComponent(id)}`,
          forbiddenTopicPayload(input),
          { version },
        ),
      ),
    );
  },

  async setForbiddenTopicActive(
    id: string,
    version: number,
    active: boolean,
  ): Promise<ForbiddenTopic> {
    return normalizeForbiddenTopic(
      unwrapData(
        await client.post(
          `/admin/forbidden-topics/${encodeURIComponent(id)}/${
            active ? "activate" : "deactivate"
          }`,
          {},
          { version },
        ),
      ),
    );
  },

  async deleteForbiddenTopic(id: string, version: number): Promise<void> {
    await client.delete(`/admin/forbidden-topics/${encodeURIComponent(id)}`, {
      version,
    });
  },

  async listManagedCards(): Promise<ManagedCard[]> {
    return normalizeList(
      await client.get("/admin/cards?limit=100&offset=0"),
      "名片列表",
      normalizeManagedCard,
    );
  },

  async uploadCardAsset(file: File): Promise<CardAssetUpload> {
    const body = new FormData();
    body.append("file", file);
    return normalizeCardAssetUpload(
      unwrapData(await client.postForm("/admin/card-assets", body)),
    );
  },

  async uploadCardVideoAsset(file: File): Promise<CardVideoAssetUpload> {
    const body = new FormData();
    body.append("file", file);
    return normalizeCardVideoAssetUpload(
      unwrapData(await client.postForm("/admin/card-video-assets", body)),
    );
  },

  async createManagedCard(input: ManagedCardInput): Promise<ManagedCard> {
    return normalizeManagedCard(
      unwrapData(
        await client.post("/admin/cards", managedCardPayload(input, false)),
      ),
    );
  },

  async updateManagedCard(
    id: string,
    version: number,
    input: ManagedCardInput,
  ): Promise<ManagedCard> {
    return normalizeManagedCard(
      unwrapData(
        await client.patch(
          `/admin/cards/${encodeURIComponent(id)}`,
          managedCardPayload(input, true),
          { version },
        ),
      ),
    );
  },

  async publishManagedCard(id: string, version: number): Promise<ManagedCard> {
    return normalizeManagedCard(
      unwrapData(
        await client.post(
          `/admin/cards/${encodeURIComponent(id)}:publish`,
          {},
          { version },
        ),
      ),
    );
  },

  async getEnterpriseTemplate(id: string): Promise<EnterpriseTemplate> {
    return normalizeEnterpriseTemplate(
      await client.get(`/admin/cards/${encodeURIComponent(id)}/enterprise-template`),
    );
  },

  async updateEnterpriseTemplate(
    id: string,
    version: number,
    themeKey: EnterpriseTemplateThemeKey,
    blocks: EnterpriseTemplateBlock[],
  ): Promise<EnterpriseTemplate> {
    return normalizeEnterpriseTemplate(
      await client.put(
        `/admin/cards/${encodeURIComponent(id)}/enterprise-template`,
        enterpriseTemplatePayload(themeKey, blocks),
        { version },
      ),
    );
  },

  async getCardComposerDefault(cardKind: ManagedCard["cardKind"]): Promise<CardComposerDefault> {
    return normalizeCardComposerDefault(
      await client.get(`/admin/card-composer/defaults/${encodeURIComponent(cardKind)}`),
    );
  },

  async updateCardComposerDefault(
    cardKind: ManagedCard["cardKind"],
    version: number,
    themeKey: EnterpriseTemplateThemeKey,
    blocks: EnterpriseTemplateBlock[],
  ): Promise<CardComposerDefault> {
    return normalizeCardComposerDefault(
      await client.put(
        `/admin/card-composer/defaults/${encodeURIComponent(cardKind)}`,
        enterpriseTemplatePayload(themeKey, blocks),
        { version },
      ),
    );
  },

  async deactivateManagedCard(
    id: string,
    version: number,
  ): Promise<ManagedCard> {
    return normalizeManagedCard(
      unwrapData(
        await client.post(
          `/admin/cards/${encodeURIComponent(id)}:deactivate`,
          {},
          { version },
        ),
      ),
    );
  },

  async provisionWeComCardContactWay(id: string): Promise<WeComCardContactWay> {
    return normalizeWeComCardContactWay(
      await client.post(
        `/admin/cards/${encodeURIComponent(id)}/wecom-contact-way`,
        {},
      ),
    );
  },
  };
}

export const adminApi = createAdminApi(apiClient);

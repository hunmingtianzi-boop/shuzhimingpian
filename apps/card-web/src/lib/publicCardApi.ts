type PublicLinkItem = Record<string, string>;

export type PublicEnterpriseTemplateBlock = {
  id: string;
  type: "identity" | "rich_text" | "business_collection" | "image_gallery" | "video_link" | "case_collection" | "trust_panel" | "faq" | "cta" | "ai_assistant";
  title?: string;
  body?: string;
  visible?: boolean;
  directory_enabled?: boolean;
  sort_order?: number;
  image_urls?: string[];
  video_url?: string;
  video_cover_url?: string;
  product_ids?: string[];
  product_items?: Array<{
    id: string;
    slug: string;
    name: string;
    category?: string;
    summary?: string;
    image_url?: string;
  }>;
  case_ids?: string[];
  case_items?: Array<{
    id: string;
    slug: string;
    title: string;
    industry?: string;
    summary?: string;
    image_url?: string;
  }>;
  faq_mode?: "all_published" | "selected";
  faq_document_ids?: string[];
  cta_label?: string;
  cta_url?: string;
  background?: {
    kind: "none" | "color" | "image";
    color?: string;
    image_url?: string;
    fit?: "cover" | "contain";
    position_x?: number;
    position_y?: number;
    overlay_color?: string;
    overlay_opacity?: number;
  };
  text_tone?: "auto" | "light" | "dark";
  content_image?: {
    url: string;
    alt?: string;
    placement: "top" | "bottom" | "left" | "right";
    fit?: "cover" | "contain";
    aspect_ratio?: "auto" | "square" | "standard" | "wide";
    width_percent?: number;
    position_x?: number;
    position_y?: number;
  };
  size_preset?: "auto" | "compact" | "standard" | "tall";
  padding_y?: "auto" | "compact" | "standard" | "spacious";
};

export type PublicCardData = {
  id: string;
  slug: string;
  card_kind?: "enterprise" | "employee";
  display_name: string;
  title: string;
  avatar_url?: string | null;
  business_summary?: string | null;
  contact_fields: PublicLinkItem[];
  wecom_contact?: {
    available: boolean;
    qr_code_url?: string | null;
    label: string;
  } | null;
  company: {
    id: string;
    name: string;
    summary: string;
    industry?: string | null;
    region?: string | null;
    website?: string | null;
    logo_url?: string | null;
    official_card_slug?: string | null;
  };
  featured_products: PublicLinkItem[];
  featured_cases: PublicLinkItem[];
  faq_items: Array<{
    id: string;
    document_id?: string;
    question: string;
    answer: string;
    source_label: string;
  }>;
  ai_assistant: {
    available: boolean;
    display_name: string;
    disclosure: string;
    welcome_message: string;
    suggested_questions: string[];
  };
  policy_versions: {
    privacy: string;
    chat_notice: string;
    lead_consent: string;
    profile_personalization: string;
  };
  enterprise_template?: {
    schema_version: 1;
    theme_key?: "brand" | "clean" | "warm";
    page_background?: PublicEnterpriseTemplateBlock["background"];
    page_text_tone?: "auto" | "light" | "dark";
    blocks: PublicEnterpriseTemplateBlock[];
  } | null;
};

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(record: JsonRecord, key: string) {
  const value = record[key];
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Public card response is missing ${key}`);
  }
  return value.trim();
}

function optionalString(record: JsonRecord, key: string) {
  const value = record[key];
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function optionalNumber(record: JsonRecord, key: string) {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stringRecordList(value: unknown): PublicLinkItem[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!isRecord(item)) return [];
    const result = Object.fromEntries(
      Object.entries(item).flatMap(([key, rawValue]) =>
        typeof rawValue === "string" && rawValue.trim()
          ? [[key, rawValue.trim()]]
          : [],
      ),
    );
    return Object.keys(result).length ? [result] : [];
  });
}

function parseEnterpriseTemplate(value: unknown): PublicCardData["enterprise_template"] {
  if (!isRecord(value) || !Array.isArray(value.blocks)) return undefined;
  const types = new Set(["identity", "rich_text", "business_collection", "image_gallery", "video_link", "case_collection", "trust_panel", "faq", "cta", "ai_assistant"]);
  const blocks = value.blocks.flatMap((raw) => {
    if (!isRecord(raw) || typeof raw.id !== "string" || typeof raw.type !== "string" || !types.has(raw.type)) return [];
    const strings = (item: unknown) => Array.isArray(item) ? item.filter((entry): entry is string => typeof entry === "string" && Boolean(entry.trim())) : undefined;
    const productItems = Array.isArray(raw.product_items) ? raw.product_items.flatMap((item) => {
      if (
        !isRecord(item)
        || typeof item.id !== "string"
        || typeof item.slug !== "string"
        || typeof item.name !== "string"
      ) return [];
      return [{ id: item.id, slug: item.slug, name: item.name, category: optionalString(item, "category"), summary: optionalString(item, "summary"), image_url: optionalString(item, "image_url") }];
    }) : undefined;
    const caseItems = Array.isArray(raw.case_items) ? raw.case_items.flatMap((item) => {
      if (
        !isRecord(item)
        || typeof item.id !== "string"
        || typeof item.slug !== "string"
        || typeof item.title !== "string"
      ) return [];
      return [{ id: item.id, slug: item.slug, title: item.title, industry: optionalString(item, "industry"), summary: optionalString(item, "summary"), image_url: optionalString(item, "image_url") }];
    }) : undefined;
    const faqMode: PublicEnterpriseTemplateBlock["faq_mode"] = raw.type === "faq"
      ? raw.faq_mode === "selected" ? "selected" : "all_published"
      : undefined;
    const rawBackground = isRecord(raw.background) ? raw.background : undefined;
    const backgroundKind: NonNullable<PublicEnterpriseTemplateBlock["background"]>["kind"] = rawBackground && (
      rawBackground.kind === "color" || rawBackground.kind === "image"
    ) ? rawBackground.kind : "none";
    const backgroundFit: NonNullable<PublicEnterpriseTemplateBlock["background"]>["fit"] =
      rawBackground?.fit === "contain" ? "contain" : "cover";
    const rawContentImage = isRecord(raw.content_image) ? raw.content_image : undefined;
    const contentImageUrl = rawContentImage ? optionalString(rawContentImage, "url") : undefined;
    const contentPlacement: NonNullable<PublicEnterpriseTemplateBlock["content_image"]>["placement"] = rawContentImage && (
      rawContentImage.placement === "bottom"
      || rawContentImage.placement === "left"
      || rawContentImage.placement === "right"
    ) ? rawContentImage.placement : "top";
    const contentFit: NonNullable<PublicEnterpriseTemplateBlock["content_image"]>["fit"] =
      rawContentImage?.fit === "contain" ? "contain" : "cover";
    const contentAspectRatio: NonNullable<PublicEnterpriseTemplateBlock["content_image"]>["aspect_ratio"] =
      rawContentImage && ["auto", "square", "standard", "wide"].includes(optionalString(rawContentImage, "aspect_ratio") ?? "")
        ? optionalString(rawContentImage, "aspect_ratio") as NonNullable<PublicEnterpriseTemplateBlock["content_image"]>["aspect_ratio"]
        : "wide";
    const textTone: PublicEnterpriseTemplateBlock["text_tone"] =
      raw.text_tone === "light" || raw.text_tone === "dark" ? raw.text_tone : "auto";
    const sizePreset: PublicEnterpriseTemplateBlock["size_preset"] =
      raw.size_preset === "compact" || raw.size_preset === "standard" || raw.size_preset === "tall"
        ? raw.size_preset
        : "auto";
    const paddingY: PublicEnterpriseTemplateBlock["padding_y"] =
      raw.padding_y === "compact" || raw.padding_y === "standard" || raw.padding_y === "spacious"
        ? raw.padding_y
        : "auto";
    return [{
      id: raw.id,
      type: raw.type as PublicEnterpriseTemplateBlock["type"],
      visible: raw.visible !== false,
      directory_enabled: raw.directory_enabled !== false,
      sort_order: typeof raw.sort_order === "number" ? raw.sort_order : 0,
      title: optionalString(raw, "title"),
      body: optionalString(raw, "body"),
      image_urls: strings(raw.image_urls),
      video_url: optionalString(raw, "video_url"),
      video_cover_url: optionalString(raw, "video_cover_url"),
      product_ids: strings(raw.product_ids),
      product_items: productItems,
      case_ids: strings(raw.case_ids),
      case_items: caseItems,
      faq_mode: faqMode,
      faq_document_ids: strings(raw.faq_document_ids),
      cta_label: optionalString(raw, "cta_label"),
      cta_url: optionalString(raw, "cta_url"),
      background: rawBackground ? {
        kind: backgroundKind,
        color: optionalString(rawBackground, "color"),
        image_url: optionalString(rawBackground, "image_url"),
        fit: backgroundFit,
        position_x: optionalNumber(rawBackground, "position_x") ?? 50,
        position_y: optionalNumber(rawBackground, "position_y") ?? 50,
        overlay_color: optionalString(rawBackground, "overlay_color"),
        overlay_opacity: optionalNumber(rawBackground, "overlay_opacity") ?? 0,
      } : undefined,
      text_tone: textTone,
      content_image: contentImageUrl ? {
        url: contentImageUrl,
        alt: rawContentImage ? optionalString(rawContentImage, "alt") : undefined,
        placement: contentPlacement,
        fit: contentFit,
        aspect_ratio: contentAspectRatio,
        width_percent: rawContentImage ? optionalNumber(rawContentImage, "width_percent") : undefined,
        position_x: rawContentImage ? optionalNumber(rawContentImage, "position_x") ?? 50 : 50,
        position_y: rawContentImage ? optionalNumber(rawContentImage, "position_y") ?? 50 : 50,
      } : undefined,
      size_preset: sizePreset,
      padding_y: paddingY,
    }];
  });
  const theme = value.theme_key;
  const rawPageBackground = isRecord(value.page_background) ? value.page_background : undefined;
  const pageBackgroundKind: NonNullable<
    NonNullable<PublicCardData["enterprise_template"]>["page_background"]
  >["kind"] = rawPageBackground?.kind === "color" || rawPageBackground?.kind === "image"
      ? rawPageBackground.kind
      : "none";
  const pageTextTone: NonNullable<PublicCardData["enterprise_template"]>["page_text_tone"] =
    value.page_text_tone === "light" || value.page_text_tone === "dark" ? value.page_text_tone : "auto";
  return {
    schema_version: 1,
    theme_key: theme === "clean" || theme === "warm" ? theme : "brand",
    page_background: rawPageBackground ? {
      kind: pageBackgroundKind,
      color: optionalString(rawPageBackground, "color"),
      image_url: optionalString(rawPageBackground, "image_url"),
      fit: rawPageBackground.fit === "contain" ? "contain" : "cover",
      position_x: optionalNumber(rawPageBackground, "position_x") ?? 50,
      position_y: optionalNumber(rawPageBackground, "position_y") ?? 50,
      overlay_color: optionalString(rawPageBackground, "overlay_color"),
      overlay_opacity: optionalNumber(rawPageBackground, "overlay_opacity") ?? 0,
    } : undefined,
    page_text_tone: pageTextTone,
    blocks,
  };
}

function parsePublicCard(value: unknown): PublicCardData {
  if (!isRecord(value) || !isRecord(value.data)) {
    throw new Error("Public card response is invalid");
  }
  const data = value.data;
  if (!isRecord(data.company) || !isRecord(data.ai_assistant)) {
    throw new Error("Public card response is incomplete");
  }
  const company = data.company;
  const assistant = data.ai_assistant;
  const rawFaq = Array.isArray(data.faq_items) ? data.faq_items : [];

  return {
    id: requiredString(data, "id"),
    slug: requiredString(data, "slug"),
    card_kind:
      data.card_kind === "enterprise" || data.card_kind === "employee"
        ? data.card_kind
        : undefined,
    display_name: requiredString(data, "display_name"),
    title: requiredString(data, "title"),
    avatar_url: optionalString(data, "avatar_url"),
    business_summary: optionalString(data, "business_summary"),
    contact_fields: stringRecordList(data.contact_fields),
    wecom_contact: isRecord(data.wecom_contact)
      ? {
          available: data.wecom_contact.available === true,
          qr_code_url: optionalString(data.wecom_contact, "qr_code_url"),
          label:
            optionalString(data.wecom_contact, "label") || "添加企业微信",
        }
      : undefined,
    company: {
      id: requiredString(company, "id"),
      name: requiredString(company, "name"),
      summary: typeof company.summary === "string" ? company.summary.trim() : "",
      industry: optionalString(company, "industry"),
      region: optionalString(company, "region"),
      website: optionalString(company, "website"),
      logo_url: optionalString(company, "logo_url"),
      official_card_slug: optionalString(company, "official_card_slug"),
    },
    featured_products: stringRecordList(data.featured_products),
    featured_cases: stringRecordList(data.featured_cases),
    faq_items: rawFaq.flatMap((rawItem) => {
      if (!isRecord(rawItem)) return [];
      try {
        const id = requiredString(rawItem, "id");
        return [
          {
            id,
            document_id: optionalString(rawItem, "document_id") || id,
            question: requiredString(rawItem, "question"),
            answer: requiredString(rawItem, "answer"),
            source_label: requiredString(rawItem, "source_label"),
          },
        ];
      } catch {
        return [];
      }
    }),
    ai_assistant: {
      available: assistant.available === true,
      display_name: requiredString(assistant, "display_name"),
      disclosure: requiredString(assistant, "disclosure"),
      welcome_message: requiredString(assistant, "welcome_message"),
      suggested_questions: Array.isArray(assistant.suggested_questions)
        ? assistant.suggested_questions.filter(
            (item): item is string =>
              typeof item === "string" && Boolean(item.trim()),
          )
        : [],
    },
    policy_versions: isRecord(data.policy_versions)
      ? {
          privacy: requiredString(data.policy_versions, "privacy"),
          chat_notice: requiredString(data.policy_versions, "chat_notice"),
          lead_consent: requiredString(data.policy_versions, "lead_consent"),
          profile_personalization: requiredString(
            data.policy_versions,
            "profile_personalization",
          ),
        }
      : {
          privacy: "privacy-v1",
          chat_notice: "chat-notice-v1",
          lead_consent: "lead-v1",
          profile_personalization: "profile-personalization-v1",
      },
    enterprise_template: parseEnterpriseTemplate(data.enterprise_template),
  };
}

function getApiBaseUrl() {
  return (import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
}

export async function fetchPublicCard(
  slug: string,
  signal?: AbortSignal,
): Promise<PublicCardData | undefined> {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) return undefined;
  const response = await fetch(`${baseUrl}/public/cards/${encodeURIComponent(slug)}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (response.status === 404) return undefined;
  if (!response.ok) throw new Error(`Public card request failed with ${response.status}`);
  return parsePublicCard(await response.json());
}

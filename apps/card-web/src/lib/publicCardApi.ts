type PublicLinkItem = Record<string, string>;

export type PublicEnterpriseTemplateBlock = {
  id: string;
  type: "identity" | "rich_text" | "business_collection" | "image_gallery" | "video_link" | "case_collection" | "trust_panel" | "faq" | "cta" | "ai_assistant" | "action_collection";
  title?: string;
  body?: string;
  visible?: boolean;
  show_title?: boolean;
  directory_enabled?: boolean;
  sort_order?: number;
  layout_variant?: "auto" | "list" | "grid" | "carousel" | "featured" | "mosaic" | "horizontal" | "vertical";
  item_limit?: number;
  action_template?: "shortcuts" | "media" | "event" | "banner" | "articles" | "video" | "buttons";
  presentation?: {
    identity_layout?: "horizontal" | "vertical";
    background?: {
      asset_url?: string;
      fit?: "cover" | "contain" | "custom";
      position?: "center" | "top" | "bottom" | "left" | "right" | "top_left" | "top_right" | "bottom_left" | "bottom_right";
      aspect_ratio?: "auto" | "16:9" | "4:3" | "3:2" | "1:1";
      focal_x?: number;
      focal_y?: number;
      scale?: number;
      opacity?: number;
      overlay?: "none" | "light" | "dark" | "brand";
    };
  };
  image_urls?: string[];
  gallery_items?: Array<{ id: string; image_url: string; title?: string; description?: string; time_label?: string; period_label?: string; badge_mode?: "title" | "time" | "period" | "custom" | "none"; badge_text?: string; alt_text?: string; link_url?: string }>;
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
    cta_label?: string;
  }>;
  case_ids?: string[];
  case_items?: Array<{
    id: string;
    slug: string;
    title: string;
    industry?: string;
    summary?: string;
    background?: string;
    solution?: string;
    result?: string;
    client_name?: string;
    metrics?: Array<{ value: string; label: string }>;
    image_url?: string;
    cta_label?: string;
  }>;
  faq_mode?: "all_published" | "selected";
  faq_document_ids?: string[];
  cta_label?: string;
  cta_url?: string;
  cta_icon?: "external" | "phone" | "mail" | "message" | "map" | "building" | "calendar" | "file" | "play";
  action_items?: Array<{
    id: string;
    title: string;
    summary?: string;
    label?: string;
    tag?: string;
    icon?: "external" | "phone" | "mail" | "message" | "map" | "building" | "calendar" | "file" | "play";
    date?: string;
    location?: string;
    source?: string;
    status?: string;
    duration?: string;
    image_url?: string;
    target_type: "external_url" | "internal_path" | "phone" | "map";
    target_value: string;
    open_mode?: "self" | "new_tab";
  }>;
};

export type PublicCardData = {
  id: string;
  slug: string;
  card_kind?: "enterprise" | "employee";
  display_name: string;
  title: string;
  avatar_url?: string | null;
  business_summary?: string | null;
  identity_titles?: string[];
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
  enterprise_template?: { schema_version: 1; theme_key?: "brand" | "clean" | "warm"; blocks: PublicEnterpriseTemplateBlock[] } | null;
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
  const types = new Set(["identity", "rich_text", "business_collection", "image_gallery", "video_link", "case_collection", "trust_panel", "faq", "cta", "ai_assistant", "action_collection"]);
  const layoutVariants = new Set(["auto", "list", "grid", "carousel", "featured", "mosaic", "horizontal", "vertical"]);
  const blocks: PublicEnterpriseTemplateBlock[] = value.blocks.flatMap((raw) => {
    if (!isRecord(raw) || typeof raw.id !== "string" || typeof raw.type !== "string" || !types.has(raw.type)) return [];
    const strings = (item: unknown) => Array.isArray(item) ? item.filter((entry): entry is string => typeof entry === "string" && Boolean(entry.trim())) : undefined;
    const productItems = Array.isArray(raw.product_items) ? raw.product_items.flatMap((item) => {
      if (
        !isRecord(item)
        || typeof item.id !== "string"
        || typeof item.slug !== "string"
        || typeof item.name !== "string"
      ) return [];
      return [{ id: item.id, slug: item.slug, name: item.name, category: optionalString(item, "category"), summary: optionalString(item, "summary"), image_url: optionalString(item, "image_url"), cta_label: optionalString(item, "cta_label") }];
    }) : undefined;
    const caseItems = Array.isArray(raw.case_items) ? raw.case_items.flatMap((item) => {
      if (
        !isRecord(item)
        || typeof item.id !== "string"
        || typeof item.slug !== "string"
        || typeof item.title !== "string"
      ) return [];
      return [{ id: item.id, slug: item.slug, title: item.title, industry: optionalString(item, "industry"), client_name: optionalString(item, "client_name"), background: optionalString(item, "background"), solution: optionalString(item, "solution"), summary: optionalString(item, "summary"), result: optionalString(item, "result"), metrics: Array.isArray(item.metrics) ? item.metrics.flatMap((metric) => isRecord(metric) && typeof metric.value === "string" && typeof metric.label === "string" ? [{ value: metric.value, label: metric.label }] : []) : undefined, image_url: optionalString(item, "image_url"), cta_label: optionalString(item, "cta_label") }];
    }) : undefined;
    const galleryItems: PublicEnterpriseTemplateBlock["gallery_items"] = Array.isArray(raw.gallery_items) ? raw.gallery_items.flatMap((item) => {
      if (!isRecord(item) || typeof item.id !== "string" || typeof item.image_url !== "string") return [];
      const badgeMode = ["title", "time", "period", "custom", "none"].includes(String(item.badge_mode)) ? item.badge_mode as "title" | "time" | "period" | "custom" | "none" : "title";
      return [{ id: item.id, image_url: item.image_url, title: optionalString(item, "title"), description: optionalString(item, "description"), time_label: optionalString(item, "time_label"), period_label: optionalString(item, "period_label"), badge_mode: badgeMode, badge_text: optionalString(item, "badge_text"), alt_text: optionalString(item, "alt_text"), link_url: optionalString(item, "link_url") }];
    }) : undefined;
    const faqMode: PublicEnterpriseTemplateBlock["faq_mode"] = raw.type === "faq"
      ? raw.faq_mode === "selected" ? "selected" : "all_published"
      : undefined;
    const presentation: PublicEnterpriseTemplateBlock["presentation"] = raw.type === "identity" && isRecord(raw.presentation)
      ? (() => {
          const identityLayout: NonNullable<PublicEnterpriseTemplateBlock["presentation"]>["identity_layout"] = raw.presentation.identity_layout === "vertical" ? "vertical" : "horizontal";
          const background: NonNullable<PublicEnterpriseTemplateBlock["presentation"]>["background"] = isRecord(raw.presentation.background)
            ? {
                asset_url: optionalString(raw.presentation.background, "asset_url"),
                fit: raw.presentation.background.fit === "contain" || raw.presentation.background.fit === "custom" ? raw.presentation.background.fit : "cover",
                position: (["center", "top", "bottom", "left", "right", "top_left", "top_right", "bottom_left", "bottom_right"] as const).includes(raw.presentation.background.position as never)
                  ? raw.presentation.background.position as NonNullable<NonNullable<PublicEnterpriseTemplateBlock["presentation"]>["background"]>["position"]
                  : "center",
                aspect_ratio: (["auto", "16:9", "4:3", "3:2", "1:1"] as const).includes(raw.presentation.background.aspect_ratio as never)
                  ? raw.presentation.background.aspect_ratio as NonNullable<NonNullable<PublicEnterpriseTemplateBlock["presentation"]>["background"]>["aspect_ratio"]
                  : "auto",
                focal_x: typeof raw.presentation.background.focal_x === "number" ? raw.presentation.background.focal_x : 50,
                focal_y: typeof raw.presentation.background.focal_y === "number" ? raw.presentation.background.focal_y : 50,
                scale: typeof raw.presentation.background.scale === "number" ? raw.presentation.background.scale : 1,
                opacity: typeof raw.presentation.background.opacity === "number" ? raw.presentation.background.opacity : 1,
                overlay: (["none", "light", "dark", "brand"] as const).includes(raw.presentation.background.overlay as never)
                  ? raw.presentation.background.overlay as NonNullable<NonNullable<PublicEnterpriseTemplateBlock["presentation"]>["background"]>["overlay"]
                  : "none",
              }
            : undefined;
          return { identity_layout: identityLayout, background };
        })()
      : undefined;
    const actionItems: PublicEnterpriseTemplateBlock["action_items"] = raw.type === "action_collection" && Array.isArray(raw.action_items)
      ? raw.action_items.flatMap((item) => {
          if (!isRecord(item)) return [];
          const targetType = item.target_type;
          if (
            typeof item.id !== "string"
            || typeof item.title !== "string"
            || typeof item.target_value !== "string"
            || (targetType !== "external_url" && targetType !== "internal_path" && targetType !== "phone" && targetType !== "map")
          ) return [];
          return [{
            id: item.id,
            title: item.title,
            summary: optionalString(item, "summary"),
            label: optionalString(item, "label"),
            tag: optionalString(item, "tag"),
            icon: ["external", "phone", "mail", "message", "map", "building", "calendar", "file", "play"].includes(optionalString(item, "icon") || "")
              ? optionalString(item, "icon") as NonNullable<PublicEnterpriseTemplateBlock["action_items"]>[number]["icon"]
              : undefined,
            date: optionalString(item, "date"),
            location: optionalString(item, "location"),
            source: optionalString(item, "source"),
            status: optionalString(item, "status"),
            duration: optionalString(item, "duration"),
            image_url: optionalString(item, "image_url"),
            target_type: targetType as NonNullable<PublicEnterpriseTemplateBlock["action_items"]>[number]["target_type"],
            target_value: item.target_value,
            open_mode: item.open_mode === "new_tab" ? "new_tab" as const : "self" as const,
          }];
        })
      : undefined;
    return [{
      id: raw.id,
      type: raw.type as PublicEnterpriseTemplateBlock["type"],
      visible: raw.visible !== false,
      show_title: raw.show_title !== false,
      directory_enabled: raw.directory_enabled !== false,
      sort_order: typeof raw.sort_order === "number" ? raw.sort_order : 0,
      layout_variant: typeof raw.layout_variant === "string" && layoutVariants.has(raw.layout_variant)
        ? raw.layout_variant as PublicEnterpriseTemplateBlock["layout_variant"]
        : "auto",
      item_limit: typeof raw.item_limit === "number" ? raw.item_limit : undefined,
      action_template: raw.type === "action_collection" && ["shortcuts", "media", "event", "banner", "articles", "video", "buttons"].includes(raw.action_template as string)
        ? raw.action_template as PublicEnterpriseTemplateBlock["action_template"]
        : undefined,
      presentation,
      title: optionalString(raw, "title"),
      body: optionalString(raw, "body"),
      image_urls: strings(raw.image_urls),
      gallery_items: galleryItems,
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
      cta_icon: ["external", "phone", "mail", "message", "map", "building", "calendar", "file", "play"].includes(optionalString(raw, "cta_icon") || "")
        ? optionalString(raw, "cta_icon") as PublicEnterpriseTemplateBlock["cta_icon"]
        : undefined,
      action_items: actionItems,
    }];
  });
  const theme = value.theme_key;
  return { schema_version: 1, theme_key: theme === "clean" || theme === "warm" ? theme : "brand", blocks };
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
    identity_titles: Array.isArray(data.identity_titles)
      ? data.identity_titles.filter((item): item is string => typeof item === "string" && Boolean(item.trim())).slice(0, 8)
      : [],
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

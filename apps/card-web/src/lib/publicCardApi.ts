type PublicLinkItem = Record<string, string>;

export type PublicCardData = {
  id: string;
  slug: string;
  card_kind?: "enterprise" | "employee";
  display_name: string;
  title: string;
  avatar_url?: string | null;
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
        return [
          {
            id: requiredString(rawItem, "id"),
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

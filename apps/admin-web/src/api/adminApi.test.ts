import { describe, expect, it, vi } from "vitest";

import { createAdminApi } from "./adminApi";
import { ApiClient } from "./client";

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function authenticatedApi(fetcher: ReturnType<typeof vi.fn<typeof fetch>>) {
  const client = new ApiClient({
    baseUrl: "https://api.example.test/api/v1",
    fetcher,
  });
  await client.login("admin@example.test", "password");
  return createAdminApi(client);
}

function tokenResponse() {
  return jsonResponse({
    data: {
      access_token: "access-token",
      csrf_token: "csrf-token",
      token_type: "bearer",
      expires_in: 900,
      refresh_expires_in: 604800,
    },
  });
}

describe("adminApi real contract", () => {
  it("normalizes and updates a versioned enterprise template envelope", async () => {
    const rawTemplate = {
      card_id: "card-enterprise",
      version: 7,
      draft: {
        schema_version: 1,
        theme_key: "warm",
        blocks: [{
          id: "gallery-1",
          type: "image_gallery",
          visible: false,
          sort_order: 4,
          title: "企业相册",
          image_urls: ["/api/v1/public/card-assets/company-1/a.webp"],
          case_items: [{ id: "server-only" }],
        }],
      },
      published: null,
    };
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({ data: rawTemplate }))
      .mockResolvedValueOnce(jsonResponse({ data: { ...rawTemplate, version: 8 } }));
    const api = await authenticatedApi(fetcher);

    const loaded = await api.getEnterpriseTemplate("card-enterprise");
    expect(loaded).toMatchObject({
      cardId: "card-enterprise",
      version: 7,
      draft: {
        themeKey: "warm",
        blocks: [{ visible: false, sortOrder: 4, imageUrls: ["/api/v1/public/card-assets/company-1/a.webp"] }],
      },
    });
    await api.updateEnterpriseTemplate("card-enterprise", 7, "clean", [
      { ...loaded.draft.blocks[0], sortOrder: 99 },
      {
        id: "ai-1",
        type: "ai_assistant",
        visible: true,
        sortOrder: 99,
        title: "在线咨询",
      },
    ]);

    expect(fetcher.mock.calls[2][0]).toBe(
      "https://api.example.test/api/v1/admin/cards/card-enterprise/enterprise-template",
    );
    expect((fetcher.mock.calls[2][1]?.headers as Headers).get("If-Match")).toBe("7");
    const body = JSON.parse(String(fetcher.mock.calls[2][1]?.body));
    expect(body).toMatchObject({
      schema_version: 1,
      theme_key: "clean",
      blocks: [
        { id: "gallery-1", visible: false, sort_order: 0 },
        { id: "ai-1", visible: true, sort_order: 1 },
      ],
    });
    expect(body.blocks[0]).not.toHaveProperty("case_items");
  });

  it("uploads a card image as multipart and normalizes the stored asset", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            url: "/api/v1/public/card-assets/company-1/asset-1.webp",
            content_type: "image/webp",
            width: 640,
            height: 640,
            size_bytes: 12_345,
          },
        }, 201),
      );
    const api = await authenticatedApi(fetcher);
    const file = new File(["image"], "avatar.png", { type: "image/png" });

    await expect(api.uploadCardAsset(file)).resolves.toEqual({
      url: "/api/v1/public/card-assets/company-1/asset-1.webp",
      contentType: "image/webp",
      width: 640,
      height: 640,
      sizeBytes: 12_345,
    });

    const request = fetcher.mock.calls[1][1];
    expect(request?.body).toBeInstanceOf(FormData);
    expect((request?.body as FormData).get("file")).toBe(file);
    expect((request?.headers as Headers).has("Content-Type")).toBe(false);
  });

  it("serializes preset icons for action entries and a single action button", async () => {
    const responseTemplate = {
      card_id: "card-enterprise",
      version: 2,
      draft: {
        schema_version: 1,
        theme_key: "brand",
        blocks: [
          { id: "identity", type: "identity", visible: true, sort_order: 0 },
          {
            id: "actions",
            type: "action_collection",
            visible: true,
            sort_order: 1,
            action_items: [{
              id: "phone-entry",
              title: "电话咨询",
              icon: "phone",
              target_type: "phone",
              target_value: "13800000000",
              open_mode: "self",
            }],
          },
          {
            id: "cta",
            type: "cta",
            visible: true,
            sort_order: 2,
            cta_label: "微信咨询",
            cta_url: "https://example.test/contact",
            cta_icon: "message",
          },
        ],
      },
      published: null,
    };
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({ data: responseTemplate }));
    const api = await authenticatedApi(fetcher);

    const updated = await api.updateEnterpriseTemplate("card-enterprise", 1, "brand", [
      { id: "identity", type: "identity", visible: true, sortOrder: 0 },
      {
        id: "actions",
        type: "action_collection",
        visible: true,
        sortOrder: 1,
        actionItems: [{
          id: "phone-entry",
          title: "电话咨询",
          icon: "phone",
          targetType: "phone",
          targetValue: "13800000000",
          openMode: "self",
        }],
      },
      {
        id: "cta",
        type: "cta",
        visible: true,
        sortOrder: 2,
        ctaLabel: "微信咨询",
        ctaUrl: "https://example.test/contact",
        ctaIcon: "message",
      },
    ]);

    const body = JSON.parse(String(fetcher.mock.calls[1][1]?.body));
    expect(body.blocks[1].action_items[0]).toMatchObject({ icon: "phone" });
    expect(body.blocks[2]).toMatchObject({ cta_icon: "message" });
    expect(updated.draft.blocks[1].actionItems?.[0].icon).toBe("phone");
    expect(updated.draft.blocks[2].ctaIcon).toBe("message");
  });

  it("uploads a card video through the dedicated media endpoint", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({
        data: {
          url: "/api/v1/public/card-video-assets/company-1/demo.mp4",
          content_type: "video/mp4",
          size_bytes: 1_048_576,
        },
      }, 201));
    const api = await authenticatedApi(fetcher);
    const file = new File(["video"], "demo.mp4", { type: "video/mp4" });

    await expect(api.uploadCardVideoAsset(file)).resolves.toEqual({
      url: "/api/v1/public/card-video-assets/company-1/demo.mp4",
      contentType: "video/mp4",
      sizeBytes: 1_048_576,
    });
    expect(fetcher.mock.calls[1][0]).toBe("https://api.example.test/api/v1/admin/card-video-assets");
    const request = fetcher.mock.calls[1][1];
    expect(request?.body).toBeInstanceOf(FormData);
    expect((request?.body as FormData).get("file")).toBe(file);
  });

  it("loads only selectable published FAQ projections", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({
        data: [{
          id: "11111111-1111-4111-8111-111111111111",
          title: "交付周期是多久？",
          answer: "标准项目通常需要四周。",
          status: "published",
          visibility: "public",
        }],
        total: 1,
      }));
    const api = await authenticatedApi(fetcher);

    await expect(api.listSelectableFaqDocuments()).resolves.toEqual([{
      id: "11111111-1111-4111-8111-111111111111",
      title: "交付周期是多久？",
      answer: "标准项目通常需要四周。",
      status: "published",
      visibility: "public",
    }]);
    expect(fetcher.mock.calls[1][0]).toBe(
      "https://api.example.test/api/v1/admin/knowledge/documents?selectable_faq=true",
    );
  });

  it("submits a local template document only when creation is confirmed", async () => {
    const card = {
      id: "card-enterprise",
      card_kind: "enterprise",
      slug: "c-enterprise",
      display_name: "示例企业",
      title: "企业名片",
      status: "draft",
      version: 1,
      share_url: "https://cards.example.test/c/c-enterprise",
      qr_url: "https://cards.example.test/c/c-enterprise",
    };
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({ data: card }, 201));
    const api = await authenticatedApi(fetcher);

    await api.createManagedCard({
      cardKind: "enterprise",
      displayName: "示例企业",
      title: "企业名片",
      avatarUrl: "",
      assistantName: "企业助手",
      welcomeMessage: "欢迎咨询",
      suggestedQuestions: [],
      identityTitles: [],
      contactFields: [],
      policyVersions: { privacy: "privacy-v1", chatNotice: "chat-v1", leadConsent: "lead-v1" },
      employeeContactVisibility: [],
      templateSourceCardId: "must-not-be-sent",
      templateDocument: {
        schemaVersion: 1,
        themeKey: "brand",
        blocks: [
          { id: "identity", type: "identity", visible: true, sortOrder: 0 },
          {
            id: "faq",
            type: "faq",
            visible: true,
            sortOrder: 1,
            faqMode: "selected",
            faqDocumentIds: ["11111111-1111-4111-8111-111111111111"],
          },
        ],
      },
    });

    const body = JSON.parse(String(fetcher.mock.calls[1][1]?.body));
    expect(body).not.toHaveProperty("template_source_card_id");
    expect(body.template_document).toMatchObject({
      schema_version: 1,
      blocks: [
        { id: "identity", sort_order: 0 },
        {
          id: "faq",
          faq_mode: "selected",
          faq_document_ids: ["11111111-1111-4111-8111-111111111111"],
          sort_order: 1,
        },
      ],
    });
  });

  it("reads the nested current-user contract", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            user: { id: "user-1", display_name: "林顾问" },
            membership: {
              id: "membership-1",
              tenant_id: "tenant-1",
              company_id: "company-1",
              role: "company_admin",
              permissions: ["company.profile.read"],
            },
          },
        }),
      );
    const api = await authenticatedApi(fetcher);

    await expect(api.me()).resolves.toEqual({
      id: "user-1",
      displayName: "林顾问",
      membershipId: "membership-1",
      tenantId: "tenant-1",
      companyId: "company-1",
      role: "company_admin",
      permissions: ["company.profile.read"],
      mustChangePassword: false,
    });
  });

  it("sends only allowed company and card fields with If-Match", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({ data: {} }))
      .mockResolvedValueOnce(jsonResponse({ data: {} }));
    const api = await authenticatedApi(fetcher);

    await api.updateCompanyProfile({
      name: "创非凡",
      summary: "企业简介",
      industry: "企业服务",
      region: "杭州",
      website: "https://example.test",
      logoUrl: "",
      positioning: "企业数字化服务",
      profileFacts: [],
      profileTags: [],
      profilePersonalizationPolicyVersion: "profile-personalization-v2",
      aiOffTopicAnswerMode: "unlimited",
      aiOffTopicQuestionLimit: 5,
      visitNotificationsEnabled: true,
      visitReportNotificationsEnabled: true,
      visitNotificationInAppEnabled: true,
      visitNotificationWecomEnabled: false,
      visitNotificationRecipientScope: "admins",
      version: 7,
    });
    await api.updateCard({
      slug: "lin-advisor",
      displayName: "林顾问",
      title: "解决方案顾问",
      avatarUrl: "",
      assistantName: "企业助手",
      welcomeMessage: "欢迎咨询",
      suggestedQuestions: ["你们提供什么服务？"],
      policyVersions: {
        privacy: "privacy-v2",
        chatNotice: "",
        leadConsent: "",
      },
      version: 4,
    });

    const companyRequest = fetcher.mock.calls[1];
    expect(companyRequest[0]).toBe(
      "https://api.example.test/api/v1/admin/company/profile",
    );
    expect((companyRequest[1]?.headers as Headers).get("If-Match")).toBe("7");
    expect(JSON.parse(String(companyRequest[1]?.body))).toEqual({
      name: "创非凡",
      summary: "企业简介",
      industry: "企业服务",
      region: "杭州",
      website: "https://example.test",
      logo_url: null,
      positioning: "企业数字化服务",
      profile_facts: [],
      profile_tags: [],
      profile_personalization_policy_version: "profile-personalization-v2",
      ai_off_topic_answer_mode: "unlimited",
      ai_off_topic_question_limit: 5,
      visit_notifications_enabled: true,
      visit_report_notifications_enabled: true,
      visit_notification_in_app_enabled: true,
      visit_notification_wecom_enabled: false,
      visit_notification_recipient_scope: "admins",
    });

    const cardRequest = fetcher.mock.calls[2];
    expect((cardRequest[1]?.headers as Headers).get("If-Match")).toBe("4");
    expect(JSON.parse(String(cardRequest[1]?.body))).toEqual({
      slug: "lin-advisor",
      display_name: "林顾问",
      title: "解决方案顾问",
      avatar_url: null,
      assistant_name: "企业助手",
      welcome_message: "欢迎咨询",
      suggested_questions: ["你们提供什么服务？"],
      policy_versions: { privacy: "privacy-v2" },
    });
  });

  it("loads detail before editing and uses the two-stage FAQ create flow", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            id: "document-1",
            title: "交付周期",
            status: "draft",
            version: 2,
            latest_version: null,
            updated_at: "2026-07-11T00:00:00Z",
            raw_text: "通常需要四周。",
            visibility: "public",
            metadata: { source_label: "企业后台" },
            editable_version_id: "version-1",
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            id: "document-2",
            title: "付款方式",
            status: "draft",
            version: 1,
          },
        }, 201),
      )
      .mockResolvedValueOnce(jsonResponse({ data: { document: {}, draft_version: {} } }))
      .mockResolvedValueOnce(jsonResponse({ data: { index_status: "pending" } }));
    const api = await authenticatedApi(fetcher);

    await expect(api.getKnowledgeDocument("document-1")).resolves.toMatchObject({
      rawText: "通常需要四周。",
      visibility: "public",
      metadata: { source_label: "企业后台" },
      editableVersionId: "version-1",
    });
    const createdId = await api.createKnowledgeDocument("付款方式");
    await api.updateKnowledgeDocument(createdId, {
      title: "付款方式",
      answer: "以合同约定为准。",
      visibility: "public",
      metadata: { source_label: "企业后台" },
    });
    await api.publishKnowledgeDocument(createdId);

    expect(createdId).toBe("document-2");
    expect(JSON.parse(String(fetcher.mock.calls[2][1]?.body))).toEqual({
      title: "付款方式",
      source_type: "faq",
    });
    expect(JSON.parse(String(fetcher.mock.calls[3][1]?.body))).toEqual({
      raw_text: "以合同约定为准。",
      title: "付款方式",
      visibility: "public",
      metadata: { source_label: "企业后台" },
    });
    expect(JSON.parse(String(fetcher.mock.calls[4][1]?.body))).toEqual({});
  });

  it("normalizes catalog resources and protects lifecycle mutations with If-Match", async () => {
    const product = {
      id: "product-1",
      slug: "enterprise-ai",
      name: "企业 AI 助手",
      summary: "可追溯问答",
      detail: "产品详情",
      visibility: "public",
      status: "draft",
      version: 3,
      sort_order: 0,
      settings: {},
    };
    const card = {
      id: "card-1",
      card_kind: "employee",
      owner_user_id: "user-1",
      slug: "c-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      display_name: "林顾问",
      title: "解决方案顾问",
      status: "published",
      version: 8,
      share_url: "https://cards.example.test/c/card-1",
      qr_url: "https://cards.example.test/c/card-1",
    };
    const forbiddenTopic = {
      id: "topic-1",
      topic: "价格承诺",
      match_terms: ["最低价"],
      action: "refuse",
      is_active: true,
      version: 2,
    };
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({ data: [product] }))
      .mockResolvedValueOnce(
        jsonResponse({ data: { ...product, status: "published", version: 4 } }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: [card] }))
      .mockResolvedValueOnce(
        jsonResponse({ data: { ...card, status: "archived", version: 9 } }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: [forbiddenTopic] }))
      .mockResolvedValueOnce(
        jsonResponse({ data: { ...forbiddenTopic, is_active: false, version: 3 } }),
      );
    const api = await authenticatedApi(fetcher);

    await expect(api.listProducts()).resolves.toMatchObject([
      { id: "product-1", name: "企业 AI 助手", version: 3 },
    ]);
    await api.publishProduct("product-1", 3);
    await expect(api.listManagedCards()).resolves.toMatchObject([
      { id: "card-1", ownerUserId: "user-1", version: 8 },
    ]);
    await api.deactivateManagedCard("card-1", 8);
    await expect(api.listForbiddenTopics()).resolves.toMatchObject([
      { id: "topic-1", matchTerms: ["最低价"], isActive: true },
    ]);
    await api.setForbiddenTopicActive("topic-1", 2, false);

    expect(fetcher.mock.calls[2][0]).toBe(
      "https://api.example.test/api/v1/admin/products/product-1:publish",
    );
    expect((fetcher.mock.calls[2][1]?.headers as Headers).get("If-Match")).toBe("3");
    expect(fetcher.mock.calls[4][0]).toBe(
      "https://api.example.test/api/v1/admin/cards/card-1:deactivate",
    );
    expect((fetcher.mock.calls[4][1]?.headers as Headers).get("If-Match")).toBe("8");
    expect(fetcher.mock.calls[6][0]).toBe(
      "https://api.example.test/api/v1/admin/forbidden-topics/topic-1/deactivate",
    );
    expect((fetcher.mock.calls[6][1]?.headers as Headers).get("If-Match")).toBe("2");
  });
});

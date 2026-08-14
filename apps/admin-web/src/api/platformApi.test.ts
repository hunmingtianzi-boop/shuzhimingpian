import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "./client";
import { createPlatformApi } from "./platformApi";

function llmProfileResponse(overrides: Record<string, unknown> = {}) {
  return {
    id: "profile/primary",
    name: "DeepSeek 主模型",
    purpose: "chat_main",
    provider: "deepseek",
    base_url: "https://api.deepseek.com",
    model: "deepseek-chat",
    thinking: "disabled",
    reasoning_effort: null,
    timeout_seconds: 30,
    max_retries: 2,
    max_concurrency: 20,
    max_output_tokens: 1000,
    temperature: 0.1,
    daily_budget_cny: 100,
    input_price_cny_per_million: 1,
    output_price_cny_per_million: 2,
    allow_general_answers: false,
    faq_fast_path_enabled: true,
    key_configured: true,
    key_hint: "sk-***1234",
    enabled: true,
    is_active: true,
    version: 4,
    last_test_status: "succeeded",
    last_test_latency_ms: 91,
    last_tested_at: "2026-07-15T12:00:00Z",
    created_at: "2026-07-15T10:00:00Z",
    updated_at: "2026-07-15T12:00:00Z",
    ...overrides,
  };
}

function onboardingResponse(overrides: Record<string, unknown> = {}) {
  return {
    id: "session/one",
    display_name: "Acme 建企任务",
    status: "review",
    tenant_slug: "acme-demo",
    tenant_name: "Acme",
    admin_account: "admin@acme.example",
    admin_display_name: "Acme 管理员",
    initial_card_display_name: "Acme 顾问",
    initial_card_title: "企业顾问",
    version: 3,
    import_batch_ids: ["batch-1"],
    suggestions: [
      {
        field: "company_name",
        value: "Acme",
        confidence: 0.9,
        generation_version: 1,
        sources: [
          {
            import_item_id: "item-1",
            file_name: "company.txt",
            document_id: "document-1",
            excerpt: "Acme 企业资料",
          },
        ],
      },
    ],
    expires_at: "2026-07-16T12:00:00Z",
    confirmed_enterprise: null,
    temporary_credential_reset_available: false,
    created_at: "2026-07-15T10:00:00Z",
    updated_at: "2026-07-15T12:00:00Z",
    ...overrides,
  };
}

describe("platformApi", () => {
  it("normalizes enterprise list records", async () => {
    const client = {
      get: vi.fn().mockResolvedValue({
        data: [
          {
            tenant_id: "tenant-1",
            tenant_slug: "acme",
            tenant_name: "Acme Tenant",
            company_id: "company-1",
            company_name: "Acme",
            status: "active",
            created_at: "2026-07-11T00:00:00Z",
          },
        ],
        total: 1,
      }),
    } as unknown as ApiClient;

    const values = await createPlatformApi(client).listEnterprises();

    expect(values).toEqual([
      expect.objectContaining({ tenantSlug: "acme", companyName: "Acme" }),
    ]);
    expect(client.get).toHaveBeenCalledWith("/platform/enterprises?limit=50&offset=0");
  });

  it("encodes enterprise search and status filters", async () => {
    const client = {
      get: vi.fn().mockResolvedValue({ data: [], total: 0 }),
    } as unknown as ApiClient;

    await createPlatformApi(client).listEnterprises({
      search: "  Acme 华东  ",
      status: "active",
      limit: 25,
    });

    expect(client.get).toHaveBeenCalledWith(
      "/platform/enterprises?limit=25&offset=0&search=Acme+%E5%8D%8E%E4%B8%9C&status=active",
    );
  });

  it("strictly normalizes the overview allowlist", async () => {
    const client = {
      get: vi.fn().mockResolvedValue({
        data: {
          generated_at: "2026-07-15T12:00:00Z",
          enterprise_count: 8,
          active_enterprise_count: 6,
          onboarding_count: 2,
          published_card_count: 17,
          visits_30d: 120,
          conversations_30d: 43,
          leads_30d: 9,
          failed_task_count: 1,
          llm_ready: true,
          import_ready: true,
          raw_text: "must be dropped",
        },
      }),
    } as unknown as ApiClient;

    const overview = await createPlatformApi(client).getOverview();

    expect(overview).toEqual(
      expect.objectContaining({ enterpriseCount: 8, llmReady: true }),
    );
    expect(Object.keys(overview)).not.toContain("raw_text");
    expect(client.get).toHaveBeenCalledWith("/platform/overview");
  });

  it("keeps only aggregate enterprise detail and server-issued published links", async () => {
    const client = {
      get: vi.fn().mockResolvedValue({
        data: {
          tenant_id: "tenant-1",
          tenant_slug: "acme",
          tenant_name: "Acme Tenant",
          company_id: "company/1",
          company_name: "Acme",
          status: "active",
          version: 3,
          onboarding_status: "completed",
          profile_completion: 80,
          employee_count: 4,
          card_count: 2,
          published_card_count: 1,
          visits_30d: 120,
          conversations_30d: 43,
          leads_30d: 9,
          cards: [
            {
              id: "card-1",
              card_kind: "enterprise",
              display_name: "王顾问",
              title: "销售总监",
              status: "published",
              updated_at: "2026-07-15T11:00:00Z",
              share_url: "https://cards.example/c/card-1",
              visitor_email: "must be dropped",
            },
            {
              id: "card-2",
              card_kind: "employee",
              display_name: "李顾问",
              title: "顾问",
              status: "draft",
              updated_at: "2026-07-14T11:00:00Z",
              share_url: null,
            },
          ],
          created_at: "2026-07-11T00:00:00Z",
          updated_at: "2026-07-15T12:00:00Z",
          conversation_body: "must be dropped",
        },
      }),
    } as unknown as ApiClient;

    const detail = await createPlatformApi(client).getEnterpriseDetail("company/1");
    const serialized = JSON.stringify(detail);

    expect(detail.cards[0].shareUrl).toBe("https://cards.example/c/card-1");
    expect(detail.cards[1].shareUrl).toBeUndefined();
    expect(serialized).not.toContain("visitor_email");
    expect(serialized).not.toContain("conversation_body");
    expect(client.get).toHaveBeenCalledWith(
      "/platform/enterprises/company%2F1",
    );
  });

  it("rejects a share URL attached to a non-published card", async () => {
    const client = {
      get: vi.fn().mockResolvedValue({
        data: {
          tenant_id: "tenant-1",
          tenant_slug: "acme",
          tenant_name: "Acme Tenant",
          company_id: "company-1",
          company_name: "Acme",
          status: "active",
          version: 1,
          onboarding_status: "completed",
          profile_completion: 60,
          employee_count: 1,
          card_count: 1,
          published_card_count: 0,
          visits_30d: 0,
          conversations_30d: 0,
          leads_30d: 0,
          cards: [
            {
              id: "card-1",
              card_kind: "enterprise",
              display_name: "草稿名片",
              title: "顾问",
              status: "draft",
              updated_at: "2026-07-15T11:00:00Z",
              share_url: "https://cards.example/c/card-1",
            },
          ],
          created_at: "2026-07-11T00:00:00Z",
          updated_at: "2026-07-15T12:00:00Z",
        },
      }),
    } as unknown as ApiClient;

    await expect(
      createPlatformApi(client).getEnterpriseDetail("company-1"),
    ).rejects.toMatchObject({ code: "INVALID_API_RESPONSE" });
  });

  it("sends lifecycle version and reason while returning only the transition projection", async () => {
    const client = {
      put: vi.fn().mockResolvedValue({
        data: {
          tenant_id: "tenant-1",
          company_id: "company/1",
          previous_status: "active",
          status: "suspended",
          version: 4,
          changed: true,
          updated_at: "2026-07-15T12:00:00Z",
          reason: "must be dropped",
          audit_hash: "must be dropped",
        },
      }),
    } as unknown as ApiClient;

    const record = await createPlatformApi(client).transitionEnterprise("company/1", {
      expectedVersion: 3,
      targetStatus: "suspended",
      reason: "  合同到期，暂停访问  ",
    });

    expect(client.put).toHaveBeenCalledWith(
      "/platform/enterprises/company%2F1/status",
      {
        expected_version: 3,
        target_status: "suspended",
        reason: "合同到期，暂停访问",
      },
    );
    expect(record).toEqual(expect.objectContaining({ status: "suspended", version: 4 }));
    expect(JSON.stringify(record)).not.toContain("reason");
    expect(JSON.stringify(record)).not.toContain("audit_hash");
  });

  it("keeps governance read models on aggregate and business-safe allowlists", async () => {
    const client = {
      get: vi
        .fn()
        .mockResolvedValueOnce({
          data: [{
            company_id: "company-1",
            company_name: "Acme",
            employee_count: 7,
            visits_30d: 31,
            unique_visitors_30d: 12,
            last_visit_at: "2026-07-15T12:00:00Z",
            employee_email: "must be dropped",
          }],
        })
        .mockResolvedValueOnce({
          data: [{
            id: "task-1",
            task_type: "knowledge_import",
            business_label: "资料导入",
            status: "failed",
            company_id: "company-1",
            company_name: "Acme",
            error_code: "PARSER_FAILED",
            created_at: "2026-07-15T11:00:00Z",
            updated_at: "2026-07-15T12:00:00Z",
            last_error: "private stack trace",
            body: "private payload",
          }],
        })
        .mockResolvedValueOnce({
          data: [{
            id: "audit-1",
            actor_display_name: "平台管理员",
            action: "enterprise.suspended",
            business_label: "停用企业",
            resource_type: "company",
            resource_id: "company-1",
            result: "succeeded",
            created_at: "2026-07-15T12:00:00Z",
            event_data: { reason: "must be dropped" },
          }],
        })
        .mockResolvedValueOnce({
          data: [{
            service: "database",
            status: "healthy",
            checked_at: "2026-07-15T12:00:00Z",
            latency_ms: 4,
            connection_string: "must be dropped",
          }],
        }),
    } as unknown as ApiClient;
    const api = createPlatformApi(client);

    const result = {
      aggregates: await api.listCompanyAggregates(),
      tasks: await api.listTasks(),
      audit: await api.listAudit(),
      health: await api.getServiceHealth(),
    };
    const serialized = JSON.stringify(result);

    expect(result.aggregates[0]).toEqual(expect.objectContaining({ employeeCount: 7 }));
    expect(result.tasks[0]).toEqual(expect.objectContaining({ businessLabel: "资料导入" }));
    expect(result.audit[0]).toEqual(expect.objectContaining({ businessLabel: "停用企业" }));
    expect(result.health[0]).toEqual(expect.objectContaining({ service: "database", latencyMs: 4 }));
    expect(serialized).not.toContain("employee_email");
    expect(serialized).not.toContain("private stack trace");
    expect(serialized).not.toContain("private payload");
    expect(serialized).not.toContain("event_data");
    expect(serialized).not.toContain("connection_string");
  });

  it("sends the initial administrator secret only in the create request", async () => {
    const client = {
      post: vi.fn().mockResolvedValue({
        data: {
          tenant_id: "tenant-1",
          tenant_slug: "acme",
          tenant_name: "Acme Tenant",
          company_id: "company-1",
          company_name: "Acme",
          company_status: "active",
          admin_user_id: "user-1",
          admin_membership_id: "membership-1",
          initial_card_id: "card-1",
          initial_card_slug: "c-random",
          created_at: "2026-07-11T00:00:00Z",
        },
      }),
    } as unknown as ApiClient;

    const created = await createPlatformApi(client).createEnterprise({
      tenantSlug: "acme",
      tenantName: "Acme Tenant",
      companyName: "Acme",
      industry: "AI",
      adminAccount: "admin@acme.test",
      adminDisplayName: "Acme Admin",
      adminPassword: "Initial-Password-2026!",
      initialCardTitle: "Acme Card",
    });

    expect(created.initialCardSlug).toBe("c-random");
    expect(client.post).toHaveBeenCalledWith(
      "/platform/enterprises",
      expect.objectContaining({
        tenant_slug: "acme",
        admin_password: "Initial-Password-2026!",
      }),
    );
    expect(JSON.stringify(created)).not.toContain("Initial-Password-2026!");
  });

  it("starts assisted onboarding without accepting a platform-selected password", async () => {
    const client = {
      post: vi.fn().mockResolvedValue({ data: onboardingResponse() }),
    } as unknown as ApiClient;
    await createPlatformApi(client).startOnboarding({
      displayName: "Acme 首次建企",
      tenantSlug: "acme",
      tenantName: "Acme Tenant",
      adminAccount: "admin@acme.test",
      adminDisplayName: "Acme Admin",
    });
    expect(client.post).toHaveBeenCalledWith(
      "/platform/onboarding",
      expect.objectContaining({
        display_name: "Acme 首次建企",
        tenant_slug: "acme",
      }),
    );
    expect(client.post).toHaveBeenCalledWith(
      "/platform/onboarding",
      expect.not.objectContaining({ admin_password: expect.anything() }),
    );
  });

  it("lists, renames and regenerates named onboarding tasks with optimistic versions", async () => {
    const regenerated = onboardingResponse({
      status: "confirmed",
      version: 5,
      temporary_credential_reset_available: true,
      credential_delivery: {
        account: "admin@acme.test",
        temporary_password: "one-time-password-2026",
        expires_at: "2026-07-22T12:00:00Z",
        shown_once: true,
      },
    });
    const client = {
      get: vi.fn().mockResolvedValue({ data: [onboardingResponse()], total: 1 }),
      patch: vi.fn().mockResolvedValue({
        data: onboardingResponse({ display_name: "Acme 华东建企", version: 4 }),
      }),
      post: vi.fn().mockResolvedValue({ data: regenerated }),
    } as unknown as ApiClient;
    const api = createPlatformApi(client);

    const tasks = await api.listOnboarding({ limit: 10, offset: 5 });
    const renamed = await api.renameOnboarding("session/one", {
      expectedVersion: 3,
      displayName: " Acme 华东建企 ",
    });
    const reset = await api.regenerateOnboardingTemporaryCredential("session/one", 4);

    expect(tasks[0]).toMatchObject({
      displayName: "Acme 建企任务",
      temporaryCredentialResetAvailable: false,
    });
    expect(renamed).toMatchObject({ displayName: "Acme 华东建企", version: 4 });
    expect(reset.credentialDelivery).toMatchObject({
      temporaryPassword: "one-time-password-2026",
      expiresAt: "2026-07-22T12:00:00Z",
    });
    expect(client.get).toHaveBeenCalledWith("/platform/onboarding?limit=10&offset=5");
    expect(client.patch).toHaveBeenCalledWith("/platform/onboarding/session%2Fone", {
      expected_version: 3,
      display_name: "Acme 华东建企",
    });
    expect(client.post).toHaveBeenCalledWith(
      "/platform/onboarding/session%2Fone/temporary-credential:regenerate",
      { expected_version: 4 },
    );
  });

  it("strictly normalizes LLM profiles and drops every server-injected secret field", async () => {
    const secret = "sk-server-must-never-enter-state";
    const client = {
      get: vi.fn().mockResolvedValue({
        data: [
          llmProfileResponse({
            key: secret,
            api_key: secret,
            api_key_ciphertext: `cipher:${secret}`,
          }),
        ],
      }),
    } as unknown as ApiClient;

    const profiles = await createPlatformApi(client).listLlmProfiles();
    const serialized = JSON.stringify(profiles);

    expect(profiles).toEqual([
      expect.objectContaining({
        id: "profile/primary",
        purpose: "chat_main",
        thinking: "disabled",
        allowGeneralAnswers: false,
        faqFastPathEnabled: true,
        isActive: true,
        lastTestStatus: "succeeded",
      }),
    ]);
    expect(Object.keys(profiles[0])).not.toEqual(
      expect.arrayContaining(["key", "api_key", "api_key_ciphertext"]),
    );
    expect(serialized).not.toContain(secret);
    expect(serialized).not.toContain("api_key_ciphertext");
  });

  it("rejects malformed LLM profile responses instead of keeping partial state", async () => {
    const client = {
      get: vi.fn().mockResolvedValue({
        data: [llmProfileResponse({ last_test_status: "maybe" })],
      }),
    } as unknown as ApiClient;

    await expect(createPlatformApi(client).listLlmProfiles()).rejects.toMatchObject({
      code: "INVALID_API_RESPONSE",
    });
  });

  it("writes an API key only in create/update/test requests and never returns it", async () => {
    const secret = "sk-client-write-only";
    const client = {
      post: vi
        .fn()
        .mockResolvedValueOnce({ data: llmProfileResponse() })
        .mockResolvedValueOnce({
          data: {
            status: "succeeded",
            provider: "deepseek",
            model: "deepseek-chat",
            latency_ms: 83,
          },
        }),
      put: vi.fn().mockResolvedValue({
        data: llmProfileResponse({ version: 5 }),
      }),
    } as unknown as ApiClient;
    const api = createPlatformApi(client);

    const created = await api.createLlmProfile({
      name: "DeepSeek 主模型",
      provider: "deepseek",
      baseUrl: "https://api.deepseek.com",
      model: "deepseek-chat",
      apiKey: secret,
      allowGeneralAnswers: true,
      faqFastPathEnabled: false,
    });
    const updated = await api.updateLlmProfile("profile/primary", {
      expectedVersion: 4,
      name: "DeepSeek 稳定模型",
      apiKey: "   ",
      allowGeneralAnswers: false,
      faqFastPathEnabled: true,
    });
    const tested = await api.testLlmProfile("profile/primary", secret);

    expect(client.post).toHaveBeenNthCalledWith(
      1,
      "/platform/settings/llm/profiles",
      expect.objectContaining({
        api_key: secret,
        allow_general_answers: true,
        faq_fast_path_enabled: false,
      }),
    );
    expect(client.put).toHaveBeenCalledWith(
      "/platform/settings/llm/profiles/profile%2Fprimary",
      {
        expected_version: 4,
        name: "DeepSeek 稳定模型",
        allow_general_answers: false,
        faq_fast_path_enabled: true,
      },
    );
    expect(client.post).toHaveBeenNthCalledWith(
      2,
      "/platform/settings/llm/profiles/profile%2Fprimary/test",
      { api_key: secret },
    );
    expect(JSON.stringify({ created, updated, tested })).not.toContain(secret);
  });

  it("activates a profile with both optimistic concurrency preconditions", async () => {
    const client = {
      post: vi.fn().mockResolvedValue({
        data: llmProfileResponse({ id: "profile/backup", version: 8 }),
      }),
    } as unknown as ApiClient;

    await createPlatformApi(client).activateLlmProfile("profile/backup", {
      expectedVersion: 7,
      expectedActiveProfileId: "profile/primary",
    });

    expect(client.post).toHaveBeenCalledWith(
      "/platform/settings/llm/profiles/profile%2Fbackup/activate",
      {
        expected_version: 7,
        expected_active_profile_id: "profile/primary",
      },
    );
  });

  it("keeps onboarding upload session-bound and forces multipart files only", async () => {
    const client = {
      postForm: vi.fn().mockResolvedValue({ data: onboardingResponse() }),
    } as unknown as ApiClient;
    const file = new File(["Acme 企业资料"], "company.txt", {
      type: "text/plain",
    });

    const session = await createPlatformApi(client).uploadOnboardingDocuments(
      "session/one",
      [file],
    );

    expect(session.suggestions[0].sources[0].fileName).toBe("company.txt");
    expect(session).toEqual(
      expect.objectContaining({
        adminAccount: "admin@acme.example",
        adminDisplayName: "Acme 管理员",
        initialCardDisplayName: "Acme 顾问",
        initialCardTitle: "企业顾问",
      }),
    );
    expect(client.postForm).toHaveBeenCalledWith(
      "/platform/onboarding/session%2Fone/imports",
      expect.any(FormData),
    );
    const form = vi.mocked(client.postForm).mock.calls[0][1] as FormData;
    expect([...form.keys()]).toEqual(["files"]);
    expect(JSON.stringify(session)).not.toContain("tenant_id");
    expect(JSON.stringify(session)).not.toContain("raw_text");
  });

  it("reads and flattens only session-scoped onboarding import progress", async () => {
    const client = {
      get: vi.fn().mockResolvedValue({
        data: {
          session_id: "session/one",
          settled: false,
          batches: [
            {
              id: "batch-1",
              status: "processing",
              total_items: 2,
              pending_items: 1,
              succeeded_items: 1,
              failed_items: 0,
              auto_publish: false,
              created_at: "2026-07-16T09:00:00Z",
              completed_at: null,
              items: [
                {
                  id: "item-1",
                  file_name: "company.pdf",
                  source_type: "pdf",
                  status: "completed",
                  error_code: null,
                  created_at: "2026-07-16T09:00:00Z",
                  completed_at: "2026-07-16T09:00:02Z",
                },
                {
                  id: "item-2",
                  file_name: "catalog.xlsx",
                  source_type: "xlsx",
                  status: "processing",
                  error_code: null,
                  created_at: "2026-07-16T09:00:00Z",
                  completed_at: null,
                },
              ],
            },
          ],
        },
      }),
    } as unknown as ApiClient;

    const status = await createPlatformApi(client).getOnboardingImports(
      "session/one",
    );

    expect(client.get).toHaveBeenCalledWith(
      "/platform/onboarding/session%2Fone/imports",
    );
    expect(status).toEqual({
      sessionId: "session/one",
      settled: false,
      items: [
        expect.objectContaining({
          id: "item-1",
          fileName: "company.pdf",
          status: "completed",
        }),
        expect.objectContaining({
          id: "item-2",
          fileName: "catalog.xlsx",
          status: "processing",
        }),
      ],
    });
    expect(JSON.stringify(status)).not.toMatch(/tenant_id|company_id|payload/);
  });

  it("sends optimistic versions for onboarding generation and confirmation", async () => {
    const client = {
      post: vi.fn().mockResolvedValue({ data: onboardingResponse({ version: 4 }) }),
    } as unknown as ApiClient;
    const api = createPlatformApi(client);

    await api.generateOnboardingSuggestions("session/one", 3);
    await api.confirmOnboarding("session/one", {
      expectedVersion: 3,
      candidateSelections: [],
      tenantName: "Acme",
      companyName: "Acme 商务",
      initialCardDisplayName: "管理员",
    });

    expect(client.post).toHaveBeenNthCalledWith(
      1,
      "/platform/onboarding/session%2Fone/suggestions",
      { expected_version: 3 },
    );
    expect(client.post).toHaveBeenNthCalledWith(
      2,
      "/platform/onboarding/session%2Fone/confirm",
      expect.objectContaining({
        expected_version: 3,
        company_name: "Acme 商务",
        initial_card_display_name: "管理员",
        candidate_selections: [],
      }),
    );
  });
});

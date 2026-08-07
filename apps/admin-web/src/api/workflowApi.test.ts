import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "./client";
import { createWorkflowApi } from "./workflowApi";

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
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

async function authenticatedApi(fetcher: ReturnType<typeof vi.fn<typeof fetch>>) {
  const client = new ApiClient({
    baseUrl: "https://api.example.test/api/v1",
    fetcher,
  });
  await client.login("admin@example.test", "password");
  return createWorkflowApi(client);
}

const conversation = {
  id: "conversation-1",
  card_id: "card-1",
  card_display_name: "林顾问",
  visitor_id: "visitor-1",
  visit_id: "visit-1",
  status: "active",
  primary_intent: "企业 AI 咨询",
  risk_level: "low",
  started_at: "2026-07-11T01:00:00Z",
  last_activity_at: "2026-07-11T01:05:00Z",
  message_count: 2,
  has_current_summary: false,
};

const summary = {
  id: "summary-1",
  conversation_id: "conversation-1",
  summary: "客户关注企业 AI 知识库。",
  interests: ["知识库"],
  strength: "high",
  next_step: "安排演示",
  risk_notes: null,
  source_message_ids: ["message-1", "message-2"],
  is_current: true,
  stale_at: null,
  approved_at: null,
  approved_by: null,
  created_at: "2026-07-11T01:06:00Z",
  updated_at: "2026-07-11T01:06:00Z",
};

const lead = {
  id: "lead-1",
  card_id: "card-1",
  card_display_name: "林顾问",
  visitor_id: "visitor-1",
  conversation_id: "conversation-1",
  owner_user_id: "user-1",
  status: "new",
  priority: "medium",
  masked_name: "林**",
  masked_contact: "138****0000",
  company_name: "创非凡",
  interest_tags: ["知识库"],
  viewed_at: null,
  closed_at: null,
  version: 3,
  created_at: "2026-07-11T01:10:00Z",
  updated_at: "2026-07-11T01:10:00Z",
  name: "林顾问",
  mobile: "13800000000",
  email: null,
  wechat: "lin-ai",
  demand: "建设企业知识库",
  followups: [],
};

const gap = {
  id: "gap-1",
  conversation_id: "conversation-1",
  question: "项目交付周期是多久？",
  reason: "missing_evidence",
  status: "pending",
  suggested_answer: null,
  occurrence_count: 3,
  last_seen_at: "2026-07-11T01:12:00Z",
  approved_version_id: null,
  evidence: {},
  created_at: "2026-07-11T01:12:00Z",
  updated_at: "2026-07-11T01:12:00Z",
};

const privacyRequest = {
  id: "privacy-1",
  visitor_id: "visitor-1",
  request_type: "deletion",
  status: "pending",
  verification_method: null,
  handled_by: null,
  completed_at: null,
  evidence: {},
  created_at: "2026-07-11T01:15:00Z",
  updated_at: "2026-07-11T01:15:00Z",
};

describe("workflowApi production contracts", () => {
  it("normalizes and regenerates conversation topic analysis", async () => {
    const topicPayload = {
      data: {
        status: "ready",
        generated_at: "2026-07-25T00:00:00Z",
        period_days: 30,
        question_count: 92,
        analyzed_question_count: 92,
        summary: "用户主要关注赛事报名与项目孵化。",
        topics: [
          {
            topic: "赛事报名",
            count: 40,
            share: 0.4348,
            sample_questions: ["怎么报名？"],
          },
        ],
        provider: "deepseek",
        model: "deepseek-chat",
      },
    };
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse(topicPayload))
      .mockResolvedValueOnce(jsonResponse(topicPayload));
    const api = await authenticatedApi(fetcher);

    await expect(api.getTopicAnalysis(30)).resolves.toMatchObject({
      status: "ready",
      questionCount: 92,
      topics: [{ topic: "赛事报名", sampleQuestions: ["怎么报名？"] }],
    });
    await expect(api.analyzeTopics(30)).resolves.toMatchObject({
      analyzedQuestionCount: 92,
      provider: "deepseek",
    });
    expect(fetcher.mock.calls[1][0]).toBe(
      "https://api.example.test/api/v1/admin/analytics/topics?period_days=30",
    );
    expect(fetcher.mock.calls[2][0]).toBe(
      "https://api.example.test/api/v1/admin/analytics/topics:analyze?period_days=30",
    );
    expect(fetcher.mock.calls[2][1]).toMatchObject({ method: "POST" });
  });

  it("normalizes paginated employee analytics and reconciliation", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(
        jsonResponse({
          data: [{
            user_id: "user-1",
            membership_id: "membership-1",
            display_name: "林顾问",
            role: "card_owner",
            membership_status: "active",
            card_count: 2,
            visits: 20,
            unique_visitors: 15,
            conversations: 8,
            leads: 3,
            conversation_rate: 0.4,
            lead_rate: 0.15,
            last_activity_at: "2026-07-12T02:00:00Z",
          }],
          total: 1,
          limit: 20,
          offset: 0,
          generated_at: "2026-07-12T03:00:00Z",
          period_days: 30,
          reconciliation: {
            card_count: 2,
            visits: 20,
            unique_visitors: 14,
            employee_unique_visitors_sum: 15,
            conversations: 8,
            total_leads: 3,
            conversation_rate: 0.4,
            lead_rate: 0.15,
            last_activity_at: "2026-07-12T02:00:00Z",
          },
        }),
      );
    const api = await authenticatedApi(fetcher);

    await expect(api.listEmployeeAnalytics({ periodDays: 30 })).resolves.toMatchObject({
      generatedAt: "2026-07-12T03:00:00Z",
      items: [{ displayName: "林顾问", cardCount: 2, leadRate: 0.15 }],
      reconciliation: { uniqueVisitors: 14, employeeUniqueVisitorsSum: 15 },
    });
    expect(fetcher.mock.calls[1][0]).toBe(
      "https://api.example.test/api/v1/admin/analytics/employees?period_days=30&limit=20&offset=0",
    );
  });

  it("normalizes dashboard metrics and paginated visits", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            generated_at: "2026-07-11T02:00:00Z",
            period_days: 30,
            visits: 42,
            unique_visitors: 31,
            conversations: 18,
            ai_answers: 27,
            total_leads: 5,
            new_leads: 5,
            pending_gaps: 2,
            unread_notifications: 4,
            conversation_rate: 0.4286,
            lead_rate: 0.119,
            daily: [{ day: "2026-07-11", visits: 8, conversations: 4, leads: 1 }],
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          data: [
            {
              id: "visit-1",
              card_id: "card-1",
              card_display_name: "林顾问",
              visitor_id: "visitor-1",
              source: "wechat",
              started_at: "2026-07-11T01:00:00Z",
              ended_at: "2026-07-11T01:03:00Z",
              duration_seconds: 180,
              conversation_count: 1,
            },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            id: "visit-1",
            card_id: "card-1",
            card_display_name: "林顾问",
            visitor_id: "visitor-1",
            source: "wechat",
            started_at: "2026-07-11T01:00:00Z",
            ended_at: "2026-07-11T01:03:00Z",
            duration_seconds: 180,
            conversation_count: 1,
            event_count: 4,
            page_durations: [{
              page_key: "detail:product:product-a",
              page_title: "产品 A",
              object_type: "product",
              object_id: "product-a",
              duration_seconds: 12.5,
              view_count: 1,
              last_viewed_at: "2026-07-11T01:02:00Z",
            }],
            questions: [{
              message_id: "message-1",
              conversation_id: "conversation-1",
              question: "这个产品多少钱？",
              asked_at: "2026-07-11T01:02:10Z",
              answer_status: "completed",
            }],
          },
        }),
      );
    const api = await authenticatedApi(fetcher);

    await expect(api.getDashboard(30)).resolves.toMatchObject({
      visits: 42,
      totalLeads: 5,
      conversationRate: 0.4286,
      daily: [{ day: "2026-07-11", leads: 1 }],
    });
    await expect(api.listVisits({ cardId: "card-1" })).resolves.toMatchObject({
      total: 1,
      items: [{ id: "visit-1", durationSeconds: 180 }],
    });
    await expect(api.getVisit("visit-1")).resolves.toMatchObject({
      eventCount: 4,
      pageDurations: [{ pageTitle: "产品 A", durationSeconds: 12.5 }],
      questions: [{ question: "这个产品多少钱？", answerStatus: "completed" }],
    });
    expect(fetcher.mock.calls[1][0]).toBe(
      "https://api.example.test/api/v1/admin/dashboard?period_days=30",
    );
    expect(fetcher.mock.calls[2][0]).toBe(
      "https://api.example.test/api/v1/admin/visits?limit=20&offset=0&card_id=card-1",
    );
    expect(fetcher.mock.calls[3][0]).toBe(
      "https://api.example.test/api/v1/admin/visits/visit-1",
    );
  });

  it("loads conversation evidence and sends a bodyless summarize request", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            ...conversation,
            messages: [
              {
                id: "message-1",
                role: "assistant",
                content: "根据企业知识回答。",
                status: "completed",
                content_redacted: false,
                created_at: "2026-07-11T01:02:00Z",
                citations: [
                  {
                    id: "citation-1",
                    chunk_id: "chunk-1",
                    rank: 1,
                    score: 0.91,
                    title: "产品说明",
                    source_type: "faq",
                    source_id: "faq-1",
                    snapshot_text: "企业知识库支持可追溯问答。",
                  },
                ],
                ai_run: {
                  provider: "deepseek",
                  model: "deepseek-chat",
                  status: "completed",
                  first_token_latency_ms: 240,
                  total_latency_ms: 980,
                  retrieval_result: {},
                  safety_result: {},
                  error_code: null,
                },
              },
            ],
            current_summary: null,
          },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: summary }))
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            ...summary,
            approved_at: "2026-07-11T01:07:00Z",
            approved_by: "user-admin",
          },
        }),
      );
    const api = await authenticatedApi(fetcher);

    await expect(api.getConversation("conversation-1")).resolves.toMatchObject({
      id: "conversation-1",
      messages: [{ citations: [{ title: "产品说明" }] }],
    });
    await expect(api.generateConversationSummary("conversation-1")).resolves.toMatchObject({
      id: "summary-1",
      nextStep: "安排演示",
    });
    const summarize = fetcher.mock.calls[2];
    expect(summarize[0]).toBe(
      "https://api.example.test/api/v1/admin/conversations/conversation-1:summarize",
    );
    expect(summarize[1]?.method).toBe("POST");
    expect(summarize[1]?.body).toBeUndefined();
    await expect(api.approveSummary("summary-1")).resolves.toMatchObject({
      id: "summary-1",
      approvedAt: "2026-07-11T01:07:00Z",
      approvedBy: "user-admin",
    });
    expect(fetcher.mock.calls[3][0]).toBe(
      "https://api.example.test/api/v1/admin/summaries/summary-1:approve",
    );
  });

  it("protects lead status with If-Match and records followups", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({ data: lead }))
      .mockResolvedValueOnce(
        jsonResponse({ data: { ...lead, status: "following", priority: "high", version: 4 } }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            id: "followup-1",
            actor_user_id: "user-1",
            followup_type: "call",
            content: "已约定演示",
            next_at: "2026-07-12T02:00:00Z",
            created_at: "2026-07-11T02:10:00Z",
          },
        }, 201),
      );
    const api = await authenticatedApi(fetcher);

    await expect(api.getLead("lead-1")).resolves.toMatchObject({ name: "林顾问", version: 3 });
    await api.updateLead("lead-1", 3, { status: "following", priority: "high" });
    await api.createLeadFollowup("lead-1", {
      followupType: "call",
      content: "已约定演示",
      nextAt: "2026-07-12T02:00:00Z",
    });

    expect((fetcher.mock.calls[2][1]?.headers as Headers).get("If-Match")).toBe("3");
    expect(JSON.parse(String(fetcher.mock.calls[2][1]?.body))).toEqual({
      status: "following",
      priority: "high",
    });
    expect(JSON.parse(String(fetcher.mock.calls[3][1]?.body))).toEqual({
      followup_type: "call",
      content: "已约定演示",
      next_at: "2026-07-12T02:00:00Z",
    });
  });

  it("uses the real gap, notification and privacy processing routes", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({ data: { ...gap, status: "drafted", suggested_answer: "通常为四周。" } }))
      .mockResolvedValueOnce(jsonResponse({ data: { ...gap, status: "indexed", suggested_answer: "通常为四周。" } }))
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            id: "notification-1",
            notification_type: "knowledge_gap",
            title: "新知识缺口",
            body: "请补充答案",
            resource_type: "knowledge_gap",
            resource_id: "gap-1",
            read_at: "2026-07-11T02:20:00Z",
            created_at: "2026-07-11T02:00:00Z",
          },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: { ...privacyRequest, status: "verified", verification_method: "mobile" } }));
    const api = await authenticatedApi(fetcher);

    await api.updateKnowledgeGap("gap-1", "通常为四周。");
    await api.approveKnowledgeGap("gap-1");
    await api.markNotificationRead("notification-1");
    await api.updatePrivacyRequest("privacy-1", {
      status: "verified",
      verificationMethod: "mobile",
    });

    expect(fetcher.mock.calls[2][0]).toBe(
      "https://api.example.test/api/v1/admin/knowledge/gaps/gap-1:approve",
    );
    expect(fetcher.mock.calls[2][1]?.body).toBeUndefined();
    expect(fetcher.mock.calls[3][0]).toBe(
      "https://api.example.test/api/v1/admin/notifications/notification-1/read",
    );
    expect(JSON.parse(String(fetcher.mock.calls[4][1]?.body))).toEqual({
      status: "verified",
      verification_method: "mobile",
    });
  });
});

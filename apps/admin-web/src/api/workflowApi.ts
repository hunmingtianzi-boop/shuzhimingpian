import { apiClient, ApiClient, ApiError, unwrapData } from "./client";
import type {
  AdminNotification,
  Conversation,
  ConversationAiRun,
  ConversationCitation,
  ConversationDetail,
  ConversationMessage,
  ConversationStatus,
  ConversationSummary,
  DashboardDailyMetric,
  DashboardOverview,
  EmployeeAnalytics,
  EmployeeAnalyticsPage,
  EmployeeAnalyticsReconciliation,
  KnowledgeGap,
  KnowledgeGapStatus,
  Lead,
  LeadDetail,
  LeadFollowup,
  LeadFollowupInput,
  LeadPriority,
  LeadStatus,
  NotificationList,
  OpportunityCandidate,
  PageResult,
  PrivacyRequest,
  PrivacyRequestStatus,
  TopicAnalysis,
  TopicAnalysisItem,
  Visit,
  VisitDetail,
} from "./types";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function invalid(label: string): never {
  throw new ApiError(`${label}接口返回了无法识别的数据。`, {
    code: "INVALID_API_RESPONSE",
  });
}

function dataRecord(payload: unknown, label: string): JsonRecord {
  const data = unwrapData(payload);
  return isRecord(data) ? data : invalid(label);
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function requiredString(value: unknown, label: string): string {
  const result = stringValue(value);
  if (!result) invalid(label);
  return result;
}

function optionalString(value: unknown): string | undefined {
  const result = stringValue(value);
  return result || undefined;
}

function numberValue(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function recordValue(value: unknown): JsonRecord {
  return isRecord(value) ? value : {};
}

function normalizePage<T>(
  payload: unknown,
  label: string,
  normalize: (value: unknown) => T,
): PageResult<T> {
  if (!isRecord(payload) || !Array.isArray(payload.data)) invalid(label);
  return {
    items: payload.data.map(normalize),
    total: numberValue(payload.total),
    limit: numberValue(payload.limit, 20),
    offset: numberValue(payload.offset),
  };
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const values = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") values.set(key, String(value));
  }
  const encoded = values.toString();
  return encoded ? `?${encoded}` : "";
}

function normalizeDaily(value: unknown): DashboardDailyMetric {
  const raw = isRecord(value) ? value : invalid("趋势数据");
  return {
    day: requiredString(raw.day, "趋势日期"),
    visits: numberValue(raw.visits),
    conversations: numberValue(raw.conversations),
    leads: numberValue(raw.leads),
  };
}

function normalizeDashboard(payload: unknown): DashboardOverview {
  const raw = dataRecord(payload, "工作台概览");
  return {
    generatedAt: requiredString(raw.generated_at, "工作台生成时间"),
    periodDays: numberValue(raw.period_days),
    visits: numberValue(raw.visits),
    uniqueVisitors: numberValue(raw.unique_visitors),
    conversations: numberValue(raw.conversations),
    aiAnswers: numberValue(raw.ai_answers),
    totalLeads: numberValue(raw.total_leads),
    newLeads: numberValue(raw.new_leads),
    pendingGaps: numberValue(raw.pending_gaps),
    unreadNotifications: numberValue(raw.unread_notifications),
    conversationRate: numberValue(raw.conversation_rate),
    leadRate: numberValue(raw.lead_rate),
    daily: Array.isArray(raw.daily) ? raw.daily.map(normalizeDaily) : [],
  };
}

function normalizeTopicItem(value: unknown): TopicAnalysisItem {
  const raw = isRecord(value) ? value : invalid("高频话题");
  return {
    topic: requiredString(raw.topic, "话题名称"),
    count: numberValue(raw.count),
    share: numberValue(raw.share),
    sampleQuestions: stringArray(raw.sample_questions),
  };
}

function normalizeTopicAnalysis(payload: unknown): TopicAnalysis {
  const raw = dataRecord(payload, "高频话题分析");
  const status = stringValue(raw.status);
  if (!["empty", "not_generated", "ready", "stale"].includes(status)) {
    invalid("高频话题分析状态");
  }
  return {
    status: status as TopicAnalysis["status"],
    generatedAt: optionalString(raw.generated_at),
    periodDays: numberValue(raw.period_days),
    questionCount: numberValue(raw.question_count),
    analyzedQuestionCount: numberValue(raw.analyzed_question_count),
    summary: optionalString(raw.summary),
    topics: Array.isArray(raw.topics) ? raw.topics.map(normalizeTopicItem) : [],
    provider: optionalString(raw.provider),
    model: optionalString(raw.model),
  };
}

function normalizeEmployeeAnalytics(value: unknown): EmployeeAnalytics {
  const raw = isRecord(value) ? value : invalid("员工表现");
  return {
    userId: requiredString(raw.user_id, "员工 user_id"),
    membershipId: requiredString(raw.membership_id, "员工 membership_id"),
    displayName: stringValue(raw.display_name, "未命名员工"),
    role: stringValue(raw.role),
    membershipStatus: stringValue(raw.membership_status),
    cardCount: numberValue(raw.card_count),
    visits: numberValue(raw.visits),
    uniqueVisitors: numberValue(raw.unique_visitors),
    conversations: numberValue(raw.conversations),
    leads: numberValue(raw.leads),
    conversationRate: numberValue(raw.conversation_rate),
    leadRate: numberValue(raw.lead_rate),
    lastActivityAt: optionalString(raw.last_activity_at),
  };
}

function normalizeEmployeeReconciliation(
  value: unknown,
): EmployeeAnalyticsReconciliation {
  const raw = isRecord(value) ? value : invalid("员工表现对账");
  return {
    cardCount: numberValue(raw.card_count),
    visits: numberValue(raw.visits),
    uniqueVisitors: numberValue(raw.unique_visitors),
    employeeUniqueVisitorsSum: numberValue(raw.employee_unique_visitors_sum),
    conversations: numberValue(raw.conversations),
    totalLeads: numberValue(raw.total_leads),
    conversationRate: numberValue(raw.conversation_rate),
    leadRate: numberValue(raw.lead_rate),
    lastActivityAt: optionalString(raw.last_activity_at),
  };
}

function normalizeEmployeeAnalyticsPage(payload: unknown): EmployeeAnalyticsPage {
  if (!isRecord(payload) || !Array.isArray(payload.data)) {
    invalid("员工表现列表");
  }
  return {
    items: payload.data.map(normalizeEmployeeAnalytics),
    total: numberValue(payload.total),
    limit: numberValue(payload.limit, 20),
    offset: numberValue(payload.offset),
    generatedAt: requiredString(payload.generated_at, "员工表现生成时间"),
    periodDays: numberValue(payload.period_days),
    reconciliation: normalizeEmployeeReconciliation(payload.reconciliation),
  };
}

function normalizeVisit(value: unknown): Visit {
  const raw = isRecord(value) ? value : invalid("访问记录");
  return {
    id: requiredString(raw.id, "访问记录 id"),
    cardId: requiredString(raw.card_id, "访问记录 card_id"),
    cardDisplayName: stringValue(raw.card_display_name, "未命名名片"),
    visitorId: requiredString(raw.visitor_id, "访问记录 visitor_id"),
    source: optionalString(raw.source),
    startedAt: requiredString(raw.started_at, "访问开始时间"),
    endedAt: optionalString(raw.ended_at),
    durationSeconds:
      typeof raw.duration_seconds === "number" ? raw.duration_seconds : undefined,
    conversationCount: numberValue(raw.conversation_count),
  };
}

function normalizeVisitDetail(payload: unknown): VisitDetail {
  const raw = dataRecord(payload, "访问明细");
  return {
    ...normalizeVisit(raw),
    eventCount: numberValue(raw.event_count),
    pageDurations: Array.isArray(raw.page_durations)
      ? raw.page_durations.map((value) => {
          const item = isRecord(value) ? value : invalid("页面停留记录");
          return {
            pageKey: requiredString(item.page_key, "页面标识"),
            pageTitle: requiredString(item.page_title, "页面名称"),
            objectType: optionalString(item.object_type),
            objectId: optionalString(item.object_id),
            durationSeconds: numberValue(item.duration_seconds),
            viewCount: numberValue(item.view_count),
            lastViewedAt: requiredString(item.last_viewed_at, "最后浏览时间"),
          };
        })
      : [],
    questions: Array.isArray(raw.questions)
      ? raw.questions.map((value) => {
          const item = isRecord(value) ? value : invalid("访客问题记录");
          return {
            messageId: requiredString(item.message_id, "问题消息 id"),
            conversationId: requiredString(item.conversation_id, "问题对话 id"),
            question: requiredString(item.question, "访客问题"),
            askedAt: requiredString(item.asked_at, "提问时间"),
            answerStatus: optionalString(item.answer_status),
          };
        })
      : [],
  };
}

function normalizeConversation(value: unknown): Conversation {
  const raw = isRecord(value) ? value : invalid("对话记录");
  return {
    id: requiredString(raw.id, "对话 id"),
    cardId: requiredString(raw.card_id, "对话 card_id"),
    cardDisplayName: stringValue(raw.card_display_name, "未命名名片"),
    visitorId: requiredString(raw.visitor_id, "对话 visitor_id"),
    visitId: optionalString(raw.visit_id),
    status: stringValue(raw.status, "unknown"),
    primaryIntent: optionalString(raw.primary_intent),
    riskLevel: stringValue(raw.risk_level, "unknown"),
    startedAt: requiredString(raw.started_at, "对话开始时间"),
    lastActivityAt: requiredString(raw.last_activity_at, "对话活跃时间"),
    messageCount: numberValue(raw.message_count),
    hasCurrentSummary: raw.has_current_summary === true,
  };
}

function normalizeOpportunity(value: unknown): OpportunityCandidate {
  const raw = isRecord(value) ? value : invalid("潜在机会");
  return {
    conversationId: requiredString(raw.conversation_id, "机会 conversation_id"),
    cardId: requiredString(raw.card_id, "机会 card_id"),
    cardDisplayName: stringValue(raw.card_display_name, "未命名名片"),
    visitorId: requiredString(raw.visitor_id, "机会 visitor_id"),
    question: requiredString(raw.question, "机会问题"),
    reason: stringValue(raw.reason, "高意向提问"),
    score: numberValue(raw.score),
    hasConsentedLead: raw.has_consented_lead === true,
    lastActivityAt: requiredString(raw.last_activity_at, "机会最后活跃时间"),
  };
}

function normalizeCitation(value: unknown): ConversationCitation {
  const raw = isRecord(value) ? value : invalid("引用记录");
  return {
    id: requiredString(raw.id, "引用 id"),
    chunkId: requiredString(raw.chunk_id, "引用 chunk_id"),
    rank: numberValue(raw.rank),
    score: numberValue(raw.score),
    title: stringValue(raw.title, "未命名来源"),
    sourceType: stringValue(raw.source_type),
    sourceId: stringValue(raw.source_id),
    snapshotText: stringValue(raw.snapshot_text),
  };
}

function normalizeAiRun(value: unknown): ConversationAiRun | undefined {
  if (!isRecord(value)) return undefined;
  return {
    provider: stringValue(value.provider),
    model: stringValue(value.model),
    status: stringValue(value.status),
    firstTokenLatencyMs:
      typeof value.first_token_latency_ms === "number"
        ? value.first_token_latency_ms
        : undefined,
    totalLatencyMs: numberValue(value.total_latency_ms),
    retrievalResult: recordValue(value.retrieval_result),
    safetyResult: recordValue(value.safety_result),
    errorCode: optionalString(value.error_code),
  };
}

function normalizeMessage(value: unknown): ConversationMessage {
  const raw = isRecord(value) ? value : invalid("对话消息");
  return {
    id: requiredString(raw.id, "对话消息 id"),
    role: stringValue(raw.role),
    content: stringValue(raw.content),
    status: stringValue(raw.status),
    contentRedacted: raw.content_redacted === true,
    createdAt: requiredString(raw.created_at, "对话消息时间"),
    citations: Array.isArray(raw.citations) ? raw.citations.map(normalizeCitation) : [],
    aiRun: normalizeAiRun(raw.ai_run),
  };
}

function normalizeSummaryValue(value: unknown): ConversationSummary {
  const raw = isRecord(value) ? value : invalid("对话纪要");
  return {
    id: requiredString(raw.id, "对话纪要 id"),
    conversationId: requiredString(raw.conversation_id, "对话纪要 conversation_id"),
    summary: stringValue(raw.summary),
    interests: stringArray(raw.interests),
    strength: optionalString(raw.strength),
    nextStep: optionalString(raw.next_step),
    riskNotes: optionalString(raw.risk_notes),
    sourceMessageIds: stringArray(raw.source_message_ids),
    isCurrent: raw.is_current === true,
    staleAt: optionalString(raw.stale_at),
    approvedAt: optionalString(raw.approved_at),
    approvedBy: optionalString(raw.approved_by),
    createdAt: requiredString(raw.created_at, "纪要创建时间"),
    updatedAt: requiredString(raw.updated_at, "纪要更新时间"),
  };
}

function normalizeSummary(payload: unknown): ConversationSummary {
  return normalizeSummaryValue(unwrapData(payload));
}

function normalizeConversationDetail(payload: unknown): ConversationDetail {
  const raw = dataRecord(payload, "对话详情");
  return {
    ...normalizeConversation(raw),
    messages: Array.isArray(raw.messages) ? raw.messages.map(normalizeMessage) : [],
    currentSummary: isRecord(raw.current_summary)
      ? normalizeSummaryValue(raw.current_summary)
      : undefined,
  };
}

function normalizeLead(value: unknown): Lead {
  const raw = isRecord(value) ? value : invalid("线索记录");
  return {
    id: requiredString(raw.id, "线索 id"),
    cardId: requiredString(raw.card_id, "线索 card_id"),
    cardDisplayName: stringValue(raw.card_display_name, "未命名名片"),
    visitorId: requiredString(raw.visitor_id, "线索 visitor_id"),
    conversationId: optionalString(raw.conversation_id),
    ownerUserId: requiredString(raw.owner_user_id, "线索 owner_user_id"),
    status: stringValue(raw.status, "new"),
    priority: stringValue(raw.priority, "medium"),
    maskedName: stringValue(raw.masked_name, "未提供"),
    maskedContact: stringValue(raw.masked_contact, "未提供"),
    companyName: optionalString(raw.company_name),
    interestTags: stringArray(raw.interest_tags),
    viewedAt: optionalString(raw.viewed_at),
    closedAt: optionalString(raw.closed_at),
    version: numberValue(raw.version, 1),
    createdAt: requiredString(raw.created_at, "线索创建时间"),
    updatedAt: requiredString(raw.updated_at, "线索更新时间"),
  };
}

function normalizeFollowup(value: unknown): LeadFollowup {
  const raw = isRecord(value) ? value : invalid("线索跟进");
  return {
    id: requiredString(raw.id, "线索跟进 id"),
    actorUserId: requiredString(raw.actor_user_id, "线索跟进 actor_user_id"),
    followupType: stringValue(raw.followup_type),
    content: stringValue(raw.content),
    nextAt: optionalString(raw.next_at),
    createdAt: requiredString(raw.created_at, "线索跟进时间"),
  };
}

function normalizeLeadDetail(payload: unknown): LeadDetail {
  const raw = dataRecord(payload, "线索详情");
  return {
    ...normalizeLead(raw),
    name: stringValue(raw.name),
    mobile: optionalString(raw.mobile),
    email: optionalString(raw.email),
    wechat: optionalString(raw.wechat),
    demand: stringValue(raw.demand),
    followups: Array.isArray(raw.followups) ? raw.followups.map(normalizeFollowup) : [],
  };
}

function normalizeGap(value: unknown): KnowledgeGap {
  const raw = isRecord(value) ? value : invalid("知识缺口");
  return {
    id: requiredString(raw.id, "知识缺口 id"),
    conversationId: requiredString(raw.conversation_id, "知识缺口 conversation_id"),
    question: stringValue(raw.question),
    reason: stringValue(raw.reason),
    status: stringValue(raw.status, "pending"),
    suggestedAnswer: optionalString(raw.suggested_answer),
    occurrenceCount: numberValue(raw.occurrence_count, 1),
    lastSeenAt: requiredString(raw.last_seen_at, "知识缺口最后发现时间"),
    approvedVersionId: optionalString(raw.approved_version_id),
    evidence: recordValue(raw.evidence),
    createdAt: requiredString(raw.created_at, "知识缺口创建时间"),
    updatedAt: requiredString(raw.updated_at, "知识缺口更新时间"),
  };
}

function normalizeNotification(value: unknown): AdminNotification {
  const raw = isRecord(value) ? value : invalid("通知");
  return {
    id: requiredString(raw.id, "通知 id"),
    notificationType: stringValue(raw.notification_type),
    title: stringValue(raw.title),
    body: stringValue(raw.body),
    resourceType: optionalString(raw.resource_type),
    resourceId: optionalString(raw.resource_id),
    readAt: optionalString(raw.read_at),
    createdAt: requiredString(raw.created_at, "通知创建时间"),
  };
}

function normalizeNotificationList(payload: unknown): NotificationList {
  if (!isRecord(payload) || !Array.isArray(payload.data)) invalid("通知列表");
  return {
    items: payload.data.map(normalizeNotification),
    total: numberValue(payload.total),
    unread: numberValue(payload.unread),
  };
}

function normalizePrivacyRequest(value: unknown): PrivacyRequest {
  const raw = isRecord(value) ? value : invalid("隐私请求");
  return {
    id: requiredString(raw.id, "隐私请求 id"),
    visitorId: requiredString(raw.visitor_id, "隐私请求 visitor_id"),
    requestType: stringValue(raw.request_type),
    status: stringValue(raw.status, "pending"),
    verificationMethod: optionalString(raw.verification_method),
    handledBy: optionalString(raw.handled_by),
    completedAt: optionalString(raw.completed_at),
    evidence: recordValue(raw.evidence),
    createdAt: requiredString(raw.created_at, "隐私请求创建时间"),
    updatedAt: requiredString(raw.updated_at, "隐私请求更新时间"),
  };
}

export function createWorkflowApi(client: ApiClient) {
  return {
    async getDashboard(periodDays = 30): Promise<DashboardOverview> {
      return normalizeDashboard(
        await client.get(`/admin/dashboard${query({ period_days: periodDays })}`),
      );
    },

    async getTopicAnalysis(periodDays = 30): Promise<TopicAnalysis> {
      return normalizeTopicAnalysis(
        await client.get(
          `/admin/analytics/topics${query({ period_days: periodDays })}`,
        ),
      );
    },

    async analyzeTopics(periodDays = 30): Promise<TopicAnalysis> {
      return normalizeTopicAnalysis(
        await client.post(
          `/admin/analytics/topics:analyze${query({ period_days: periodDays })}`,
        ),
      );
    },

    async listEmployeeAnalytics(options: {
      periodDays?: number;
      limit?: number;
      offset?: number;
    } = {}): Promise<EmployeeAnalyticsPage> {
      return normalizeEmployeeAnalyticsPage(
        await client.get(
          `/admin/analytics/employees${query({
            period_days: options.periodDays ?? 30,
            limit: options.limit ?? 20,
            offset: options.offset ?? 0,
          })}`,
        ),
      );
    },

    async listVisits(options: {
      limit?: number;
      offset?: number;
      cardId?: string;
    } = {}): Promise<PageResult<Visit>> {
      return normalizePage(
        await client.get(
          `/admin/visits${query({
            limit: options.limit ?? 20,
            offset: options.offset ?? 0,
            card_id: options.cardId,
          })}`,
        ),
        "访问记录列表",
        normalizeVisit,
      );
    },

    async getVisit(id: string): Promise<VisitDetail> {
      return normalizeVisitDetail(
        await client.get(`/admin/visits/${encodeURIComponent(id)}`),
      );
    },

    async listConversations(options: {
      limit?: number;
      offset?: number;
      status?: ConversationStatus;
      cardId?: string;
      visitorId?: string;
    } = {}): Promise<PageResult<Conversation>> {
      return normalizePage(
        await client.get(
          `/admin/conversations${query({
            limit: options.limit ?? 20,
            offset: options.offset ?? 0,
            status: options.status,
            card_id: options.cardId,
            visitor_id: options.visitorId,
          })}`,
        ),
        "对话列表",
        normalizeConversation,
      );
    },

    async getConversation(id: string): Promise<ConversationDetail> {
      return normalizeConversationDetail(
        await client.get(`/admin/conversations/${encodeURIComponent(id)}`),
      );
    },

    async listOpportunities(options: {
      limit?: number;
      offset?: number;
    } = {}): Promise<PageResult<OpportunityCandidate>> {
      return normalizePage(
        await client.get(
          `/admin/opportunities${query({
            limit: options.limit ?? 20,
            offset: options.offset ?? 0,
          })}`,
        ),
        "潜在机会列表",
        normalizeOpportunity,
      );
    },

    async generateConversationSummary(id: string): Promise<ConversationSummary> {
      return normalizeSummary(
        await client.post(
          `/admin/conversations/${encodeURIComponent(id)}:summarize`,
        ),
      );
    },

    async getSummary(id: string): Promise<ConversationSummary> {
      return normalizeSummary(
        await client.get(`/admin/summaries/${encodeURIComponent(id)}`),
      );
    },

    async approveSummary(id: string): Promise<ConversationSummary> {
      return normalizeSummary(
        await client.post(`/admin/summaries/${encodeURIComponent(id)}:approve`),
      );
    },

    async listLeads(options: {
      limit?: number;
      offset?: number;
      status?: LeadStatus;
    } = {}): Promise<PageResult<Lead>> {
      return normalizePage(
        await client.get(
          `/admin/leads${query({
            limit: options.limit ?? 20,
            offset: options.offset ?? 0,
            status: options.status,
          })}`,
        ),
        "线索列表",
        normalizeLead,
      );
    },

    async getLead(id: string): Promise<LeadDetail> {
      return normalizeLeadDetail(
        await client.get(`/admin/leads/${encodeURIComponent(id)}`),
      );
    },

    async updateLead(
      id: string,
      version: number,
      input: { status: LeadStatus; priority: LeadPriority },
    ): Promise<LeadDetail> {
      return normalizeLeadDetail(
        await client.patch(
          `/admin/leads/${encodeURIComponent(id)}`,
          { status: input.status, priority: input.priority },
          { version },
        ),
      );
    },

    async createLeadFollowup(
      id: string,
      input: LeadFollowupInput,
    ): Promise<LeadFollowup> {
      return normalizeFollowup(
        unwrapData(
          await client.post(`/admin/leads/${encodeURIComponent(id)}/followups`, {
            followup_type: input.followupType,
            content: input.content.trim(),
            next_at: input.nextAt || null,
          }),
        ),
      );
    },

    async listKnowledgeGaps(options: {
      limit?: number;
      offset?: number;
      status?: KnowledgeGapStatus;
    } = {}): Promise<PageResult<KnowledgeGap>> {
      return normalizePage(
        await client.get(
          `/admin/knowledge/gaps${query({
            limit: options.limit ?? 20,
            offset: options.offset ?? 0,
            status: options.status,
          })}`,
        ),
        "知识缺口列表",
        normalizeGap,
      );
    },

    async updateKnowledgeGap(id: string, suggestedAnswer: string): Promise<KnowledgeGap> {
      return normalizeGap(
        unwrapData(
          await client.patch(`/admin/knowledge/gaps/${encodeURIComponent(id)}`, {
            suggested_answer: suggestedAnswer.trim(),
          }),
        ),
      );
    },

    async approveKnowledgeGap(id: string): Promise<KnowledgeGap> {
      return normalizeGap(
        unwrapData(
          await client.post(`/admin/knowledge/gaps/${encodeURIComponent(id)}:approve`),
        ),
      );
    },

    async rejectKnowledgeGap(id: string): Promise<KnowledgeGap> {
      return normalizeGap(
        unwrapData(
          await client.post(`/admin/knowledge/gaps/${encodeURIComponent(id)}:reject`),
        ),
      );
    },

    async listNotifications(options: {
      limit?: number;
      unreadOnly?: boolean;
    } = {}): Promise<NotificationList> {
      return normalizeNotificationList(
        await client.get(
          `/admin/notifications${query({
            limit: options.limit ?? 50,
            unread_only: options.unreadOnly,
          })}`,
        ),
      );
    },

    async markNotificationRead(id: string): Promise<AdminNotification> {
      return normalizeNotification(
        unwrapData(
          await client.post(`/admin/notifications/${encodeURIComponent(id)}/read`),
        ),
      );
    },

    async listPrivacyRequests(options: {
      limit?: number;
      offset?: number;
      status?: PrivacyRequestStatus;
    } = {}): Promise<PageResult<PrivacyRequest>> {
      return normalizePage(
        await client.get(
          `/admin/privacy-requests${query({
            limit: options.limit ?? 20,
            offset: options.offset ?? 0,
            status: options.status,
          })}`,
        ),
        "隐私请求列表",
        normalizePrivacyRequest,
      );
    },

    async updatePrivacyRequest(
      id: string,
      input: { status: PrivacyRequestStatus; verificationMethod?: string },
    ): Promise<PrivacyRequest> {
      return normalizePrivacyRequest(
        unwrapData(
          await client.patch(`/admin/privacy-requests/${encodeURIComponent(id)}`, {
            status: input.status,
            verification_method: input.verificationMethod?.trim() || null,
          }),
        ),
      );
    },
  };
}

export const workflowApi = createWorkflowApi(apiClient);

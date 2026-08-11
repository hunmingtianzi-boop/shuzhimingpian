export type AdminUser = {
  id: string;
  displayName: string;
  membershipId: string;
  tenantId: string;
  companyId: string;
  role?: string;
  permissions: string[];
};

export type MemberRole = "company_admin" | "card_owner";
export type MemberStatus = "active" | "disabled";
export type MemberLifecycleStatus = MemberStatus | "suspended";
export type MemberRowOutcome =
  | "created"
  | "updated"
  | "unchanged"
  | "duplicate"
  | "failed";

export type CompanyMember = {
  membershipId: string;
  userId: string;
  account: string;
  displayName: string;
  jobTitle?: string;
  avatarUrl?: string;
  businessSummary?: string;
  role: MemberRole;
  permissions: string[];
  status: MemberLifecycleStatus;
  credentialEnabled: boolean;
  createdAt: string;
  updatedAt: string;
};

export type MemberCreateInput = {
  account: string;
  displayName: string;
  password: string;
  email?: string;
  mobile?: string;
  jobTitle?: string;
  avatarUrl?: string;
  businessSummary?: string;
  role: MemberRole;
  permissions: string[];
  status: MemberStatus;
  rotatePassword?: boolean;
};

export type MemberAccessInput = {
  displayName?: string;
  jobTitle?: string;
  avatarUrl?: string;
  businessSummary?: string;
  role?: MemberRole;
  permissions?: string[];
};

export type MemberSelfProfileInput = {
  avatarUrl: string;
};

export type MemberRowError = {
  code: string;
  message: string;
  fields: string[];
};

export type BulkMemberRowResult = {
  rowNumber: number;
  account?: string;
  outcome: MemberRowOutcome;
  member?: CompanyMember;
  error?: MemberRowError;
  duplicateOfRow?: number;
};

export type BulkMemberResult = {
  batchId: string;
  summary: {
    total: number;
    succeeded: number;
    created: number;
    updated: number;
    unchanged: number;
    duplicated: number;
    failed: number;
  };
  rows: BulkMemberRowResult[];
};

export type MemberPasswordReset = {
  membershipId: string;
  passwordChangedAt: string;
  sessionsRevoked: number;
};

export type CompanyProfile = {
  id?: string;
  name: string;
  summary: string;
  industry: string;
  region: string;
  website: string;
  logoUrl: string;
  profilePersonalizationPolicyVersion: string;
  version?: number;
  updatedAt?: string;
};

export type CompanyProfileInput = Omit<
  CompanyProfile,
  "id" | "updatedAt"
>;

export type CardSettings = {
  id?: string;
  displayName: string;
  title: string;
  slug: string;
  avatarUrl: string;
  assistantName: string;
  welcomeMessage: string;
  suggestedQuestions: string[];
  policyVersions: {
    privacy: string;
    chatNotice: string;
    leadConsent: string;
  };
  status?: string;
  version?: number;
  updatedAt?: string;
};

export type CardSettingsInput = Omit<
  CardSettings,
  "id" | "status" | "updatedAt"
>;

export type KnowledgeStatus =
  | "draft"
  | "review_pending"
  | "published"
  | "archived"
  | string;

export type KnowledgeDocument = {
  id: string;
  title: string;
  status: KnowledgeStatus;
  sourceType?: string;
  visibility?: KnowledgeVisibility;
  version?: number;
  latestVersion?: {
    id: string;
    versionNumber: number;
    reviewStatus: string;
    chunkCount: number;
    indexedChunkCount: number;
    indexStatus?: string;
    indexErrorCode?: string;
  };
  updatedAt?: string;
};

export type KnowledgeVisibility = "public" | "authenticated" | "internal";

export type KnowledgeDocumentDetail = KnowledgeDocument & {
  rawText: string;
  visibility: KnowledgeVisibility;
  metadata: Record<string, unknown>;
  editableVersionId?: string;
};

export type KnowledgeDocumentInput = {
  title: string;
  answer: string;
  visibility: KnowledgeVisibility;
  metadata: Record<string, unknown>;
};

export type SelectableFaqDocument = {
  id: string;
  title: string;
  answer: string;
  status: "published";
  visibility: "public";
};

export type LoginInput = {
  account: string;
  credential: string;
};

export type PlatformEnterprise = {
  tenantId: string;
  tenantSlug: string;
  tenantName: string;
  companyId: string;
  companyName: string;
  status: string;
  createdAt: string;
  version?: number;
};

export type PlatformCardProjection = {
  id: string;
  cardKind: "enterprise" | "employee";
  displayName: string;
  title: string;
  status: string;
  updatedAt: string;
  shareUrl?: string;
};

export type PlatformEnterpriseDetail = PlatformEnterprise & {
  version: number;
  onboardingStatus: string;
  profileCompletion: number;
  employeeCount: number;
  cardCount: number;
  publishedCardCount: number;
  visits30d: number;
  conversations30d: number;
    leads30d: number;
    cards: PlatformCardProjection[];
    businessProfile: PlatformOnboardingSuggestion[];
    updatedAt: string;
};

export type PlatformEnterpriseLifecycle = {
  tenantId: string;
  companyId: string;
  previousStatus: "active" | "suspended" | "disabled";
  status: "active" | "suspended";
  version: number;
  changed: boolean;
  updatedAt: string;
};

export type PlatformOverview = {
  generatedAt: string;
  enterpriseCount: number;
  activeEnterpriseCount: number;
  onboardingCount: number;
  publishedCardCount: number;
  visits30d: number;
  conversations30d: number;
  leads30d: number;
  failedTaskCount: number;
  llmReady: boolean;
  importReady: boolean;
};

export type PlatformLlmPurpose = "chat_main";
export type PlatformLlmThinking = "enabled" | "disabled";
export type PlatformLlmTestStatus = "untested" | "succeeded" | "failed";

export type PlatformLlmProfile = {
  id: string;
  name: string;
  purpose: PlatformLlmPurpose;
  provider: string;
  baseUrl: string;
  model: string;
  thinking: PlatformLlmThinking;
  reasoningEffort?: "high" | "max";
  timeoutSeconds: number;
  maxRetries: number;
  maxConcurrency: number;
  maxOutputTokens: number;
  temperature: number;
  dailyBudgetCny: number;
  inputPriceCnyPerMillion: number;
  outputPriceCnyPerMillion: number;
  allowGeneralAnswers: boolean;
  faqFastPathEnabled: boolean;
  keyConfigured: boolean;
  keyHint?: string;
  enabled: boolean;
  isActive: boolean;
  version: number;
  lastTestStatus: PlatformLlmTestStatus;
  lastTestLatencyMs?: number;
  lastTestedAt?: string;
  createdAt: string;
  updatedAt: string;
};

export type CreatePlatformLlmProfileInput = {
  name: string;
  provider: string;
  baseUrl: string;
  model: string;
  apiKey: string;
  thinking?: PlatformLlmThinking;
  reasoningEffort?: "high" | "max";
  timeoutSeconds?: number;
  maxRetries?: number;
  maxConcurrency?: number;
  maxOutputTokens?: number;
  temperature?: number;
  dailyBudgetCny?: number;
  inputPriceCnyPerMillion?: number;
  outputPriceCnyPerMillion?: number;
  allowGeneralAnswers?: boolean;
  faqFastPathEnabled?: boolean;
  enabled?: boolean;
};

export type UpdatePlatformLlmProfileInput = Partial<
  Omit<CreatePlatformLlmProfileInput, "apiKey">
> & {
  apiKey?: string;
  expectedVersion: number;
};

export type ActivatePlatformLlmProfileInput = {
  expectedVersion: number;
  expectedActiveProfileId?: string;
};

export type PlatformLlmConnectionTest = {
  status: "succeeded" | "failed";
  provider: string;
  model: string;
  latencyMs: number;
  errorCode?: string;
};

export type PlatformOnboardingStatus =
  | "draft"
  | "processing"
  | "review"
  | "manual_required"
  | "ready_to_confirm"
  | "confirmed"
  | "cancelled"
  | "expired"
  | "failed";

export type StartPlatformOnboardingInput = {
  tenantSlug: string;
  tenantName?: string;
  adminAccount: string;
  adminDisplayName: string;
  adminPassword: string;
};

/**
 * The only client-selected import target. The server resolves provisional
 * tenant/company scope from this owned session and never accepts raw scope IDs.
 */
export type PlatformOnboardingImportTarget = {
  onboardingSessionId: string;
};

export type PlatformOnboardingSuggestionSource = {
  importItemId: string;
  fileName: string;
  documentId?: string;
  excerpt?: string;
};

export type PlatformOnboardingSuggestion = {
  field: string;
  value: string;
  confidence?: number;
  generationVersion: number;
  sources: PlatformOnboardingSuggestionSource[];
};

export type PlatformOnboardingSession = {
  id: string;
  status: PlatformOnboardingStatus;
  tenantSlug: string;
  tenantName?: string;
  adminAccount?: string;
  adminDisplayName?: string;
  initialCardDisplayName?: string;
  initialCardTitle?: string;
  version: number;
  importBatchIds: string[];
  suggestions: PlatformOnboardingSuggestion[];
  businessProfile?: PlatformOnboardingSuggestion[];
  expiresAt?: string;
  confirmedEnterprise?: CreatedPlatformEnterprise;
  createdAt: string;
  updatedAt: string;
};

export type PlatformOnboardingImportItemStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "dead_letter";

export type PlatformOnboardingImportItem = {
  id: string;
  fileName: string;
  sourceType: string;
  status: PlatformOnboardingImportItemStatus;
  errorCode?: string;
  createdAt: string;
  completedAt?: string;
};

export type PlatformOnboardingImportStatus = {
  sessionId: string;
  settled: boolean;
  items: PlatformOnboardingImportItem[];
};

export type ConfirmPlatformOnboardingInput = {
  expectedVersion: number;
  tenantName: string;
  companyName: string;
  industry?: string;
  summary?: string;
  website?: string;
  initialCardDisplayName: string;
  initialCardTitle?: string;
  assistantName?: string;
  welcomeMessage?: string;
};

export type PlatformCompanyAggregate = {
  companyId: string;
  companyName: string;
  employeeCount: number;
  visits30d: number;
  uniqueVisitors30d: number;
  lastVisitAt?: string;
};

export type PlatformTaskProjection = {
  id: string;
  taskType: string;
  businessLabel: string;
  status: string;
  companyId?: string;
  companyName?: string;
  errorCode?: string;
  createdAt: string;
  updatedAt: string;
};

export type PlatformAuditProjection = {
  id: string;
  actorDisplayName: string;
  action: string;
  businessLabel: string;
  resourceType: string;
  resourceId?: string;
  result: string;
  createdAt: string;
};

export type PlatformServiceHealth = {
  service: "api" | "database" | "redis" | "object_storage" | "worker";
  status: "healthy" | "degraded" | "unavailable";
  checkedAt: string;
  latencyMs?: number;
  errorCode?: string;
};

export type CreatePlatformEnterpriseInput = {
  tenantSlug: string;
  tenantName: string;
  companyName: string;
  industry: string;
  adminAccount: string;
  adminDisplayName: string;
  adminPassword: string;
  initialCardTitle: string;
};

export type CreatedPlatformEnterprise = PlatformEnterprise & {
  adminUserId: string;
  adminMembershipId: string;
  initialCardId: string;
  initialCardSlug: string;
};

export type ContentStatus =
  | "draft"
  | "review_pending"
  | "published"
  | "archived"
  | string;

export type ContentVisibility = "public" | "authenticated" | "internal";

export type VersionedResource = {
  id: string;
  status: ContentStatus;
  version: number;
  publishedAt?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type Product = VersionedResource & {
  slug: string;
  name: string;
  category: string;
  summary: string;
  detail: string;
  audience: string;
  priceBoundary: string;
  imageUrl: string;
  visibility: ContentVisibility;
  sortOrder: number;
  settings: Record<string, unknown>;
};

export type ProductInput = Omit<
  Product,
  "id" | "status" | "version" | "publishedAt" | "createdAt" | "updatedAt"
>;

export type CaseStudy = VersionedResource & {
  slug: string;
  title: string;
  industry: string;
  background: string;
  solution: string;
  result: string;
  clientDisplayName: string;
  imageUrl: string;
  visibility: ContentVisibility;
  sortOrder: number;
  settings: Record<string, unknown>;
};

export type CaseStudyInput = Omit<
  CaseStudy,
  "id" | "status" | "version" | "publishedAt" | "createdAt" | "updatedAt"
>;

export type ForbiddenAction = "refuse" | "handoff" | "safe_template";

export type ForbiddenTopic = {
  id: string;
  topic: string;
  matchTerms: string[];
  action: ForbiddenAction;
  safeResponse: string;
  isActive: boolean;
  version: number;
  createdAt?: string;
  updatedAt?: string;
};

export type ForbiddenTopicInput = Omit<
  ForbiddenTopic,
  "id" | "version" | "createdAt" | "updatedAt"
>;

export type IdentityContactKind = "phone" | "wechat" | "email" | "location" | "website" | "other";

export type IdentityContactField = {
  id: string;
  kind: IdentityContactKind;
  label: string;
  value: string;
  href?: string;
};

export type ManagedCard = VersionedResource & {
  cardKind: "enterprise" | "employee";
  ownerUserId?: string;
  slug: string;
  displayName: string;
  title: string;
  avatarUrl: string;
  assistantName: string;
  welcomeMessage: string;
  suggestedQuestions: string[];
  policyVersions: {
    privacy: string;
    chatNotice: string;
    leadConsent: string;
  };
  identityTitles?: string[];
  contactFields?: IdentityContactField[];
  employeeContactVisibility?: Array<"mobile" | "email">;
  shareUrl: string;
  qrUrl: string;
};

export type ManagedCardInput = {
  cardKind: ManagedCard["cardKind"];
  ownerUserId?: string;
  displayName: string;
  title: string;
  avatarUrl: string;
  assistantName: string;
  welcomeMessage: string;
  suggestedQuestions: string[];
  policyVersions: ManagedCard["policyVersions"];
  identityTitles: string[];
  contactFields: IdentityContactField[];
  employeeContactVisibility: Array<"mobile" | "email">;
  /** Empty means use the company default configuration on create. */
  templateSourceCardId?: string;
  /** In-memory customize-before-create result; never creates an orphan card. */
  templateDocument?: EnterpriseTemplate["draft"];
  /** Local wizard state; never sent to the API. */
  composerMode?: "default" | "customize";
};

export type WeComCardContactWay = {
  id: string;
  cardId: string;
  ownerUserId: string;
  qrCodeUrl?: string;
  provisionedAt: string;
};

export type CardAssetUpload = {
  url: string;
  contentType: "image/webp";
  width: number;
  height: number;
  sizeBytes: number;
};

export type EnterpriseTemplateBlockType =
  | "identity"
  | "rich_text"
  | "business_collection"
  | "image_gallery"
  | "video_link"
  | "case_collection"
  | "trust_panel"
  | "faq"
  | "cta"
  | "action_collection"
  | "ai_assistant";

export type EnterpriseTemplateLayoutVariant =
  | "auto"
  | "list"
  | "grid"
  | "carousel"
  | "featured"
  | "mosaic"
  | "horizontal"
  | "vertical";

export type EnterpriseTemplateActionTargetType =
  | "external_url"
  | "internal_path"
  | "phone"
  | "map";

/** Matches the presentation families used by the card-studio simulator. */
export type EnterpriseTemplateActionTemplate =
  | "shortcuts"
  | "media"
  | "event"
  | "banner"
  | "articles"
  | "video"
  | "buttons";

export type EnterpriseTemplateActionItem = {
  id: string;
  title: string;
  summary?: string;
  label?: string;
  tag?: string;
  icon?: "external" | "building" | "calendar" | "file" | "play";
  date?: string;
  location?: string;
  source?: string;
  status?: string;
  duration?: string;
  imageUrl?: string;
  targetType: EnterpriseTemplateActionTargetType;
  targetValue: string;
  openMode: "self" | "new_tab";
};

export type EnterpriseTemplateGalleryItem = {
  id: string;
  imageUrl: string;
  title?: string;
  description?: string;
  timeLabel?: string;
  periodLabel?: string;
  badgeMode: "title" | "time" | "period" | "custom" | "none";
  badgeText?: string;
  altText?: string;
  linkUrl?: string;
};

export type EnterpriseTemplateProductOverride = {
  id: string; title?: string; category?: string; summary?: string; imageUrl?: string; ctaLabel?: string;
};

export type EnterpriseTemplateCaseOverride = {
  id: string; title?: string; industry?: string; clientName?: string; background?: string;
  solution?: string; summary?: string; result?: string; imageUrl?: string; ctaLabel?: string;
  metrics?: Array<{ value: string; label: string }>;
};

export type EnterpriseTemplatePresentation = {
  identityLayout?: "horizontal" | "vertical";
  background?: {
    assetUrl?: string;
    fit?: "cover" | "contain" | "custom";
    position?: "center" | "top" | "bottom" | "left" | "right" | "topLeft" | "topRight" | "bottomLeft" | "bottomRight";
    aspectRatio?: "auto" | "16:9" | "4:3" | "3:2" | "1:1";
    focalX?: number;
    focalY?: number;
    scale?: number;
    opacity?: number;
    overlay?: "none" | "light" | "dark" | "brand";
  };
};

export type EnterpriseTemplateBlock = {
  id: string;
  type: EnterpriseTemplateBlockType;
  visible: boolean;
  showTitle?: boolean;
  directoryEnabled?: boolean;
  sortOrder: number;
  title?: string;
  body?: string;
  imageUrls?: string[];
  galleryItems?: EnterpriseTemplateGalleryItem[];
  videoUrl?: string;
  videoCoverUrl?: string;
  productIds?: string[];
  productOverrides?: EnterpriseTemplateProductOverride[];
  caseIds?: string[];
  caseOverrides?: EnterpriseTemplateCaseOverride[];
  layoutVariant?: EnterpriseTemplateLayoutVariant;
  itemLimit?: number;
  /** Only used by the action-entry block; controls its information shape. */
  actionTemplate?: EnterpriseTemplateActionTemplate;
  presentation?: EnterpriseTemplatePresentation;
  actionItems?: EnterpriseTemplateActionItem[];
  /** FAQ content always resolves from the company knowledge base. */
  faqMode?: "all_published" | "selected";
  /** Ordered canonical KnowledgeDocument ids, used only in selected mode. */
  faqDocumentIds?: string[];
  ctaLabel?: string;
  ctaUrl?: string;
};

export type EnterpriseTemplate = {
  cardId: string;
  version: number;
  draft: {
    schemaVersion: 1;
    themeKey: EnterpriseTemplateThemeKey;
    blocks: EnterpriseTemplateBlock[];
  };
  published?: {
    schemaVersion: 1;
    themeKey: EnterpriseTemplateThemeKey;
    blocks: EnterpriseTemplateBlock[];
  };
};

export type CardComposerDefault = {
  cardKind: ManagedCard["cardKind"];
  version: number;
  document: EnterpriseTemplate["draft"];
};

export type EnterpriseTemplateThemeKey = "brand" | "clean" | "warm";

export type PageResult<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type DashboardDailyMetric = {
  day: string;
  visits: number;
  conversations: number;
  leads: number;
};

export type EnterpriseReadiness = {
  generatedAt: string;
  llmReady: boolean;
  unpublishedCardCount: number;
  processingImportBatchCount: number;
  failedImportBatchCount: number;
};

export type DashboardOverview = {
  generatedAt: string;
  periodDays: number;
  visits: number;
  uniqueVisitors: number;
  conversations: number;
  aiAnswers: number;
  totalLeads: number;
  newLeads: number;
  pendingGaps: number;
  unreadNotifications: number;
  conversationRate: number;
  leadRate: number;
  daily: DashboardDailyMetric[];
};

export type TopicAnalysisStatus =
  | "empty"
  | "not_generated"
  | "ready"
  | "stale";

export type TopicAnalysisItem = {
  topic: string;
  count: number;
  share: number;
  sampleQuestions: string[];
};

export type TopicAnalysis = {
  status: TopicAnalysisStatus;
  generatedAt?: string;
  periodDays: number;
  questionCount: number;
  analyzedQuestionCount: number;
  summary?: string;
  topics: TopicAnalysisItem[];
  provider?: string;
  model?: string;
};

export type EmployeeAnalytics = {
  userId: string;
  membershipId: string;
  displayName: string;
  role: string;
  membershipStatus: string;
  cardCount: number;
  visits: number;
  uniqueVisitors: number;
  conversations: number;
  leads: number;
  conversationRate: number;
  leadRate: number;
  lastActivityAt?: string;
};

export type EmployeeAnalyticsReconciliation = {
  cardCount: number;
  visits: number;
  uniqueVisitors: number;
  employeeUniqueVisitorsSum: number;
  conversations: number;
  totalLeads: number;
  conversationRate: number;
  leadRate: number;
  lastActivityAt?: string;
};

export type EmployeeAnalyticsPage = PageResult<EmployeeAnalytics> & {
  generatedAt: string;
  periodDays: number;
  reconciliation: EmployeeAnalyticsReconciliation;
};

export type Visit = {
  id: string;
  cardId: string;
  cardDisplayName: string;
  visitorId: string;
  source?: string;
  startedAt: string;
  endedAt?: string;
  durationSeconds?: number;
  conversationCount: number;
};

export type ConversationStatus = "active" | "closed" | "expired" | "blocked";

export type Conversation = {
  id: string;
  cardId: string;
  cardDisplayName: string;
  visitorId: string;
  visitId?: string;
  status: string;
  primaryIntent?: string;
  riskLevel: string;
  startedAt: string;
  lastActivityAt: string;
  messageCount: number;
  hasCurrentSummary: boolean;
};

export type OpportunityCandidate = {
  conversationId: string;
  cardId: string;
  cardDisplayName: string;
  visitorId: string;
  question: string;
  reason: string;
  score: number;
  hasConsentedLead: boolean;
  lastActivityAt: string;
};

export type ConversationCitation = {
  id: string;
  chunkId: string;
  rank: number;
  score: number;
  title: string;
  sourceType: string;
  sourceId: string;
  snapshotText: string;
};

export type ConversationAiRun = {
  provider: string;
  model: string;
  status: string;
  firstTokenLatencyMs?: number;
  totalLatencyMs: number;
  retrievalResult: Record<string, unknown>;
  safetyResult: Record<string, unknown>;
  errorCode?: string;
};

export type ConversationMessage = {
  id: string;
  role: string;
  content: string;
  status: string;
  contentRedacted: boolean;
  createdAt: string;
  citations: ConversationCitation[];
  aiRun?: ConversationAiRun;
};

export type ConversationSummary = {
  id: string;
  conversationId: string;
  summary: string;
  interests: string[];
  strength?: string;
  nextStep?: string;
  riskNotes?: string;
  sourceMessageIds: string[];
  isCurrent: boolean;
  staleAt?: string;
  approvedAt?: string;
  approvedBy?: string;
  createdAt: string;
  updatedAt: string;
};

export type ConversationDetail = Conversation & {
  messages: ConversationMessage[];
  currentSummary?: ConversationSummary;
};

export type LeadStatus = "new" | "viewed" | "following" | "won" | "lost" | "invalid";
export type LeadPriority = "low" | "medium" | "high";

export type Lead = {
  id: string;
  cardId: string;
  cardDisplayName: string;
  visitorId: string;
  conversationId?: string;
  ownerUserId: string;
  status: string;
  priority: string;
  maskedName: string;
  maskedContact: string;
  companyName?: string;
  interestTags: string[];
  viewedAt?: string;
  closedAt?: string;
  version: number;
  createdAt: string;
  updatedAt: string;
};

export type LeadFollowup = {
  id: string;
  actorUserId: string;
  followupType: string;
  content: string;
  nextAt?: string;
  createdAt: string;
};

export type LeadDetail = Lead & {
  name: string;
  mobile?: string;
  email?: string;
  wechat?: string;
  demand: string;
  followups: LeadFollowup[];
};

export type LeadFollowupInput = {
  followupType: "note" | "call" | "message" | "meeting" | "status_change";
  content: string;
  nextAt?: string;
};

export type KnowledgeGapStatus =
  | "pending"
  | "drafted"
  | "approved"
  | "indexing"
  | "indexed"
  | "rejected"
  | "failed";

export type KnowledgeGap = {
  id: string;
  conversationId: string;
  question: string;
  reason: string;
  status: string;
  suggestedAnswer?: string;
  occurrenceCount: number;
  lastSeenAt: string;
  approvedVersionId?: string;
  evidence: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type AdminNotification = {
  id: string;
  notificationType: string;
  title: string;
  body: string;
  resourceType?: string;
  resourceId?: string;
  readAt?: string;
  createdAt: string;
};

export type NotificationList = {
  items: AdminNotification[];
  total: number;
  unread: number;
};

export type PrivacyRequestStatus =
  | "pending"
  | "verified"
  | "in_progress"
  | "completed"
  | "rejected";

export type PrivacyRequest = {
  id: string;
  visitorId: string;
  requestType: string;
  status: string;
  verificationMethod?: string;
  handledBy?: string;
  completedAt?: string;
  evidence: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

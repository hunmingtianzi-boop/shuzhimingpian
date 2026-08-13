import { apiClient, ApiClient, ApiError, unwrapData } from "./client";

type JsonRecord = Record<string, unknown>;

export type KnowledgeImportBatchStatus =
  | "pending"
  | "processing"
  | "completed"
  | "completed_with_errors"
  | "failed"
  | "dead_letter";
export type KnowledgeImportItemStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "dead_letter";

export type KnowledgeImportSourceType =
  | "pdf"
  | "docx"
  | "pptx"
  | "xlsx"
  | "csv"
  | "txt"
  | "md"
  | "html"
  | "htm"
  | "png"
  | "jpg"
  | "jpeg"
  | "webp"
  | "tiff"
  | "bmp";

/**
 * Individual pipeline stages are deliberately optional for compatibility with
 * the original import endpoint. Once available they distinguish extraction,
 * indexing and publication rather than treating a completed worker job as a
 * published knowledge item.
 */
export type KnowledgeImportStageStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "skipped";

export type KnowledgeImportItem = {
  id: string;
  fileName: string;
  sourceType: KnowledgeImportSourceType;
  status: KnowledgeImportItemStatus;
  rowNumber?: number;
  documentId?: string;
  versionId?: string;
  errorCode?: string;
  parseStatus?: KnowledgeImportStageStatus;
  indexStatus?: KnowledgeImportStageStatus;
  publishStatus?: KnowledgeImportStageStatus;
  publishedAt?: string;
  createdAt: string;
  completedAt?: string;
};

export type KnowledgeImportBatch = {
  id: string;
  status: KnowledgeImportBatchStatus;
  totalItems: number;
  pendingItems: number;
  succeededItems: number;
  failedItems: number;
  autoPublish: boolean;
  createdAt: string;
  completedAt?: string;
  items: KnowledgeImportItem[];
};

export type KnowledgeImportList = {
  items: KnowledgeImportBatch[];
  total: number;
  limit: number;
  offset: number;
};

export type ContentImportCategory =
  | "enterprise_profile"
  | "products"
  | "case_studies"
  | "faqs"
  | "unclassified";
export type ContentImportCandidateStatus = "pending_review" | "accepted" | "ignored" | "conflict";

export type ContentImportCandidate = {
  id: string;
  runId: string;
  category: ContentImportCategory;
  payload: Record<string, string>;
  sourceId: string;
  sourceText: string;
  confidence: number;
  status: ContentImportCandidateStatus;
  targetResourceType?: string;
  targetResourceId?: string;
  version: number;
};

export type ContentImportRun = {
  id: string;
  batchId: string;
  status: "processing" | "review" | "manual_required";
  provider: string;
  model: string;
  attempts: number;
  failureCode?: string;
  counts: Record<string, number>;
  candidates: ContentImportCandidate[];
  createdAt: string;
};

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value) {
    throw new ApiError(`知识导入接口响应缺少 ${field}。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value;
}

function requiredCount(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new ApiError(`知识导入接口响应缺少 ${field}。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

const batchStatuses = new Set<KnowledgeImportBatchStatus>([
  "pending", "processing", "completed", "completed_with_errors", "failed", "dead_letter",
]);
const itemStatuses = new Set<KnowledgeImportItemStatus>([
  "pending", "processing", "completed", "failed", "dead_letter",
]);
const sourceTypes = new Set<KnowledgeImportSourceType>([
  "pdf", "docx", "pptx", "xlsx", "csv", "txt", "md", "html", "htm",
  "png", "jpg", "jpeg", "webp", "tiff", "bmp",
]);
const stageStatuses = new Set<KnowledgeImportStageStatus>([
  "pending", "processing", "completed", "failed", "skipped",
]);

function optionalStageStatus(value: unknown): KnowledgeImportStageStatus | undefined {
  return typeof value === "string" && stageStatuses.has(value as KnowledgeImportStageStatus)
    ? value as KnowledgeImportStageStatus
    : undefined;
}

function normalizeItem(value: unknown): KnowledgeImportItem {
  if (!isRecord(value)) {
    throw new ApiError("知识导入文件结果无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  const status = requiredString(value.status, "item.status") as KnowledgeImportItemStatus;
  const sourceType = requiredString(value.source_type, "item.source_type");
  if (!itemStatuses.has(status) || !sourceTypes.has(sourceType as KnowledgeImportSourceType)) {
    throw new ApiError("知识导入文件状态或类型无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    id: requiredString(value.id, "item.id"),
    fileName: requiredString(value.file_name, "item.file_name"),
    sourceType: sourceType as KnowledgeImportSourceType,
    status,
    rowNumber: typeof value.row_number === "number" ? value.row_number : undefined,
    documentId: optionalString(value.document_id),
    versionId: optionalString(value.version_id),
    errorCode: optionalString(value.error_code),
    parseStatus: optionalStageStatus(value.parse_status),
    indexStatus: optionalStageStatus(value.index_status),
    publishStatus: optionalStageStatus(value.publish_status),
    publishedAt: optionalString(value.published_at),
    createdAt: requiredString(value.created_at, "item.created_at"),
    completedAt: optionalString(value.completed_at),
  };
}

function normalizeBatch(value: unknown): KnowledgeImportBatch {
  if (!isRecord(value)) {
    throw new ApiError("知识导入批次响应无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  const status = requiredString(value.status, "status") as KnowledgeImportBatchStatus;
  if (!batchStatuses.has(status)) {
    throw new ApiError("知识导入批次状态无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  if (value.items !== undefined && !Array.isArray(value.items)) {
    throw new ApiError("知识导入文件列表无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    id: requiredString(value.id, "id"),
    status,
    totalItems: requiredCount(value.total_items, "total_items"),
    pendingItems: requiredCount(value.pending_items, "pending_items"),
    succeededItems: requiredCount(value.succeeded_items, "succeeded_items"),
    failedItems: requiredCount(value.failed_items, "failed_items"),
    autoPublish: value.auto_publish === true,
    createdAt: requiredString(value.created_at, "created_at"),
    completedAt: optionalString(value.completed_at),
    items: (value.items ?? []).map(normalizeItem),
  };
}

const contentCategories = new Set<ContentImportCategory>([
  "enterprise_profile", "products", "case_studies", "faqs", "unclassified",
]);
const candidateStatuses = new Set<ContentImportCandidateStatus>([
  "pending_review", "accepted", "ignored", "conflict",
]);

function normalizeCandidate(value: unknown): ContentImportCandidate {
  if (!isRecord(value) || !isRecord(value.payload)) {
    throw new ApiError("智能整理候选响应无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  const category = requiredString(value.category, "candidate.category") as ContentImportCategory;
  const status = requiredString(value.status, "candidate.status") as ContentImportCandidateStatus;
  if (!contentCategories.has(category) || !candidateStatuses.has(status)) {
    throw new ApiError("智能整理候选分类或状态无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  const payload = Object.fromEntries(
    Object.entries(value.payload).map(([key, field]) => [key, typeof field === "string" ? field : ""]),
  );
  const confidence = typeof value.confidence === "number" ? value.confidence : Number.NaN;
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    throw new ApiError("智能整理候选置信度无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    id: requiredString(value.id, "candidate.id"),
    runId: requiredString(value.run_id, "candidate.run_id"),
    category,
    payload,
    sourceId: requiredString(value.source_id, "candidate.source_id"),
    sourceText: requiredString(value.source_text, "candidate.source_text"),
    confidence,
    status,
    targetResourceType: optionalString(value.target_resource_type),
    targetResourceId: optionalString(value.target_resource_id),
    version: requiredCount(value.version, "candidate.version"),
  };
}

function normalizeContentRun(value: unknown): ContentImportRun {
  if (!isRecord(value) || !Array.isArray(value.candidates) || !isRecord(value.counts)) {
    throw new ApiError("智能整理任务响应无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  const runStatus = requiredString(value.status, "run.status");
  if (!["processing", "review", "manual_required"].includes(runStatus)) {
    throw new ApiError("智能整理任务状态无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    id: requiredString(value.id, "run.id"),
    batchId: requiredString(value.batch_id, "run.batch_id"),
    status: runStatus as ContentImportRun["status"],
    provider: requiredString(value.provider, "run.provider"),
    model: requiredString(value.model, "run.model"),
    attempts: requiredCount(value.attempts, "run.attempts"),
    failureCode: optionalString(value.failure_code),
    counts: Object.fromEntries(Object.entries(value.counts).map(([key, count]) => [key, requiredCount(count, `counts.${key}`)])),
    candidates: value.candidates.map(normalizeCandidate),
    createdAt: requiredString(value.created_at, "run.created_at"),
  };
}

export function createKnowledgeImportsApi(client: ApiClient = apiClient) {
  return {
    async create(
      files: File[],
      options: { autoPublish?: boolean } = {},
    ): Promise<KnowledgeImportBatch> {
      const body = new FormData();
      files.forEach((file) => body.append("files", file, file.name));
      // Omit the default so older API deployments remain usable while the
      // server-side setting is rolling out. The server must still enforce that
      // only an enterprise administrator may enable it.
      if (options.autoPublish) body.append("auto_publish", "true");
      return normalizeBatch(unwrapData(await client.postForm("/admin/knowledge/imports", body)));
    },

    async list(options: { limit?: number; offset?: number } = {}): Promise<KnowledgeImportList> {
      const limit = options.limit ?? 20;
      const offset = options.offset ?? 0;
      const payload = await client.get(`/admin/knowledge/imports?limit=${limit}&offset=${offset}`);
      if (!isRecord(payload) || !Array.isArray(payload.data)) {
        throw new ApiError("知识导入批次列表无法识别。", { code: "INVALID_API_RESPONSE" });
      }
      return {
        items: payload.data.map(normalizeBatch),
        total: requiredCount(payload.total, "total"),
        limit: requiredCount(payload.limit, "limit"),
        offset: requiredCount(payload.offset, "offset"),
      };
    },

    async get(id: string): Promise<KnowledgeImportBatch> {
      return normalizeBatch(
        unwrapData(await client.get(`/admin/knowledge/imports/${encodeURIComponent(id)}`)),
      );
    },
  };
}

export const knowledgeImportsApi = createKnowledgeImportsApi();

export function createContentImportsApi(client: ApiClient = apiClient) {
  return {
    async generate(batchId: string, options: { retry?: boolean } = {}): Promise<ContentImportRun> {
      return normalizeContentRun(unwrapData(await client.post("/admin/content-import-runs", {
        batch_id: batchId,
        retry: options.retry === true,
      })));
    },
    async list(): Promise<ContentImportRun[]> {
      const payload = await client.get("/admin/content-import-runs");
      if (!isRecord(payload) || !Array.isArray(payload.data)) {
        throw new ApiError("智能整理任务列表无法识别。", { code: "INVALID_API_RESPONSE" });
      }
      return payload.data.map(normalizeContentRun);
    },
    async get(runId: string): Promise<ContentImportRun> {
      return normalizeContentRun(unwrapData(await client.get(`/admin/content-import-runs/${encodeURIComponent(runId)}`)));
    },
    async update(candidate: ContentImportCandidate): Promise<ContentImportCandidate> {
      return normalizeCandidate(unwrapData(await client.patch(
        `/admin/content-import-candidates/${encodeURIComponent(candidate.id)}`,
        { expected_version: candidate.version, category: candidate.category, payload: candidate.payload },
      )));
    },
    async accept(candidate: ContentImportCandidate, applyFields: string[] = []): Promise<ContentImportCandidate> {
      return normalizeCandidate(unwrapData(await client.post(
        `/admin/content-import-candidates/${encodeURIComponent(candidate.id)}/accept`,
        { expected_version: candidate.version, apply_fields: applyFields },
      )));
    },
    async ignore(candidate: ContentImportCandidate): Promise<ContentImportCandidate> {
      return normalizeCandidate(unwrapData(await client.post(
        `/admin/content-import-candidates/${encodeURIComponent(candidate.id)}/ignore`,
        { expected_version: candidate.version, apply_fields: [] },
      )));
    },
  };
}

export const contentImportsApi = createContentImportsApi();

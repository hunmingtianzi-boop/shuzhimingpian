import { apiClient, ApiClient, ApiError, unwrapData } from "./client";

type JsonRecord = Record<string, unknown>;

export type ExportType = "visitors" | "leads" | "conversations";
export type ExportStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "expired";

export type DataExport = {
  id: string;
  exportType: ExportType;
  status: ExportStatus;
  includeSensitive: boolean;
  rowCount?: number;
  fileName?: string;
  contentType?: string;
  failureCode?: string;
  createdAt: string;
  completedAt?: string;
  expiresAt?: string;
};

export type ExportList = {
  items: DataExport[];
  total: number;
  limit: number;
  offset: number;
};

export type ExportDownload = {
  blob: Blob;
  fileName: string;
};

export type ExportAvailability = {
  visitors: number;
  leads: number;
  conversations: number;
  generatedAt: string;
};

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringField(value: unknown, field: string): string {
  if (typeof value !== "string" || !value) {
    throw new ApiError(`导出接口响应缺少 ${field}。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

function normalizeExport(value: unknown): DataExport {
  if (!isRecord(value)) {
    throw new ApiError("导出接口返回了无法识别的数据。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  const exportType = stringField(value.export_type, "export_type");
  const status = stringField(value.status, "status");
  if (!["visitors", "leads", "conversations"].includes(exportType)) {
    throw new ApiError("导出类型无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  if (!["pending", "processing", "completed", "failed", "expired"].includes(status)) {
    throw new ApiError("导出状态无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    id: stringField(value.id, "id"),
    exportType: exportType as ExportType,
    status: status as ExportStatus,
    includeSensitive: value.include_sensitive === true,
    rowCount: typeof value.row_count === "number" ? value.row_count : undefined,
    fileName: optionalString(value.file_name),
    contentType: optionalString(value.content_type),
    failureCode: optionalString(value.failure_code),
    createdAt: stringField(value.created_at, "created_at"),
    completedAt: optionalString(value.completed_at),
    expiresAt: optionalString(value.expires_at),
  };
}

function fileNameFromDisposition(value: string | null): string | undefined {
  const encoded = value?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (!encoded) return undefined;
  try {
    return decodeURIComponent(encoded.replace(/^"|"$/g, ""));
  } catch {
    return undefined;
  }
}

export function createExportsApi(client: ApiClient = apiClient) {
  return {
    async availability(): Promise<ExportAvailability> {
      const value = unwrapData(await client.get("/admin/exports/availability"));
      if (!isRecord(value)) {
        throw new ApiError("可导出数据统计接口返回了无法识别的数据。", {
          code: "INVALID_API_RESPONSE",
        });
      }
      return {
        visitors: typeof value.visitors === "number" ? value.visitors : 0,
        leads: typeof value.leads === "number" ? value.leads : 0,
        conversations: typeof value.conversations === "number" ? value.conversations : 0,
        generatedAt: stringField(value.generated_at, "generated_at"),
      };
    },

    async list(options: { limit?: number; offset?: number } = {}): Promise<ExportList> {
      const limit = options.limit ?? 50;
      const offset = options.offset ?? 0;
      const payload = await client.get(`/admin/exports?limit=${limit}&offset=${offset}`);
      if (!isRecord(payload) || !Array.isArray(payload.data)) {
        throw new ApiError("导出列表接口返回了无法识别的数据。", {
          code: "INVALID_API_RESPONSE",
        });
      }
      return {
        items: payload.data.map(normalizeExport),
        total: typeof payload.total === "number" ? payload.total : payload.data.length,
        limit: typeof payload.limit === "number" ? payload.limit : limit,
        offset: typeof payload.offset === "number" ? payload.offset : offset,
      };
    },

    async create(exportType: ExportType, includeSensitive = false): Promise<DataExport> {
      const idempotencyKey = `admin-export-${crypto.randomUUID()}`;
      return normalizeExport(
        unwrapData(
          await client.post(
            `/admin/exports/${exportType}`,
            { include_sensitive: includeSensitive },
            { idempotencyKey },
          ),
        ),
      );
    },

    async get(id: string): Promise<DataExport> {
      return normalizeExport(unwrapData(await client.get(`/admin/exports/${id}`)));
    },

    async download(id: string, fallbackName?: string): Promise<ExportDownload> {
      const response = await client.download(`/admin/exports/${id}/download`);
      return {
        blob: await response.blob(),
        fileName:
          fileNameFromDisposition(response.headers.get("Content-Disposition")) ||
          fallbackName ||
          `export-${id}.csv`,
      };
    },
  };
}

export const exportsApi = createExportsApi();

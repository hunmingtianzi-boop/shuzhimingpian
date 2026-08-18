import { apiClient, ApiClient, ApiError, unwrapData } from "./client";
import type {
  BulkMemberResult,
  CompanyMember,
  MemberAccessInput,
  MemberCreateInput,
  MemberLifecycleStatus,
  MemberPasswordReset,
  MemberRole,
  MemberSelfProfileInput,
  MemberRowOutcome,
  MemberStatus,
} from "./types";

type JsonRecord = Record<string, unknown>;

export const MEMBER_ROLE_LABELS: Record<MemberRole, string> = {
  company_admin: "企业管理员",
  card_owner: "名片成员",
};

export const MEMBER_STATUS_LABELS: Record<MemberLifecycleStatus, string> = {
  active: "启用",
  suspended: "暂停",
  disabled: "停用",
};

function record(value: unknown, label: string): JsonRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ApiError(`${label}接口响应格式无效。`, { code: "INVALID_API_RESPONSE" });
  }
  return value as JsonRecord;
}

function string(value: unknown, field: string): string {
  if (typeof value !== "string" || !value) {
    throw new ApiError(`接口响应缺少 ${field}。`, { code: "INVALID_API_RESPONSE" });
  }
  return value;
}

function number(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ApiError(`接口响应缺少 ${field}。`, { code: "INVALID_API_RESPONSE" });
  }
  return value;
}

function memberRole(value: unknown): MemberRole {
  if (value === "company_admin" || value === "card_owner") return value;
  throw new ApiError("接口响应包含未知成员角色。", { code: "INVALID_API_RESPONSE" });
}

function memberStatus(value: unknown): MemberLifecycleStatus {
  if (value === "active" || value === "suspended" || value === "disabled") return value;
  throw new ApiError("接口响应包含未知成员状态。", { code: "INVALID_API_RESPONSE" });
}

function companyMember(value: unknown): CompanyMember {
  const item = record(value, "成员");
  const permissions = item.permissions;
  if (!Array.isArray(permissions) || !permissions.every((permission) => typeof permission === "string")) {
    throw new ApiError("接口响应中的成员权限无效。", { code: "INVALID_API_RESPONSE" });
  }
  if (typeof item.credential_enabled !== "boolean") {
    throw new ApiError("接口响应中的凭据状态无效。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    membershipId: string(item.membership_id, "membership_id"),
    userId: string(item.user_id, "user_id"),
    account: string(item.account, "account"),
    displayName: string(item.display_name, "display_name"),
    jobTitle: typeof item.job_title === "string" ? item.job_title : undefined,
    avatarUrl: typeof item.avatar_url === "string" ? item.avatar_url : undefined,
    businessSummary: typeof item.business_summary === "string" ? item.business_summary : undefined,
    publicPositioning: typeof item.public_positioning === "string" ? item.public_positioning : undefined,
    identityTitles: Array.isArray(item.identity_titles) ? item.identity_titles.filter((value): value is string => typeof value === "string") : [],
    professionalTags: Array.isArray(item.professional_tags) ? item.professional_tags.filter((value): value is string => typeof value === "string") : [],
    email: typeof item.email === "string" ? item.email : undefined,
    mobile: typeof item.mobile === "string" ? item.mobile : undefined,
    role: memberRole(item.role),
    permissions,
    status: memberStatus(item.status),
    credentialEnabled: item.credential_enabled,
    createdAt: string(item.created_at, "created_at"),
    updatedAt: string(item.updated_at, "updated_at"),
  };
}

function memberPayload(input: MemberCreateInput): JsonRecord {
  const payload: JsonRecord = {
    account: input.account.trim(),
    display_name: input.displayName.trim(),
    password: input.password,
    email: input.email?.trim() || null,
    mobile: input.mobile?.trim() || null,
    role: input.role,
    permissions: input.permissions,
    status: input.status,
    rotate_password: Boolean(input.rotatePassword),
  };
  if (input.jobTitle !== undefined) payload.job_title = input.jobTitle.trim() || null;
  if (input.avatarUrl !== undefined) payload.avatar_url = input.avatarUrl.trim() || null;
  if (input.businessSummary !== undefined) {
    payload.business_summary = input.businessSummary.trim() || null;
  }
  if (input.publicPositioning !== undefined) payload.public_positioning = input.publicPositioning.trim() || null;
  if (input.identityTitles !== undefined) payload.identity_titles = input.identityTitles.map((value) => value.trim()).filter(Boolean).slice(0, 5);
  if (input.professionalTags !== undefined) payload.professional_tags = input.professionalTags.map((value) => value.trim()).filter(Boolean).slice(0, 3);
  return payload;
}

function bulkResult(value: unknown): BulkMemberResult {
  const result = record(unwrapData(value), "批量导入");
  const summary = record(result.summary, "批量导入摘要");
  if (!Array.isArray(result.rows)) {
    throw new ApiError("批量导入接口响应缺少 rows。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    batchId: string(result.batch_id, "batch_id"),
    summary: {
      total: number(summary.total, "summary.total"),
      succeeded: number(summary.succeeded, "summary.succeeded"),
      created: number(summary.created, "summary.created"),
      updated: number(summary.updated, "summary.updated"),
      unchanged: number(summary.unchanged, "summary.unchanged"),
      duplicated: number(summary.duplicated, "summary.duplicated"),
      failed: number(summary.failed, "summary.failed"),
    },
    rows: result.rows.map((raw) => {
      const row = record(raw, "批量导入行");
      const outcome = row.outcome as MemberRowOutcome;
      if (!["created", "updated", "unchanged", "duplicate", "failed"].includes(outcome)) {
        throw new ApiError("批量导入接口响应包含未知结果。", { code: "INVALID_API_RESPONSE" });
      }
      const error = row.error === null || row.error === undefined ? undefined : record(row.error, "导入错误");
      const fields = error?.fields;
      return {
        rowNumber: number(row.row_number, "row_number"),
        account: typeof row.account === "string" ? row.account : undefined,
        outcome,
        member: row.member ? companyMember(row.member) : undefined,
        error: error ? {
          code: string(error.code, "error.code"),
          message: string(error.message, "error.message"),
          fields: Array.isArray(fields) && fields.every((field) => typeof field === "string") ? fields : [],
        } : undefined,
        duplicateOfRow: typeof row.duplicate_of_row === "number" ? row.duplicate_of_row : undefined,
      };
    }),
  };
}

export function createMemberApi(client: ApiClient) {
  return {
    async listMembers(limit = 50, offset = 0) {
      const payload = record(await client.get(`/admin/members?limit=${limit}&offset=${offset}`), "成员列表");
      if (!Array.isArray(payload.data)) {
        throw new ApiError("成员列表接口响应缺少 data。", { code: "INVALID_API_RESPONSE" });
      }
      return {
        items: payload.data.map(companyMember),
        total: number(payload.total, "total"),
        limit: number(payload.limit, "limit"),
        offset: number(payload.offset, "offset"),
      };
    },
    async createMember(input: MemberCreateInput): Promise<CompanyMember> {
      return companyMember(unwrapData(await client.post("/admin/members", memberPayload(input))));
    },
    async updateMember(membershipId: string, input: MemberAccessInput): Promise<CompanyMember> {
      const body: JsonRecord = {};
      if (input.displayName !== undefined) body.display_name = input.displayName.trim();
      if (input.jobTitle !== undefined) body.job_title = input.jobTitle.trim() || null;
      if (input.avatarUrl !== undefined) body.avatar_url = input.avatarUrl.trim() || null;
      if (input.businessSummary !== undefined) body.business_summary = input.businessSummary.trim() || null;
      if (input.publicPositioning !== undefined) body.public_positioning = input.publicPositioning.trim() || null;
      if (input.identityTitles !== undefined) body.identity_titles = input.identityTitles.map((value) => value.trim()).filter(Boolean).slice(0, 5);
      if (input.professionalTags !== undefined) body.professional_tags = input.professionalTags.map((value) => value.trim()).filter(Boolean).slice(0, 3);
      if (input.email !== undefined) body.email = input.email.trim() || null;
      if (input.mobile !== undefined) body.mobile = input.mobile.trim() || null;
      if (input.role !== undefined) body.role = input.role;
      if (input.permissions !== undefined) body.permissions = input.permissions;
      return companyMember(unwrapData(await client.patch(`/admin/members/${encodeURIComponent(membershipId)}`, body)));
    },
    async updateMyProfile(input: MemberSelfProfileInput): Promise<CompanyMember> {
      return companyMember(unwrapData(await client.patch("/admin/members/me/profile", {
        avatar_url: input.avatarUrl.trim() || null,
      })));
    },
    async setStatus(membershipId: string, status: MemberStatus): Promise<CompanyMember> {
      return companyMember(unwrapData(await client.put(`/admin/members/${encodeURIComponent(membershipId)}/status`, { status })));
    },
    async resetPassword(membershipId: string, password: string): Promise<MemberPasswordReset> {
      const data = record(unwrapData(await client.post(`/admin/members/${encodeURIComponent(membershipId)}/password:reset`, {
        password,
        revoke_sessions: true,
      })), "密码重置");
      return {
        membershipId: string(data.membership_id, "membership_id"),
        passwordChangedAt: string(data.password_changed_at, "password_changed_at"),
        sessionsRevoked: number(data.sessions_revoked, "sessions_revoked"),
      };
    },
    async bulkJson(rows: Array<Record<string, unknown>>): Promise<BulkMemberResult> {
      return bulkResult(await client.post("/admin/members/bulk", { rows }));
    },
    async bulkCsv(csvText: string): Promise<BulkMemberResult> {
      return bulkResult(await client.post("/admin/members/bulk:csv", { csv_text: csvText }));
    },
  };
}

export const memberApi = createMemberApi(apiClient);

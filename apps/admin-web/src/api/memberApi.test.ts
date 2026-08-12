import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "./client";
import { createMemberApi } from "./memberApi";

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function tokenResponse() {
  return jsonResponse({ data: { access_token: "token", csrf_token: "csrf" } });
}

const member = {
  membership_id: "membership-1",
  user_id: "user-1",
  account: "member@example.test",
  display_name: "张三",
  email: "member@example.test",
  mobile: "+8613800138000",
  role: "card_owner",
  permissions: ["card.read"],
  status: "active",
  credential_enabled: true,
  created_at: "2026-07-11T00:00:00Z",
  updated_at: "2026-07-11T00:00:00Z",
};

async function authenticatedApi(fetcher: ReturnType<typeof vi.fn<typeof fetch>>) {
  const client = new ApiClient({ baseUrl: "https://api.example.test/api/v1", fetcher });
  await client.login("admin@example.test", "password");
  return createMemberApi(client);
}

describe("memberApi real contract", () => {
  it("normalizes the paginated list including suspended lifecycle status", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({ data: [{ ...member, status: "suspended" }], total: 1, limit: 50, offset: 0 }));
    const api = await authenticatedApi(fetcher);

    await expect(api.listMembers()).resolves.toEqual({
      items: [expect.objectContaining({ membershipId: "membership-1", displayName: "张三", status: "suspended" })],
      total: 1,
      limit: 50,
      offset: 0,
    });
    expect(fetcher.mock.calls[1][0]).toBe("https://api.example.test/api/v1/admin/members?limit=50&offset=0");
  });

  it("sends exact create, update, status and password-reset payloads", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({ data: member }, 201))
      .mockResolvedValueOnce(jsonResponse({ data: member }))
      .mockResolvedValueOnce(jsonResponse({ data: { ...member, status: "disabled" } }))
      .mockResolvedValueOnce(jsonResponse({ data: { membership_id: "membership-1", password_changed_at: "2026-07-12T00:00:00Z", sessions_revoked: 2 } }));
    const api = await authenticatedApi(fetcher);

    await api.createMember({
      account: " member@example.test ", displayName: " 张三 ", password: "SecurePassword!2026",
      email: "", mobile: "", role: "card_owner", permissions: ["card.read"], status: "active", rotatePassword: true,
    });
    await api.updateMember("membership-1", {
      displayName: "张三",
      email: " updated@example.test ",
      mobile: " +8613900139000 ",
      role: "card_owner",
      permissions: ["card.read"],
    });
    await api.setStatus("membership-1", "disabled");
    await expect(api.resetPassword("membership-1", "AnotherSecure!2026")).resolves.toMatchObject({ sessionsRevoked: 2 });

    expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual({
      account: "member@example.test", display_name: "张三", password: "SecurePassword!2026",
      email: null, mobile: null, role: "card_owner", permissions: ["card.read"], status: "active", rotate_password: true,
    });
    expect(JSON.parse(String(fetcher.mock.calls[2][1]?.body))).toEqual({
      display_name: "张三",
      email: "updated@example.test",
      mobile: "+8613900139000",
      role: "card_owner",
      permissions: ["card.read"],
    });
    expect(JSON.parse(String(fetcher.mock.calls[3][1]?.body))).toEqual({ status: "disabled" });
    expect(JSON.parse(String(fetcher.mock.calls[4][1]?.body))).toEqual({ password: "AnotherSecure!2026", revoke_sessions: true });
  });

  it("normalizes CSV bulk outcomes and row-level errors", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({ data: {
        batch_id: "batch-1",
        summary: { total: 2, succeeded: 1, created: 1, updated: 0, unchanged: 0, duplicated: 0, failed: 1 },
        rows: [
          { row_number: 1, account: "ok@example.test", outcome: "created", member },
          { row_number: 2, account: "bad", outcome: "failed", error: { code: "ROW_INVALID", message: "invalid", fields: ["password"] } },
        ],
      } }));
    const api = await authenticatedApi(fetcher);

    await expect(api.bulkCsv("account,display_name,password\n...")).resolves.toMatchObject({
      batchId: "batch-1",
      summary: { total: 2, failed: 1 },
      rows: [{ rowNumber: 1, outcome: "created" }, { rowNumber: 2, error: { fields: ["password"] } }],
    });
    expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual({ csv_text: "account,display_name,password\n..." });
  });
});

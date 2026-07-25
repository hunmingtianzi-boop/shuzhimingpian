import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "./client";
import { createExportsApi } from "./exportsApi";

const exportRow = {
  id: "11111111-1111-1111-1111-111111111111",
  export_type: "leads",
  status: "completed",
  include_sensitive: false,
  row_count: 2,
  file_name: "leads.csv",
  content_type: "text/csv; charset=utf-8",
  failure_code: null,
  created_at: "2026-07-12T00:00:00Z",
  completed_at: "2026-07-12T00:01:00Z",
  expires_at: "2026-07-13T00:01:00Z",
};

async function authenticatedClient(fetcher: ReturnType<typeof vi.fn<typeof fetch>>) {
  const client = new ApiClient({ baseUrl: "https://api.example.test", fetcher });
  await client.login("admin", "password");
  return client;
}

describe("exportsApi", () => {
  it("creates and lists normalized asynchronous exports", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        access_token: "access", csrf_token: "csrf",
      } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: exportRow }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        data: [exportRow], total: 1, limit: 50, offset: 0,
      }), { status: 200 }));
    const api = createExportsApi(await authenticatedClient(fetcher));

    await expect(api.create("leads")).resolves.toMatchObject({
      exportType: "leads", status: "completed", rowCount: 2,
    });
    await expect(api.list()).resolves.toMatchObject({ total: 1, items: [{ id: exportRow.id }] });

    const createRequest = fetcher.mock.calls[1];
    expect(createRequest[0]).toBe("https://api.example.test/admin/exports/leads");
    expect((createRequest[1]?.headers as Headers).get("Idempotency-Key")).toMatch(/^admin-export-/);
    expect(JSON.parse(String(createRequest[1]?.body))).toEqual({ include_sensitive: false });
  });

  it("loads real exportable data counts", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        access_token: "access", csrf_token: "csrf",
      } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        data: {
          visitors: 42,
          leads: 0,
          conversations: 42,
          generated_at: "2026-07-25T00:00:00Z",
        },
      }), { status: 200 }));
    const api = createExportsApi(await authenticatedClient(fetcher));

    await expect(api.availability()).resolves.toMatchObject({
      visitors: 42,
      leads: 0,
      conversations: 42,
    });
    expect(fetcher.mock.calls[1][0]).toBe(
      "https://api.example.test/admin/exports/availability",
    );
  });

  it("downloads binary CSV and decodes the server filename", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        access_token: "access", csrf_token: "csrf",
      } }), { status: 200 }))
      .mockResolvedValueOnce(new Response("\ufeffid\r\nlead-1\r\n", {
        status: 200,
        headers: { "Content-Disposition": "attachment; filename*=UTF-8''%E7%BA%BF%E7%B4%A2.csv" },
      }));
    const api = createExportsApi(await authenticatedClient(fetcher));

    const result = await api.download(exportRow.id);
    expect(result.fileName).toBe("线索.csv");
    expect(await result.blob.text()).toContain("lead-1");
    expect((fetcher.mock.calls[1][1]?.headers as Headers).get("Authorization")).toBe("Bearer access");
  });
});

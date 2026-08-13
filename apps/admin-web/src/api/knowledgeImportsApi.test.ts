import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "./client";
import { createContentImportsApi, createKnowledgeImportsApi } from "./knowledgeImportsApi";

const item = {
  id: "item-1", file_name: "knowledge.pdf", source_type: "pdf", status: "completed",
  row_number: null, document_id: "document-1", version_id: "version-1", error_code: null,
  created_at: "2026-07-12T00:00:00Z", completed_at: "2026-07-12T00:01:00Z",
};
const batch = {
  id: "batch-1", sequence_number: 1, display_name: "首批企业资料", version: 1,
  status: "completed", total_items: 1, pending_items: 0,
  succeeded_items: 1, failed_items: 0, created_at: "2026-07-12T00:00:00Z",
  completed_at: "2026-07-12T00:01:00Z", items: [item],
};

function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

describe("knowledgeImportsApi", () => {
  it("uploads repeated multipart files without forcing a JSON content type", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ data: { access_token: "access", csrf_token: "csrf" } }))
      .mockResolvedValueOnce(response({ data: batch }, 202));
    const client = new ApiClient({ baseUrl: "https://api.example.test", fetcher });
    await client.login("admin", "password");
    const api = createKnowledgeImportsApi(client);

    await expect(api.create([
      new File(["pdf"], "knowledge.pdf", { type: "application/pdf" }),
      new File(["raw_text,title\nanswer,FAQ"], "faq.csv", { type: "text/csv" }),
    ])).resolves.toMatchObject({ id: "batch-1", succeededItems: 1 });

    const request = fetcher.mock.calls[1][1];
    expect(request?.body).toBeInstanceOf(FormData);
    expect((request?.body as FormData).getAll("files")).toHaveLength(2);
    expect((request?.headers as Headers).has("Content-Type")).toBe(false);
  });

  it("sends automatic publication only when the enterprise admin opts in", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ data: { access_token: "access", csrf_token: "csrf" } }))
      .mockResolvedValueOnce(response({ data: { ...batch, auto_publish: true } }, 202));
    const client = new ApiClient({ baseUrl: "https://api.example.test", fetcher });
    await client.login("admin", "password");
    const api = createKnowledgeImportsApi(client);

    await api.create([new File(["pdf"], "knowledge.pdf", { type: "application/pdf" })], {
      autoPublish: true,
    });

    const form = fetcher.mock.calls[1][1]?.body as FormData;
    expect(form.get("auto_publish")).toBe("true");
  });

  it("normalizes list and detail responses", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ data: { access_token: "access", csrf_token: "csrf" } }))
      .mockResolvedValueOnce(response({ data: [{ ...batch, items: [] }], total: 1, limit: 20, offset: 0 }))
      .mockResolvedValueOnce(response({ data: batch }));
    const client = new ApiClient({ baseUrl: "https://api.example.test", fetcher });
    await client.login("admin", "password");
    const api = createKnowledgeImportsApi(client);

    await expect(api.list()).resolves.toMatchObject({ total: 1, items: [{ id: "batch-1" }] });
    await expect(api.get("batch-1")).resolves.toMatchObject({
      items: [{ fileName: "knowledge.pdf", documentId: "document-1" }],
    });
  });
});

describe("contentImportsApi", () => {
  it("normalizes review candidates and sends edited payload with optimistic version", async () => {
    const candidate = {
      id: "candidate-1", run_id: "run-1", category: "faqs",
      payload: { question: "如何联系？", answer: "请拨打企业电话。" },
      source_id: "item-1", source_text: "如何联系？请拨打企业电话。",
      confidence: 0.92, status: "pending_review", version: 1,
      created_at: "2026-08-12T00:00:00Z", updated_at: "2026-08-12T00:00:00Z",
    };
    const run = {
      id: "run-1", batch_id: "batch-1", status: "review", provider: "deepseek",
      model: "deepseek-chat", attempts: 1, counts: { faqs: 1 }, candidates: [candidate],
      created_at: "2026-08-12T00:00:00Z", updated_at: "2026-08-12T00:00:00Z",
    };
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ data: { access_token: "access", csrf_token: "csrf" } }))
      .mockResolvedValueOnce(response({ data: run }, 201))
      .mockResolvedValueOnce(response({ data: candidate }));
    const client = new ApiClient({ baseUrl: "https://api.example.test", fetcher });
    await client.login("admin", "password");
    const api = createContentImportsApi(client);

    const generated = await api.generate("batch-1");
    expect(generated.candidates[0]).toMatchObject({ category: "faqs", payload: { question: "如何联系？" } });
    await api.update(generated.candidates[0]);

    expect(JSON.parse(String(fetcher.mock.calls[2][1]?.body))).toEqual({
      expected_version: 1,
      category: "faqs",
      payload: { question: "如何联系？", answer: "请拨打企业电话。" },
    });
  });
});

import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { knowledgeImportsApi, type KnowledgeImportBatch } from "../api/knowledgeImportsApi";
import { adminApi } from "../api/adminApi";
import { adminLightTheme } from "../theme";
import { KnowledgeImportPanel, validateKnowledgeImportFiles } from "./KnowledgeImportPanel";

const batch: KnowledgeImportBatch = {
  id: "batch-1", sequenceNumber: 1, displayName: "首批企业资料", version: 1,
  status: "completed_with_errors", totalItems: 2, pendingItems: 0,
  succeededItems: 1, failedItems: 1, autoPublish: false, createdAt: "2026-07-12T00:00:00Z",
  completedAt: "2026-07-12T00:01:00Z",
  items: [
    { id: "item-1", fileName: "guide.pdf", sourceType: "pdf", status: "completed", documentId: "document-1", versionId: "version-1", createdAt: "2026-07-12T00:00:00Z", completedAt: "2026-07-12T00:01:00Z" },
    { id: "item-2", fileName: "faq.csv", sourceType: "csv", status: "failed", rowNumber: 3, errorCode: "CSV_RAW_TEXT_REQUIRED", createdAt: "2026-07-12T00:00:00Z", completedAt: "2026-07-12T00:01:00Z" },
  ],
};

function renderPanel(props: React.ComponentProps<typeof KnowledgeImportPanel> = {}) {
  return render(<FluentProvider theme={adminLightTheme}><KnowledgeImportPanel {...props} /></FluentProvider>);
}

describe("validateKnowledgeImportFiles", () => {
  it("rejects unsupported, oversized and over-count selections before upload", () => {
    expect(validateKnowledgeImportFiles([new File(["x"], "unsafe.exe")])).toMatch(/不支持文件/);
    expect(validateKnowledgeImportFiles([new File(["x"], "deck.pptx")])).toBeUndefined();
    expect(validateKnowledgeImportFiles([new File(["x"], "scan.webp")])).toBeUndefined();
    expect(validateKnowledgeImportFiles([new File([new Uint8Array(10 * 1024 * 1024 + 1)], "large.pdf")])).toMatch(/超过 10 MiB/);
    expect(validateKnowledgeImportFiles(Array.from({ length: 6 }, (_, index) => new File(["x"], `${index}.csv`)))).toMatch(/最多/);
  });
});

describe("KnowledgeImportPanel", () => {
  beforeEach(() => {
    vi.spyOn(knowledgeImportsApi, "list").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue({
      name: "拓浙 AI 集团", summary: "", industry: "AI", region: "杭州", website: "https://tuozhe.example.com",
      logoUrl: "", profilePersonalizationPolicyVersion: "v1", version: 1,
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("creates a batch and states that imported content remains a draft", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(knowledgeImportsApi, "create").mockResolvedValue(batch);
    renderPanel();
    const input = screen.getByLabelText("选择知识文件");
    await user.upload(input, [new File(["pdf"], "guide.pdf", { type: "application/pdf" }), new File(["raw_text\nanswer"], "faq.csv", { type: "text/csv" })]);
    await user.click(screen.getByRole("button", { name: "创建导入批次" }));

    await waitFor(() => expect(create).toHaveBeenCalledWith(expect.arrayContaining([expect.objectContaining({ name: "guide.pdf" })])));
    expect(await screen.findByText(/内容只会生成草稿/)).toBeInTheDocument();
    expect(screen.getByText("错误码：CSV_RAW_TEXT_REQUIRED")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /已生成待审核草稿/ })).toBeInTheDocument();
  });

  it("shows validation feedback and does not call the server", async () => {
    const create = vi.spyOn(knowledgeImportsApi, "create");
    renderPanel();
    fireEvent.change(screen.getByLabelText("选择知识文件"), {
      target: { files: [new File(["x"], "unsafe.exe")] },
    });
    expect(await screen.findByText(/不支持文件/)).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("lets an enterprise admin request automatic publish explicitly", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(knowledgeImportsApi, "create").mockResolvedValue({ ...batch, autoPublish: true });
    renderPanel();
    await user.upload(screen.getByLabelText("选择知识文件"), new File(["slide"], "deck.pptx", { type: "application/vnd.openxmlformats-officedocument.presentationml.presentation" }));
    await user.click(screen.getByLabelText("解析完成后自动更新并发布到知识库"));
    await user.click(screen.getByRole("button", { name: "创建导入批次" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ name: "deck.pptx" })]),
      { autoPublish: true },
    ));
    expect(await screen.findByText(/尝试发布/)).toBeInTheDocument();
  });

  it("loads batch detail on demand and exposes per-file error codes", async () => {
    const user = userEvent.setup();
    vi.mocked(knowledgeImportsApi.list).mockResolvedValue({ items: [{ ...batch, items: [] }], total: 1, limit: 20, offset: 0 });
    vi.spyOn(knowledgeImportsApi, "get").mockResolvedValue(batch);
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "查看结果" }));
    expect(await screen.findByText("错误码：CSV_RAW_TEXT_REQUIRED")).toBeInTheDocument();
  });

  it("offers deletion for content generated by an import", async () => {
    const user = userEvent.setup();
    const onRequestDeleteDocument = vi.fn();
    vi.mocked(knowledgeImportsApi.list).mockResolvedValue({ items: [{ ...batch, items: [] }], total: 1, limit: 20, offset: 0 });
    vi.spyOn(knowledgeImportsApi, "get").mockResolvedValue(batch);
    renderPanel({ onRequestDeleteDocument });

    await user.click(await screen.findByRole("button", { name: "查看结果" }));
    await user.click(await screen.findByRole("button", { name: "删除内容" }));

    expect(onRequestDeleteDocument).toHaveBeenCalledWith("document-1");
  });
});

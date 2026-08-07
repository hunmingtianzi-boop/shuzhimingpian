import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import { scheduledPublicationsApi } from "../api/scheduledPublicationsApi";
import type { CaseStudy, Product } from "../api/types";
import { adminLightTheme } from "../theme";
import { CatalogPage } from "./CatalogPage";

const product: Product = {
  id: "product-1",
  slug: "enterprise-ai",
  name: "企业 AI 助手",
  category: "AI 服务",
  summary: "可追溯的企业问答",
  detail: "产品详情",
  audience: "企业客户",
  priceBoundary: "按项目报价",
  imageUrl: "",
  visibility: "public",
  sortOrder: 1,
  settings: {},
  status: "draft",
  version: 3,
  updatedAt: "2026-07-11T00:00:00Z",
};

const caseStudy: CaseStudy = {
  id: "case-1",
  slug: "factory-ai",
  title: "制造企业知识助手",
  industry: "制造业",
  background: "需要统一知识入口。",
  solution: "建设企业知识助手。",
  result: "完成知识上线。",
  clientDisplayName: "示例制造企业",
  imageUrl: "",
  visibility: "public",
  sortOrder: 2,
  settings: {},
  status: "draft",
  version: 5,
  updatedAt: "2026-07-11T00:00:00Z",
};

function renderPage(kind: "product" | "case") {
  return render(
    <FluentProvider theme={adminLightTheme}>
      <CatalogPage kind={kind} />
    </FluentProvider>,
  );
}

describe("CatalogPage", () => {
  beforeEach(() => {
    vi.spyOn(scheduledPublicationsApi, "list").mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("publishes a product with its optimistic version after confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listProducts").mockResolvedValue([product]);
    const publish = vi
      .spyOn(adminApi, "publishProduct")
      .mockResolvedValue({ ...product, status: "published", version: 4 });
    renderPage("product");

    await screen.findByText("企业 AI 助手");
    await user.click(screen.getByRole("button", { name: "发布" }));
    expect(screen.getByRole("dialog", { name: "确认发布产品" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认发布" }));

    await waitFor(() => expect(publish).toHaveBeenCalledWith("product-1", 3));
    expect(await screen.findByText("产品已由服务端确认发布。")).toBeInTheDocument();
  });

  it("schedules a product draft with its optimistic version", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listProducts").mockResolvedValue([product]);
    const create = vi.spyOn(scheduledPublicationsApi, "create").mockResolvedValue({
      id: "schedule-1",
      resourceType: "product",
      resourceId: "product-1",
      targetVersion: 3,
      scheduledBy: "user-1",
      scheduledAt: "2099-01-01T01:00:00Z",
      status: "pending",
      attempts: 0,
      maxAttempts: 5,
      nextAttemptAt: "2099-01-01T01:00:00Z",
      version: 1,
    });
    renderPage("product");

    await screen.findByText("企业 AI 助手");
    await user.click(screen.getByRole("button", { name: "定时发布" }));
    const scheduleDialog = await screen.findByRole("dialog", {
      name: "设置定时发布",
    });
    fireEvent.change(await within(scheduleDialog).findByLabelText(/发布时间/), {
      target: { value: "2099-01-01T09:00" },
    });
    await user.click(
      await within(scheduleDialog).findByRole("button", { name: "确认定时发布" }),
    );

    await waitFor(() => expect(create).toHaveBeenCalledWith(expect.objectContaining({
      targetType: "product",
      targetId: "product-1",
      version: 3,
    })));
    await waitFor(() =>
      expect(scheduleDialog).not.toBeInTheDocument(),
    );
  });

  it("edits a product and keeps the server version for If-Match", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listProducts").mockResolvedValue([product]);
    const update = vi
      .spyOn(adminApi, "updateProduct")
      .mockResolvedValue({ ...product, name: "企业知识助手", version: 4 });
    renderPage("product");

    await screen.findByText("企业 AI 助手");
    await user.click(screen.getByRole("button", { name: "编辑" }));
    const editor = await screen.findByRole("dialog", { name: "编辑产品" });
    const name = await within(editor).findByRole("textbox", { name: /产品名称/ });
    fireEvent.change(name, { target: { value: "企业知识助手" } });
    const updatedEditor = await screen.findByRole("dialog", { name: "编辑产品" });
    await user.click(
      await within(updatedEditor).findByRole("button", { name: "保存产品" }),
    );

    await waitFor(() => expect(update).toHaveBeenCalled());
    expect(update.mock.calls[0][0]).toBe("product-1");
    expect(update.mock.calls[0][1]).toBe(3);
    expect(update.mock.calls[0][2]).toMatchObject({ name: "企业知识助手" });
  });

  it("confirms archive and delete before calling destructive actions", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listProducts").mockResolvedValue([product]);
    const archive = vi
      .spyOn(adminApi, "archiveProduct")
      .mockResolvedValue({ ...product, status: "archived", version: 4 });
    const remove = vi.spyOn(adminApi, "deleteProduct").mockResolvedValue(undefined);
    renderPage("product");

    await screen.findByText("企业 AI 助手");
    await user.click(screen.getByRole("button", { name: "归档" }));
    const archiveDialog = await screen.findByRole("dialog", {
      name: "确认归档产品",
    });
    await user.click(
      await within(archiveDialog).findByRole("button", { name: "确认归档" }),
    );
    await waitFor(() => expect(archive).toHaveBeenCalledWith("product-1", 3));
    await waitFor(() =>
      expect(archiveDialog).not.toBeInTheDocument(),
    );

    await user.click(await screen.findByRole("button", { name: "删除" }));
    expect(remove).not.toHaveBeenCalled();
    const deleteDialog = await screen.findByRole("dialog", {
      name: "确认删除产品",
      hidden: true,
    });
    await user.click(
      await within(deleteDialog).findByRole("button", { name: "确认删除", hidden: true }),
    );
    await waitFor(() => expect(remove).toHaveBeenCalledWith("product-1", 3));
    await waitFor(() =>
      expect(deleteDialog).not.toBeInTheDocument(),
    );
  }, 15_000);

  it("creates a case from the accessible empty state", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([]);
    const create = vi.spyOn(adminApi, "createCaseStudy").mockResolvedValue(caseStudy);
    renderPage("case");

    await screen.findByText("尚未创建案例");
    await user.click(screen.getAllByRole("button", { name: "新建案例" })[0]);
    fireEvent.change(screen.getByRole("textbox", { name: /案例标题/ }), {
      target: { value: caseStudy.title },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /链接标识/ }), {
      target: { value: caseStudy.slug },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /项目背景/ }), {
      target: { value: caseStudy.background },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /解决方案/ }), {
      target: { value: caseStudy.solution },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /项目成果/ }), {
      target: { value: caseStudy.result },
    });
    await user.click(screen.getByRole("button", { name: "保存案例" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0]).toMatchObject({
      title: caseStudy.title,
      slug: caseStudy.slug,
    });
  });
});

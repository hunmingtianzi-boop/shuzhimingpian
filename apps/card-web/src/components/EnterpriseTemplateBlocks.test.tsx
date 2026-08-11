import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { CardPageExperience } from "@cf/card-page-renderer";
import { describe, expect, it, vi } from "vitest";

import { EnterpriseTemplateBlocks, toCardPageBlock } from "./EnterpriseTemplateBlocks";

describe("EnterpriseTemplateBlocks", () => {
  it("uses the exact simulator card component tree with real adapter data", () => {
    const { container } = render(
      <EnterpriseTemplateBlocks
        blocks={[
          { id: "identity", type: "identity", sort_order: 0 },
          { id: "overview", type: "rich_text", title: "概览", body: "真实定位", sort_order: 1 },
          { id: "business", type: "business_collection", title: "核心业务", product_items: [{ id: "p1", slug: "real-service", name: "真实业务", image_url: "/real-service.webp" }], sort_order: 2 },
        ]}
        identityData={{ kind: "employee", name: "林小满", headline: "解决方案顾问" }}
        directory
      />,
    );

    const page = container.querySelector(".public-frame > .card-page");
    expect(page?.querySelector(":scope > .card-topbar")).toBeInTheDocument();
    expect(page?.querySelector(".identity-block + .card-directory")).toBeInTheDocument();
    expect(page?.querySelector(".card-content .overview-panel")).toHaveTextContent("真实定位");
    expect(page?.querySelector(".service-grid .service-card")).toHaveTextContent("真实业务");
    expect(page?.querySelector(".service-grid .service-card")).toHaveClass("has-media");
    expect(screen.getByRole("img", { name: "真实业务展示图" })).toHaveAttribute("src", "/real-service.webp");
  });

  it("renders visible blocks in the published order and hides disabled blocks", () => {
    render(<EnterpriseTemplateBlocks blocks={[
      { id: "later", type: "rich_text", title: "第二块", body: "第二块内容", sort_order: 2 },
      { id: "hidden", type: "rich_text", title: "不公开", visible: false, sort_order: 0 },
      { id: "first", type: "rich_text", title: "第一块", body: "第一块内容", sort_order: 1 },
    ]} />);

    const headings = screen.getAllByRole("heading").map((node) => node.textContent);
    expect(headings).toEqual(["第一块", "第二块"]);
    expect(screen.queryByText("不公开")).not.toBeInTheDocument();
  });

  it("adapts employee copy and keeps empty editor placeholders off the public card", () => {
    const { container } = render(<CardPageExperience
      blocks={[
        { id: "identity", type: "identity", sortOrder: 0 },
        { id: "intro", type: "rich_text", title: "企业介绍", body: "个人业务介绍", sortOrder: 1 },
        { id: "business", type: "business_collection", title: "核心业务", productItems: [], sortOrder: 2 },
        { id: "cases", type: "case_collection", title: "代表案例", caseItems: [], sortOrder: 3 },
      ]}
      data={{ identity: { kind: "employee", name: "徐松波", headline: "创始人 / 总经理" } }}
      directory
    />);

    expect(screen.getByRole("heading", { name: "个人介绍" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "企业介绍" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "核心业务" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "代表案例" })).not.toBeInTheDocument();
    expect(container.querySelector(".empty-state")).not.toBeInTheDocument();
  });

  it("renders frozen case items and rejects non-HTTPS actions", () => {
    render(<EnterpriseTemplateBlocks blocks={[
      { id: "cases", type: "case_collection", title: "客户案例", case_items: [{ id: "case-1", slug: "delivery-case", title: "交付案例", summary: "已完成验收" }] },
      { id: "unsafe", type: "cta", title: "危险链接", cta_label: "打开", cta_url: "javascript:alert(1)" },
    ]} />);

    expect(screen.getByText("交付案例")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "打开" })).not.toBeInTheDocument();
  });

  it("renders only the products resolved for the published business block", () => {
    render(<EnterpriseTemplateBlocks
      blocks={[{
        id: "business",
        type: "business_collection",
        title: "核心业务",
        product_ids: ["product-1"],
        product_items: [{
          id: "product-1",
          slug: "selected-product",
          name: "已选产品",
          summary: "来自发布引用",
        }],
      }]}
      products={[{
        slug: "unselected-product",
        name: "未选产品",
        category: "其他",
        summary: "不应显示",
        detail: "",
        audience: "",
        priceBoundary: "",
        imageUrl: "",
        sortOrder: 0,
        publishedAt: "2026-08-06T00:00:00Z",
      }]}
    />);

    expect(screen.getByText("已选产品")).toBeInTheDocument();
    expect(screen.queryByText("未选产品")).not.toBeInTheDocument();
  });

  it("opens the existing assistant from an AI block", () => {
    const onAssistant = vi.fn();
    render(
      <EnterpriseTemplateBlocks
        blocks={[{ id: "ai", type: "ai_assistant", title: "企业 AI", body: "基于已审核资料提供咨询。" }]}
        onAssistant={onAssistant}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "开始咨询" }));
    expect(onAssistant).toHaveBeenCalledOnce();
  });

  it("filters selected FAQ records by canonical document id and keeps the configured order", () => {
    const { container } = render(
      <EnterpriseTemplateBlocks
        blocks={[{
          id: "faq",
          type: "faq",
          title: "常见问题",
          body: "这段手填答案不应再展示",
          faq_mode: "selected",
          faq_document_ids: ["document-2", "document-1"],
        }]}
        faqItems={[
          { id: "source-1", document_id: "document-1", question: "问题一", answer: "答案一" },
          { id: "source-2", document_id: "document-2", question: "问题二", answer: "答案二" },
          { id: "source-3", document_id: "document-3", question: "不应展示", answer: "答案三" },
        ]}
      />,
    );

    const questions = Array.from(container.querySelectorAll(".cpr-faq-list .faq-question strong"))
      .map((node) => node.textContent);
    expect(questions).toEqual(["问题二", "问题一"]);
    expect(screen.queryByText("不应展示")).not.toBeInTheDocument();
    expect(screen.queryByText("这段手填答案不应再展示")).not.toBeInTheDocument();
  });

  it("uses distinct quantity-aware layouts instead of one repeated card grid", () => {
    const { container } = render(
      <EnterpriseTemplateBlocks
        blocks={[
          {
            id: "business",
            type: "business_collection",
            title: "核心业务",
            product_items: [{ id: "p1", slug: "p1", name: "单项重点" }],
          },
          {
            id: "cases",
            type: "case_collection",
            title: "案例",
            case_items: [
              { id: "c1", slug: "c1", title: "案例一" },
              { id: "c2", slug: "c2", title: "案例二" },
            ],
          },
          {
            id: "gallery",
            type: "image_gallery",
            title: "图集",
            image_urls: ["/one.jpg", "/two.jpg", "/three.jpg"],
          },
        ]}
      />,
    );

    expect(container.querySelector(".cpr-product-list--single")).toBeInTheDocument();
    expect(container.querySelector(".cpr-case-list--pair")).toBeInTheDocument();
    expect(container.querySelector(".cpr-gallery--many")).toBeInTheDocument();
  });

  it("derives an operable directory from the same visible ordered blocks", () => {
    const onNavigate = vi.fn();
    render(
      <CardPageExperience
        blocks={[
          { id: "second", type: "rich_text", title: "第二部分", body: "第二部分内容", sortOrder: 2 },
          { id: "hidden", type: "rich_text", title: "隐藏部分", sortOrder: 0, visible: false },
          { id: "first", type: "rich_text", title: "第一部分", body: "第一部分内容", sortOrder: 1 },
        ]}
        directory={{ onNavigate }}
      />,
    );

    const directory = screen.getByRole("navigation", { name: "名片内容导航" });
    const buttons = Array.from(directory.querySelectorAll("button"));
    expect(buttons.map((button) => button.textContent)).toEqual(["第一部分", "第二部分"]);
    fireEvent.click(buttons[1]);
    expect(onNavigate).toHaveBeenCalledWith("second");
  });

  it("keeps identity visible while honoring its configured position", () => {
    const { container } = render(
      <CardPageExperience
        blocks={[
          { id: "copy", type: "rich_text", title: "前置内容", body: "先展示内容", sortOrder: 1 },
          { id: "identity", type: "identity", visible: false, sortOrder: 2 },
        ]}
        data={{ identity: { kind: "employee", name: "林小满", headline: "解决方案顾问" } }}
      />,
    );

    const renderedIds = Array.from(container.querySelectorAll("[data-card-page-block]"))
      .map((node) => node.getAttribute("data-card-page-block"));
    expect(renderedIds).toEqual(["copy", "identity"]);
    expect(screen.getByRole("heading", { name: "林小满" })).toBeInTheDocument();
  });

  it("renders identity background presentation from the real template contract", () => {
    const { container } = render(
      <EnterpriseTemplateBlocks
        blocks={[{
          id: "identity",
          type: "identity",
          presentation: {
            identity_layout: "vertical",
            background: {
              asset_url: "/api/v1/public/assets/company/card.webp",
              fit: "custom",
              position: "top_right",
              scale: 1.25,
              opacity: 0.42,
              overlay: "light",
            },
          },
        }]}
        identityData={{ kind: "employee", name: "林小满", headline: "解决方案顾问" }}
      />,
    );

    const identity = container.querySelector(".cpr-identity");
    const background = container.querySelector<HTMLElement>(".cpr-identity-background");
    expect(identity).toHaveClass("cpr-identity--vertical", "cpr-identity--has-background");
    expect(background?.style.backgroundImage).toContain("/api/v1/public/assets/company/card.webp");
    expect(background?.style.backgroundPosition).toBe("right top");
    expect(background?.style.backgroundSize).toBe("125%");
    expect(background?.style.opacity).toBe("0.42");
    expect(container.querySelector(".cpr-identity-overlay--light")).toBeInTheDocument();
  });

  it("renders an action collection with safe whole-card links and reports actions", () => {
    const onAction = vi.fn();
    render(
      <EnterpriseTemplateBlocks
        blocks={[{
          id: "actions",
          type: "action_collection",
          title: "行动入口",
          layout_variant: "grid",
          item_limit: 2,
          action_items: [
            {
              id: "event",
              title: "世界会展大会",
              summary: "查看大会日程与报名方式",
              label: "查看详情",
              image_url: "/api/v1/public/assets/company/event.webp",
              target_type: "external_url",
              target_value: "https://events.example.test/conference",
              open_mode: "new_tab",
            },
            {
              id: "phone",
              title: "预约咨询",
              target_type: "phone",
              target_value: "+86 138-0013-8000",
              open_mode: "self",
            },
            {
              id: "unsafe",
              title: "危险入口",
              target_type: "internal_path",
              target_value: "//evil.example.test",
              open_mode: "self",
            },
          ],
        }]}
        onAction={onAction}
      />,
    );

    const eventLink = screen.getByRole("link", { name: /世界会展大会/ });
    expect(eventLink).toHaveAttribute("href", "https://events.example.test/conference");
    expect(eventLink).toHaveAttribute("target", "_blank");
    expect(screen.getByRole("link", { name: /预约咨询/ })).toHaveAttribute("href", "tel:+8613800138000");
    expect(screen.queryByText("危险入口")).not.toBeInTheDocument();
    fireEvent.click(eventLink);
    expect(onAction).toHaveBeenCalledWith(expect.objectContaining({ id: "event", targetType: "external_url" }));
  });

  it("maps snake_case action collection and identity background fields once", () => {
    expect(toCardPageBlock({
      id: "actions",
      type: "action_collection",
      layout_variant: "featured",
      item_limit: 4,
      action_items: [{
        id: "official-site",
        title: "企业官网",
        image_url: "/api/v1/public/assets/company/site.webp",
        target_type: "internal_path",
        target_value: "/company",
        open_mode: "self",
      }],
    })).toMatchObject({
      layoutVariant: "featured",
      itemLimit: 4,
      actionItems: [{
        id: "official-site",
        imageUrl: "/api/v1/public/assets/company/site.webp",
        targetType: "internal_path",
        targetValue: "/company",
      }],
    });
  });
});

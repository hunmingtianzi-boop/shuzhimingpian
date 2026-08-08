import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { CardPageExperience } from "@cf/card-page-renderer";
import { describe, expect, it, vi } from "vitest";

import { EnterpriseTemplateBlocks } from "./EnterpriseTemplateBlocks";

describe("EnterpriseTemplateBlocks", () => {
  it("renders visible blocks in the published order and hides disabled blocks", () => {
    render(<EnterpriseTemplateBlocks blocks={[
      { id: "later", type: "rich_text", title: "第二块", sort_order: 2 },
      { id: "hidden", type: "rich_text", title: "不公开", visible: false, sort_order: 0 },
      { id: "first", type: "rich_text", title: "第一块", sort_order: 1 },
    ]} />);

    const headings = screen.getAllByRole("heading").map((node) => node.textContent);
    expect(headings).toEqual(["第一块", "第二块"]);
    expect(screen.queryByText("不公开")).not.toBeInTheDocument();
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
        blocks={[{ id: "ai", type: "ai_assistant", title: "企业 AI" }]}
        onAssistant={onAssistant}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "开始咨询" }));
    expect(onAssistant).toHaveBeenCalledOnce();
  });

  it("renders published block backgrounds and rich-text content images", () => {
    const { container } = render(
      <EnterpriseTemplateBlocks
        pageBackground={{
          kind: "image",
          image_url: "/api/v1/public/card-assets/company-1/page.webp",
          position_x: 36,
          position_y: 64,
          overlay_color: "#000000",
          overlay_opacity: 0.38,
        }}
        pageTextTone="light"
        blocks={[{
          id: "story",
          type: "rich_text",
          title: "品牌故事",
          body: "持续更新的企业内容入口。",
          background: {
            kind: "image",
            image_url: "/api/v1/public/card-assets/company-1/background.webp",
            fit: "cover",
            position_x: 24,
            position_y: 68,
            overlay_color: "#102b2f",
            overlay_opacity: 0.5,
          },
          text_tone: "light",
          content_image: {
            url: "/api/v1/public/card-assets/company-1/story.webp",
            alt: "团队共创",
            placement: "right",
            fit: "contain",
            aspect_ratio: "standard",
            width_percent: 42,
            position_x: 28,
            position_y: 72,
          },
          size_preset: "tall",
          padding_y: "spacious",
        }]}
      />,
    );

    expect(screen.getByAltText("团队共创")).toHaveAttribute(
      "src",
      "/api/v1/public/card-assets/company-1/story.webp",
    );
    expect(container.querySelector(".cpr-rich-media--right")).toBeInTheDocument();
    expect(container.querySelector(".cpr-block-inner--tone-light")).toBeInTheDocument();
    expect(container.querySelector(".cpr-block-background"))
      .toHaveStyle({ backgroundPosition: "24% 68%" });
    expect(container.querySelector(".cpr-page-background"))
      .toHaveStyle({ backgroundPosition: "36% 64%" });
    expect(container.querySelector(".cpr-block-inner--size-tall"))
      .toHaveClass("cpr-block-inner--padding-spacious");
    expect(screen.getByAltText("团队共创")).toHaveStyle({
      aspectRatio: "4 / 3",
      objectPosition: "28% 72%",
    });
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

    const questions = Array.from(container.querySelectorAll(".cpr-faq-list summary strong"))
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
          { id: "second", type: "rich_text", title: "第二部分", sortOrder: 2 },
          { id: "hidden", type: "rich_text", title: "隐藏部分", sortOrder: 0, visible: false },
          { id: "first", type: "rich_text", title: "第一部分", sortOrder: 1 },
        ]}
        directory={{ onNavigate }}
      />,
    );

    const directory = screen.getByRole("navigation", { name: "名片内容导航" });
    const buttons = Array.from(directory.querySelectorAll("button"));
    expect(buttons.map((button) => button.textContent)).toEqual(["01第一部分", "02第二部分"]);
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
});

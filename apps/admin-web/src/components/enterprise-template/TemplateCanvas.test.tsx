import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type {
  CaseStudy,
  EnterpriseTemplateBlock,
  Product,
  SelectableFaqDocument,
} from "../../api/types";
import { TemplateCanvas } from "./TemplateCanvas";

const product: Product = {
  id: "product-1",
  slug: "growth-engine",
  name: "增长引擎",
  category: "数字化产品",
  summary: "统一客户触点与线索跟进。",
  detail: "覆盖获客、培育与成交全流程。",
  audience: "成长型企业",
  priceBoundary: "按方案报价",
  imageUrl: "/api/v1/public/card-assets/company-1/product.webp",
  visibility: "public",
  sortOrder: 0,
  settings: {},
  status: "published",
  version: 2,
};

const caseStudy: CaseStudy = {
  id: "case-1",
  slug: "retail-growth",
  title: "零售增长案例",
  industry: "零售",
  background: "门店与线上线索分散。",
  solution: "重构客户运营和销售协同流程。",
  result: "有效线索转化率提升 32%。",
  clientDisplayName: "示例客户",
  imageUrl: "/api/v1/public/card-assets/company-1/case.webp",
  visibility: "public",
  sortOrder: 0,
  settings: {},
  status: "published",
  version: 3,
};

const faq: SelectableFaqDocument = {
  id: "faq-1",
  title: "项目多久可以交付？",
  answer: "标准项目通常四到六周完成。",
  status: "published",
  visibility: "public",
};

const blocks: EnterpriseTemplateBlock[] = [
  { id: "identity", type: "identity", visible: true, sortOrder: 0, title: "基础名片" },
  {
    id: "story",
    type: "rich_text",
    visible: true,
    sortOrder: 1,
    title: "品牌故事",
    body: "一张名片，也是一处持续更新的品牌内容入口。",
    background: {
      kind: "color",
      color: "#173b40",
      overlayColor: "#000000",
      overlayOpacity: 0,
    },
    textTone: "light",
    contentImage: {
      url: "/api/v1/public/card-assets/company-1/story.webp",
      alt: "团队共创现场",
      placement: "left",
      fit: "cover",
      aspectRatio: "square",
      widthPercent: 44,
      positionX: 32,
      positionY: 68,
    },
    sizePreset: "tall",
    paddingY: "spacious",
  },
  {
    id: "products",
    type: "business_collection",
    visible: true,
    sortOrder: 1,
    title: "核心业务",
    productIds: [product.id],
  },
  {
    id: "cases",
    type: "case_collection",
    visible: true,
    sortOrder: 2,
    title: "客户案例",
    caseIds: [caseStudy.id],
  },
  {
    id: "faq",
    type: "faq",
    visible: true,
    sortOrder: 3,
    title: "常见问题",
    faqMode: "all_published",
    faqDocumentIds: [],
  },
  {
    id: "video",
    type: "video_link",
    visible: true,
    sortOrder: 4,
    title: "企业视频",
    videoUrl: "https://video.example.test/intro",
  },
  {
    id: "cta",
    type: "cta",
    visible: true,
    sortOrder: 5,
    title: "联系我们",
    ctaLabel: "预约沟通",
    ctaUrl: "https://example.test/contact",
  },
  {
    id: "assistant",
    type: "ai_assistant",
    visible: true,
    sortOrder: 6,
    title: "企业 AI 助手",
  },
];

describe("TemplateCanvas draft interactions", () => {
  it("opens real product and case details, previews AI, and keeps native page actions", async () => {
    const user = userEvent.setup();
    const onSelectBlock = vi.fn();
    const { container } = render(
      <TemplateCanvas
        blocks={blocks}
        pageBackground={{
          kind: "image",
          imageUrl: "/api/v1/public/card-assets/company-1/page.webp",
          positionX: 35,
          positionY: 65,
          overlayColor: "#000000",
          overlayOpacity: 0.3,
        }}
        pageTextTone="light"
        products={[product]}
        cases={[caseStudy]}
        faqItems={[faq]}
        identity={{
          cardKind: "enterprise",
          displayName: "拓途商务",
          title: "企业数字化服务",
        }}
        onSelectBlock={onSelectBlock}
        onMoveBlock={vi.fn()}
      />,
    );

    expect(screen.getByText(faq.answer).closest("details")).toHaveAttribute("open");
    expect(screen.getByAltText("团队共创现场")).toHaveAttribute(
      "src",
      "/api/v1/public/card-assets/company-1/story.webp",
    );
    expect(screen.getByAltText("团队共创现场")).toHaveStyle({
      aspectRatio: "1 / 1",
      objectPosition: "32% 68%",
    });
    expect(screen.getByRole("heading", { name: "品牌故事" }).closest(".cpr-block-inner"))
      .toHaveClass("cpr-block-inner--tone-light");
    expect(screen.getByRole("heading", { name: "品牌故事" }).closest(".cpr-block-inner"))
      .toHaveClass("cpr-block-inner--size-tall", "cpr-block-inner--padding-spacious");
    expect(container.querySelector("#bp-template-block-story .cpr-block-background"))
      .toHaveStyle({ backgroundColor: "#173b40" });
    expect(container.querySelector(".cpr-page-background")).toHaveStyle({
      backgroundPosition: "35% 65%",
    });
    expect(screen.getByRole("link", { name: /播放视频/ })).toHaveAttribute(
      "href",
      "https://video.example.test/intro",
    );
    expect(screen.getByRole("link", { name: /预约沟通/ })).toHaveAttribute(
      "href",
      "https://example.test/contact",
    );

    await user.click(screen.getByRole("button", { name: /增长引擎/ }));
    expect(screen.getByRole("article", { name: "产品详情预览" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: product.name })).toBeInTheDocument();
    expect(screen.getByText(product.category)).toBeInTheDocument();
    expect(screen.getByText(product.summary)).toBeInTheDocument();
    expect(screen.getByText(product.detail)).toBeInTheDocument();
    expect(screen.getByAltText(`${product.name}封面`)).toHaveAttribute(
      "src",
      product.imageUrl,
    );
    expect(onSelectBlock).toHaveBeenCalledWith("products");

    await user.click(screen.getByRole("button", { name: "返回名片页面" }));
    await user.click(screen.getByRole("button", { name: /零售增长案例/ }));
    expect(screen.getByRole("article", { name: "案例详情预览" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: caseStudy.title })).toBeInTheDocument();
    expect(screen.getByText(caseStudy.industry)).toBeInTheDocument();
    expect(screen.getByText(caseStudy.solution)).toBeInTheDocument();
    expect(screen.getByText(caseStudy.result)).toBeInTheDocument();
    expect(screen.getByAltText(`${caseStudy.title}封面`)).toHaveAttribute(
      "src",
      caseStudy.imageUrl,
    );
    expect(onSelectBlock).toHaveBeenCalledWith("cases");

    await user.click(screen.getByRole("button", { name: "返回名片页面" }));
    await user.click(screen.getByRole("button", { name: "继续问 AI" }));
    expect(screen.getByRole("region", { name: "AI 助手预览" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "公开页将打开 AI 助手" })).toBeInTheDocument();
    expect(screen.getByText(`将带入问题：${faq.title}`)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "返回名片页面" }));
    await user.click(screen.getByRole("button", { name: /开始咨询/ }));
    expect(screen.getByText("编辑器只预览入口和跳转效果，不会在这里发起真实问答。")).toBeInTheDocument();
  });
});

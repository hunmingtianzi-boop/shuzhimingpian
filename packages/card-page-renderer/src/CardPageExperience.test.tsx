import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  CardPageExperience,
  safeCardPageActionHref,
  type CardPageActionItem,
} from "./CardPageExperience";

describe("CardPageExperience production presentation", () => {
  it("renders identity background above real identity data without moving fields", () => {
    const markup = renderToStaticMarkup(
      <CardPageExperience
        blocks={[{
          id: "identity",
          type: "identity",
          presentation: {
            identityLayout: "vertical",
            background: {
              assetUrl: "/api/v1/public/assets/company/card.webp",
              fit: "custom",
              position: "top_right",
              scale: 1.25,
              opacity: 0.42,
              overlay: "light",
            },
          },
        }]}
        data={{ identity: { kind: "employee", name: "林小满", headline: "解决方案顾问" } }}
      />,
    );

    expect(markup).toContain("cpr-identity--vertical");
    expect(markup).toContain("cpr-identity--has-background");
    expect(markup).toContain("card.webp");
    expect(markup).toContain("林小满");
  });

  it("keeps action collection targets within the public safety contract", () => {
    const safeInternal: CardPageActionItem = {
      id: "company",
      title: "企业介绍",
      targetType: "internal_path",
      targetValue: "/company?from=card",
    };
    const unsafeInternal: CardPageActionItem = {
      ...safeInternal,
      id: "unsafe",
      targetValue: "//evil.example.test",
    };

    expect(safeCardPageActionHref(safeInternal)).toBe("/company?from=card");
    expect(safeCardPageActionHref(unsafeInternal)).toBeUndefined();
  });

  it("labels enterprise introduction data as enterprise material", () => {
    const markup = renderToStaticMarkup(<CardPageExperience
      blocks={[
        { id: "identity", type: "identity", sortOrder: 0 },
        { id: "intro", type: "rich_text", title: "企业介绍", body: "企业简介", sortOrder: 1 },
      ]}
      data={{ identity: { kind: "enterprise", name: "示例企业" } }}
    />);

    expect(markup).toContain("企业资料");
    expect(markup).not.toContain("员工信息");
  });

  it("renders simulator-style case hierarchy and configurable gallery badges", () => {
    const markup = renderToStaticMarkup(<CardPageExperience blocks={[
      { id: "identity", type: "identity", sortOrder: 0 },
      { id: "cases", type: "case_collection", sortOrder: 1, layoutVariant: "featured", caseItems: [
        { id: "case-1", title: "增长案例", industry: "零售", summary: "统一客户触点", metrics: [{ value: "+68%", label: "转化提升" }] },
        { id: "case-2", title: "共创案例", industry: "教育" },
      ] },
      { id: "gallery", type: "image_gallery", sortOrder: 2, layoutVariant: "mosaic", galleryItems: [
        { id: "photo-1", imageUrl: "/photo.webp", title: "项目启动", timeLabel: "2026.08", badgeMode: "time" },
      ] },
    ]}/>);

    expect(markup).toContain("case-story--lead");
    expect(markup).toContain("case-story--text-only");
    expect(markup).toContain("CASE 01");
    expect(markup).not.toContain("case-cover-placeholder");
    expect(markup).toContain("+68%");
    expect(markup).toContain("2026.08");
  });

  it("uses a real business image when supplied and keeps text-only items placeholder free", () => {
    const markup = renderToStaticMarkup(<CardPageExperience blocks={[
      { id: "identity", type: "identity", sortOrder: 0 },
      { id: "services", type: "business_collection", sortOrder: 1, layoutVariant: "grid", productItems: [
        { id: "product-1", name: "智能名片", summary: "连接员工与企业服务", imageUrl: "/product.webp" },
        { id: "product-2", name: "客户管理", summary: "统一客户触点" },
      ] },
    ]}/>);

    expect(markup).toContain("service-card has-media");
    expect(markup).toContain("智能名片展示图");
    expect(markup).toContain("/product.webp");
    expect(markup).toContain("service-card text-only");
    expect(markup).not.toContain("service-placeholder");
  });

});

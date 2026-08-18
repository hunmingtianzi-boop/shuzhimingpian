import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { StudioCardPage, type StudioModule } from "@cf/card-page-renderer";
import { describe, expect, it } from "vitest";

function renderModules(modules: StudioModule[]) {
  return render(<StudioCardPage modules={modules} title="V2 名片" editor/>);
}

describe("Studio V2 production components", () => {
  it("separates employee identity hierarchy from long-form introduction", () => {
    const { container } = renderModules([{
      id: "identity",
      type: "identity",
      title: "基础名片",
      source: "企业员工",
      identity: {
        variant: "v2",
        kind: "employee",
        name: "徐松波",
        headline: "AI 人才与项目共创",
        titles: ["创始人", "总经理", "企业 AI 顾问"],
        companyName: "拓浙 AI 集团",
        summary: "这段长摘要不应进入 V2 基础名片。",
        contacts: [{ id: "phone", kind: "phone", label: "电话", value: "13800000000" }],
      },
    }]);

    expect(screen.getByRole("region", { name: "员工基础名片" })).toBeInTheDocument();
    expect(screen.getByText("创始人")).toBeInTheDocument();
    expect(screen.getByText("总经理")).toBeInTheDocument();
    expect(screen.getByText("拓浙 AI 集团")).toBeInTheDocument();
    expect(screen.queryByText("这段长摘要不应进入 V2 基础名片。")).not.toBeInTheDocument();
    expect(container.querySelector(".identity-v2--employee .identity-v2-title-lines")).toBeInTheDocument();
  });

  it("renders enterprise facts with a logo composition instead of employee titles", () => {
    const { container } = renderModules([{
      id: "identity",
      type: "identity",
      title: "基础名片",
      source: "企业资料",
      identity: {
        variant: "v2",
        kind: "enterprise",
        name: "拓浙 AI 集团",
        imageUrl: "/logo.webp",
        headline: "AI 人才发展与产业场景服务",
        facts: [
          { label: "成立时间", value: "2016 年" },
          { label: "总部地点", value: "杭州" },
        ],
      },
    }]);

    expect(screen.getByRole("region", { name: "企业基础名片" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "拓浙 AI 集团企业标识" })).toHaveAttribute("src", "/logo.webp");
    expect(screen.getByText("成立时间")).toBeInTheDocument();
    expect(screen.getByText("2016 年")).toBeInTheDocument();
    expect(container.querySelector(".identity-v2--enterprise .identity-v2-facts")).toBeInTheDocument();
    expect(container.querySelector(".identity-v2-title-lines")).not.toBeInTheDocument();
  });

  it("uses a lightweight row for one quick entry", () => {
    const { container } = renderModules([{
      id: "quick",
      type: "actions",
      title: "快捷入口",
      source: "自定义链接",
      actionTemplate: "quick",
      items: [{ id: "official", title: "企业官网", subtitle: "访问官网", href: "https://example.com", imageUrl: "/mark.webp" }],
    }]);

    expect(screen.getByRole("link", { name: /企业官网/ })).toBeInTheDocument();
    expect(container.querySelector('[data-module-id="quick"].quick-links-module')).toBeInTheDocument();
    expect(container.querySelector(".quick-links.is-single .quick-link-item")).toBeInTheDocument();
    expect(container.querySelector(".quick-link-icon img")).toHaveAttribute("src", "/mark.webp");
  });

  it("caps the visible grid at four positions and reveals overflow on demand", () => {
    const items = Array.from({ length: 6 }, (_, index) => ({ id: `item-${index}`, title: `入口 ${index + 1}`, href: `#item-${index}` }));
    const { container } = renderModules([{
      id: "quick",
      type: "actions",
      title: "快捷入口",
      source: "自定义链接",
      actionTemplate: "quick",
      items,
    }]);

    expect(container.querySelectorAll(".quick-links > .quick-link-item")).toHaveLength(4);
    expect(screen.queryByText("入口 4")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /更多/ }));
    expect(screen.getByText("入口 4")).toBeInTheDocument();
    expect(screen.getByText("入口 6")).toBeInTheDocument();
  });
});

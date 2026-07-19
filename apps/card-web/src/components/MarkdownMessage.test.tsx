import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarkdownMessage } from "./MarkdownMessage";

const mermaidMock = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(async () => ({
    svg: '<svg xmlns="http://www.w3.org/2000/svg"><text>需求到交付</text></svg>',
  })),
}));

vi.mock("mermaid", () => ({ default: mermaidMock }));

describe("MarkdownMessage", () => {
  it("renders normal model formatting as semantic text", () => {
    render(
      <MarkdownMessage
        content={
          "### 合作方式\n\n**重点**\n\n1. 第一项\n2. 第二项\n\n> 这是引用\n\n`示例代码`"
        }
      />,
    );

    expect(screen.getByRole("heading", { name: "合作方式", level: 3 })).toBeInTheDocument();
    expect(screen.getByText("重点").tagName).toBe("STRONG");
    expect(screen.getByRole("list")).toHaveTextContent("第一项");
    expect(screen.getByText("这是引用").closest("blockquote")).not.toBeNull();
    expect(screen.getByText("示例代码").tagName).toBe("CODE");
  });

  it("keeps links safe and does not turn model HTML into elements", () => {
    const { container } = render(
      <MarkdownMessage content={'[官网](https://example.com) <img src=x onerror="alert(1)" />'} />,
    );

    const link = screen.getByRole("link", { name: "官网" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders ordered steps as a flow and keeps GFM tables scrollable", () => {
    render(
      <MarkdownMessage
        content={
          "### 合作流程\n\n1. 提交需求\n2. 场景评估\n3. 阶段验证\n\n" +
          "| 项目 | 信息 |\n| --- | --- |\n| 周期 | 按项目确认 |\n| 验收 | 分阶段完成 |"
        }
      />,
    );

    expect(screen.getByRole("list")).toHaveClass("message-flow");
    expect(screen.getByRole("region", { name: "回答数据表" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("table")).toHaveTextContent("按项目确认");
  });

  it("renders a fenced Mermaid block as an accessible diagram", async () => {
    render(
      <MarkdownMessage
        content={"```mermaid\nflowchart TD\n  A[需求] --> B[交付]\n```"}
      />,
    );

    expect(screen.getByLabelText("正在绘制图示")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "AI 生成的关系图" })).toHaveTextContent(
      "需求到交付",
    );
    expect(mermaidMock.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ securityLevel: "strict", startOnLoad: false }),
    );
  });
});

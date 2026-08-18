import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { StandaloneCardStudioV2 } from "./StandaloneCardStudioV2";

describe("StandaloneCardStudioV2", () => {
  it("edits enterprise positioning and custom facts without duplicating the rendering tree", () => {
    render(<StandaloneCardStudioV2/>);
    fireEvent.click(screen.getByRole("button", { name: "企业" }));

    fireEvent.change(screen.getByRole("textbox", { name: "企业定位" }), { target: { value: "企业智能化与人才共创" } });
    expect(screen.getByText("企业智能化与人才共创")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "企业信息项1小标题" }), { target: { value: "服务客户" } });
    fireEvent.change(screen.getByRole("textbox", { name: "企业信息项1内容" }), { target: { value: "300+ 企业" } });
    expect(screen.getByText("服务客户")).toBeInTheDocument();
    expect(screen.getByText("300+ 企业")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "删除企业信息项4" }));
    fireEvent.click(screen.getByRole("button", { name: "＋ 添加企业信息项" }));
    expect(screen.getByRole("textbox", { name: "企业信息项4小标题" })).toHaveValue("新信息");
  });

  it("edits employee positioning, identities and tags inline", () => {
    render(<StandaloneCardStudioV2/>);

    fireEvent.change(screen.getByRole("textbox", { name: "个人定位" }), { target: { value: "企业 AI 解决方案顾问" } });
    expect(screen.getByText("企业 AI 解决方案顾问")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "身份头衔1" }), { target: { value: "联合创始人" } });
    expect(screen.getByText("联合创始人")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "专业标签1" }), { target: { value: "场景 AI" } });
    expect(screen.getByText("场景 AI")).toBeInTheDocument();
  });

  it("keeps quick-entry text stable while adding entries and uploading an icon", async () => {
    const user = userEvent.setup();
    render(<StandaloneCardStudioV2/>);
    fireEvent.click(screen.getByRole("button", { name: /快捷入口自定义链接/ }));

    const title = screen.getByRole("textbox", { name: "快捷入口1名称" });
    fireEvent.change(title, { target: { value: "官方门户" } });
    fireEvent.change(screen.getByRole("textbox", { name: "快捷入口1跳转地址" }), { target: { value: "https://portal.example.com" } });
    expect(screen.getByRole("link", { name: /官方门户/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "＋ 添加快捷入口" }));
    expect(screen.getByRole("textbox", { name: "快捷入口2名称" })).toHaveValue("新入口");

    const file = new File(["icon"], "portal.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("上传快捷入口1图标"), file);
    await waitFor(() => expect(screen.getByRole("textbox", { name: "快捷入口1名称" })).toHaveValue("官方门户"));
    expect(screen.getByRole("link", { name: /官方门户/ })).toBeInTheDocument();
  });
});

import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import type { ManagedCard } from "../api/types";
import { AuthContext } from "../auth/AuthContext";
import type { AuthContextValue } from "../auth/AuthContext";
import { adminLightTheme } from "../theme";
import { CardsPage } from "./CardsPage";

const draftCard: ManagedCard = {
  id: "card-1",
  cardKind: "employee",
  ownerUserId: "user-1",
  slug: "c-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  displayName: "林顾问",
  title: "解决方案顾问",
  avatarUrl: "",
  assistantName: "企业助手",
  welcomeMessage: "欢迎咨询",
  suggestedQuestions: ["你们提供什么服务？"],
  policyVersions: {
    privacy: "privacy-v1",
    chatNotice: "chat-v1",
    leadConsent: "lead-v1",
  },
  status: "draft",
  version: 6,
  shareUrl: "https://cards.example.test/c/card-1",
  qrUrl: "https://cards.example.test/c/card-1",
  updatedAt: "2026-07-11T00:00:00Z",
};

const companyAdminAuth: AuthContextValue = {
  status: "authenticated",
  user: {
    id: "user-1",
    displayName: "企业管理员",
    membershipId: "membership-1",
    tenantId: "tenant-1",
    companyId: "company-1",
    role: "company_admin",
    permissions: [],
  },
  loginPending: false,
  apiConfigured: true,
  login: async () => undefined,
  logout: async () => undefined,
};

function renderPage() {
  return render(
    <FluentProvider theme={adminLightTheme}>
      <AuthContext.Provider value={companyAdminAuth}>
        <CardsPage />
      </AuthContext.Provider>
    </FluentProvider>,
  );
}

describe("CardsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("publishes a draft card with its current version", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([draftCard]);
    const publish = vi
      .spyOn(adminApi, "publishManagedCard")
      .mockResolvedValue({ ...draftCard, status: "published", version: 7 });
    renderPage();

    await screen.findByText("林顾问");
    await user.click(screen.getByRole("button", { name: "发布" }));
    const publishDialog = await screen.findByRole("dialog", { name: "确认发布名片" });
    await user.click(within(publishDialog).getByRole("button", { name: "确认发布" }));

    await waitFor(() => expect(publish).toHaveBeenCalledWith("card-1", 6));
  });

  it("copies the server share value", async () => {
    const user = userEvent.setup();
    const publishedCard = { ...draftCard, status: "published", version: 7 };
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([publishedCard]);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    renderPage();

    await screen.findByText("林顾问");
    const publicLink = screen.getByRole("link", { name: "打开公开页" });
    expect(publicLink).toHaveAttribute("href", publishedCard.shareUrl);
    expect(publicLink).toHaveAttribute("target", "_blank");
    expect(publicLink).toHaveAttribute("rel", "noopener noreferrer");
    await user.click(screen.getByRole("button", { name: "分享" }));
    const shareDialog = await screen.findByRole("dialog", { name: "分享名片" });
    await user.click(within(shareDialog).getByRole("button", { name: "复制分享链接" }));
    expect(writeText).toHaveBeenCalledWith(publishedCard.shareUrl);
    const updatedShareDialog = await screen.findByRole("dialog", { name: "分享名片" });
    expect(
      await within(updatedShareDialog).findByText("分享链接已复制。"),
    ).toBeInTheDocument();
    await user.click(within(updatedShareDialog).getByRole("button", { name: "关闭" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "分享名片" })).not.toBeInTheDocument(),
    );
  });

  it("does not expose a public-page action for draft cards", async () => {
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([draftCard]);
    renderPage();

    await screen.findByText("林顾问");
    expect(
      screen.queryByRole("link", { name: "打开公开页" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "分享" }),
    ).not.toBeInTheDocument();
  });

  it("confirms deactivation before invalidating a public card", async () => {
    const user = userEvent.setup();
    const publishedCard = { ...draftCard, status: "published", version: 7 };
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([publishedCard]);
    const deactivate = vi
      .spyOn(adminApi, "deactivateManagedCard")
      .mockResolvedValue({ ...publishedCard, status: "archived", version: 8 });
    renderPage();

    await screen.findByText("林顾问");
    await user.click(screen.getByRole("button", { name: "停用" }));
    expect(deactivate).not.toHaveBeenCalled();
    const deactivateDialog = await screen.findByRole("dialog", { name: "确认停用名片" });
    await user.click(within(deactivateDialog).getByRole("button", { name: "确认停用" }));
    await waitFor(() => expect(deactivate).toHaveBeenCalledWith("card-1", 7));
  });

  it("creates an employee card without allowing the browser to choose a slug", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([]);
    const create = vi.spyOn(adminApi, "createManagedCard").mockResolvedValue(draftCard);
    renderPage();

    await screen.findByText("尚未创建名片");
    await user.click(screen.getByRole("button", { name: "新建员工名片" }));
    fireEvent.change(screen.getByRole("textbox", { name: /展示姓名/ }), {
      target: { value: "林顾问" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /职务或头衔/ }), {
      target: { value: "解决方案顾问" },
    });
    expect(screen.queryByRole("textbox", { name: /公开标识/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存名片" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0]).not.toHaveProperty("slug");
    expect(create.mock.calls[0][0]).toMatchObject({ cardKind: "employee" });
  });

  it("uploads the selected employee image before saving the card", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([]);
    const upload = vi.spyOn(adminApi, "uploadCardAsset").mockResolvedValue({
      url: "/api/v1/public/card-assets/company-1/asset-1.webp",
      contentType: "image/webp",
      width: 640,
      height: 640,
      sizeBytes: 12_345,
    });
    const create = vi.spyOn(adminApi, "createManagedCard").mockResolvedValue(draftCard);
    renderPage();

    await screen.findByText("尚未创建名片");
    await user.click(screen.getByRole("button", { name: "新建员工名片" }));
    fireEvent.change(screen.getByRole("textbox", { name: /展示姓名/ }), {
      target: { value: "林顾问" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /职务或头衔/ }), {
      target: { value: "解决方案顾问" },
    });
    const file = new File(["image"], "avatar.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("选择员工头像"), file);
    expect(screen.getByText("avatar.png")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存名片" }));

    await waitFor(() => expect(upload).toHaveBeenCalledWith(file));
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0].avatarUrl).toBe(
      "/api/v1/public/card-assets/company-1/asset-1.webp",
    );
  });

  it("creates an enterprise official card without an employee owner", async () => {
    const user = userEvent.setup();
    const enterpriseCard: ManagedCard = {
      ...draftCard,
      id: "card-enterprise",
      cardKind: "enterprise",
      ownerUserId: undefined,
      displayName: "拓途商务",
      title: "企业数字化服务",
    };
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([]);
    const create = vi
      .spyOn(adminApi, "createManagedCard")
      .mockResolvedValue(enterpriseCard);
    renderPage();

    await screen.findByText("尚未创建名片");
    await user.click(screen.getByRole("button", { name: "新建企业名片" }));
    expect(
      screen.getByText("归企业所有，不绑定任何员工；发布后作为企业公开主页。"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: /企业名称/ }), {
      target: { value: "拓途商务" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /业务定位或品牌标语/ }), {
      target: { value: "企业数字化服务" },
    });
    expect(
      screen.queryByRole("textbox", { name: /所有者用户 ID/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("选择企业 Logo")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存名片" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0]).toMatchObject({
      cardKind: "enterprise",
      displayName: "拓途商务",
    });
    expect(create.mock.calls[0][0].ownerUserId).toBe("");
  });
});

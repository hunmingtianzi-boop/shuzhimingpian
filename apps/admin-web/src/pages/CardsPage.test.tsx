import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import { memberApi } from "../api/memberApi";
import type {
  EnterpriseTemplate,
  EnterpriseTemplateThemeKey,
  ManagedCard,
  ManagedCardInput,
} from "../api/types";
import { AuthContext } from "../auth/AuthContext";
import type { AuthContextValue } from "../auth/AuthContext";
import { adminLightTheme } from "../theme";

vi.mock("../components/EnterpriseTemplateEditor", () => ({
  EnterpriseTemplateEditor: ({
    open,
    card,
    creationDraft,
    onClose,
    onDraftConfirm,
    onEditBasicSettings,
  }: {
    open: boolean;
    card?: ManagedCard;
    creationDraft?: {
      cardKind: ManagedCard["cardKind"];
      identityPreview: {
        displayName: string;
        title: string;
        avatarUrl?: string;
        identityTitles?: string[];
        contactFields?: ManagedCardInput["contactFields"];
      };
    };
    onClose: () => void;
    onDraftConfirm?: (
      document: EnterpriseTemplate["draft"],
      identity: Pick<ManagedCardInput, "identityTitles" | "contactFields">,
    ) => void | Promise<void>;
    onEditBasicSettings?: (card: ManagedCard) => void;
  }) => {
    if (!open) return null;
    if (card) {
      return (
        <div role="dialog" aria-label="名片页面编辑器">
          <span>{card.displayName}</span>
          <button type="button" onClick={() => onEditBasicSettings?.(card)}>编辑基础资料</button>
          <button type="button" onClick={onClose}>关闭编辑器</button>
        </div>
      );
    }
    if (!creationDraft) return null;
    const document = {
      schemaVersion: 1 as const,
      themeKey: "brand" as EnterpriseTemplateThemeKey,
      blocks: [],
    };
    return (
      <div role="dialog" aria-label={`创建前设计${creationDraft.cardKind === "employee" ? "员工" : "企业"}名片`}>
        <span>{creationDraft.identityPreview.displayName}</span>
        <button type="button" onClick={onClose}>取消创建</button>
        <button type="button" onClick={() => void onDraftConfirm?.(document, {
          identityTitles: creationDraft.identityPreview.identityTitles ?? [],
          contactFields: creationDraft.identityPreview.contactFields ?? [],
        })}>
          使用此设计创建名片
        </button>
      </div>
    );
  },
}));

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
  changePassword: async () => undefined,
  logout: async () => undefined,
};

const employeeMember = {
  membershipId: "membership-employee",
  userId: "user-employee",
  account: "employee@example.test",
  displayName: "林顾问",
  jobTitle: "解决方案顾问",
  avatarUrl: "/employee-avatar.webp",
  businessSummary: "负责企业数字化解决方案。",
  role: "card_owner" as const,
  permissions: [],
  status: "active" as const,
  credentialEnabled: true,
  createdAt: "2026-08-01T00:00:00Z",
  updatedAt: "2026-08-01T00:00:00Z",
};

const cardOwnerAuth: AuthContextValue = {
  ...companyAdminAuth,
  user: {
    ...companyAdminAuth.user!,
    id: employeeMember.userId,
    membershipId: employeeMember.membershipId,
    displayName: employeeMember.displayName,
    role: "card_owner",
  },
};

function renderPage(auth: AuthContextValue = companyAdminAuth) {
  return render(
    <FluentProvider theme={adminLightTheme}>
      <AuthContext.Provider value={auth}>
        <CardsPage />
      </AuthContext.Provider>
    </FluentProvider>,
  );
}

describe("CardsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns from basic settings cancellation to the card page editor", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([draftCard]);
    vi.spyOn(memberApi, "listMembers").mockResolvedValue({ items: [employeeMember], total: 1, limit: 100, offset: 0 });
    renderPage();

    await screen.findByText("林顾问");
    await user.click(screen.getByRole("button", { name: "编辑内容" }));
    const pageEditor = await screen.findByRole("dialog", { name: "名片页面编辑器" });
    await user.click(within(pageEditor).getByRole("button", { name: "编辑基础资料" }));

    const basicSettings = await screen.findByRole("dialog");
    expect(within(basicSettings).getByText("编辑员工名片")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "名片页面编辑器" })).not.toBeInTheDocument();
    await user.click(within(basicSettings).getByRole("button", { name: "取消", hidden: true }));

    await waitFor(() => expect(screen.queryByText("编辑员工名片")).not.toBeInTheDocument());
    expect(screen.getByRole("dialog", { name: "名片页面编辑器", hidden: true })).toBeInTheDocument();
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
    await user.click(
      await within(publishDialog).findByRole("button", { name: "确认发布" }),
    );

    await waitFor(() => expect(publish).toHaveBeenCalledWith("card-1", 6));
    await waitFor(() =>
      expect(publishDialog).not.toBeInTheDocument(),
    );
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
    await user.click(
      await within(shareDialog).findByRole("button", { name: "复制分享链接" }),
    );
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(publishedCard.shareUrl),
    );
    expect(
      await within(shareDialog).findByText("分享链接已复制。"),
    ).toBeInTheDocument();
    await user.click(
      await within(shareDialog).findByRole("button", { name: "关闭" }),
    );
    await waitFor(() =>
      expect(shareDialog).not.toBeInTheDocument(),
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
    await user.click(
      await within(deactivateDialog).findByRole("button", { name: "确认停用" }),
    );
    await waitFor(() => expect(deactivate).toHaveBeenCalledWith("card-1", 7));
  });

  it("creates an employee card by selecting an enterprise employee", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([]);
    vi.spyOn(memberApi, "listMembers").mockResolvedValue({ items: [employeeMember], total: 1, limit: 100, offset: 0 });
    const create = vi.spyOn(adminApi, "createManagedCard").mockResolvedValue(draftCard);
    renderPage();

    await screen.findByText("尚未创建名片");
    await user.click(screen.getByRole("button", { name: "新建员工名片" }));
    const employeeSelect = await screen.findByRole("combobox", { name: "选择企业员工" });
    await user.selectOptions(employeeSelect, employeeMember.userId);
    await user.click(screen.getByRole("checkbox", { name: "公开工作手机" }));
    expect(screen.queryByRole("textbox", { name: /公开标识/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /所有者用户 ID/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "创建名片", hidden: true }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0]).not.toHaveProperty("slug");
    expect(create.mock.calls[0][0]).toMatchObject({
      cardKind: "employee",
      ownerUserId: employeeMember.userId,
      displayName: employeeMember.displayName,
      title: employeeMember.jobTitle,
      employeeContactVisibility: ["mobile"],
    });
  });

  it("drops unfinished contact rows and warns when shortcuts exceed the public limit", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([]);
    vi.spyOn(memberApi, "listMembers").mockResolvedValue({ items: [employeeMember], total: 1, limit: 100, offset: 0 });
    const create = vi.spyOn(adminApi, "createManagedCard").mockResolvedValue(draftCard);
    renderPage();

    await screen.findByText("尚未创建名片");
    await user.click(screen.getByRole("button", { name: "新建员工名片" }));
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "选择企业员工" }),
      employeeMember.userId,
    );
    await user.click(screen.getByRole("checkbox", { name: "公开工作手机" }));
    await user.click(screen.getByRole("checkbox", { name: "公开工作邮箱" }));
    for (let index = 0; index < 4; index += 1) {
      await user.click(screen.getByRole("button", { name: "添加联系方式" }));
    }
    const values = screen.getAllByRole("textbox", { name: "内容" });
    await user.type(values[0], "13800000001");
    await user.type(values[1], "13800000002");
    await user.type(values[2], "13800000003");

    expect(screen.getByText(/有 1 条联系方式尚未填写内容/)).toBeInTheDocument();
    expect(screen.getByText(/当前共有 5 个公开联系方式/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "创建名片", hidden: true }));
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0].contactFields).toHaveLength(3);
    expect(create.mock.calls[0][0].contactFields.every((field) => field.value.trim())).toBe(true);
  });

  it("keeps employee identity canonical while allowing avatar upload from the card flow", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([]);
    vi.spyOn(memberApi, "listMembers").mockResolvedValue({ items: [employeeMember], total: 1, limit: 100, offset: 0 });
    renderPage();

    await screen.findByText("尚未创建名片");
    await user.click(screen.getByRole("button", { name: "新建员工名片" }));
    const employeeSelect = await screen.findByRole("combobox", { name: "选择企业员工" });
    expect(screen.getByText("姓名、职位、头像和业务摘要统一来自企业员工；在这里上传头像也会同步到对应员工资料。")).toBeInTheDocument();
    expect(screen.getByLabelText("选择员工头像")).toBeDisabled();
    await user.selectOptions(employeeSelect, employeeMember.userId);
    expect(screen.getByLabelText("选择员工头像")).toBeEnabled();
    expect(screen.getByText("支持 PNG、JPEG、WebP，最大 5 MiB；保存后同步到企业员工及其公开名片。")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "公开工作邮箱" })).toBeInTheDocument();
  });

  it("keeps the bound employee identity read-only after creation", async () => {
    const user = userEvent.setup();
    const boundMember = {
      ...employeeMember,
      membershipId: "membership-1",
      userId: draftCard.ownerUserId as string,
    };
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([draftCard]);
    vi.spyOn(memberApi, "listMembers").mockResolvedValue({
      items: [boundMember], total: 1, limit: 100, offset: 0,
    });
    renderPage();

    await screen.findByText("林顾问");
    await user.click(screen.getByRole("button", { name: "编辑" }));
    const employeeSelect = await screen.findByRole("combobox", { name: "选择企业员工" });
    expect(employeeSelect).toBeDisabled();
    expect(screen.getByText("员工身份已绑定；姓名、职位和头像请在企业员工资料中维护。")).toBeInTheDocument();
  });

  it("uploads an employee avatar and syncs it to the bound enterprise employee", async () => {
    const user = userEvent.setup();
    const uploadedUrl = "/api/v1/public/card-assets/avatar.webp";
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([]);
    vi.spyOn(memberApi, "listMembers").mockResolvedValue({ items: [employeeMember], total: 1, limit: 100, offset: 0 });
    const upload = vi.spyOn(adminApi, "uploadCardAsset").mockResolvedValue({
      url: uploadedUrl,
      contentType: "image/webp",
      width: 640,
      height: 640,
      sizeBytes: 2048,
    });
    const updateMember = vi.spyOn(memberApi, "updateMember").mockResolvedValue({
      ...employeeMember,
      avatarUrl: uploadedUrl,
    });
    const create = vi.spyOn(adminApi, "createManagedCard").mockResolvedValue({
      ...draftCard,
      ownerUserId: employeeMember.userId,
      avatarUrl: uploadedUrl,
    });
    renderPage();

    await screen.findByText("尚未创建名片");
    await user.click(screen.getByRole("button", { name: "新建员工名片" }));
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "选择企业员工" }),
      employeeMember.userId,
    );
    const avatar = new File(["avatar"], "portrait.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("选择员工头像"), avatar);
    expect(await screen.findByText(/portrait\.png/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "创建名片" }));

    await waitFor(() => expect(upload).toHaveBeenCalledWith(avatar));
    await waitFor(() => expect(updateMember).toHaveBeenCalledWith(
      employeeMember.membershipId,
      { avatarUrl: uploadedUrl },
    ));
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0]).toMatchObject({
      cardKind: "employee",
      ownerUserId: employeeMember.userId,
      avatarUrl: "",
    });
  });

  it("lets a card owner write an uploaded avatar through their own employee profile", async () => {
    const user = userEvent.setup();
    const uploadedUrl = "/api/v1/public/card-assets/self-avatar.webp";
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([]);
    vi.spyOn(memberApi, "listMembers").mockRejectedValue(new ApiError("无成员列表权限", {
      code: "PERMISSION_DENIED",
      status: 403,
    }));
    vi.spyOn(adminApi, "uploadCardAsset").mockResolvedValue({
      url: uploadedUrl,
      contentType: "image/webp",
      width: 640,
      height: 640,
      sizeBytes: 2048,
    });
    const updateMyProfile = vi.spyOn(memberApi, "updateMyProfile").mockResolvedValue({
      ...employeeMember,
      avatarUrl: uploadedUrl,
    });
    const updateMember = vi.spyOn(memberApi, "updateMember");
    vi.spyOn(adminApi, "createManagedCard").mockResolvedValue({
      ...draftCard,
      ownerUserId: employeeMember.userId,
      avatarUrl: uploadedUrl,
    });
    renderPage(cardOwnerAuth);

    await screen.findByText("尚未创建名片");
    await user.click(screen.getByRole("button", { name: "新建员工名片" }));
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "选择企业员工" }),
      employeeMember.userId,
    );
    await user.upload(
      screen.getByLabelText("选择员工头像"),
      new File(["avatar"], "self.png", { type: "image/png" }),
    );
    await user.click(screen.getByRole("button", { name: "创建名片", hidden: true }));

    await waitFor(() => expect(updateMyProfile).toHaveBeenCalledWith({ avatarUrl: uploadedUrl }));
    expect(updateMember).not.toHaveBeenCalled();
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
    await user.click(screen.getByRole("button", { name: "创建名片" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0]).toMatchObject({
      cardKind: "enterprise",
      displayName: "拓途商务",
    });
    expect(create.mock.calls[0][0].ownerUserId).toBe("");
  });

  it("copies a same-kind card configuration on the quick create path", async () => {
    const user = userEvent.setup();
    const source: ManagedCard = {
      ...draftCard,
      id: "enterprise-source",
      cardKind: "enterprise",
      ownerUserId: undefined,
      displayName: "参考企业",
      title: "参考页面",
    };
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([source]);
    const create = vi.spyOn(adminApi, "createManagedCard").mockResolvedValue({
      ...source,
      id: "enterprise-created",
      displayName: "新企业",
    });
    renderPage();

    await screen.findByText("参考企业");
    await user.click(screen.getByRole("button", { name: "新建企业名片" }));
    fireEvent.change(screen.getByRole("textbox", { name: /企业名称/ }), {
      target: { value: "新企业" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /业务定位或品牌标语/ }), {
      target: { value: "新定位" },
    });
    const configuration = screen.getByRole("combobox", { name: "配置来源" });
    await waitFor(() => expect(within(configuration).getByRole("option", {
      name: "复制「参考企业」的页面配置（快速创建）",
    })).toBeInTheDocument());
    await user.selectOptions(configuration, `copy:${source.id}`);
    await user.click(screen.getByRole("button", { name: "创建名片" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0]).toMatchObject({
      cardKind: "enterprise",
      templateSourceCardId: source.id,
    });
  });

  it("cancels create-before-design without persisting a card", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([]);
    const create = vi.spyOn(adminApi, "createManagedCard");
    renderPage();

    await screen.findByText("尚未创建名片");
    await user.click(screen.getByRole("button", { name: "新建企业名片" }));
    fireEvent.change(screen.getByRole("textbox", { name: /企业名称/ }), {
      target: { value: "待设计企业" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /业务定位或品牌标语/ }), {
      target: { value: "待设计定位" },
    });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "配置来源" }),
      "customize",
    );
    await user.click(screen.getByRole("button", { name: "下一步：设计名片页面", hidden: true }));

    const composer = await screen.findByRole("dialog", { name: "创建前设计企业名片" });
    expect(create).not.toHaveBeenCalled();
    await user.click(within(composer).getByRole("button", { name: "取消创建" }));
    await waitFor(() => expect(composer).not.toBeInTheDocument());
    expect(create).not.toHaveBeenCalled();
  });

  it("cancels employee custom design without uploading or mutating identity", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([]);
    vi.spyOn(memberApi, "listMembers").mockResolvedValue({
      items: [employeeMember], total: 1, limit: 100, offset: 0,
    });
    const upload = vi.spyOn(adminApi, "uploadCardAsset");
    const updateMember = vi.spyOn(memberApi, "updateMember");
    const updateMyProfile = vi.spyOn(memberApi, "updateMyProfile");
    const create = vi.spyOn(adminApi, "createManagedCard");
    renderPage();

    await screen.findByText("尚未创建名片");
    await user.click(screen.getByRole("button", { name: "新建员工名片" }));
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "选择企业员工" }),
      employeeMember.userId,
    );
    await user.upload(
      screen.getByLabelText("选择员工头像"),
      new File(["avatar"], "cancelled.png", { type: "image/png" }),
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "配置来源" }),
      "customize",
    );
    await user.click(screen.getByRole("button", {
      name: "下一步：设计名片页面",
      hidden: true,
    }));

    const composer = await screen.findByRole("dialog", { name: "创建前设计员工名片" });
    await user.click(within(composer).getByRole("button", { name: "取消创建" }));
    await waitFor(() => expect(composer).not.toBeInTheDocument());
    expect(upload).toHaveBeenCalledTimes(0);
    expect(updateMember).toHaveBeenCalledTimes(0);
    expect(updateMyProfile).toHaveBeenCalledTimes(0);
    expect(create).toHaveBeenCalledTimes(0);
  });

  it("persists employee avatar and card only after custom design confirmation", async () => {
    const user = userEvent.setup();
    const uploadedUrl = "/api/v1/public/card-assets/custom-avatar.webp";
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([]);
    vi.spyOn(memberApi, "listMembers").mockResolvedValue({
      items: [employeeMember], total: 1, limit: 100, offset: 0,
    });
    const upload = vi.spyOn(adminApi, "uploadCardAsset").mockResolvedValue({
      url: uploadedUrl,
      contentType: "image/webp",
      width: 640,
      height: 640,
      sizeBytes: 2048,
    });
    const updateMember = vi.spyOn(memberApi, "updateMember").mockResolvedValue({
      ...employeeMember,
      avatarUrl: uploadedUrl,
    });
    const create = vi.spyOn(adminApi, "createManagedCard").mockResolvedValue({
      ...draftCard,
      ownerUserId: employeeMember.userId,
      avatarUrl: uploadedUrl,
    });
    renderPage();

    await screen.findByText("尚未创建名片");
    await user.click(screen.getByRole("button", { name: "新建员工名片" }));
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "选择企业员工" }),
      employeeMember.userId,
    );
    const avatar = new File(["avatar"], "custom.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("选择员工头像"), avatar);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "配置来源" }),
      "customize",
    );
    await user.click(screen.getByRole("button", { name: "下一步：设计名片页面", hidden: true }));

    const composer = await screen.findByRole("dialog", { name: "创建前设计员工名片" });
    expect(screen.getByText(employeeMember.displayName)).toBeInTheDocument();
    expect(upload).not.toHaveBeenCalled();
    expect(updateMember).not.toHaveBeenCalled();
    expect(create).not.toHaveBeenCalled();
    await user.click(within(composer).getByRole("button", { name: "使用此设计创建名片" }));

    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    expect(upload).toHaveBeenNthCalledWith(1, avatar);
    await waitFor(() => expect(updateMember).toHaveBeenCalledTimes(1));
    expect(updateMember).toHaveBeenNthCalledWith(
      1,
      employeeMember.membershipId,
      { avatarUrl: uploadedUrl },
    );
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create.mock.calls[0][0]).toMatchObject({
      cardKind: "employee",
      ownerUserId: employeeMember.userId,
      avatarUrl: "",
      templateSourceCardId: undefined,
      templateDocument: {
        schemaVersion: 1,
        themeKey: "brand",
        blocks: [],
      },
    });
  });
});

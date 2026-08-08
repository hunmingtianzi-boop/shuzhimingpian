import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import type {
  CaseStudy,
  EnterpriseTemplate,
  ManagedCard,
  SelectableFaqDocument,
} from "../api/types";
import { adminLightTheme } from "../theme";
import { EnterpriseTemplateEditor } from "./EnterpriseTemplateEditor";

const card: ManagedCard = {
  id: "card-enterprise",
  cardKind: "enterprise",
  slug: "c-enterprise",
  displayName: "拓途商务",
  title: "企业数字化服务",
  avatarUrl: "/api/v1/public/card-assets/company-1/logo.webp",
  assistantName: "拓途助手",
  welcomeMessage: "欢迎咨询",
  suggestedQuestions: [],
  policyVersions: { privacy: "p1", chatNotice: "c1", leadConsent: "l1" },
  shareUrl: "https://cards.example.test/c/tuotu",
  qrUrl: "https://cards.example.test/c/tuotu",
  status: "draft",
  version: 7,
};

const publishedCase: CaseStudy = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "retail-growth",
  title: "零售增长案例",
  industry: "零售",
  background: "",
  solution: "",
  result: "转化率提升",
  clientDisplayName: "示例客户",
  imageUrl: "/case.webp",
  visibility: "public",
  sortOrder: 0,
  settings: {},
  status: "published",
  version: 2,
};

const companyProfile = {
  id: "company-1",
  name: "拓途商务",
  summary: "企业数字化服务",
  industry: "企业服务",
  region: "杭州",
  website: "https://tuotu.example.test",
  logoUrl: card.avatarUrl,
  profilePersonalizationPolicyVersion: "profile-v1",
  version: 3,
};

const identityBlock = {
  id: "identity",
  type: "identity" as const,
  visible: true,
  sortOrder: 0,
  title: "基础名片",
};

const selectableFaqs: SelectableFaqDocument[] = [
  {
    id: "faq-delivery",
    title: "项目多久可以交付？",
    answer: "标准项目一般在四到六周完成交付。",
    status: "published",
    visibility: "public",
  },
  {
    id: "faq-support",
    title: "是否提供售后支持？",
    answer: "项目上线后提供持续运维与使用培训。",
    status: "published",
    visibility: "public",
  },
];

function template(overrides: Partial<EnterpriseTemplate> = {}): EnterpriseTemplate {
  return {
    cardId: card.id,
    version: card.version,
    draft: {
      schemaVersion: 1,
      themeKey: "brand",
      blocks: [
        identityBlock,
        {
          id: "rich-1",
          type: "rich_text",
          visible: true,
          sortOrder: 1,
          title: "企业介绍",
          body: "我们帮助企业持续增长。",
        },
        {
          id: "ai-1",
          type: "ai_assistant",
          visible: true,
          sortOrder: 2,
          title: "在线咨询",
        },
      ],
    },
    ...overrides,
  };
}

function renderEditor(props: Partial<React.ComponentProps<typeof EnterpriseTemplateEditor>> = {}) {
  const handlers = {
    onClose: vi.fn(),
    onEditBasicSettings: vi.fn(),
    onRequestPublish: vi.fn(),
    onSaved: vi.fn(),
  };
  render(
    <FluentProvider theme={adminLightTheme}>
      <EnterpriseTemplateEditor
        card={card}
        open
        {...handlers}
        {...props}
      />
    </FluentProvider>,
  );
  return handlers;
}

describe("EnterpriseTemplateEditor", () => {
  beforeEach(() => {
    vi.spyOn(adminApi, "listProducts").mockResolvedValue([]);
    vi.spyOn(adminApi, "listSelectableFaqDocuments").mockResolvedValue([]);
  });
  afterEach(() => vi.restoreAllMocks());

  it("loads the actual published page as an operable preview and keeps a live draft mode", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(template());
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([publishedCase]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    renderEditor({ card: { ...card, status: "published" } });

    const publicPage = await screen.findByTitle("实际公开名片页面");
    expect(publicPage).toHaveAttribute("src", card.shareUrl);
    expect(screen.getByRole("tab", { name: "线上" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    await user.click(screen.getByRole("tab", { name: "草稿" }));
    expect(screen.getByRole("navigation", { name: "企业名片内容导航预览" })).toBeInTheDocument();
  });

  it("reorders blocks, preserves the original mobile shell and saves the draft", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(template());
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([publishedCase]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    const update = vi.spyOn(adminApi, "updateEnterpriseTemplate").mockImplementation(
      async (_id, _version, themeKey, blocks) => template({
        version: 8,
        draft: { schemaVersion: 1, themeKey, blocks },
      }),
    );
    renderEditor();

    const aiStructureItem = await screen.findByRole("button", { name: /03\s*在线咨询/ });
    expect(screen.getByRole("heading", { name: "实际名片页面" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "企业名片内容导航预览" })).toBeInTheDocument();
    expect(screen.getByText(/拖动手柄调整顺序/)).toBeInTheDocument();
    expect(screen.getAllByLabelText("拖动基础名片调整位置")).toHaveLength(2);
    expect(screen.queryByLabelText("视觉主题")).not.toBeInTheDocument();
    await user.click(aiStructureItem);
    await user.click(screen.getByRole("button", { name: "上移" }));
    // Tabster can temporarily mark the portal surface aria-hidden in jsdom after
    // a focus change. Keep exercising the rendered controls instead of relying
    // on that browser-only focus state in this unit test.
    const publicCheckboxes = screen.getAllByRole("checkbox", {
      name: "公开展示",
      hidden: true,
    });
    await user.click(publicCheckboxes[0]);
    await user.click(screen.getByRole("button", { name: "保存草稿", hidden: true }));

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(update.mock.calls[0][0]).toBe(card.id);
    expect(update.mock.calls[0][1]).toBe(7);
    expect(update.mock.calls[0][2]).toBe("brand");
    expect(update.mock.calls[0][3].map((block) => block.id)).toEqual(["identity", "ai-1", "rich-1"]);
    expect(update.mock.calls[0][3].map((block) => block.sortOrder)).toEqual([0, 1, 2]);
    expect(update.mock.calls[0][3][1].visible).toBe(false);
    expect(update.mock.calls[0][3][0]).toEqual(expect.objectContaining({ id: "identity", visible: true }));
    expect(await screen.findByText("草稿已保存，公开页仍保持上一次发布内容。")).toBeInTheDocument();
  }, 15_000);

  it("uploads gallery images through the existing asset service before saving", async () => {
    const user = userEvent.setup();
    const galleryTemplate = template({
      draft: {
        schemaVersion: 1,
        themeKey: "clean",
        blocks: [identityBlock, {
          id: "gallery-1",
          type: "image_gallery",
          visible: true,
          sortOrder: 1,
          title: "项目现场",
          imageUrls: [],
        }, {
          id: "ai-1",
          type: "ai_assistant",
          visible: true,
          sortOrder: 2,
          title: "在线咨询",
        }],
      },
    });
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(galleryTemplate);
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    const upload = vi.spyOn(adminApi, "uploadCardAsset").mockResolvedValue({
      url: "/api/v1/public/card-assets/company-1/gallery.webp",
      contentType: "image/webp",
      width: 1200,
      height: 900,
      sizeBytes: 22_000,
    });
    const update = vi.spyOn(adminApi, "updateEnterpriseTemplate").mockResolvedValue({
      ...galleryTemplate,
      version: 8,
      draft: {
        ...galleryTemplate.draft,
        blocks: galleryTemplate.draft.blocks.map((block) => block.id === "gallery-1"
          ? { ...block, imageUrls: ["/api/v1/public/card-assets/company-1/gallery.webp"] }
          : block),
      },
    });
    renderEditor();

    await user.click(await screen.findByRole("button", { name: /02\s*项目现场/ }));
    expect(await screen.findByText("请至少上传一张图片。")).toBeInTheDocument();
    const file = new File(["image"], "gallery.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("选择项目现场图片"), file);
    await waitFor(() => expect(upload).toHaveBeenCalledWith(file));
    expect(await screen.findByAltText("展示图片 1")).toHaveAttribute(
      "src",
      "/api/v1/public/card-assets/company-1/gallery.webp",
    );
    await user.click(screen.getByRole("button", { name: "保存草稿", hidden: true }));
    await waitFor(() => expect(update).toHaveBeenCalled());
    expect(update.mock.calls[0][3].find((block) => block.id === "gallery-1")?.imageUrls).toEqual([
      "/api/v1/public/card-assets/company-1/gallery.webp",
    ]);
  }, 15_000);

  it("adds a shared block background and a rich-text content image", async () => {
    const user = userEvent.setup();
    const richTemplate = template();
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(richTemplate);
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    const upload = vi.spyOn(adminApi, "uploadCardAsset")
      .mockResolvedValueOnce({
        url: "/api/v1/public/card-assets/company-1/story.webp",
        contentType: "image/webp",
        width: 1200,
        height: 800,
        sizeBytes: 18_000,
      })
      .mockResolvedValueOnce({
        url: "/api/v1/public/card-assets/company-1/background.webp",
        contentType: "image/webp",
        width: 1600,
        height: 900,
        sizeBytes: 24_000,
      })
      .mockResolvedValueOnce({
        url: "/api/v1/public/card-assets/company-1/page-background.webp",
        contentType: "image/webp",
        width: 1800,
        height: 1200,
        sizeBytes: 28_000,
      });
    const update = vi.spyOn(adminApi, "updateEnterpriseTemplate").mockImplementation(
      async (_id, _version, themeKey, blocks) => template({
        version: 8,
        draft: { schemaVersion: 1, themeKey, blocks },
      }),
    );
    renderEditor();

    await user.click(await screen.findByRole("button", { name: /02\s*企业介绍/ }));
    const contentFile = new File(["content"], "story.png", { type: "image/png" });
    const backgroundFile = new File(["background"], "background.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("选择企业介绍内容图片"), contentFile);
    await waitFor(() => expect(screen.getByAltText("内容图片预览")).toBeInTheDocument());
    await user.click(screen.getByRole("radio", { name: "左侧", hidden: true }));
    await user.click(screen.getByRole("radio", { name: "1:1", hidden: true }));
    await user.click(screen.getByRole("radio", { name: "高版", hidden: true }));
    await user.click(screen.getByRole("radio", { name: "多", hidden: true }));
    const blockBackgroundSettings = screen.getByRole("region", { name: "板块背景", hidden: true });
    await user.click(within(blockBackgroundSettings).getByRole("radio", { name: "图片", hidden: true }));
    await user.upload(screen.getByLabelText("选择企业介绍背景图片"), backgroundFile);
    await waitFor(() => expect(screen.getByAltText("板块背景预览")).toBeInTheDocument());
    await user.click(screen.getByRole("radio", { name: "浅色字", hidden: true }));
    const pageSettings = screen.getByRole("region", { name: "页面外观", hidden: true });
    await user.click(within(pageSettings).getByRole("radio", { name: "图片", hidden: true }));
    const pageBackgroundFile = new File(["page"], "page-background.png", { type: "image/png" });
    await user.upload(within(pageSettings).getByLabelText("选择整体背景图片"), pageBackgroundFile);
    await waitFor(() => expect(screen.getByAltText("整体背景预览")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "保存草稿", hidden: true }));

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(upload).toHaveBeenNthCalledWith(1, contentFile);
    expect(upload).toHaveBeenNthCalledWith(2, backgroundFile);
    expect(upload).toHaveBeenNthCalledWith(3, pageBackgroundFile);
    expect(update.mock.calls[0][3].find((block) => block.id === "rich-1")).toEqual(
      expect.objectContaining({
        textTone: "light",
        background: expect.objectContaining({
          kind: "image",
          imageUrl: "/api/v1/public/card-assets/company-1/background.webp",
          overlayOpacity: 0.42,
        }),
        contentImage: expect.objectContaining({
          url: "/api/v1/public/card-assets/company-1/story.webp",
          placement: "left",
          aspectRatio: "square",
        }),
        sizePreset: "tall",
        paddingY: "spacious",
      }),
    );
    expect(update.mock.calls[0][4]).toEqual(expect.objectContaining({
      kind: "image",
      imageUrl: "/api/v1/public/card-assets/company-1/page-background.webp",
    }));
  }, 15_000);

  it("selects published cases and enters the existing publish confirmation", async () => {
    const user = userEvent.setup();
    const caseTemplate = template({
      draft: {
        schemaVersion: 1,
        themeKey: "brand",
        blocks: [identityBlock, {
          id: "cases-1",
          type: "case_collection",
          visible: true,
          sortOrder: 1,
          title: "客户案例",
          caseIds: [],
        }, {
          id: "ai-1",
          type: "ai_assistant",
          visible: true,
          sortOrder: 2,
          title: "在线咨询",
        }],
      },
    });
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(caseTemplate);
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([publishedCase]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    vi.spyOn(adminApi, "updateEnterpriseTemplate").mockImplementation(
      async (_id, _version, themeKey, blocks) => ({
        ...caseTemplate,
        version: 8,
        draft: { schemaVersion: 1, themeKey, blocks },
      }),
    );
    const handlers = renderEditor();

    await user.click(await screen.findByRole("button", { name: /02\s*客户案例/ }));
    const picker = screen.getByRole("group", { name: "选择已发布案例" });
    await user.click(within(picker).getByRole("checkbox", { name: /零售增长案例/ }));
    await user.click(screen.getByRole("button", { name: "保存草稿", hidden: true }));
    const publishButton = screen.getByRole("button", { name: "进入发布确认", hidden: true });
    await waitFor(() => expect(publishButton).toBeEnabled());
    fireEvent.click(publishButton);

    expect(handlers.onRequestPublish).toHaveBeenCalledWith(expect.objectContaining({
      id: card.id,
      version: 8,
    }));
  }, 15_000);

  it("adds a free module from the library and persists it immediately as a draft", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(template());
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    const update = vi.spyOn(adminApi, "updateEnterpriseTemplate").mockImplementation(
      async (_id, _version, themeKey, blocks) => template({
        version: 8,
        draft: { schemaVersion: 1, themeKey, blocks },
      }),
    );
    renderEditor();

    await screen.findByRole("button", { name: "图片画廊" });
    await user.click(screen.getByRole("button", { name: "图片画廊" }));

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(update.mock.calls[0][3]).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: "image_gallery" }),
    ]));
    expect(await screen.findByText("图片画廊已加入草稿。请补齐内容后再发布。")).toBeInTheDocument();
  }, 15_000);

  it("binds FAQ blocks to selectable published knowledge instead of a free-text answer", async () => {
    const user = userEvent.setup();
    const faqTemplate = template({
      draft: {
        schemaVersion: 1,
        themeKey: "brand",
        blocks: [identityBlock, {
          id: "faq-1",
          type: "faq",
          visible: true,
          directoryEnabled: true,
          sortOrder: 1,
          title: "常见问题",
          faqMode: "all_published",
          faqDocumentIds: [],
        }],
      },
    });
    vi.mocked(adminApi.listSelectableFaqDocuments).mockResolvedValue(selectableFaqs);
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(faqTemplate);
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    const update = vi.spyOn(adminApi, "updateEnterpriseTemplate").mockImplementation(
      async (_id, _version, themeKey, blocks) => ({
        ...faqTemplate,
        version: 8,
        draft: { schemaVersion: 1, themeKey, blocks },
      }),
    );
    renderEditor();

    await user.click(await screen.findByRole("button", { name: /02\s*常见问题/ }));
    expect(screen.queryByRole("textbox", { name: "回答内容" })).not.toBeInTheDocument();
    expect(screen.getByText("数据来源：知识 FAQ")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /自动同步全部公开 FAQ/ })).toBeChecked();
    expect(screen.getByRole("link", { name: /前往管理/ })).toHaveAttribute("href", expect.stringContaining("knowledge"));

    await user.click(screen.getByRole("radio", { name: "精选展示" }));
    await user.click(screen.getByRole("checkbox", { name: "项目多久可以交付？" }));
    await user.click(screen.getByRole("checkbox", { name: "是否提供售后支持？" }));
    await user.click(screen.getByRole("button", { name: "上移 FAQ：是否提供售后支持？" }));
    await user.click(screen.getByRole("button", { name: "保存草稿" }));

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(update.mock.calls[0][3].find((block) => block.id === "faq-1")).toEqual(expect.objectContaining({
      faqMode: "selected",
      faqDocumentIds: ["faq-support", "faq-delivery"],
    }));
  }, 15_000);

  it("keeps customize-before-create changes local until explicit confirmation", async () => {
    const user = userEvent.setup();
    const onDraftConfirm = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    vi.spyOn(adminApi, "getCardComposerDefault").mockResolvedValue({
      cardKind: "employee",
      version: 3,
      document: template().draft,
    });
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    const updateDefault = vi.spyOn(adminApi, "updateCardComposerDefault");
    const updateCard = vi.spyOn(adminApi, "updateEnterpriseTemplate");

    renderEditor({
      card: undefined,
      creationDraft: {
        cardKind: "employee",
        identityPreview: {
          displayName: "林晓",
          title: "客户成功经理",
          avatarUrl: "/portrait.webp",
        },
      },
      onDraftConfirm,
      onClose,
    });

    await user.click(await screen.findByRole("button", { name: "图文介绍" }));
    expect(updateDefault).not.toHaveBeenCalled();
    expect(updateCard).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "使用此设计创建名片" }));

    await waitFor(() => expect(onDraftConfirm).toHaveBeenCalledTimes(1));
    expect(onDraftConfirm.mock.calls[0][0]).toEqual(expect.objectContaining({
      schemaVersion: 1,
      themeKey: "brand",
      blocks: expect.arrayContaining([expect.objectContaining({ type: "rich_text" })]),
    }));
    expect(onClose).toHaveBeenCalled();
    expect(updateDefault).not.toHaveBeenCalled();
    expect(updateCard).not.toHaveBeenCalled();
  }, 15_000);
});

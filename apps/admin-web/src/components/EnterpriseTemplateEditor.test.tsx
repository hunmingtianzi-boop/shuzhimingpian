import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import type {
  CaseStudy,
  EnterpriseTemplate,
  EnterpriseTemplateBlock,
  ManagedCard,
  SelectableFaqDocument,
} from "../api/types";
import { adminLightTheme } from "../theme";
import { EnterpriseTemplateEditor, getEnterpriseTemplateBlockIssue } from "./EnterpriseTemplateEditor";

// The editor behavior tests exercise our sortable commands and persisted
// ordering, not dnd-kit's sensor implementation. Keep the jsdom suite on one
// React dispatcher even when a Windows worktree reuses an external pnpm store.
vi.mock("@dnd-kit/core", () => ({
  DndContext: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  KeyboardSensor: class KeyboardSensor {},
  PointerSensor: class PointerSensor {},
  closestCenter: vi.fn(),
  useSensor: vi.fn(() => ({})),
  useSensors: vi.fn((...sensors: unknown[]) => sensors),
}));

vi.mock("@dnd-kit/sortable", () => ({
  SortableContext: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  arrayMove: <T,>(items: T[], from: number, to: number) => {
    const next = [...items];
    const [item] = next.splice(from, 1);
    if (item !== undefined) next.splice(to, 0, item);
    return next;
  },
  sortableKeyboardCoordinates: vi.fn(),
  useSortable: vi.fn(() => ({
    attributes: {},
    listeners: {},
    setNodeRef: vi.fn(),
    transform: null,
    transition: undefined,
    isDragging: false,
  })),
  verticalListSortingStrategy: {},
}));

vi.mock("@dnd-kit/utilities", () => ({
  CSS: { Transform: { toString: vi.fn(() => undefined) } },
}));

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
  logoUrl: "/api/v1/public/card-assets/company-1/company-logo.webp",
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
  it("accepts a tel-prefixed phone target and leaves normalization to the API mapper", () => {
    const block = {
      id: "actions-test",
      type: "action_collection",
      visible: true,
      sortOrder: 0,
      title: "快捷入口",
      actionItems: [{
        id: "phone-test",
        title: "电话咨询",
        targetType: "phone",
        targetValue: "tel:+8613812345688",
        openMode: "self",
      }],
    } satisfies EnterpriseTemplateBlock;
    expect(getEnterpriseTemplateBlockIssue(block)).toBeUndefined();
  });
  it("uses the exact simulator editor shell and shared panel primitives", async () => {
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(template());
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([publishedCase]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    renderEditor();
    await screen.findByRole("button", { name: /01\s*基础名片/ });
    const shell = document.querySelector(".studio-shell");
    expect(shell?.querySelector(":scope > .fui-DialogTitle .studio-topbar")).toBeInTheDocument();
    expect(shell?.querySelector(".studio-grid > .studio-panel.left .module-row")).toBeInTheDocument();
    expect(shell?.querySelector(".studio-grid > .studio-canvas .canvas-toolbar")).toBeInTheDocument();
    expect(shell?.querySelector(".studio-grid > .studio-panel.right .inspector-title")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "拓途商务企业标识" })).toHaveAttribute(
      "src",
      new URL(companyProfile.logoUrl, window.location.origin).href,
    );
  });

  beforeEach(() => {
    vi.spyOn(adminApi, "listProducts").mockResolvedValue([]);
    vi.spyOn(adminApi, "listSelectableFaqDocuments").mockResolvedValue([]);
  });
  afterEach(() => vi.restoreAllMocks());

  it("opens the current shared draft renderer and keeps the published page as an explicit comparison", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(template());
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([publishedCase]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    renderEditor({ card: { ...card, status: "published" } });

    expect(await screen.findByRole("navigation", { name: "企业名片内容导航预览" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "草稿" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.queryByTitle("实际公开名片页面")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "线上" }));
    expect(await screen.findByTitle("实际公开名片页面")).toHaveAttribute("src", card.shareUrl);
  }, 15_000);

  it("keeps empty and in-progress input values when the parent recreates equivalent props", async () => {
    const user = userEvent.setup();
    const load = vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(template({
      draft: {
        schemaVersion: 1,
        themeKey: "brand",
        blocks: [identityBlock, {
          id: "rich-new",
          type: "rich_text",
          visible: true,
          sortOrder: 1,
          title: "图文介绍",
          body: "待编辑内容",
        }],
      },
    }));
    const update = vi.spyOn(adminApi, "updateEnterpriseTemplate").mockImplementation(
      async (_id, _version, themeKey, blocks) => template({
        version: 8,
        draft: { schemaVersion: 1, themeKey, blocks },
      }),
    );
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([publishedCase]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);

    function RecreatingParent() {
      const [, setTick] = useState(0);
      const [currentCard, setCurrentCard] = useState(card);
      return <FluentProvider theme={adminLightTheme}>
        <button type="button" onClick={() => setTick((current) => current + 1)}>父层刷新</button>
        <EnterpriseTemplateEditor
          card={{ ...currentCard, identityTitles: [...(currentCard.identityTitles ?? [])] }}
          open
          onClose={vi.fn()}
          onEditBasicSettings={vi.fn()}
          onRequestPublish={vi.fn()}
          onSaved={(updatedCard) => {
            if (updatedCard) setCurrentCard(updatedCard);
          }}
        />
      </FluentProvider>;
    }

    render(<RecreatingParent />);
    await user.click(await screen.findByRole("button", { name: /02\s*图文介绍/ }));
    const titleInput = screen.getByRole("textbox", { name: "模块标题" });
    const bodyInput = screen.getByRole("textbox", { name: "内容" });
    await user.clear(titleInput);
    await user.clear(bodyInput);
    expect(titleInput).toHaveValue("");
    let composedValue = "";
    for (const character of "连续输入不会闪回") {
      composedValue += character;
      fireEvent.change(bodyInput, { target: { value: composedValue } });
    }
    await waitFor(() => expect(bodyInput).toHaveValue("连续输入不会闪回"));

    fireEvent.compositionStart(bodyInput);
    fireEvent.change(bodyInput, { target: { value: "中文输入法组词中" } });
    expect(bodyInput).toHaveValue("中文输入法组词中");
    fireEvent.compositionEnd(bodyInput, { data: "中" });
    fireEvent.change(bodyInput, { target: { value: "中文输入法组词完成" } });
    await waitFor(() => expect(bodyInput).toHaveValue("中文输入法组词完成"));

    await user.click(screen.getByRole("button", { name: "父层刷新" }));
    expect(titleInput).toHaveValue("");
    expect(bodyInput).toHaveValue("中文输入法组词完成");
    expect(load).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "保存草稿", hidden: true }));
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(load).toHaveBeenCalledTimes(1);
    expect(bodyInput).toHaveValue("中文输入法组词完成");
    expect(update.mock.calls[0][3]).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "rich-new", title: "", body: "中文输入法组词完成", showTitle: false }),
    ]));
  }, 15_000);

  it("keeps a newly added action module editable while its draft has not been saved", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(template());
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    const update = vi.spyOn(adminApi, "updateEnterpriseTemplate");
    renderEditor();

    await user.click(await screen.findByRole("tab", { name: "添加模块" }));
    await user.click(screen.getByRole("button", { name: /^行动按钮/ }));

    const labelInput = await screen.findByRole("textbox", { name: "按钮文案", hidden: true });
    expect(labelInput).toBeEnabled();
    await user.type(labelInput, "预约交流");
    expect(labelInput).toHaveValue("预约交流");
    expect(update).not.toHaveBeenCalled();

  }, 15_000);

  it("keeps every action-entry field stable while the live preview refreshes", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(template());
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    renderEditor();

    await user.click(await screen.findByRole("tab", { name: "添加模块" }));
    await user.click(screen.getByRole("button", { name: /^快捷入口/ }));
    await user.click(await screen.findByRole("button", { name: "添加入口", hidden: true }));

    const title = screen.getByRole("textbox", { name: "入口名称", hidden: true });
    const target = screen.getByRole("textbox", { name: "跳转网址", hidden: true });
    expect(target).toHaveValue("");
    fireEvent.change(title, { target: { value: "世界会展大会" } });
    fireEvent.change(target, { target: { value: "https://example.com/conference" } });
    await user.click(screen.getByRole("button", { name: "使用活动图标", hidden: true }));

    await new Promise((resolve) => window.setTimeout(resolve, 180));
    expect(screen.getByRole("textbox", { name: "入口名称", hidden: true })).toBe(title);
    expect(title).toHaveValue("世界会展大会");
    expect(target).toHaveValue("https://example.com/conference");
    expect(screen.getByRole("button", { name: "使用活动图标", hidden: true })).toHaveAttribute("aria-pressed", "true");
  }, 15_000);

  it("offers visual icon presets for a single action button", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(template());
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    renderEditor();

    await user.click(await screen.findByRole("tab", { name: "添加模块" }));
    await user.click(screen.getByRole("button", { name: /^行动按钮/ }));
    const messagePreset = await screen.findByRole("button", { name: "使用咨询图标", hidden: true });
    await user.click(messagePreset);

    expect(messagePreset).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("group", { name: "预设图标", hidden: true })).toBeInTheDocument();
  }, 15_000);

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

    await screen.findByRole("button", { name: /02\s*企业介绍/ });
    expect(screen.queryByRole("button", { name: /在线咨询/ })).not.toBeInTheDocument();
    expect(screen.getByTitle("手机预览")).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByRole("navigation", { name: "企业名片内容导航预览" })).toBeInTheDocument();
    expect(screen.getByText(/拖动手柄调整顺序/)).toBeInTheDocument();
    expect(screen.getAllByLabelText("拖动基础名片调整位置")).toHaveLength(2);
    expect(screen.getByLabelText("视觉模板")).toHaveValue("brand");
    await user.click(screen.getByRole("button", { name: /02\s*企业介绍/, hidden: true }));
    await user.click(screen.getByRole("button", { name: "上移", hidden: true }));
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
    expect(update.mock.calls[0][3].map((block) => block.id)).toEqual(["rich-1", "identity"]);
    expect(update.mock.calls[0][3].map((block) => block.sortOrder)).toEqual([0, 1]);
    expect(update.mock.calls[0][3][0]).toEqual(expect.objectContaining({ id: "rich-1", visible: false }));
    expect(update.mock.calls[0][3][1]).toEqual(expect.objectContaining({ id: "identity", visible: true }));
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
    expect(await screen.findByAltText("gallery")).toHaveAttribute(
      "src",
      new URL(
        "/api/v1/public/card-assets/company-1/gallery.webp",
        window.location.origin,
      ).href,
    );
    expect(screen.getByRole("link", { name: /预览原图/, hidden: true })).toHaveAttribute(
      "href",
      expect.stringContaining("/api/v1/public/card-assets/company-1/gallery.webp"),
    );
    await user.click(screen.getByRole("button", { name: "保存草稿", hidden: true }));
    await waitFor(() => expect(update).toHaveBeenCalled());
    expect(update.mock.calls[0][3].find((block) => block.id === "gallery-1")?.imageUrls).toEqual([
      "/api/v1/public/card-assets/company-1/gallery.webp",
    ]);
  }, 15_000);

  it("uploads a real video asset and exposes a separate test-play link", async () => {
    const user = userEvent.setup();
    const videoTemplate = template({
      draft: {
        schemaVersion: 1,
        themeKey: "brand",
        blocks: [identityBlock, {
          id: "video-1",
          type: "video_link",
          visible: true,
          sortOrder: 1,
          title: "项目视频",
          videoCoverUrl: "/api/v1/public/card-assets/company-1/video-cover.webp",
        }],
      },
    });
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(videoTemplate);
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    const upload = vi.spyOn(adminApi, "uploadCardVideoAsset").mockResolvedValue({
      url: "/api/v1/public/card-video-assets/company-1/demo.mp4",
      contentType: "video/mp4",
      sizeBytes: 1_048_576,
    });
    renderEditor();

    await user.click(await screen.findByRole("button", { name: /02\s*项目视频/ }));
    const file = new File(["video"], "demo.mp4", { type: "video/mp4" });
    await user.upload(screen.getByLabelText("选择项目视频文件"), file);
    await waitFor(() => expect(upload).toHaveBeenCalledWith(file));
    expect(await screen.findByText("视频文件已上传并写入当前模块。")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /测试播放/, hidden: true })).toHaveAttribute(
      "href",
      expect.stringContaining("/api/v1/public/card-video-assets/company-1/demo.mp4"),
    );
    expect(getEnterpriseTemplateBlockIssue({
      id: "video-1",
      type: "video_link",
      visible: true,
      sortOrder: 1,
      videoUrl: "/api/v1/public/card-video-assets/company-1/demo.mp4",
      videoCoverUrl: "/cover.webp",
    })).toBeUndefined();
  }, 15_000);

  it("normalizes the identity layout and persists background with collection settings", async () => {
    const user = userEvent.setup();
    const layoutTemplate = template({
      draft: {
        schemaVersion: 1,
        themeKey: "brand",
        blocks: [{
          ...identityBlock,
          layoutVariant: "vertical",
          presentation: {
            identityLayout: "vertical",
            background: {
              fit: "cover",
              position: "center",
              scale: 1,
              opacity: 0.28,
              overlay: "light",
            },
          },
        }, {
          id: "business",
          type: "business_collection",
          visible: true,
          sortOrder: 1,
          title: "核心业务",
          layoutVariant: "auto",
          itemLimit: 4,
        }],
      },
    });
    vi.spyOn(adminApi, "getEnterpriseTemplate").mockResolvedValue(layoutTemplate);
    vi.spyOn(adminApi, "listCaseStudies").mockResolvedValue([]);
    vi.spyOn(adminApi, "getCompanyProfile").mockResolvedValue(companyProfile);
    const upload = vi.spyOn(adminApi, "uploadCardAsset").mockResolvedValue({
      url: "/api/v1/public/card-assets/company-1/identity-background.webp",
      contentType: "image/webp",
      width: 1600,
      height: 900,
      sizeBytes: 32_000,
    });
    const update = vi.spyOn(adminApi, "updateEnterpriseTemplate").mockImplementation(
      async (_id, _version, themeKey, blocks) => ({
        ...layoutTemplate,
        version: 8,
        draft: { schemaVersion: 1, themeKey, blocks },
      }),
    );
    renderEditor();

    await screen.findByText("基础名片背景");
    expect(screen.queryByRole("radio", { name: "横向" })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "竖向" })).not.toBeInTheDocument();
    expect(screen.getByText("企业信息项")).toBeInTheDocument();
    expect(screen.getByText(/最多 4 项，每项由小标题和内容组成/)).toBeInTheDocument();
    expect(document.querySelectorAll("[data-editor-pane]")).toHaveLength(3);
    const background = new File(["background"], "identity.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("选择基础名片背景图片"), background);
    await waitFor(() => expect(upload).toHaveBeenCalledWith(background));
    expect(await screen.findByAltText("基础名片背景预览")).toHaveAttribute(
      "src",
      new URL(
        "/api/v1/public/card-assets/company-1/identity-background.webp",
        window.location.origin,
      ).href,
    );
    const [scaleSlider, opacitySlider] = screen.getAllByRole("slider", { hidden: true });
    fireEvent.change(scaleSlider, { target: { value: "118" } });
    fireEvent.change(opacitySlider, { target: { value: "78" } });

    await user.click(screen.getByRole("button", { name: /02\s*核心业务/ }));
    // Tabster can temporarily mark the portal surface aria-hidden in jsdom
    // after a focus change. The controls remain rendered and interactive.
    await user.click(screen.getByRole("radio", { name: /双列宫格/, hidden: true }));
    expect(screen.getByRole("radio", { name: /双列宫格/, hidden: true })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await user.click(screen.getByRole("button", { name: "保存草稿", hidden: true }));

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    const savedBlocks = update.mock.calls[0][3];
    expect(savedBlocks.find((block) => block.id === "identity")).toEqual(expect.objectContaining({
      layoutVariant: "horizontal",
      presentation: expect.objectContaining({
        identityLayout: "horizontal",
        background: expect.objectContaining({
          assetUrl: "/api/v1/public/card-assets/company-1/identity-background.webp",
          scale: 1.18,
          opacity: 0.78,
          overlay: "light",
        }),
      }),
    }));
    expect(savedBlocks.find((block) => block.id === "business")).toEqual(expect.objectContaining({
      layoutVariant: "grid",
      itemLimit: 4,
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
    const picker = screen.getByRole("group", { name: "选择并调整已发布案例", hidden: true });
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

  it("adds a free module from the library without blocking its form on an immediate save", async () => {
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

    await user.click(await screen.findByRole("tab", { name: "添加模块" }));
    await screen.findByRole("button", { name: /^图片画廊/ });
    await user.click(screen.getByRole("button", { name: /^图片画廊/ }));

    expect(update).not.toHaveBeenCalled();
    expect(await screen.findByText("图片画廊已加入当前草稿；请先补齐内容，再保存草稿。")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "模块标题", hidden: true })).toBeEnabled();
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
    expect(screen.getByRole("radio", { name: /自动同步全部公开 FAQ/, hidden: true })).toBeChecked();
    expect(screen.getByRole("link", { name: /前往管理/ })).toHaveAttribute("href", expect.stringContaining("knowledge"));

    await user.click(screen.getByRole("radio", { name: "精选展示", hidden: true }));
    await user.click(screen.getByRole("checkbox", { name: "项目多久可以交付？", hidden: true }));
    await user.click(screen.getByRole("checkbox", { name: "是否提供售后支持？", hidden: true }));
    await user.click(screen.getByRole("button", { name: "上移 FAQ：是否提供售后支持？", hidden: true }));
    await user.click(screen.getByRole("button", { name: "保存草稿", hidden: true }));

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
          identityTitles: [],
          contactFields: [],
        },
      },
      onDraftConfirm,
      onClose,
    });

    expect(await screen.findByRole("button", { name: /02\s*个人介绍/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /02\s*企业介绍/ })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("tab", { name: "添加模块", hidden: true }));
    await user.click(await screen.findByRole("button", { name: /^图文介绍/, hidden: true }));
    expect(updateDefault).not.toHaveBeenCalled();
    expect(updateCard).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "使用此设计创建名片", hidden: true }));

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

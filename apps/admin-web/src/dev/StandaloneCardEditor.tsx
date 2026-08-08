import { Button, MessageBar, MessageBarBody, MessageBarTitle } from "@fluentui/react-components";
import { Edit24Regular } from "@fluentui/react-icons";
import { useMemo, useState } from "react";

import type {
  CardComposerDefault,
  CaseStudy,
  CompanyProfile,
  EnterpriseTemplate,
  EnterpriseTemplateBlock,
  EnterpriseTemplateThemeKey,
  ManagedCard,
  Product,
  SelectableFaqDocument,
} from "../api/types";
import {
  EnterpriseTemplateEditor,
  type EnterpriseTemplateEditorDataSource,
} from "../components/EnterpriseTemplateEditor";
import previewAiUrl from "./assets/preview-ai.svg";
import previewAvatarUrl from "./assets/preview-avatar.svg";
import previewCaseUrl from "./assets/preview-case.svg";
import previewContactUrl from "./assets/preview-contact.svg";
import previewSmartCardUrl from "./assets/preview-smart-card.svg";
import previewStoryUrl from "./assets/preview-story.svg";

const previewCard: ManagedCard = {
  id: "local-preview-card",
  cardKind: "enterprise",
  slug: "local-preview",
  displayName: "创非凡数智名片",
  title: "企业智能名片与 AI 接待",
  avatarUrl: previewAvatarUrl,
  assistantName: "企业 AI 助手",
  welcomeMessage: "欢迎了解企业业务、产品与合作方式。",
  suggestedQuestions: ["可以解决哪些业务问题？", "如何开始合作？"],
  policyVersions: {
    privacy: "local-preview",
    chatNotice: "local-preview",
    leadConsent: "local-preview",
  },
  shareUrl: "",
  qrUrl: "",
  status: "draft",
  version: 1,
};

const previewCompany: CompanyProfile = {
  id: "local-preview-company",
  name: "创非凡数智名片",
  summary: "把企业资料、员工名片、AI 接待与线索沉淀放进一个可持续运营的页面。",
  industry: "企业数字化服务",
  region: "杭州",
  website: "https://example.com",
  logoUrl: previewCard.avatarUrl,
  profilePersonalizationPolicyVersion: "local-preview",
  version: 1,
};

const previewProducts: Product[] = [
  {
    id: "product-card",
    slug: "smart-card",
    name: "数智名片",
    category: "企业展示",
    summary: "统一呈现企业、员工与业务内容，并支持实时更新。",
    detail: "示例内容，仅用于本地编辑器预览。",
    audience: "企业市场与销售团队",
    priceBoundary: "需结合接入范围评估",
    imageUrl: previewSmartCardUrl,
    visibility: "public",
    sortOrder: 0,
    settings: {},
    status: "published",
    version: 1,
  },
  {
    id: "product-ai",
    slug: "ai-reception",
    name: "AI 智能接待",
    category: "访客转化",
    summary: "根据已审核知识回答访客问题，并把高意向需求交给团队。",
    detail: "示例内容，仅用于本地编辑器预览。",
    audience: "客户服务与销售团队",
    priceBoundary: "需结合知识量与用量评估",
    imageUrl: previewAiUrl,
    visibility: "public",
    sortOrder: 1,
    settings: {},
    status: "published",
    version: 1,
  },
];

const previewCases: CaseStudy[] = [
  {
    id: "case-enterprise",
    slug: "enterprise-preview",
    title: "企业内容统一运营示例",
    industry: "企业服务",
    background: "企业资料分散在多个渠道，更新成本较高。",
    solution: "通过统一名片页面维护品牌、业务、案例与咨询入口。",
    result: "示例结果，仅用于本地编辑器交互预览。",
    clientDisplayName: "本地预览企业",
    imageUrl: previewCaseUrl,
    visibility: "public",
    sortOrder: 0,
    settings: {},
    status: "published",
    version: 1,
  },
];

const previewFaqs: SelectableFaqDocument[] = [
  {
    id: "faq-capability",
    title: "数智名片可以承载哪些内容？",
    answer: "可以展示企业与员工信息、产品、案例、FAQ、行动入口和 AI 助手。",
    status: "published",
    visibility: "public",
  },
  {
    id: "faq-update",
    title: "页面发布后还能继续修改吗？",
    answer: "可以。编辑内容先保存为草稿，确认发布后才会替换公开版本。",
    status: "published",
    visibility: "public",
  },
];

const initialBlocks: EnterpriseTemplateBlock[] = [
  {
    id: "identity",
    type: "identity",
    visible: true,
    directoryEnabled: true,
    sortOrder: 0,
    title: "基础名片",
  },
  {
    id: "introduction",
    type: "rich_text",
    visible: true,
    directoryEnabled: true,
    sortOrder: 1,
    title: "企业介绍",
    body: "让每一张企业名片都能持续更新内容、接待访客并沉淀业务机会。",
    contentImage: {
      url: previewStoryUrl,
      alt: "企业团队讨论数智名片方案",
      placement: "top",
      fit: "cover",
      aspectRatio: "wide",
      widthPercent: 100,
      positionX: 50,
      positionY: 48,
    },
    sizePreset: "standard",
    paddingY: "standard",
  },
  {
    id: "business",
    type: "business_collection",
    visible: true,
    directoryEnabled: true,
    sortOrder: 2,
    title: "核心业务",
    productIds: previewProducts.map((item) => item.id),
  },
  {
    id: "cases",
    type: "case_collection",
    visible: true,
    directoryEnabled: true,
    sortOrder: 3,
    title: "服务案例",
    caseIds: previewCases.map((item) => item.id),
  },
  {
    id: "faq",
    type: "faq",
    visible: true,
    directoryEnabled: true,
    sortOrder: 4,
    title: "常见问题",
    faqMode: "all_published",
    faqDocumentIds: [],
  },
  {
    id: "contact",
    type: "cta",
    visible: true,
    directoryEnabled: true,
    sortOrder: 5,
    title: "开始合作",
    body: "留下需求，交给团队继续跟进。",
    ctaLabel: "访问企业官网",
    ctaUrl: "https://example.com",
    background: {
      kind: "image",
      color: "#183438",
      imageUrl: previewContactUrl,
      fit: "cover",
      positionX: 50,
      positionY: 52,
      overlayColor: "#102b2f",
      overlayOpacity: 0.64,
    },
    textTone: "light",
  },
  {
    id: "assistant",
    type: "ai_assistant",
    visible: true,
    directoryEnabled: true,
    sortOrder: 6,
    title: "AI 助手",
    body: "直接提问，快速了解业务与合作方式。",
  },
];

function cloneBlocks(blocks: EnterpriseTemplateBlock[]) {
  return blocks.map((block) => ({
    ...block,
    imageUrls: block.imageUrls ? [...block.imageUrls] : undefined,
    productIds: block.productIds ? [...block.productIds] : undefined,
    caseIds: block.caseIds ? [...block.caseIds] : undefined,
    faqDocumentIds: block.faqDocumentIds ? [...block.faqDocumentIds] : undefined,
    background: block.background ? { ...block.background } : undefined,
    contentImage: block.contentImage ? { ...block.contentImage } : undefined,
  }));
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
        return;
      }
      reject(new Error("无法读取图片内容。"));
    });
    reader.addEventListener("error", () => reject(reader.error ?? new Error("无法读取图片内容。")));
    reader.readAsDataURL(file);
  });
}

function createPreviewDataSource(): EnterpriseTemplateEditorDataSource {
  let version = 1;
  let themeKey: EnterpriseTemplateThemeKey = "brand";
  let pageBackground: EnterpriseTemplateBlock["background"] = {
    kind: "color",
    color: "#edf4f3",
    fit: "cover",
    positionX: 50,
    positionY: 50,
    overlayColor: "#000000",
    overlayOpacity: 0,
  };
  let pageTextTone: EnterpriseTemplate["draft"]["pageTextTone"] = "auto";
  let blocks = cloneBlocks(initialBlocks);

  const enterpriseTemplate = (): EnterpriseTemplate => ({
    cardId: previewCard.id,
    version,
    draft: {
      schemaVersion: 1,
      themeKey,
      pageBackground: pageBackground ? { ...pageBackground } : undefined,
      pageTextTone,
      blocks: cloneBlocks(blocks),
    },
  });
  const composerDefault = (cardKind: ManagedCard["cardKind"]): CardComposerDefault => ({
    cardKind,
    version,
    document: enterpriseTemplate().draft,
  });
  const save = (
    nextThemeKey: EnterpriseTemplateThemeKey,
    nextBlocks: EnterpriseTemplateBlock[],
    nextPageBackground?: EnterpriseTemplateBlock["background"],
    nextPageTextTone?: EnterpriseTemplate["draft"]["pageTextTone"],
  ) => {
    version += 1;
    themeKey = nextThemeKey;
    pageBackground = nextPageBackground ? { ...nextPageBackground } : undefined;
    pageTextTone = nextPageTextTone ?? "auto";
    blocks = cloneBlocks(nextBlocks);
  };

  return {
    async getEnterpriseTemplate() {
      return enterpriseTemplate();
    },
    async getCardComposerDefault(cardKind) {
      return composerDefault(cardKind);
    },
    async listProducts() {
      return previewProducts;
    },
    async listCaseStudies() {
      return previewCases;
    },
    async getCompanyProfile() {
      return previewCompany;
    },
    async listSelectableFaqDocuments() {
      return previewFaqs;
    },
    async uploadCardAsset(file) {
      return {
        url: await readFileAsDataUrl(file),
        contentType: "image/webp",
        width: 0,
        height: 0,
        sizeBytes: file.size,
      };
    },
    async updateEnterpriseTemplate(_cardId, _expectedVersion, nextThemeKey, nextBlocks, nextPageBackground, nextPageTextTone) {
      save(nextThemeKey, nextBlocks, nextPageBackground, nextPageTextTone);
      return enterpriseTemplate();
    },
    async updateCardComposerDefault(cardKind, _expectedVersion, nextThemeKey, nextBlocks, nextPageBackground, nextPageTextTone) {
      save(nextThemeKey, nextBlocks, nextPageBackground, nextPageTextTone);
      return composerDefault(cardKind);
    },
  };
}

export function StandaloneCardEditor() {
  const [open, setOpen] = useState(true);
  const [notice, setNotice] = useState("这是独立的本地演示，修改只保存在当前页面内存中；真实发布请使用正式后台。");
  const dataSource = useMemo(createPreviewDataSource, []);

  return (
    <main className="standalone-editor-preview">
      <section aria-labelledby="standalone-editor-title">
        <span>本地开发预览</span>
        <h1 id="standalone-editor-title">名片页面编辑器</h1>
        <p>后端未启动时，可在这里独立体验页面结构、实时画布、属性编辑、拖动、上传和草稿保存。本页不会修改线上名片。</p>
        <MessageBar intent="info">
          <MessageBarBody>
            <MessageBarTitle>当前状态</MessageBarTitle>
            {notice}
          </MessageBarBody>
        </MessageBar>
        <Button appearance="primary" icon={<Edit24Regular />} onClick={() => setOpen(true)}>
          打开编辑器
        </Button>
      </section>

      <EnterpriseTemplateEditor
        card={previewCard}
        open={open}
        dataSource={dataSource}
        onClose={() => setOpen(false)}
        onEditBasicSettings={() => setNotice("基础资料属于外层名片管理功能，独立预览不写入真实企业数据。")}
        onRequestPublish={() => setNotice("模拟发布已确认。本页不连接线上数据；请在正式后台的“企业与员工名片”中执行真实发布。")}
        onSaved={() => setNotice("草稿已保存到当前页面内存，刷新页面后会重置。")}
      />
    </main>
  );
}

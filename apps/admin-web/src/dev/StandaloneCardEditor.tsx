import { Button, MessageBar, MessageBarBody, MessageBarTitle } from "@fluentui/react-components";
import { Edit24Regular } from "@fluentui/react-icons";
import { useMemo, useState } from "react";

import type {
  CardComposerDefault,
  EnterpriseTemplate,
  EnterpriseTemplateBlock,
  EnterpriseTemplateThemeKey,
  ManagedCard,
} from "../api/types";
import {
  EnterpriseTemplateEditor,
  type EnterpriseTemplateEditorDataSource,
} from "../components/EnterpriseTemplateEditor";
import {
  tuozheCard as previewCard,
  tuozheCases as previewCases,
  tuozheCompany as previewCompany,
  tuozheFaqs as previewFaqs,
  tuozheInitialBlocks as initialBlocks,
  tuozheProducts as previewProducts,
} from "./tuozheCardPreset";

function cloneBlocks(blocks: EnterpriseTemplateBlock[]) {
  return blocks.map((block) => ({
    ...block,
    imageUrls: block.imageUrls ? [...block.imageUrls] : undefined,
    productIds: block.productIds ? [...block.productIds] : undefined,
    caseIds: block.caseIds ? [...block.caseIds] : undefined,
    faqDocumentIds: block.faqDocumentIds ? [...block.faqDocumentIds] : undefined,
    galleryItems: block.galleryItems?.map((item) => ({ ...item })),
    actionItems: block.actionItems?.map((item) => ({ ...item })),
    productOverrides: block.productOverrides?.map((item) => ({ ...item })),
    caseOverrides: block.caseOverrides?.map((item) => ({
      ...item,
      metrics: item.metrics?.map((metric) => ({ ...metric })),
    })),
    presentation: block.presentation ? {
      ...block.presentation,
      background: block.presentation.background
        ? { ...block.presentation.background }
        : undefined,
    } : undefined,
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
  let blocks = cloneBlocks(initialBlocks);

  const enterpriseTemplate = (): EnterpriseTemplate => ({
    cardId: previewCard.id,
    version,
    draft: {
      schemaVersion: 1,
      themeKey,
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
  ) => {
    version += 1;
    themeKey = nextThemeKey;
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
    async updateCompanyProfile(input) {
      void input;
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
    async uploadCardVideoAsset(file) {
      return {
        url: await readFileAsDataUrl(file),
        contentType: file.type === "video/webm" ? "video/webm" as const : "video/mp4" as const,
        sizeBytes: file.size,
      };
    },
    async updateManagedCard(_cardId, _expectedVersion, input) {
      version += 1;
      return {
        ...previewCard,
        ...input,
        id: previewCard.id,
        shareUrl: previewCard.shareUrl,
        qrUrl: previewCard.qrUrl,
        status: previewCard.status,
        version,
      };
    },
    async updateEnterpriseTemplate(_cardId, _expectedVersion, nextThemeKey, nextBlocks) {
      save(nextThemeKey, nextBlocks);
      return enterpriseTemplate();
    },
    async updateCardComposerDefault(cardKind, _expectedVersion, nextThemeKey, nextBlocks) {
      save(nextThemeKey, nextBlocks);
      return composerDefault(cardKind);
    },
  };
}

export function StandaloneCardEditor() {
  const [open, setOpen] = useState(true);
  const [notice, setNotice] = useState("拓浙审核草稿已载入；修改只保存在当前页面内存中，不会发布或改动线上名片。");
  const dataSource = useMemo(createPreviewDataSource, []);

  return (
    <main className="standalone-editor-preview">
      <section aria-labelledby="standalone-editor-title">
        <span>本地审核草稿</span>
        <h1 id="standalone-editor-title">拓浙AI生态 · 名片页面编辑器</h1>
        <p>已根据 tuotuzju.com 当前公开资料整理。你可以在现有编辑器中继续调整结构、文案、图片和入口；本页不会修改线上名片。</p>
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
        onEditBasicSettings={() => setNotice("拓浙基础资料已作为审核预设载入；独立预览不会写入真实企业数据。")}
        onRequestPublish={() => setNotice("已完成本地发布检查，但没有连接线上发布接口；审核通过后再同步到正式后台。")}
        onSaved={() => setNotice("拓浙草稿已保存到当前页面内存；刷新页面会恢复为本次审核预设。")}
      />
    </main>
  );
}

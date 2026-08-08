import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  Spinner,
} from "@fluentui/react-components";
import {
  Add24Regular,
  Delete24Regular,
  Edit24Regular,
  Save24Regular,
  Send24Regular,
} from "@fluentui/react-icons";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, KeyboardEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type {
  CaseStudy,
  CompanyProfile,
  EnterpriseTemplateBlock,
  EnterpriseTemplateBlockBackground,
  EnterpriseTemplateBlockType,
  EnterpriseTemplateThemeKey,
  ManagedCard,
  Product,
  SelectableFaqDocument,
} from "../api/types";
import { resolveApiResourceUrl } from "../lib/resourceUrl";
import { ActionConfirmDialog } from "./ActionConfirmDialog";
import { TemplateBlockInspector } from "./enterprise-template/TemplateBlockInspector";
import { TemplateCanvas } from "./enterprise-template/TemplateCanvas";
import { TemplatePageSettings } from "./enterprise-template/TemplatePageSettings";
import { FormFeedback } from "./FormFeedback";

const MAX_CARD_IMAGE_BYTES = 5 * 1024 * 1024;
const CARD_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export const enterpriseTemplateBlockLabels: Record<EnterpriseTemplateBlockType, string> = {
  identity: "基础名片",
  rich_text: "图文介绍",
  business_collection: "核心业务",
  image_gallery: "图片画廊",
  video_link: "视频",
  case_collection: "案例集合",
  trust_panel: "企业资料",
  faq: "常见问题",
  cta: "行动按钮",
  ai_assistant: "AI 助手入口",
};

function nextBlockId(type: EnterpriseTemplateBlockType) {
  const suffix = typeof crypto.randomUUID === "function"
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10);
  return `${type}-${suffix}`;
}

export function createEnterpriseTemplateBlock(
  type: EnterpriseTemplateBlockType,
): EnterpriseTemplateBlock {
  return {
    id: nextBlockId(type),
    type,
    visible: true,
    directoryEnabled: true,
    sortOrder: 0,
    title: enterpriseTemplateBlockLabels[type],
    ...(type === "faq" ? { faqMode: "all_published" as const, faqDocumentIds: [] } : {}),
  };
}

export function moveEnterpriseTemplateBlock(
  blocks: EnterpriseTemplateBlock[],
  index: number,
  direction: -1 | 1,
) {
  const target = index + direction;
  if (target < 0 || target >= blocks.length) return blocks;
  const next = [...blocks];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

function normalizeEnterpriseTemplateBlockOrder(
  blocks: EnterpriseTemplateBlock[],
): EnterpriseTemplateBlock[] {
  return blocks.map((block, sortOrder) => (
    block.sortOrder === sortOrder ? block : { ...block, sortOrder }
  ));
}

function isHttpsUrl(value?: string) {
  if (!value) return false;
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}

export function getEnterpriseTemplateBlockIssue(
  block: EnterpriseTemplateBlock,
  selectableFaqs?: SelectableFaqDocument[],
) {
  // The API deliberately ignores incomplete hidden blocks when publishing.
  // Keep the editor's gate aligned so a hidden draft module cannot silently
  // disable the publish action.
  if (!block.visible) return undefined;

  switch (block.type) {
    case "image_gallery":
      return block.imageUrls?.length ? undefined : "请至少上传一张图片。";
    case "video_link":
      if (!isHttpsUrl(block.videoUrl)) return "请输入有效的 HTTPS 视频地址。";
      if (!block.videoCoverUrl) return "请上传视频封面。";
      return undefined;
    case "business_collection":
      return block.id === "business" || block.productIds?.length ? undefined : "请至少选择一个已发布产品。";
    case "case_collection":
      return block.id === "cases" || block.caseIds?.length ? undefined : "请至少选择一个已发布案例。";
    case "faq": {
      if (block.faqMode !== "selected") return undefined;
      const selectedIds = block.faqDocumentIds ?? [];
      if (!selectedIds.length) return "精选展示模式下请至少选择一条 FAQ。";
      if (selectableFaqs) {
        const eligibleIds = new Set(selectableFaqs.map((item) => item.id));
        if (selectedIds.some((id) => !eligibleIds.has(id))) {
          return "精选列表包含已撤回或非公开的 FAQ，请重新选择。";
        }
      }
      return undefined;
    }
    case "cta":
      if (!block.ctaLabel?.trim()) return "请输入按钮文案。";
      return isHttpsUrl(block.ctaUrl) ? undefined : "请输入有效的 HTTPS 跳转地址。";
    default:
      return undefined;
  }
}

export type EnterpriseTemplatePublishCheck = {
  key: string;
  label: string;
  ready: boolean;
};

export function getEnterpriseTemplatePublishChecks(
  card: ManagedCard,
  blocks: EnterpriseTemplateBlock[],
  company?: CompanyProfile,
  selectableFaqs?: SelectableFaqDocument[],
): EnterpriseTemplatePublishCheck[] {
  const hasContactRoute = blocks.some(
    (block) =>
      (block.type === "cta" && isHttpsUrl(block.ctaUrl)) ||
      block.type === "ai_assistant",
  );
  return [
    { key: "name", label: "企业名称", ready: Boolean(card.displayName.trim()) },
    { key: "positioning", label: "业务定位或品牌标语", ready: Boolean(card.title.trim()) },
    { key: "brand", label: "企业 Logo", ready: Boolean(card.avatarUrl.trim() || company?.logoUrl.trim()) },
    { key: "blocks", label: "全部内容区块完整", ready: blocks.every((block) => !getEnterpriseTemplateBlockIssue(block, selectableFaqs)) },
    { key: "contact", label: "至少一个联系入口（官网、行动按钮或 AI 助手）", ready: hasContactRoute || Boolean(company?.website.trim()) },
  ];
}

function toApiError(cause: unknown, message: string, code: string) {
  return cause instanceof ApiError ? cause : new ApiError(message, { code });
}

function SortableStructureItem({
  block,
  index,
  busy,
  selected,
  onSelect,
  onRemove,
}: {
  block: EnterpriseTemplateBlock;
  index: number;
  busy: boolean;
  selected: boolean;
  onSelect: () => void;
  onRemove?: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: block.id,
    disabled: busy,
  });
  return (
    <li
      ref={setNodeRef}
      className={`${isDragging ? "is-dragging" : ""}${selected ? " is-selected" : ""}`.trim() || undefined}
      style={{ transform: CSS.Transform.toString(transform), transition }}
    >
      <div className="template-structure-row">
        <button
          type="button"
          className="template-drag-handle"
          aria-label={`拖动${enterpriseTemplateBlockLabels[block.type]}调整位置`}
          disabled={busy}
          {...attributes}
          {...listeners}
        >⠿</button>
        <button
          type="button"
          className="template-structure-select"
          aria-current={selected ? "true" : undefined}
          onClick={onSelect}
          disabled={busy}
        >
          <span>{String(index + 1).padStart(2, "0")}</span>
          <strong>{block.title || enterpriseTemplateBlockLabels[block.type]}</strong>
        </button>
        {onRemove ? (
          <button
            type="button"
            className="template-structure-remove"
            aria-label={`删除${block.title || enterpriseTemplateBlockLabels[block.type]}板块`}
            title="删除板块"
            disabled={busy}
            onClick={onRemove}
          >
            <Delete24Regular aria-hidden="true" />
          </button>
        ) : null}
      </div>
    </li>
  );
}

function validateImage(file: File) {
  if (!CARD_IMAGE_TYPES.has(file.type)) {
    return new ApiError("仅支持 PNG、JPEG 或 WebP 图片。", {
      code: "CARD_ASSET_UNSUPPORTED_TYPE",
    });
  }
  if (file.size > MAX_CARD_IMAGE_BYTES) {
    return new ApiError("图片不能超过 5 MiB。", {
      code: "CARD_ASSET_TOO_LARGE",
    });
  }
  return undefined;
}

type EnterpriseTemplateEditorProps = {
  card?: ManagedCard;
  defaultKind?: ManagedCard["cardKind"];
  creationDraft?: {
    cardKind: ManagedCard["cardKind"];
    sourceCardId?: string;
    identityPreview: {
      displayName: string;
      title: string;
      avatarUrl?: string;
    };
  };
  open: boolean;
  onClose: () => void;
  onEditBasicSettings: (card: ManagedCard) => void;
  onRequestPublish: (card: ManagedCard) => void | Promise<void>;
  onSaved: (card?: ManagedCard) => void;
  onDraftConfirm?: (document: {
    schemaVersion: 1;
    themeKey: EnterpriseTemplateThemeKey;
    pageBackground?: EnterpriseTemplateBlockBackground;
    pageTextTone?: "auto" | "light" | "dark";
    blocks: EnterpriseTemplateBlock[];
  }) => void | Promise<void>;
  dataSource?: EnterpriseTemplateEditorDataSource;
};

export type EnterpriseTemplateEditorDataSource = Pick<
  typeof adminApi,
  | "getEnterpriseTemplate"
  | "getCardComposerDefault"
  | "listProducts"
  | "listCaseStudies"
  | "getCompanyProfile"
  | "listSelectableFaqDocuments"
  | "uploadCardAsset"
  | "updateEnterpriseTemplate"
  | "updateCardComposerDefault"
>;

export function EnterpriseTemplateEditor({
  card,
  defaultKind,
  creationDraft,
  open,
  onClose,
  onEditBasicSettings,
  onRequestPublish,
  onSaved,
  onDraftConfirm,
  dataSource = adminApi,
}: EnterpriseTemplateEditorProps) {
  const [blocks, setBlocks] = useState<EnterpriseTemplateBlock[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [cases, setCases] = useState<CaseStudy[]>([]);
  const [selectableFaqs, setSelectableFaqs] = useState<SelectableFaqDocument[]>([]);
  const [company, setCompany] = useState<CompanyProfile>();
  const [version, setVersion] = useState<number>();
  const [themeKey, setThemeKey] = useState<EnterpriseTemplateThemeKey>("brand");
  const [pageBackground, setPageBackground] = useState<EnterpriseTemplateBlockBackground>();
  const [pageTextTone, setPageTextTone] = useState<"auto" | "light" | "dark">("auto");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploadingKey, setUploadingKey] = useState<string>();
  const [dirty, setDirty] = useState(false);
  const [savedNotice, setSavedNotice] = useState<string>();
  const [error, setError] = useState<ApiError>();
  const [previewMode, setPreviewMode] = useState<"draft" | "published">("draft");
  const [selectedBlockId, setSelectedBlockId] = useState<string>();
  const [removeTarget, setRemoveTarget] = useState<EnterpriseTemplateBlock>();
  const [publishTarget, setPublishTarget] = useState<ManagedCard>();
  const [publishing, setPublishing] = useState(false);
  const [publishError, setPublishError] = useState<ApiError>();
  const [mobilePane, setMobilePane] = useState<"structure" | "preview" | "content">("structure");
  const galleryInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const coverInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const backgroundInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const contentImageInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const pageBackgroundInputRef = useRef<HTMLInputElement | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  useEffect(() => {
    if (!open || (!card && !defaultKind && !creationDraft)) return;
    let active = true;
    setLoading(true);
    setError(undefined);
    setSavedNotice(undefined);
    setDirty(false);
    setPublishTarget(undefined);
    setPublishError(undefined);
    void Promise.all([
      card
        ? dataSource.getEnterpriseTemplate(card.id)
        : creationDraft?.sourceCardId
          ? dataSource.getEnterpriseTemplate(creationDraft.sourceCardId)
          : dataSource.getCardComposerDefault(
              creationDraft?.cardKind ?? defaultKind as ManagedCard["cardKind"],
            ),
      dataSource.listProducts(),
      dataSource.listCaseStudies(),
      dataSource.getCompanyProfile(),
      dataSource.listSelectableFaqDocuments(),
    ])
      .then(([template, productResult, caseResult, companyProfile, faqResult]) => {
        if (!active) return;
        const document = "draft" in template ? template.draft : template.document;
        setBlocks(document.blocks);
        setVersion(template.version);
        setThemeKey(document.themeKey);
        setPageBackground(document.pageBackground);
        setPageTextTone(document.pageTextTone ?? "auto");
        setProducts(productResult);
        setCases(caseResult);
        setCompany(companyProfile);
        setSelectableFaqs(faqResult);
        setSelectedBlockId((current) => (
          document.blocks.some((block) => block.id === current)
            ? current
            : document.blocks[0]?.id
        ));
        setPreviewMode(card?.status === "published" && card.shareUrl ? "published" : "draft");
      })
      .catch((cause) => {
        if (active) {
          setError(toApiError(cause, "读取企业模板失败。", "TEMPLATE_LOAD_FAILED"));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [card, creationDraft, dataSource, defaultKind, open]);

  const mutateBlocks = (
    updater: (current: EnterpriseTemplateBlock[]) => EnterpriseTemplateBlock[],
  ) => {
    setBlocks((current) => normalizeEnterpriseTemplateBlockOrder(updater(current)));
    setPreviewMode("draft");
    setDirty(true);
    setSavedNotice(undefined);
    setError(undefined);
  };

  const updateBlock = (index: number, patch: Partial<EnterpriseTemplateBlock>) => {
    mutateBlocks((current) =>
      current.map((block, position) =>
        position === index ? { ...block, ...patch } : block,
      ),
    );
  };

  const updatePageAppearance = (
    background: EnterpriseTemplateBlockBackground | undefined,
    textTone = pageTextTone,
  ) => {
    setPageBackground(background);
    setPageTextTone(background ? textTone : "auto");
    setPreviewMode("draft");
    setDirty(true);
    setSavedNotice(undefined);
    setError(undefined);
  };

  const moveBlock = (index: number, direction: -1 | 1) => {
    mutateBlocks((current) => moveEnterpriseTemplateBlock(current, index, direction));
  };

  const moveBlockById = (activeId: string, overId: string) => {
    if (activeId === overId) return;
    mutateBlocks((current) => {
      const from = current.findIndex((block) => block.id === activeId);
      const to = current.findIndex((block) => block.id === overId);
      return from < 0 || to < 0 ? current : arrayMove(current, from, to);
    });
  };

  const handleStructureDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    moveBlockById(String(active.id), String(over.id));
  };

  const showMobilePane = (
    pane: "structure" | "preview" | "content",
    targetId: string,
  ) => {
    setMobilePane(pane);
    document.getElementById(targetId)?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
      inline: "start",
    });
  };

  const duplicateBlock = (index: number) => {
    let duplicatedId: string | undefined;
    mutateBlocks((current) => {
      const source = current[index];
      if (!source || current.length >= 24) return current;
      const duplicate = { ...source, id: nextBlockId(source.type) };
      duplicatedId = duplicate.id;
      return [...current.slice(0, index + 1), duplicate, ...current.slice(index + 1)];
    });
    if (duplicatedId) setSelectedBlockId(duplicatedId);
  };

  const removeBlock = (index: number) => {
    const current = blocks[index];
    if (!current || current.type === "identity") return;
    const fallback = blocks[index + 1]?.id ?? blocks[index - 1]?.id;
    mutateBlocks((items) => items.filter((block) => block.id !== current.id));
    setSelectedBlockId(fallback);
  };

  const confirmRemoveBlock = () => {
    if (!removeTarget) return;
    const index = blocks.findIndex((block) => block.id === removeTarget.id);
    if (index >= 0) removeBlock(index);
    setRemoveTarget(undefined);
  };

  const handleBlockKeyDown = (
    event: KeyboardEvent<HTMLElement>,
    index: number,
  ) => {
    if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
    event.preventDefault();
    moveBlock(index, event.key === "ArrowUp" ? -1 : 1);
  };

  const uploadGalleryImages = async (
    index: number,
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const files = [...(event.target.files ?? [])];
    event.target.value = "";
    if (!files.length) return;
    const invalid = files.map(validateImage).find(Boolean);
    if (invalid) {
      setError(invalid);
      return;
    }
    const block = blocks[index];
    if (!block) return;
    if ((block.imageUrls?.length ?? 0) + files.length > 12) {
      setError(new ApiError("每个图片画廊最多 12 张图片。", { code: "TEMPLATE_IMAGE_LIMIT" }));
      return;
    }
    setUploadingKey(`${block.id}:gallery`);
    setError(undefined);
    try {
      const uploaded = [];
      for (const file of files) uploaded.push(await dataSource.uploadCardAsset(file));
      updateBlock(index, {
        imageUrls: [...(block.imageUrls ?? []), ...uploaded.map((item) => item.url)],
      });
    } catch (cause) {
      setError(toApiError(cause, "上传展示图片失败。", "TEMPLATE_IMAGE_UPLOAD_FAILED"));
    } finally {
      setUploadingKey(undefined);
    }
  };

  const uploadVideoCover = async (
    index: number,
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const invalid = validateImage(file);
    if (invalid) {
      setError(invalid);
      return;
    }
    const block = blocks[index];
    if (!block) return;
    setUploadingKey(`${block.id}:cover`);
    setError(undefined);
    try {
      const uploaded = await dataSource.uploadCardAsset(file);
      updateBlock(index, { videoCoverUrl: uploaded.url });
    } catch (cause) {
      setError(toApiError(cause, "上传视频封面失败。", "TEMPLATE_COVER_UPLOAD_FAILED"));
    } finally {
      setUploadingKey(undefined);
    }
  };

  const uploadBackgroundImage = async (
    index: number,
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const invalid = validateImage(file);
    if (invalid) {
      setError(invalid);
      return;
    }
    const block = blocks[index];
    if (!block) return;
    setUploadingKey(`${block.id}:background`);
    setError(undefined);
    try {
      const uploaded = await dataSource.uploadCardAsset(file);
      updateBlock(index, {
        background: {
          kind: "image",
          imageUrl: uploaded.url,
          color: block.background?.color ?? "#eef3f4",
          fit: block.background?.imageUrl ? block.background.fit ?? "cover" : "contain",
          positionX: block.background?.positionX ?? 50,
          positionY: block.background?.positionY ?? 50,
          overlayColor: block.background?.overlayColor ?? "#000000",
          overlayOpacity: block.background?.overlayOpacity ?? 0.42,
        },
      });
    } catch (cause) {
      setError(toApiError(cause, "上传板块背景失败。", "TEMPLATE_BACKGROUND_UPLOAD_FAILED"));
    } finally {
      setUploadingKey(undefined);
    }
  };

  const uploadContentImage = async (
    index: number,
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const invalid = validateImage(file);
    if (invalid) {
      setError(invalid);
      return;
    }
    const block = blocks[index];
    if (!block || block.type !== "rich_text") return;
    setUploadingKey(`${block.id}:content-image`);
    setError(undefined);
    try {
      const uploaded = await dataSource.uploadCardAsset(file);
      updateBlock(index, {
        contentImage: {
          url: uploaded.url,
          alt: block.contentImage?.alt,
          placement: block.contentImage?.placement ?? "top",
          fit: block.contentImage?.fit ?? "cover",
          aspectRatio: block.contentImage?.aspectRatio ?? "wide",
          widthPercent: block.contentImage?.widthPercent ?? 100,
          positionX: block.contentImage?.positionX ?? 50,
          positionY: block.contentImage?.positionY ?? 50,
        },
      });
    } catch (cause) {
      setError(toApiError(cause, "上传内容图片失败。", "TEMPLATE_CONTENT_IMAGE_UPLOAD_FAILED"));
    } finally {
      setUploadingKey(undefined);
    }
  };

  const uploadPageBackground = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const invalid = validateImage(file);
    if (invalid) {
      setError(invalid);
      return;
    }
    setUploadingKey("page:background");
    setError(undefined);
    try {
      const uploaded = await dataSource.uploadCardAsset(file);
      updatePageAppearance({
        kind: "image",
        imageUrl: uploaded.url,
        color: pageBackground?.color ?? "#eef3f4",
        fit: pageBackground?.imageUrl ? pageBackground.fit ?? "cover" : "contain",
        positionX: pageBackground?.positionX ?? 50,
        positionY: pageBackground?.positionY ?? 50,
        overlayColor: pageBackground?.overlayColor ?? "#000000",
        overlayOpacity: pageBackground?.overlayOpacity ?? 0.42,
      });
    } catch (cause) {
      setError(toApiError(cause, "上传整体背景失败。", "TEMPLATE_PAGE_BACKGROUND_UPLOAD_FAILED"));
    } finally {
      setUploadingKey(undefined);
    }
  };

  const persistDraft = async (
    nextBlocks: EnterpriseTemplateBlock[],
    savedNotice: string,
  ) => {
    if (creationDraft || (!card && !defaultKind) || !version || saving) return undefined;
    setSaving(true);
    setError(undefined);
    try {
      const template = card
        ? await dataSource.updateEnterpriseTemplate(card.id, version, themeKey, nextBlocks, pageBackground, pageTextTone)
        : await dataSource.updateCardComposerDefault(
            defaultKind as ManagedCard["cardKind"], version, themeKey, nextBlocks, pageBackground, pageTextTone,
          );
      const document = "draft" in template ? template.draft : template.document;
      setBlocks(document.blocks);
      setVersion(template.version);
      setThemeKey(document.themeKey);
      setPageBackground(document.pageBackground);
      setPageTextTone(document.pageTextTone ?? "auto");
      setDirty(false);
      setSavedNotice(savedNotice);
      const updatedCard = card ? { ...card, version: template.version } : undefined;
      onSaved(updatedCard);
      return updatedCard;
    } catch (cause) {
      setError(toApiError(cause, "保存企业模板失败。", "TEMPLATE_SAVE_FAILED"));
      return undefined;
    } finally {
      setSaving(false);
    }
  };

  const saveDraft = async () => persistDraft(
    blocks,
    card
      ? "草稿已保存，公开页仍保持上一次发布内容。"
      : "默认配置已保存；之后新建的同类名片会自动使用它。",
  );

  const confirmCreationDraft = async () => {
    if (!creationDraft || !onDraftConfirm || saving || !draftValid) return;
    setSaving(true);
    setError(undefined);
    try {
      await onDraftConfirm({
        schemaVersion: 1,
        themeKey,
        pageBackground,
        pageTextTone,
        blocks: normalizeEnterpriseTemplateBlockOrder(blocks),
      });
      onClose();
    } catch (cause) {
      setError(toApiError(cause, "创建名片失败，请检查填写内容后重试。", "CARD_CREATE_FAILED"));
    } finally {
      setSaving(false);
    }
  };

  const addLibraryBlock = async (type: EnterpriseTemplateBlockType) => {
    if (busy || blocks.length >= 24) return;
    const nextBlock = createEnterpriseTemplateBlock(type);
    const nextBlocks = normalizeEnterpriseTemplateBlockOrder([...blocks, nextBlock]);
    setBlocks(nextBlocks);
    setSelectedBlockId(nextBlock.id);
    setPreviewMode("draft");
    setDirty(true);
    setSavedNotice(undefined);
    setError(undefined);
    const label = enterpriseTemplateBlockLabels[type];
    if (creationDraft) {
      setSavedNotice(`${label}已加入本次名片设计；确认创建前不会写入后台。`);
      return;
    }
    await persistDraft(
      nextBlocks,
      `${label}已加入草稿。请补齐内容后再发布。`,
    );
  };

  const requestPublish = async () => {
    if (!card || !version || !draftValid || !publishReady || saving) return;
    if (dirty) {
      const updatedCard = await persistDraft(
        blocks,
        "草稿已保存，可以确认发布。",
      );
      if (updatedCard) {
        setPublishError(undefined);
        setPublishTarget(updatedCard);
      }
      return;
    }
    setPublishError(undefined);
    setPublishTarget({ ...card, version });
  };

  const confirmPublish = async () => {
    if (!publishTarget || publishing) return;
    setPublishing(true);
    setPublishError(undefined);
    try {
      await onRequestPublish(publishTarget);
      setPublishTarget(undefined);
      setSavedNotice("名片已发布，公开页现在使用本次确认的内容。");
    } catch (cause) {
      setPublishError(toApiError(cause, "发布名片失败。", "CARD_PUBLISH_FAILED"));
    } finally {
      setPublishing(false);
    }
  };

  const publishedProducts = products.filter((item) => item.status === "published");
  const publishedCases = cases.filter((item) => item.status === "published");
  const publishChecks = card?.cardKind === "enterprise"
    ? getEnterpriseTemplatePublishChecks(card, blocks, company, selectableFaqs)
    : [];
  const blockIssues = blocks.map((block) => getEnterpriseTemplateBlockIssue(block, selectableFaqs));
  const draftValid = blockIssues.every((issue) => !issue);
  const publishReady = draftValid && publishChecks.every((item) => item.ready);
  const busy = loading || saving || Boolean(uploadingKey);
  const effectiveCompanySummary = card
    ? card.title.trim() && card.title.trim() !== card.displayName.trim()
      ? card.title
      : company?.summary || card.title
    : company?.summary || "";
  const effectiveKind = card?.cardKind ?? creationDraft?.cardKind ?? defaultKind ?? "enterprise";
  const effectiveDisplayName = card?.displayName
    || creationDraft?.identityPreview.displayName
    || company?.name
    || "名片主体";
  const effectiveTitle = card?.title
    || creationDraft?.identityPreview.title
    || effectiveCompanySummary
    || "业务定位或职位信息";
  const effectiveAvatarUrl = card?.avatarUrl
    || creationDraft?.identityPreview.avatarUrl
    || company?.logoUrl;
  const selectedIndex = blocks.findIndex((block) => block.id === selectedBlockId);
  const selectedBlock = selectedIndex >= 0 ? blocks[selectedIndex] : blocks[0];
  const selectedIssue = selectedIndex >= 0 ? blockIssues[selectedIndex] : blockIssues[0];

  const editorTitle = creationDraft
    ? `设计${creationDraft.cardKind === "employee" ? "员工" : "企业"}名片`
    : card
      ? `编辑${card.cardKind === "enterprise" ? "企业" : "员工"}名片内容`
      : `编辑${defaultKind === "employee" ? "员工" : "企业"}名片默认配置`;

  const editorDescription = creationDraft
    ? "先完成页面设计，再一次性创建名片；取消不会产生空名片或写入草稿。"
    : card
      ? "基础资料保持与企业或员工身份一致；页面结构保存为草稿，发布确认后才替换公开页。"
      : "默认配置只保存页面结构和展示规则，之后新建名片会自动绑定最新企业或员工资料。";

  if (open) {
    return (
      <>
      <Dialog
        open
        onOpenChange={(_, data) => {
          if (!data.open && !busy) onClose();
        }}
      >
        <DialogSurface className="enterprise-template-dialog enterprise-template-dialog-v2">
          <DialogBody>
            <DialogTitle>
              <div className="template-composer-title">
                <span>{creationDraft ? "创建前设计" : card ? "页面编辑器" : "默认配置"}</span>
                <strong>{editorTitle}</strong>
              </div>
            </DialogTitle>
            <DialogContent className="template-composer-dialog-content">
              <div className="template-composer-context">
                <p>{editorDescription}</p>
                <div>
                  <span>{effectiveKind === "employee" ? "员工名片" : "企业名片"}</span>
                  <strong>{effectiveDisplayName}</strong>
                  {dirty ? <b>未保存</b> : <b className="is-saved">已同步</b>}
                </div>
              </div>
              <FormFeedback error={error} />
              {savedNotice ? <p className="template-save-notice" role="status">{savedNotice}</p> : null}

              {loading ? (
                <div className="template-loading template-composer-loading" role="status">
                  <Spinner size="small" />
                  <span>正在读取页面结构与真实业务数据…</span>
                </div>
              ) : (card || defaultKind || creationDraft) ? (
                <>
                  <nav className="template-mobile-pane-tabs" aria-label="编辑器区域切换">
                    <button
                      type="button"
                      aria-current={mobilePane === "structure" ? "page" : undefined}
                      onClick={() => showMobilePane("structure", "template-editor-structure")}
                    >结构</button>
                    <button
                      type="button"
                      aria-current={mobilePane === "preview" ? "page" : undefined}
                      onClick={() => showMobilePane("preview", "template-editor-preview")}
                    >画布</button>
                    <button
                      type="button"
                      aria-current={mobilePane === "content" ? "page" : undefined}
                      onClick={() => showMobilePane("content", "template-editor-content")}
                    >属性</button>
                  </nav>
                  <div className="enterprise-template-composer">
                  <aside
                    className="template-composer-pane template-structure-pane"
                    id="template-editor-structure"
                    aria-label="页面结构与模块库"
                  >
                    <header className="template-pane-heading">
                      <div><span>结构</span><h2>页面与模块</h2></div>
                      <strong>{blocks.length}/24</strong>
                    </header>
                    <p className="template-pane-hint">拖动手柄调整顺序；点击模块后，中间页面和右侧属性会同步选中。</p>

                    <TemplatePageSettings
                      background={pageBackground}
                      textTone={pageTextTone}
                      busy={busy}
                      uploading={uploadingKey === "page:background"}
                      inputRef={pageBackgroundInputRef}
                      onChange={updatePageAppearance}
                      onUpload={(event) => void uploadPageBackground(event)}
                    />

                    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleStructureDragEnd}>
                      <SortableContext items={blocks.map((block) => block.id)} strategy={verticalListSortingStrategy}>
                        <ol className="template-structure-list">
                          {blocks.map((block, index) => (
                            <SortableStructureItem
                              key={block.id}
                              block={block}
                              index={index}
                              busy={busy}
                              selected={block.id === selectedBlock?.id}
                              onSelect={() => setSelectedBlockId(block.id)}
                              onRemove={block.type === "identity" ? undefined : () => setRemoveTarget(block)}
                            />
                          ))}
                        </ol>
                      </SortableContext>
                    </DndContext>

                    <section className="template-module-library template-module-library-v2" aria-labelledby="template-module-library-title">
                      <div>
                        <strong id="template-module-library-title">添加模块</strong>
                        <span>模块加入当前页面底部，随后可直接拖动到目标位置。</span>
                      </div>
                      <div className="template-module-library-actions">
                        {Object.entries(enterpriseTemplateBlockLabels)
                          .filter(([value]) => value !== "identity")
                          .map(([value, label]) => (
                            <button
                              key={value}
                              type="button"
                              disabled={busy || blocks.length >= 24}
                              onClick={() => void addLibraryBlock(value as EnterpriseTemplateBlockType)}
                            >
                              <Add24Regular aria-hidden="true" />
                              <span>{label}</span>
                            </button>
                          ))}
                      </div>
                    </section>

                    <section className="template-identity-source-summary">
                      {effectiveAvatarUrl ? <img src={resolveApiResourceUrl(effectiveAvatarUrl)} alt="名片头像" /> : <i>{effectiveDisplayName.slice(0, 1)}</i>}
                      <div><strong>{effectiveDisplayName}</strong><span>{effectiveTitle}</span></div>
                      {card ? (
                        <Button appearance="subtle" size="small" icon={<Edit24Regular />} onClick={() => onEditBasicSettings(card)}>
                          基础资料
                        </Button>
                      ) : null}
                    </section>
                  </aside>

                  <main
                    className="template-composer-pane template-canvas-pane"
                    id="template-editor-preview"
                    aria-label="名片实时画布"
                  >
                    <header className="template-pane-heading template-canvas-heading">
                      <div>
                        <span>{previewMode === "published" ? "线上版本" : "实时草稿"}</span>
                        <h2>实际名片页面</h2>
                      </div>
                      <div className="template-preview-modes" role="tablist" aria-label="名片预览模式">
                        <button
                          type="button"
                          role="tab"
                          aria-selected={previewMode === "draft"}
                          className={previewMode === "draft" ? "is-active" : undefined}
                          onClick={() => setPreviewMode("draft")}
                        >草稿</button>
                        {card?.shareUrl ? (
                          <button
                            type="button"
                            role="tab"
                            aria-selected={previewMode === "published"}
                            className={previewMode === "published" ? "is-active" : undefined}
                            onClick={() => setPreviewMode("published")}
                          >线上</button>
                        ) : null}
                      </div>
                    </header>
                    <p className="template-pane-hint">这是与访客端共用的页面组件。可滚动、展开 FAQ，并从专用手柄拖动模块。</p>

                    <div className="template-phone-frame template-phone-frame-v2">
                      <div className="template-phone-screen">
                        {previewMode === "published" && card?.shareUrl ? (
                          <iframe
                            className="template-public-page-frame"
                            src={card.shareUrl}
                            title="实际公开名片页面"
                            allow="clipboard-write; fullscreen"
                          />
                        ) : (
                          <TemplateCanvas
                            blocks={blocks}
                            pageBackground={pageBackground}
                            pageTextTone={pageTextTone}
                            products={publishedProducts}
                            cases={publishedCases}
                            faqItems={selectableFaqs}
                            identity={{
                              cardKind: effectiveKind,
                              displayName: effectiveDisplayName,
                              title: effectiveTitle,
                              avatarUrl: effectiveAvatarUrl,
                              companyName: company?.name,
                              summary: company?.summary,
                              positioning: effectiveCompanySummary || company?.summary,
                            }}
                            selectedBlockId={selectedBlock?.id}
                            onSelectBlock={setSelectedBlockId}
                            onMoveBlock={moveBlockById}
                          />
                        )}
                      </div>
                    </div>
                    {card?.shareUrl ? (
                      <a className="template-open-public-link" href={card.shareUrl} target="_blank" rel="noreferrer">在新窗口打开公开页</a>
                    ) : null}
                  </main>

                  <aside
                    className="template-composer-pane template-inspector-pane"
                    id="template-editor-content"
                    aria-label="区块属性"
                  >
                    <header className="template-pane-heading">
                      <div><span>属性</span><h2>{selectedBlock ? enterpriseTemplateBlockLabels[selectedBlock.type] : "选择模块"}</h2></div>
                    </header>
                    <p className="template-pane-hint">只编辑当前选中的模块，页面变化会实时出现在中间。</p>
                    {selectedBlock ? (
                      <TemplateBlockInspector
                        block={selectedBlock}
                        index={selectedIndex >= 0 ? selectedIndex : 0}
                        blockCount={blocks.length}
                        busy={busy}
                        issue={selectedIssue}
                        uploadingKey={uploadingKey}
                        products={publishedProducts}
                        cases={publishedCases}
                        selectableFaqs={selectableFaqs}
                        labels={enterpriseTemplateBlockLabels}
                        galleryInputRefs={galleryInputRefs}
                        coverInputRefs={coverInputRefs}
                        backgroundInputRefs={backgroundInputRefs}
                        contentImageInputRefs={contentImageInputRefs}
                        onUpdate={(patch) => updateBlock(selectedIndex >= 0 ? selectedIndex : 0, patch)}
                        onMove={(direction) => moveBlock(selectedIndex >= 0 ? selectedIndex : 0, direction)}
                        onDuplicate={() => duplicateBlock(selectedIndex >= 0 ? selectedIndex : 0)}
                        onRemove={() => selectedBlock && setRemoveTarget(selectedBlock)}
                        onGalleryUpload={(event) => void uploadGalleryImages(selectedIndex >= 0 ? selectedIndex : 0, event)}
                        onCoverUpload={(event) => void uploadVideoCover(selectedIndex >= 0 ? selectedIndex : 0, event)}
                        onBackgroundUpload={(event) => void uploadBackgroundImage(selectedIndex >= 0 ? selectedIndex : 0, event)}
                        onContentImageUpload={(event) => void uploadContentImage(selectedIndex >= 0 ? selectedIndex : 0, event)}
                      />
                    ) : <p className="template-inspector-empty">请从左侧结构或中间页面选择一个模块。</p>}

                    {card?.cardKind === "enterprise" ? (
                      <section className="template-publish-checks template-publish-checks-v2" aria-labelledby="publish-check-title">
                        <h2 id="publish-check-title">发布检查</h2>
                        <ul>
                          {publishChecks.map((item) => (
                            <li className={item.ready ? "is-ready" : "is-missing"} key={item.key}>
                              <span aria-hidden="true">{item.ready ? "✓" : "!"}</span>
                              {item.label}
                            </li>
                          ))}
                        </ul>
                      </section>
                    ) : null}
                  </aside>
                  </div>
                </>
              ) : null}
            </DialogContent>
            <DialogActions className="enterprise-template-actions enterprise-template-actions-v2">
              <div className="template-action-status" aria-live="polite">
                {dirty ? "页面有未保存修改" : creationDraft ? "创建前不会写入后台" : "当前页面已同步"}
              </div>
              <Button appearance="secondary" onClick={onClose} disabled={busy}>{creationDraft ? "取消创建" : "关闭"}</Button>
              {creationDraft ? (
                <Button
                  appearance="primary"
                  icon={<Send24Regular />}
                  onClick={() => void confirmCreationDraft()}
                  disabled={busy || !draftValid || !onDraftConfirm}
                >{saving ? "创建中…" : "使用此设计创建名片"}</Button>
              ) : (
                <>
                  <Button
                    appearance="secondary"
                    icon={<Save24Regular />}
                    onClick={() => void saveDraft()}
                    disabled={busy || !dirty}
                  >{saving ? "保存中…" : card ? "保存草稿" : "保存默认配置"}</Button>
                  <Button
                    appearance="primary"
                    icon={<Send24Regular />}
                    onClick={() => void requestPublish()}
                    disabled={busy || !publishReady || !card}
                  >{dirty ? "保存并进入发布确认" : "进入发布确认"}</Button>
                </>
              )}
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
      <ActionConfirmDialog
        open={Boolean(publishTarget)}
        title="确认发布名片"
        description="发布后，公开链接会立即使用当前已保存的页面内容。"
        confirmLabel="确认发布"
        pendingLabel="正在发布"
        pending={publishing}
        error={publishError}
        detail={publishTarget ? (
          <div className="publish-target">
            <strong>{publishTarget.displayName || "未命名名片"}</strong>
            <span>待发布版本：{publishTarget.version}</span>
            <ul className="publish-checklist-summary">
              <li>企业名称、业务定位和 Logo 已复核</li>
              <li>当前草稿中的区块、图片、视频和案例将冻结为公开快照</li>
              <li>确认后公开页会立即更新</li>
            </ul>
          </div>
        ) : undefined}
        onCancel={() => {
          setPublishTarget(undefined);
          setPublishError(undefined);
        }}
        onConfirm={() => void confirmPublish()}
      />
      <ActionConfirmDialog
        open={Boolean(removeTarget)}
        title="删除名片板块"
        description="该板块会从当前草稿中移除。保存草稿后删除才会写入后台，已经发布的名片在再次发布前不会变化。"
        confirmLabel="确认删除"
        pendingLabel="正在删除"
        pending={false}
        destructive
        detail={removeTarget ? (
          <div className="publish-target">
            <strong>{removeTarget.title || enterpriseTemplateBlockLabels[removeTarget.type]}</strong>
            <span>{enterpriseTemplateBlockLabels[removeTarget.type]}</span>
          </div>
        ) : undefined}
        onCancel={() => setRemoveTarget(undefined)}
        onConfirm={confirmRemoveBlock}
      />
      </>
    );
  }

  return null;
}

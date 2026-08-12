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
  ArrowClockwise24Regular,
  ArrowRedo24Regular,
  ArrowUndo24Regular,
  Edit24Regular,
  Eye24Regular,
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
import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, KeyboardEvent } from "react";
import { StudioEditorShell, StudioIcon, StudioModuleRow, type StudioIconName } from "@cf/card-page-renderer";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type {
  CaseStudy,
  CompanyProfile,
  EnterpriseTemplateActionItem,
  EnterpriseTemplateBlock,
  EnterpriseTemplateBlockType,
  EnterpriseTemplateThemeKey,
  IdentityContactField,
  ManagedCardInput,
  ManagedCard,
  Product,
  SelectableFaqDocument,
} from "../api/types";
import { resolveApiResourceUrl } from "../lib/resourceUrl";
import { TemplateBlockInspector } from "./enterprise-template/TemplateBlockInspector";
import { CardStudioEditorSurface } from "./enterprise-template/CardStudioEditorSurface";
import { TemplateCanvas } from "./enterprise-template/TemplateCanvas";
import { FormFeedback } from "./FormFeedback";

const MAX_CARD_IMAGE_BYTES = 5 * 1024 * 1024;
const CARD_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_CARD_VIDEO_BYTES = 50 * 1024 * 1024;
const CARD_VIDEO_TYPES = new Set(["video/mp4", "video/webm"]);
const LEGACY_OVERVIEW_DEFAULT = "把企业的业务经验变成可复用的 AI 能力，让销售更懂客户，让服务更快抵达。";

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
  action_collection: "行动入口",
  ai_assistant: "AI 助手入口",
};

const enterpriseTemplateBlockDescriptions: Partial<Record<EnterpriseTemplateBlockType, string>> = {
  rich_text: "标题、正文与介绍内容",
  business_collection: "引用真实业务库",
  image_gallery: "上传图片并编辑角标",
  video_link: "视频封面与播放地址",
  case_collection: "引用真实案例库",
  trust_panel: "企业认证与公开资料",
  faq: "引用已发布问答库",
  cta: "单个主要行动按钮",
  action_collection: "多个页面或联系入口",
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
    showTitle: type !== "identity",
    directoryEnabled: true,
    sortOrder: 0,
    title: enterpriseTemplateBlockLabels[type],
    ...(type === "faq" ? { faqMode: "all_published" as const, faqDocumentIds: [] } : {}),
    ...(type === "identity" ? {
      layoutVariant: "horizontal" as const,
      presentation: {
        identityLayout: "horizontal" as const,
        background: {
          fit: "cover" as const,
          position: "center" as const,
          aspectRatio: "auto" as const,
          focalX: 50,
          focalY: 50,
          scale: 1,
          opacity: 0.28,
          overlay: "light" as const,
        },
      },
    } : {}),
    ...(["business_collection", "case_collection", "image_gallery"].includes(type) ? {
      layoutVariant: "auto" as const,
      itemLimit: 4,
    } : {}),
    ...(type === "action_collection" ? {
      layoutVariant: "grid" as const,
      itemLimit: 4,
      actionItems: [],
    } : {}),
  };
}

function isActionTargetValid(item: EnterpriseTemplateActionItem) {
  const target = item.targetValue.trim();
  if (!item.title.trim() || !target) return false;
  if (item.targetType === "external_url") return isHttpsUrl(target);
  if (item.targetType === "internal_path") return /^\/(?!\/)/.test(target);
  if (item.targetType === "phone") {
    const phone = target.replace(/^tel:/i, "");
    return /^\+?[0-9][0-9()\-\s]{4,24}$/.test(phone);
  }
  return target.length >= 2;
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

function isPlayableVideoUrl(value?: string) {
  const target = value?.trim();
  return Boolean(target && (
    isHttpsUrl(target)
    || /^\/api\/v1\/public\/card-video-assets\//.test(target)
  ));
}

export function getEnterpriseTemplateBlockIssue(
  block: EnterpriseTemplateBlock,
  selectableFaqs?: SelectableFaqDocument[],
) {
  if (!block.visible) return undefined;

  switch (block.type) {
    case "image_gallery":
      return block.imageUrls?.length ? undefined : "请至少上传一张图片。";
    case "video_link":
      if (!isPlayableVideoUrl(block.videoUrl)) return "请上传视频或输入有效的 HTTPS 视频地址。";
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
    case "action_collection":
      if (!block.actionItems?.length) return "请至少添加一个行动入口。";
      return block.actionItems.every(isActionTargetValid)
        ? undefined
        : "请补齐入口标题，并检查跳转目标格式。";
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
      (block.type === "action_collection" && block.actionItems?.some(isActionTargetValid)) ||
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
  displayTitle,
  index,
  busy,
  selected,
  onSelect,
}: {
  block: EnterpriseTemplateBlock;
  displayTitle: string;
  index: number;
  busy: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  const blockSourceLabels: Partial<Record<EnterpriseTemplateBlockType, string>> = {
    identity: "企业 / 员工资料",
    rich_text: "名片内容",
    business_collection: "真实业务库",
    image_gallery: "企业素材库",
    video_link: "视频链接",
    case_collection: "真实案例库",
    trust_panel: "企业认证资料",
    faq: "真实问答库",
    cta: "行动链接",
    action_collection: "行动入口",
  };
  const blockIcons: Partial<Record<EnterpriseTemplateBlockType, StudioIconName>> = {
    identity: "user",
    rich_text: "user",
    business_collection: "briefcase",
    image_gallery: "image",
    video_link: "play",
    case_collection: "building",
    trust_panel: "check",
    faq: "help",
    cta: "external",
    action_collection: "external",
    ai_assistant: "message",
  };
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: block.id,
    disabled: busy,
  });
  return <li ref={setNodeRef} className={`${isDragging ? "is-dragging" : ""}${selected ? " is-selected" : ""}`.trim() || undefined} style={{ transform: CSS.Transform.toString(transform), transition }} data-row-id={block.id}>
    <StudioModuleRow
      title={displayTitle}
      ariaLabel={`${String(index + 1).padStart(2, "0")} ${displayTitle}`}
      source={blockSourceLabels[block.type] || "页面内容"}
      icon={blockIcons[block.type] || "grid"}
      selected={selected}
      required={block.type === "identity"}
      hidden={block.visible === false}
      onSelect={onSelect}
      dragHandle={<button type="button" className="mini-button" aria-label={`拖动${enterpriseTemplateBlockLabels[block.type]}调整位置`} disabled={busy} {...attributes} {...listeners}><StudioIcon name="grip" /></button>}
    />
  </li>;
}

function templateBlockDisplayTitle(
  block: EnterpriseTemplateBlock,
  cardKind: "enterprise" | "employee",
) {
  const title = block.title || enterpriseTemplateBlockLabels[block.type];
  if (cardKind === "employee" && block.type === "rich_text" && title === "企业介绍") {
    return "个人介绍";
  }
  return title;
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

function validateVideo(file: File) {
  if (!CARD_VIDEO_TYPES.has(file.type)) {
    return new ApiError("仅支持 MP4 或 WebM 视频。", {
      code: "CARD_VIDEO_ASSET_UNSUPPORTED_TYPE",
    });
  }
  if (file.size > MAX_CARD_VIDEO_BYTES) {
    return new ApiError("视频不能超过 50 MiB。", {
      code: "CARD_VIDEO_ASSET_TOO_LARGE",
    });
  }
  return undefined;
}

function normalizeIdentityContactFields(fields: IdentityContactField[]) {
  return fields
    .map((field) => ({
      ...field,
      label: field.label.trim(),
      value: field.value.trim(),
      href: field.href?.trim() || undefined,
    }))
    .filter((field) => Boolean(field.value));
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
      identityTitles: string[];
      contactFields: IdentityContactField[];
    };
  };
  open: boolean;
  onClose: () => void;
  onEditBasicSettings: (card: ManagedCard) => void;
  onRequestPublish: (card: ManagedCard) => void;
  onSaved: (card?: ManagedCard) => void;
  onDraftConfirm?: (document: {
    schemaVersion: 1;
    themeKey: EnterpriseTemplateThemeKey;
    blocks: EnterpriseTemplateBlock[];
  }, identity: { identityTitles: string[]; contactFields: IdentityContactField[] }) => void | Promise<void>;
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
  | "uploadCardVideoAsset"
  | "updateManagedCard"
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
  const blocksRef = useRef<EnterpriseTemplateBlock[]>([]);
  const [canvasBlocks, setCanvasBlocks] = useState<EnterpriseTemplateBlock[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [cases, setCases] = useState<CaseStudy[]>([]);
  const [selectableFaqs, setSelectableFaqs] = useState<SelectableFaqDocument[]>([]);
  const [company, setCompany] = useState<CompanyProfile>();
  const [version, setVersion] = useState<number>();
  const [themeKey, setThemeKey] = useState<EnterpriseTemplateThemeKey>("brand");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploadingKey, setUploadingKey] = useState<string>();
  const [dirty, setDirty] = useState(false);
  const [savedNotice, setSavedNotice] = useState<string>();
  const [error, setError] = useState<ApiError>();
  const [previewMode, setPreviewMode] = useState<"draft" | "published">("draft");
  const [previewDevice, setPreviewDevice] = useState<"mobile" | "wide">("mobile");
  const [structureTab, setStructureTab] = useState<"structure" | "library">("structure");
  const [mobilePane, setMobilePane] = useState<"structure" | "canvas" | "inspector">("canvas");
  const [tabletSidePane, setTabletSidePane] = useState<"structure" | "inspector">("structure");
  const [selectedBlockId, setSelectedBlockId] = useState<string>();
  const [identityTitles, setIdentityTitles] = useState<string[]>([]);
  const [identityContactFields, setIdentityContactFields] = useState<IdentityContactField[]>([]);
  const [identityDirty, setIdentityDirty] = useState(false);
  const [undoStack, setUndoStack] = useState<Array<{ blocks: EnterpriseTemplateBlock[]; themeKey: EnterpriseTemplateThemeKey }>>([]);
  const [redoStack, setRedoStack] = useState<Array<{ blocks: EnterpriseTemplateBlock[]; themeKey: EnterpriseTemplateThemeKey }>>([]);
  const galleryInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const videoInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const coverInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const backgroundInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const actionCoverInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const collectionCoverInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const canvasStageRef = useRef<HTMLDivElement | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const replaceBlocks = (next: EnterpriseTemplateBlock[]) => {
    blocksRef.current = next;
    setBlocks(next);
  };
  // Parent pages may recreate equivalent card/draft objects while the user is
  // typing. Reloading on object identity would replace every controlled input,
  // making clicks and keystrokes appear to flash and disappear.
  const editorSourceKey = card
    ? `card:${card.id}:${card.version}:${card.updatedAt ?? ""}:${JSON.stringify(card.identityTitles ?? [])}:${JSON.stringify(card.contactFields ?? [])}`
    : creationDraft
      ? `draft:${creationDraft.cardKind}:${creationDraft.sourceCardId ?? ""}:${JSON.stringify(creationDraft.identityPreview)}`
      : `default:${defaultKind ?? ""}`;

  useEffect(() => {
    if (!open || (!card && !defaultKind && !creationDraft)) return;
    let active = true;
    setLoading(true);
    setError(undefined);
    setSavedNotice(undefined);
    setDirty(false);
    setIdentityDirty(false);
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
        const normalizedBlocks = normalizeEnterpriseTemplateBlockOrder(
          document.blocks.filter((block) => block.type !== "ai_assistant"),
        );
        const upgradedLegacyOverview = normalizedBlocks.some((block) => (
          block.type === "rich_text" && block.title?.trim() === "概览" && !block.body?.trim()
        ));
        const editableBlocks = normalizedBlocks.map((block) => (
          block.type === "rich_text" && block.title?.trim() === "概览" && !block.body?.trim()
            ? { ...block, body: LEGACY_OVERVIEW_DEFAULT }
            : block
        ));
        const removedLegacyAiBlock = editableBlocks.length !== document.blocks.length;
        replaceBlocks(editableBlocks);
        setCanvasBlocks(editableBlocks);
        setUndoStack([]);
        setRedoStack([]);
        setVersion(template.version);
        setThemeKey(document.themeKey);
        setProducts(productResult);
        setCases(caseResult);
        setCompany(companyProfile);
        setIdentityTitles(card?.identityTitles ?? creationDraft?.identityPreview.identityTitles ?? []);
        setIdentityContactFields(normalizeIdentityContactFields(
          card?.contactFields ?? creationDraft?.identityPreview.contactFields ?? [],
        ));
        setSelectableFaqs(faqResult);
        setSelectedBlockId((current) => (
          editableBlocks.some((block) => block.id === current)
            ? current
            : editableBlocks[0]?.id
        ));
        if (removedLegacyAiBlock || upgradedLegacyOverview) {
          setDirty(true);
          setSavedNotice([
            removedLegacyAiBlock ? "已移除旧版 AI 助手区块" : "",
            upgradedLegacyOverview ? "已将旧版预览文案转为可编辑的真实内容" : "",
          ].filter(Boolean).join("；") + "。保存草稿后生效。");
        }
        // The editor must open on the current shared renderer. Published mode
        // is an explicit comparison target and may still show an older release.
        setPreviewMode("draft");
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
  }, [dataSource, editorSourceKey, open]);

  // Keep controlled fields responsive while a large, draggable public-page
  // preview is present. Rapid edits are coalesced into one near-real-time
  // canvas refresh instead of rebuilding the entire card for every keypress.
  useEffect(() => {
    const timer = window.setTimeout(() => setCanvasBlocks(blocks), 100);
    return () => window.clearTimeout(timer);
  }, [blocks]);

  const mutateBlocks = (
    updater: (current: EnterpriseTemplateBlock[]) => EnterpriseTemplateBlock[],
  ) => {
    const current = blocksRef.current;
    const next = normalizeEnterpriseTemplateBlockOrder(updater(current));
    if (next === current) return;
    blocksRef.current = next;
    setBlocks(next);
    setUndoStack((history) => [...history.slice(-23), { blocks: current, themeKey }]);
    setRedoStack([]);
    setPreviewMode("draft");
    setDirty(true);
    setSavedNotice(undefined);
    setError(undefined);
  };

  const changeTheme = (nextThemeKey: EnterpriseTemplateThemeKey) => {
    if (nextThemeKey === themeKey) return;
    setUndoStack((history) => [...history.slice(-23), { blocks, themeKey }]);
    setRedoStack([]);
    setThemeKey(nextThemeKey);
    setPreviewMode("draft");
    setDirty(true);
    setSavedNotice(undefined);
  };

  const undoChange = () => {
    const previous = undoStack.at(-1);
    if (!previous || busy) return;
    setUndoStack((history) => history.slice(0, -1));
    setRedoStack((history) => [...history.slice(-23), { blocks, themeKey }]);
    replaceBlocks(previous.blocks);
    setThemeKey(previous.themeKey);
    setPreviewMode("draft");
    setDirty(true);
    setSavedNotice("已撤销上一步修改；保存后才会写入草稿。");
  };

  const redoChange = () => {
    const next = redoStack.at(-1);
    if (!next || busy) return;
    setRedoStack((history) => history.slice(0, -1));
    setUndoStack((history) => [...history.slice(-23), { blocks, themeKey }]);
    replaceBlocks(next.blocks);
    setThemeKey(next.themeKey);
    setPreviewMode("draft");
    setDirty(true);
    setSavedNotice("已重做修改；保存后才会写入草稿。");
  };

  const updateBlock = (index: number, patch: Partial<EnterpriseTemplateBlock>) => {
    mutateBlocks((current) =>
      current.map((block, position) =>
        position === index ? { ...block, ...patch } : block,
      ),
    );
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
    const existingGalleryItems = block.galleryItems ?? (block.imageUrls ?? []).map((imageUrl, itemIndex) => ({
      id: `legacy-${itemIndex + 1}`,
      imageUrl,
      badgeMode: "title" as const,
      title: `工作记录 ${itemIndex + 1}`,
    }));
    if (existingGalleryItems.length + files.length > 12) {
      setError(new ApiError("每个图片画廊最多 12 张图片。", { code: "TEMPLATE_IMAGE_LIMIT" }));
      return;
    }
    setUploadingKey(`${block.id}:gallery`);
    setError(undefined);
    try {
      const uploaded = [];
      for (const file of files) uploaded.push(await dataSource.uploadCardAsset(file));
      const nextItems = [...existingGalleryItems, ...uploaded.map((item, uploadedIndex) => ({
        id: `gallery-${crypto.randomUUID()}`,
        imageUrl: item.url,
        title: files[uploadedIndex]?.name.replace(/\.[^.]+$/, "") || `工作记录 ${existingGalleryItems.length + uploadedIndex + 1}`,
        badgeMode: "title" as const,
      }))];
      updateBlock(index, {
        galleryItems: nextItems,
        imageUrls: nextItems.map((item) => item.imageUrl),
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

  const uploadVideoAsset = async (
    index: number,
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const invalid = validateVideo(file);
    if (invalid) {
      setError(invalid);
      return;
    }
    const block = blocks[index];
    if (!block || block.type !== "video_link") return;
    setUploadingKey(`${block.id}:video`);
    setError(undefined);
    try {
      const uploaded = await dataSource.uploadCardVideoAsset(file);
      updateBlock(index, { videoUrl: uploaded.url });
      setSavedNotice(`视频“${file.name}”已上传，保存页面后正式生效。`);
    } catch (cause) {
      setError(toApiError(cause, "上传视频失败。", "TEMPLATE_VIDEO_UPLOAD_FAILED"));
    } finally {
      setUploadingKey(undefined);
    }
  };

  const uploadIdentityBackground = async (
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
    if (!block || block.type !== "identity") return;
    setUploadingKey(`${block.id}:background`);
    setError(undefined);
    try {
      const uploaded = await dataSource.uploadCardAsset(file);
      updateBlock(index, {
        presentation: {
          ...block.presentation,
          identityLayout: block.presentation?.identityLayout ?? "horizontal",
          background: {
            fit: "cover",
            position: "center",
            aspectRatio: "auto",
            focalX: 50,
            focalY: 50,
            scale: 1,
            opacity: 0.28,
            overlay: "light",
            ...block.presentation?.background,
            assetUrl: uploaded.url,
          },
        },
      });
    } catch (cause) {
      setError(toApiError(cause, "上传基础名片背景失败。", "TEMPLATE_BACKGROUND_UPLOAD_FAILED"));
    } finally {
      setUploadingKey(undefined);
    }
  };

  const uploadActionCover = async (
    index: number,
    actionId: string,
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
    if (!block || block.type !== "action_collection") return;
    setUploadingKey(`${block.id}:action:${actionId}`);
    setError(undefined);
    try {
      const uploaded = await dataSource.uploadCardAsset(file);
      updateBlock(index, {
        actionItems: block.actionItems?.map((item) => (
          item.id === actionId ? { ...item, imageUrl: uploaded.url } : item
        )),
      });
    } catch (cause) {
      setError(toApiError(cause, "上传行动入口封面失败。", "TEMPLATE_ACTION_COVER_UPLOAD_FAILED"));
    } finally {
      setUploadingKey(undefined);
    }
  };

  const uploadCollectionCover = async (
    index: number,
    kind: "product" | "case",
    itemId: string,
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const invalid = validateImage(file);
    if (invalid) { setError(invalid); return; }
    const block = blocks[index];
    if (!block) return;
    setUploadingKey(`${block.id}:${kind}:${itemId}`);
    setError(undefined);
    try {
      const uploaded = await dataSource.uploadCardAsset(file);
      if (kind === "product") {
        const current = block.productOverrides?.find((item) => item.id === itemId);
        updateBlock(index, { productOverrides: [...(block.productOverrides ?? []).filter((item) => item.id !== itemId), { ...current, id: itemId, imageUrl: uploaded.url }] });
      } else {
        const current = block.caseOverrides?.find((item) => item.id === itemId);
        updateBlock(index, { caseOverrides: [...(block.caseOverrides ?? []).filter((item) => item.id !== itemId), { ...current, id: itemId, imageUrl: uploaded.url }] });
      }
    } catch (cause) {
      setError(toApiError(cause, "上传展示图片失败。", "TEMPLATE_COLLECTION_COVER_UPLOAD_FAILED"));
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
      let baseVersion = version;
      let savedCard = card;
      if (card && identityDirty) {
        const cardInput: ManagedCardInput = {
          cardKind: card.cardKind,
          ownerUserId: card.ownerUserId,
          displayName: card.displayName,
          title: card.title,
          avatarUrl: card.avatarUrl,
          assistantName: card.assistantName,
          welcomeMessage: card.welcomeMessage,
          suggestedQuestions: card.suggestedQuestions,
          policyVersions: card.policyVersions,
          identityTitles,
          contactFields: normalizeIdentityContactFields(identityContactFields),
          employeeContactVisibility: card.employeeContactVisibility ?? [],
        };
        savedCard = await dataSource.updateManagedCard(card.id, baseVersion, cardInput);
        baseVersion = savedCard.version;
      }
      const template = card
        ? await dataSource.updateEnterpriseTemplate(card.id, baseVersion, themeKey, nextBlocks)
        : await dataSource.updateCardComposerDefault(defaultKind as ManagedCard["cardKind"], version, themeKey, nextBlocks);
      const document = "draft" in template ? template.draft : template.document;
      replaceBlocks(document.blocks);
      setVersion(template.version);
      setThemeKey(document.themeKey);
      setDirty(false);
      setIdentityDirty(false);
      setSavedNotice(savedNotice);
      const updatedCard = card && savedCard ? { ...savedCard, version: template.version } : undefined;
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
        blocks: normalizeEnterpriseTemplateBlockOrder(blocks),
      }, { identityTitles, contactFields: normalizeIdentityContactFields(identityContactFields) });
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
    setUndoStack((history) => [...history.slice(-23), { blocks, themeKey }]);
    setRedoStack([]);
    replaceBlocks(nextBlocks);
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
    if (!card || !version || saving) return;
    if (!draftValid || !publishReady) {
      const issueIndex = blockIssues.findIndex(Boolean);
      if (issueIndex >= 0) {
        setSelectedBlockId(blocks[issueIndex]?.id);
        setMobilePane("inspector");
      }
      const issue = issueIndex >= 0 ? blockIssues[issueIndex] : undefined;
      const missing = publishChecks.filter((item) => !item.ready).map((item) => item.label);
      setError(new ApiError(
        issue
          ? `${templateBlockDisplayTitle(blocks[issueIndex], effectiveKind)}：${issue}`
          : `发布前请补齐：${missing.join("、") || "名片必填信息"}。`,
        { code: "CARD_PUBLISH_INCOMPLETE" },
      ));
      return;
    }
    if (dirty) {
      const updatedCard = await persistDraft(blocks, "草稿已保存，可以进入发布确认。");
      if (updatedCard) onRequestPublish(updatedCard);
      return;
    }
    onRequestPublish({ ...card, version });
  };

  const publishedProducts = useMemo(
    () => products.filter((item) => item.status === "published"),
    [products],
  );
  const publishedCases = useMemo(
    () => cases.filter((item) => item.status === "published"),
    [cases],
  );
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
  const previewIdentityContactFields: IdentityContactField[] = useMemo(() => [
    ...identityContactFields,
    ...(company?.website && !identityContactFields.some((field) => field.kind === "website")
      ? [{ id: "company-website", kind: "website" as const, label: "企业官网", value: company.website, href: company.website }]
      : []),
    ...(company?.region && !identityContactFields.some((field) => field.kind === "location")
      ? [{ id: "company-address", kind: "location" as const, label: "公司地址", value: company.region }]
      : []),
  ], [company?.region, company?.website, identityContactFields]);
  const selectedIndex = blocks.findIndex((block) => block.id === selectedBlockId);
  const selectedBlock = selectedIndex >= 0 ? blocks[selectedIndex] : blocks[0];
  // The inspector must receive raw editable values. Display fallbacks belong
  // only to the structure list and preview; feeding them into controlled
  // inputs makes an intentionally empty value impossible to keep.
  const selectedInspectorBlock = selectedBlock;
  const previewBlocks = useMemo(() => canvasBlocks.map((block) => ({
    ...block,
    title: templateBlockDisplayTitle(block, effectiveKind),
  })), [canvasBlocks, effectiveKind]);
  const selectedIssue = selectedIndex >= 0 ? blockIssues[selectedIndex] : blockIssues[0];

  const selectStructureBlock = (blockId: string) => {
    setSelectedBlockId(blockId);
    window.requestAnimationFrame(() => {
      const target = document.getElementById(`bp-template-block-${blockId}`);
      const scroller = canvasStageRef.current;
      if (target && scroller) {
        const targetRect = target.getBoundingClientRect();
        const scrollerRect = scroller.getBoundingClientRect();
        const targetTop = targetRect.top - scrollerRect.top + scroller.scrollTop;
        const stickySafeTop = 92;
        const availableHeight = Math.max(120, scroller.clientHeight - stickySafeTop - 20);
        const targetViewportTop = targetRect.height >= availableHeight
          ? stickySafeTop
          : stickySafeTop + (availableHeight - targetRect.height) / 2;
        const nextScrollTop = Math.max(0, targetTop - targetViewportTop);
        if (typeof scroller.scrollTo === "function") {
          scroller.scrollTo({ top: nextScrollTop, behavior: "smooth" });
        } else {
          scroller.scrollTop = nextScrollTop;
        }
      }
    });
  };

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
      <Dialog
        open
        onOpenChange={(_, data) => {
          if (!data.open && !busy) onClose();
        }}
      >
        <DialogSurface className="enterprise-template-dialog enterprise-template-dialog-v2">
          <CardStudioEditorSurface>
          <DialogBody className="template-studio-dialog-body">
            <StudioEditorShell className="template-studio-shell">
            <DialogTitle className="template-studio-title-shell">
              <div className="studio-topbar template-studio-topbar">
                <div className="studio-brand template-composer-title">
                  <button type="button" className="back-button template-editor-back" onClick={onClose} disabled={busy}>← 返回</button>
                  <span className="studio-divider" aria-hidden="true" />
                  <strong className="document-title">{effectiveDisplayName}的数字名片 ✎</strong>
                  <span className={`autosave ${dirty ? "is-dirty" : "is-saved"}`}>{dirty ? "有未保存修改" : "✓ 已自动保存"}</span>
                </div>
                <div className="studio-history" aria-label="编辑历史">
                  <button className="toolbar-button icon-only" type="button" title="撤销" disabled={busy || !undoStack.length} onClick={undoChange}><ArrowUndo24Regular /></button>
                  <button className="toolbar-button icon-only" type="button" title="重做" disabled={busy || !redoStack.length} onClick={redoChange}><ArrowRedo24Regular /></button>
                </div>
                <div className="studio-actions template-studio-actions">
                  <button className="toolbar-button" type="button" onClick={() => { setMobilePane("canvas"); setPreviewMode("draft"); }}><Eye24Regular />预览</button>
                  {creationDraft ? null : (
                    <button className="toolbar-button" aria-label={card ? "保存草稿" : "保存默认配置"} type="button" onClick={() => void saveDraft()} disabled={busy || !dirty}>
                      <Save24Regular />
                      {saving ? "保存中…" : card ? "保存" : "保存默认配置"}
                    </button>
                  )}
                  {creationDraft ? (
                    <button className="toolbar-button primary" type="button" onClick={() => void confirmCreationDraft()} disabled={busy || !draftValid || !onDraftConfirm}>
                      <Send24Regular />
                      {saving ? "创建中…" : "使用此设计创建名片"}
                    </button>
                  ) : (
                    <button className="toolbar-button primary" aria-label="进入发布确认" type="button" onClick={() => void requestPublish()} disabled={busy || !card}>
                      <Send24Regular />
                      {dirty ? "保存并发布" : "发布"}
                    </button>
                  )}
                </div>
              </div>
            </DialogTitle>
            <DialogContent className="template-composer-dialog-content">
              {(creationDraft || !card) ? <div className="template-composer-context">
                <p>{editorDescription}</p>
                <div>
                  <span>{effectiveKind === "employee" ? "员工名片" : "企业名片"}</span>
                  <strong>{effectiveDisplayName}</strong>
                  {dirty ? <b>未保存</b> : <b className="is-saved">已同步</b>}
                </div>
              </div> : null}
              <FormFeedback error={error} />
              {savedNotice ? <p className="template-save-notice" role="status">{savedNotice}</p> : null}

              {loading ? (
                <div className="template-loading template-composer-loading" role="status">
                  <Spinner size="small" />
                  <span>正在读取页面结构与真实业务数据…</span>
                </div>
              ) : (card || defaultKind || creationDraft) ? (
                <>
                <nav className="template-responsive-pane-tabs" aria-label="编辑器区域切换">
                  {([
                    ["structure", "页面结构"],
                    ["canvas", "实时页面"],
                    ["inspector", "模块设置"],
                  ] as const).map(([pane, label]) => (
                    <button
                      key={pane}
                      type="button"
                      className={mobilePane === pane ? "is-active" : undefined}
                      aria-pressed={mobilePane === pane}
                      onClick={() => {
                        setMobilePane(pane);
                        if (pane !== "canvas") setTabletSidePane(pane);
                      }}
                    >{label}</button>
                  ))}
                </nav>
                <div className="studio-grid enterprise-template-composer">
                  <aside
                    className="studio-panel left template-composer-pane template-structure-pane"
                    id="template-editor-structure"
                    data-editor-pane="structure"
                    data-mobile-active={mobilePane === "structure" ? "true" : "false"}
                    data-tablet-active={tabletSidePane === "structure" ? "true" : "false"}
                    aria-label="页面结构与模块库"
                  >
                    <div className="panel-tabs template-panel-tabs" role="tablist" aria-label="页面结构工具">
                      <button type="button" role="tab" aria-selected={structureTab === "structure"} className={`panel-tab ${structureTab === "structure" ? "active is-active" : ""}`} onClick={() => setStructureTab("structure")}>页面结构</button>
                      <button type="button" role="tab" aria-selected={structureTab === "library"} className={`panel-tab ${structureTab === "library" ? "active is-active" : ""}`} onClick={() => setStructureTab("library")}>添加模块</button>
                    </div>
                    <div className="panel-scroll">

                    {structureTab === "structure" ? (
                      <div className="template-structure-tab-content">
                        <p className="template-pane-hint">拖动手柄调整顺序。基础名片必须保留，但同样可以移动。</p>
                        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleStructureDragEnd}>
                          <SortableContext items={blocks.map((block) => block.id)} strategy={verticalListSortingStrategy}>
                            <ol className="template-structure-list module-list">
                              {blocks.map((block, index) => (
                                <SortableStructureItem
                                  key={block.id}
                                  block={block}
                                  displayTitle={templateBlockDisplayTitle(block, effectiveKind)}
                                  index={index}
                                  busy={busy}
                                  selected={block.id === selectedBlock?.id}
                                  onSelect={() => selectStructureBlock(block.id)}
                                />
                              ))}
                            </ol>
                          </SortableContext>
                        </DndContext>
                        <button type="button" className="template-add-module-switch add-module-button" onClick={() => setStructureTab("library")}>＋ 添加内容模块</button>
                      </div>
                    ) : (
                    <section className="template-module-library template-module-library-v2 is-tab-panel" aria-labelledby="template-module-library-title">
                      <div>
                        <strong id="template-module-library-title">添加模块</strong>
                        <span>模块加入页面底部，随后可拖到任意位置；数据继续引用真实业务库。</span>
                      </div>
                      <div className="template-module-library-actions">
                        {Object.entries(enterpriseTemplateBlockLabels)
                          .filter(([value]) => value !== "identity" && value !== "ai_assistant")
                          .map(([value, label]) => (
                            <button
                              key={value}
                              type="button" className="library-card"
                              disabled={busy || blocks.length >= 24}
                              onClick={() => { void addLibraryBlock(value as EnterpriseTemplateBlockType); setStructureTab("structure"); }}
                            >
                              <Add24Regular aria-hidden="true" />
                              <span><strong>{label}</strong><small>{enterpriseTemplateBlockDescriptions[value as EnterpriseTemplateBlockType]}</small></span>
                            </button>
                          ))}
                      </div>
                    </section>
                    )}

                    <section className="template-identity-source-summary">
                      {effectiveAvatarUrl ? <img src={resolveApiResourceUrl(effectiveAvatarUrl)} alt="名片头像" /> : <i>{effectiveDisplayName.slice(0, 1)}</i>}
                      <div><strong>{effectiveDisplayName}</strong><span>{effectiveTitle}</span></div>
                      {card ? (
                        <Button appearance="subtle" size="small" icon={<Edit24Regular />} onClick={() => onEditBasicSettings(card)}>
                          基础资料
                        </Button>
                      ) : null}
                    </section>
                    </div>
                  </aside>

                  <main
                    className="studio-canvas template-composer-pane template-canvas-pane"
                    id="template-editor-preview"
                    data-editor-pane="canvas"
                    data-mobile-active={mobilePane === "canvas" ? "true" : "false"}
                    data-tablet-active="true"
                    aria-label="名片实时画布"
                  >
                    <div className="canvas-toolbar template-canvas-toolbar">
                      <div className="segmented template-device-switch" role="group" aria-label="预览设备">
                        <button type="button" className={previewDevice === "mobile" ? "active is-active" : undefined} aria-pressed={previewDevice === "mobile"} title="手机预览" onClick={() => setPreviewDevice("mobile")}>▯</button>
                        <button type="button" className={previewDevice === "wide" ? "active is-active" : undefined} aria-pressed={previewDevice === "wide"} title="宽屏预览" onClick={() => setPreviewDevice("wide")}>▱</button>
                      </div>
                      <select className="canvas-select" aria-label="视觉模板" value={themeKey} onChange={(event) => changeTheme(event.target.value as EnterpriseTemplateThemeKey)}>
                        <option value="brand">清透商务模板</option>
                        <option value="clean">纯净内容模板</option>
                        <option value="warm">温和关系模板</option>
                      </select>
                      <div className="template-preview-modes segmented" role="tablist" aria-label="名片预览模式">
                        <button type="button" role="tab" aria-selected={previewMode === "draft"} className={previewMode === "draft" ? "active is-active" : undefined} onClick={() => setPreviewMode("draft")}>草稿</button>
                        {card?.shareUrl ? <button type="button" role="tab" aria-selected={previewMode === "published"} className={previewMode === "published" ? "active is-active" : undefined} onClick={() => setPreviewMode("published")}>线上</button> : null}
                      </div>
                      <button className="toolbar-button icon-only" type="button" title="刷新画布" onClick={() => setPreviewMode((current) => current)}><ArrowClockwise24Regular /></button>
                    </div>
                    <div className="canvas-stage" ref={canvasStageRef}>
                      <div className={`editor-preview ${previewDevice === "wide" ? "wide" : ""}`}>
                        {previewMode === "published" && card?.shareUrl ? (
                          <iframe
                            className="template-public-page-frame"
                            src={card.shareUrl}
                            title="实际公开名片页面"
                            allow="clipboard-write; fullscreen"
                          />
                        ) : (
                          <TemplateCanvas
                            blocks={previewBlocks}
                            themeKey={themeKey}
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
                              identityTitles,
                              contactFields: previewIdentityContactFields,
                            }}
                            selectedBlockId={selectedBlock?.id}
                            onSelectBlock={setSelectedBlockId}
                            onMoveBlock={moveBlockById}
                          />
                        )}
                      </div>
                      {card?.shareUrl ? <a className="template-open-public-link" href={card.shareUrl} target="_blank" rel="noreferrer">在新窗口打开公开页</a> : null}
                    </div>
                  </main>

                  <aside
                    className="studio-panel right template-composer-pane template-inspector-pane"
                    id="template-editor-content"
                    data-editor-pane="inspector"
                    data-mobile-active={mobilePane === "inspector" ? "true" : "false"}
                    data-tablet-active={tabletSidePane === "inspector" ? "true" : "false"}
                    aria-label="区块属性"
                  >
                    <div className="template-inspector-heading">
                      <strong>模块设置</strong>
                      <span>当前选中模块</span>
                    </div>
                    <div className="panel-scroll">
                    <p className="template-pane-hint">只编辑当前选中的模块，页面变化会实时出现在中间。</p>
                    {selectedInspectorBlock ? (
                      <TemplateBlockInspector
                        block={selectedInspectorBlock}
                        index={selectedIndex >= 0 ? selectedIndex : 0}
                        blockCount={blocks.length}
                        busy={busy}
                        issue={selectedIssue}
                        uploadingKey={uploadingKey}
                        products={publishedProducts}
                        cases={publishedCases}
                        selectableFaqs={selectableFaqs}
                        labels={enterpriseTemplateBlockLabels}
                        identityTitles={identityTitles}
                        identityContactFields={identityContactFields}
                        galleryInputRefs={galleryInputRefs}
                        videoInputRefs={videoInputRefs}
                        coverInputRefs={coverInputRefs}
                        backgroundInputRefs={backgroundInputRefs}
                        actionCoverInputRefs={actionCoverInputRefs}
                        collectionCoverInputRefs={collectionCoverInputRefs}
                        onUpdate={(patch) => updateBlock(selectedIndex >= 0 ? selectedIndex : 0, patch)}
                        onIdentityTitlesChange={(titles) => {
                          setIdentityTitles(titles);
                          setDirty(true);
                          setIdentityDirty(true);
                          setSavedNotice(undefined);
                        }}
                        onIdentityContactFieldsChange={(fields) => {
                          setIdentityContactFields(fields);
                          setDirty(true);
                          setIdentityDirty(true);
                          setSavedNotice(undefined);
                        }}
                        onMove={(direction) => moveBlock(selectedIndex >= 0 ? selectedIndex : 0, direction)}
                        onDuplicate={() => duplicateBlock(selectedIndex >= 0 ? selectedIndex : 0)}
                        onRemove={() => removeBlock(selectedIndex >= 0 ? selectedIndex : 0)}
                        onGalleryUpload={(event) => void uploadGalleryImages(selectedIndex >= 0 ? selectedIndex : 0, event)}
                        onVideoUpload={(event) => void uploadVideoAsset(selectedIndex >= 0 ? selectedIndex : 0, event)}
                        onCoverUpload={(event) => void uploadVideoCover(selectedIndex >= 0 ? selectedIndex : 0, event)}
                        onBackgroundUpload={(event) => void uploadIdentityBackground(selectedIndex >= 0 ? selectedIndex : 0, event)}
                        onActionCoverUpload={(actionId, event) => void uploadActionCover(selectedIndex >= 0 ? selectedIndex : 0, actionId, event)}
                        onCollectionCoverUpload={(kind, itemId, event) => void uploadCollectionCover(selectedIndex >= 0 ? selectedIndex : 0, kind, itemId, event)}
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
                    </div>
                  </aside>
                </div>
                </>
              ) : null}
            </DialogContent>
            </StudioEditorShell>
          </DialogBody>
          </CardStudioEditorSurface>
        </DialogSurface>
      </Dialog>
    );
  }

  return null;
}

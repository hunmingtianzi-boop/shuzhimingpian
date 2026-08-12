import {
  Button,
  Checkbox,
  Field,
  Input,
  Radio,
  RadioGroup,
  Select,
  Slider,
  Textarea,
} from "@fluentui/react-components";
import {
  Add24Regular,
  ArrowDown24Regular,
  ArrowUp24Regular,
  ArrowUpload24Regular,
  Copy24Regular,
  Delete24Regular,
  Open24Regular,
} from "@fluentui/react-icons";
import type { ChangeEvent, MutableRefObject, PointerEvent as ReactPointerEvent } from "react";
import { StudioInspectorSection, StudioInspectorTitle, type StudioIconName } from "@cf/card-page-renderer";
import { IdentityTitlesEditor } from "../IdentityTitlesEditor";

import type {
  CaseStudy,
  EnterpriseTemplateActionItem,
  EnterpriseTemplateBlock,
  EnterpriseTemplateGalleryItem,
  EnterpriseTemplateLayoutVariant,
  IdentityContactField,
  IdentityContactKind,
  Product,
  SelectableFaqDocument,
} from "../../api/types";
import { APP_PATHS, appHref } from "../../routing";
import { resolveApiResourceUrl } from "../../lib/resourceUrl";

type Props = {
  block: EnterpriseTemplateBlock;
  index: number;
  blockCount: number;
  busy: boolean;
  issue?: string;
  uploadingKey?: string;
  products: Product[];
  cases: CaseStudy[];
  selectableFaqs: SelectableFaqDocument[];
  labels: Record<EnterpriseTemplateBlock["type"], string>;
  identityTitles: string[];
  identityContactFields: IdentityContactField[];
  galleryInputRefs: MutableRefObject<Record<string, HTMLInputElement | null>>;
  videoInputRefs: MutableRefObject<Record<string, HTMLInputElement | null>>;
  coverInputRefs: MutableRefObject<Record<string, HTMLInputElement | null>>;
  backgroundInputRefs: MutableRefObject<Record<string, HTMLInputElement | null>>;
  actionCoverInputRefs: MutableRefObject<Record<string, HTMLInputElement | null>>;
  collectionCoverInputRefs: MutableRefObject<Record<string, HTMLInputElement | null>>;
  onUpdate: (patch: Partial<EnterpriseTemplateBlock>) => void;
  onIdentityTitlesChange: (titles: string[]) => void;
  onIdentityContactFieldsChange: (fields: IdentityContactField[]) => void;
  onMove: (direction: -1 | 1) => void;
  onDuplicate: () => void;
  onRemove: () => void;
  onGalleryUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onVideoUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onCoverUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onBackgroundUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onActionCoverUpload: (actionId: string, event: ChangeEvent<HTMLInputElement>) => void;
  onCollectionCoverUpload: (kind: "product" | "case", itemId: string, event: ChangeEvent<HTMLInputElement>) => void;
};

const identityContactKindLabels: Record<IdentityContactKind, string> = {
  phone: "电话",
  wechat: "微信 / 企业微信",
  email: "邮箱",
  location: "地址",
  website: "官网",
  other: "其他",
};

const PUBLIC_CONTACT_SHORTCUT_LIMIT = 4;

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

function moveItem(items: string[], id: string, direction: -1 | 1) {
  const index = items.indexOf(id);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

const layoutOptions: Partial<Record<EnterpriseTemplateBlock["type"], Array<{
  value: EnterpriseTemplateLayoutVariant;
  label: string;
  detail: string;
}>>> = {
  business_collection: [
    { value: "auto", label: "智能排布", detail: "根据数量自动选择" },
    { value: "list", label: "纵向列表", detail: "适合标题与摘要较长" },
    { value: "grid", label: "双列宫格", detail: "适合 2–4 项快速浏览" },
    { value: "carousel", label: "横向滑动", detail: "适合 4 项以上" },
  ],
  case_collection: [
    { value: "auto", label: "智能排布", detail: "有图无图都能自适应" },
    { value: "featured", label: "主次案例", detail: "一个重点 + 多个补充" },
    { value: "list", label: "纵向图文", detail: "突出完整案例叙事" },
    { value: "grid", label: "双列宫格", detail: "适合短标题与多案例" },
    { value: "carousel", label: "横向滑动", detail: "适合移动端连续浏览" },
  ],
  image_gallery: [
    { value: "auto", label: "智能排布", detail: "按图片数量自动变化" },
    { value: "mosaic", label: "拼贴画廊", detail: "主图 + 次图，视觉最丰富" },
    { value: "grid", label: "等宽宫格", detail: "适合同规格作品图片" },
    { value: "carousel", label: "横向滑动", detail: "保留更大的单图尺寸" },
  ],
  action_collection: [
    { value: "grid", label: "快捷入口宫格", detail: "适合 2–5 个高频入口" },
    { value: "list", label: "图文链接列表", detail: "标题、摘要和行动更完整" },
    { value: "carousel", label: "横向滑动", detail: "适合连续活动或文章" },
    { value: "featured", label: "主入口 + 次入口", detail: "突出最重要的一个行动" },
  ],
};

const actionTemplateOptions = [
  ["shortcuts", "快捷入口", "适合 2–5 个高频去处"],
  ["media", "图文链接卡", "图片、摘要与详情入口"],
  ["event", "活动专题", "时间、地点、状态与报名"],
  ["banner", "品牌横幅", "一张主图承托一个重点行动"],
  ["articles", "文章列表", "来源、日期与连续阅读"],
  ["video", "视频入口", "封面、播放符号与时长"],
  ["buttons", "简洁行动按钮", "官网、下载、预约等轻量动作"],
] as const;

const backgroundPositionFocal = {
  center: [50, 50], top: [50, 0], bottom: [50, 100], left: [0, 50], right: [100, 50],
  topLeft: [0, 0], topRight: [100, 0], bottomLeft: [0, 100], bottomRight: [100, 100],
} as const;

const backgroundRatioOptions = [
  ["auto", "跟随名片"], ["16:9", "横向 16:9"], ["4:3", "标准 4:3"], ["3:2", "照片 3:2"], ["1:1", "方形 1:1"],
] as const;

function nextActionItem(): EnterpriseTemplateActionItem {
  const suffix = typeof crypto.randomUUID === "function"
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10);
  return {
    id: `action-${suffix}`,
    title: "新入口",
    label: "查看详情",
    targetType: "external_url",
    targetValue: "https://",
    openMode: "new_tab",
  };
}

function actionTestHref(item: EnterpriseTemplateActionItem) {
  const target = item.targetValue.trim();
  if (item.targetType === "external_url") return isHttpsUrl(target) ? target : undefined;
  if (item.targetType === "internal_path") return /^\/(?!\/)/.test(target) ? target : undefined;
  if (item.targetType === "phone") return target ? `tel:${target.replace(/[^+\d]/g, "")}` : undefined;
  return target ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(target)}` : undefined;
}

export function TemplateBlockInspector({
  block,
  index,
  blockCount,
  busy,
  issue,
  uploadingKey,
  products,
  cases,
  selectableFaqs,
  labels,
  identityTitles,
  identityContactFields,
  galleryInputRefs,
  videoInputRefs,
  coverInputRefs,
  backgroundInputRefs,
  actionCoverInputRefs,
  collectionCoverInputRefs,
  onUpdate,
  onIdentityTitlesChange,
  onIdentityContactFieldsChange,
  onMove,
  onDuplicate,
  onRemove,
  onGalleryUpload,
  onVideoUpload,
  onCoverUpload,
  onBackgroundUpload,
  onActionCoverUpload,
  onCollectionCoverUpload,
}: Props) {
  const isIdentity = block.type === "identity";
  const completedIdentityContacts = identityContactFields.filter((field) => field.value.trim());
  const incompleteIdentityContactCount = identityContactFields.length - completedIdentityContacts.length;
  const updateIdentityContact = (id: string, patch: Partial<IdentityContactField>) => {
    onIdentityContactFieldsChange(identityContactFields.map((field) => (
      field.id === id ? { ...field, ...patch } : field
    )));
  };
  const addIdentityContact = () => {
    if (identityContactFields.length >= 8) return;
    const suffix = typeof crypto.randomUUID === "function"
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
    onIdentityContactFieldsChange([...identityContactFields, {
      id: `contact-${suffix}`,
      kind: "phone",
      label: "电话",
      value: "",
      href: "",
    }]);
  };
  const galleryUploading = uploadingKey === `${block.id}:gallery`;
  const videoUploading = uploadingKey === `${block.id}:video`;
  const coverUploading = uploadingKey === `${block.id}:cover`;
  const backgroundUploading = uploadingKey === `${block.id}:background`;
  const galleryItems: EnterpriseTemplateGalleryItem[] = block.galleryItems ?? (block.imageUrls ?? []).map((imageUrl, itemIndex) => ({
    id: `legacy-${itemIndex + 1}`,
    imageUrl,
    title: `工作记录 ${itemIndex + 1}`,
    badgeMode: "title" as const,
  }));
  const updateProductOverride = (id: string, patch: Record<string, string | undefined>) => onUpdate({
    productOverrides: [
      ...(block.productOverrides ?? []).filter((item) => item.id !== id),
      { ...(block.productOverrides ?? []).find((item) => item.id === id), id, ...patch },
    ],
  });
  const updateCaseOverride = (id: string, patch: Record<string, string | undefined>) => onUpdate({
    caseOverrides: [
      ...(block.caseOverrides ?? []).filter((item) => item.id !== id),
      { ...(block.caseOverrides ?? []).find((item) => item.id === id), id, ...patch },
    ],
  });
  const updateCaseMetric = (id: string, metricIndex: number, field: "value" | "label", value: string) => {
    const current = block.caseOverrides?.find((item) => item.id === id);
    const metrics = Array.from({ length: 3 }, (_, index) => current?.metrics?.[index] ?? { value: "", label: "" });
    metrics[metricIndex] = { ...metrics[metricIndex], [field]: value };
    onUpdate({ caseOverrides: [...(block.caseOverrides ?? []).filter((item) => item.id !== id), { ...current, id, metrics }] });
  };
  const availableLayouts = layoutOptions[block.type];
  const backgroundOpacityPercent = Math.round(
    Math.min(1, Math.max(0.08, block.presentation?.background?.opacity ?? 0.28)) * 100,
  );
  const selectedFaqIds = block.faqDocumentIds ?? [];
  const identityBackground = block.presentation?.background;
  const backgroundAspectRatio = identityBackground?.aspectRatio ?? "auto";
  const cropAspectRatio = backgroundAspectRatio === "auto" ? "16 / 9" : backgroundAspectRatio.replace(":", " / ");
  const cropFocalX = Math.max(0, Math.min(100, identityBackground?.focalX ?? 50));
  const cropFocalY = Math.max(0, Math.min(100, identityBackground?.focalY ?? 50));
  const updateBackgroundFocus = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.type === "pointermove" && event.buttons !== 1) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    if (event.type === "pointerdown") {
      event.currentTarget.setPointerCapture(event.pointerId);
      event.preventDefault();
    }
    const focalX = Math.round(Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * 100);
    const focalY = Math.round(Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) * 100);
    onUpdate({
      presentation: {
        ...block.presentation,
        background: { ...identityBackground, focalX, focalY },
      },
    });
  };
  const faqById = new Map(selectableFaqs.map((item) => [item.id, item]));
  const orderedFaqs = [
    ...selectedFaqIds.flatMap((id) => {
      const item = faqById.get(id);
      return item ? [item] : [];
    }),
    ...selectableFaqs.filter((item) => !selectedFaqIds.includes(item.id)),
  ];
  const inspectorMeta: Record<EnterpriseTemplateBlock["type"], { icon: StudioIconName; description: string; source: string }> = {
    identity: { icon: "user", description: "身份、企业背书与快捷联系", source: "企业 / 员工资料" },
    rich_text: { icon: "user", description: "个人或企业介绍内容", source: "名片内容" },
    business_collection: { icon: "briefcase", description: "按数量和场景选择业务排布", source: "真实业务库" },
    image_gallery: { icon: "image", description: "活动、团队与项目现场", source: "企业素材库" },
    video_link: { icon: "play", description: "真实封面与在线播放入口", source: "视频链接" },
    case_collection: { icon: "building", description: "真实场景、方案与成果", source: "真实案例库" },
    trust_panel: { icon: "check", description: "企业认证与公开资料", source: "企业资料" },
    faq: { icon: "help", description: "直接选择已发布问答", source: "真实问答库" },
    cta: { icon: "external", description: "轻量行动与跳转入口", source: "行动链接" },
    action_collection: { icon: "external", description: "官网、活动、资料与电话入口", source: "自定义内容" },
    ai_assistant: { icon: "message", description: "使用默认底部 AI 接待入口", source: "企业资料" },
  };
  const meta = inspectorMeta[block.type];

  return (
    <div className="template-inspector-content studio-inspector-content">
      <StudioInspectorTitle icon={meta.icon} title={labels[block.type]} description={meta.description} />
      <StudioInspectorSection title="数据来源">
        <div className="source-card"><div><strong>{meta.source}</strong><span> · 已同步</span></div><span>{block.type === "faq" ? `可选 ${selectableFaqs.length} 条` : "实时引用"}</span></div>
      </StudioInspectorSection>
      <StudioInspectorSection title="内容与展示">

      <div className="template-inspector-visibility">
        {isIdentity ? (
          <div className="template-identity-lock">
            <strong>始终公开展示</strong>
            <span>基础名片可以调整位置，但不能隐藏或删除。</span>
          </div>
        ) : (
          <Checkbox
            checked={block.visible}
            label="公开展示"
            disabled={busy}
            onChange={(_, data) => onUpdate({ visible: data.checked === true })}
          />
        )}
        {!isIdentity ? (
          <Checkbox
            checked={block.showTitle !== false}
            label="显示模块标题"
            disabled={busy}
            onChange={(_, data) => onUpdate({ showTitle: data.checked === true })}
          />
        ) : null}
        <Checkbox
          checked={block.directoryEnabled !== false}
          label="加入页面目录"
          disabled={busy}
          onChange={(_, data) => onUpdate({ directoryEnabled: data.checked === true })}
        />
      </div>

      {isIdentity ? (
        <div className="identity-inspector-fields">
          <Field label="身份头衔" hint="逐条添加、独立排序；保存后同步到真实公开名片。">
            <IdentityTitlesEditor values={identityTitles} disabled={busy} onChange={onIdentityTitlesChange} />
          </Field>
          <div className="identity-inspector-contact-heading">
            <div><strong>联系快捷入口</strong><span>电话、微信、邮箱、地址和官网都会在基础名片中显示。</span></div>
            <Button type="button" size="small" appearance="secondary" icon={<Add24Regular />} disabled={busy || identityContactFields.length >= 8} onClick={addIdentityContact}>
              添加
            </Button>
          </div>
          <div className="identity-inspector-contact-list">
            {identityContactFields.map((contact) => (
              <div className="identity-inspector-contact-row" key={contact.id}>
                <Select
                  aria-label="联系方式类型"
                  value={contact.kind}
                  disabled={busy}
                  onChange={(_, data) => {
                    const kind = data.value as IdentityContactKind;
                    updateIdentityContact(contact.id, { kind, label: identityContactKindLabels[kind] });
                  }}
                >
                  {Object.entries(identityContactKindLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                </Select>
                <Input aria-label="显示名称" value={contact.label} disabled={busy} onChange={(_, data) => updateIdentityContact(contact.id, { label: data.value })} />
                <Input aria-label="联系方式内容" value={contact.value} disabled={busy} placeholder="公开显示内容" onChange={(_, data) => updateIdentityContact(contact.id, { value: data.value })} />
                <Input aria-label="点击目标" value={contact.href ?? ""} disabled={busy} placeholder="可选：https / tel / mailto" onChange={(_, data) => updateIdentityContact(contact.id, { href: data.value })} />
                <Button
                  type="button"
                  appearance="subtle"
                  icon={<Delete24Regular />}
                  aria-label={`删除${contact.label || "联系方式"}`}
                  disabled={busy}
                  onClick={() => onIdentityContactFieldsChange(identityContactFields.filter((field) => field.id !== contact.id))}
                />
              </div>
            ))}
            {!identityContactFields.length ? <p>暂无自定义入口；可直接补充微信、公司地址、官网等真实资料。</p> : null}
          </div>
          {incompleteIdentityContactCount > 0 ? (
            <p className="template-field-warning" role="status">
              有 {incompleteIdentityContactCount} 条入口未填写内容，保存时会自动忽略。
            </p>
          ) : null}
          {completedIdentityContacts.length > PUBLIC_CONTACT_SHORTCUT_LIMIT ? (
            <p className="template-field-warning" role="status">
              已配置 {completedIdentityContacts.length} 条；公开页首屏快捷入口最多展示 {PUBLIC_CONTACT_SHORTCUT_LIMIT} 条，超出项不会出现在首屏快捷栏。
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="template-inspector-order" aria-label="模块位置操作">
        <Button
          appearance="subtle"
          size="small"
          icon={<ArrowUp24Regular />}
          disabled={index === 0 || busy}
          onClick={() => onMove(-1)}
        >上移</Button>
        <Button
          appearance="subtle"
          size="small"
          icon={<ArrowDown24Regular />}
          disabled={index === blockCount - 1 || busy}
          onClick={() => onMove(1)}
        >下移</Button>
        {!isIdentity ? (
          <>
            <Button
              appearance="subtle"
              size="small"
              icon={<Copy24Regular />}
              disabled={busy || blockCount >= 24}
              onClick={onDuplicate}
            >复制</Button>
            <Button
              appearance="subtle"
              size="small"
              icon={<Delete24Regular />}
              disabled={busy}
              onClick={onRemove}
            >删除</Button>
          </>
        ) : null}
      </div>

      {isIdentity ? (
        <>
          <div className="template-identity-note">
            <strong>基础名片信息自动同步</strong>
            <p>企业名片读取企业资料；员工名片读取企业员工资料。这里不保存姓名、职位、头像或联系方式副本。</p>
          </div>
          <section className="template-inspector-fields template-identity-presentation" aria-label="基础名片布局与背景">
            <div className="field">
              <label>身份排布</label>
              <div className="option-grid">
                {([[
                  "horizontal", "横向身份卡", "首屏信息密度更高",
                ], [
                  "vertical", "纵向身份卡", "突出头像与个人信任",
                ]] as const).map(([value, title, detail]) => (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-label={value === "horizontal" ? "横向" : "竖向"}
                    aria-checked={(block.presentation?.identityLayout ?? "horizontal") === value}
                    className={`option-card ${(block.presentation?.identityLayout ?? "horizontal") === value ? "active" : ""}`}
                    disabled={busy}
                    onClick={() => onUpdate({
                      layoutVariant: value,
                      presentation: { ...block.presentation, identityLayout: value },
                    })}
                  ><strong>{title}</strong><small>{detail}</small></button>
                ))}
              </div>
            </div>

            <div className="template-media-field field">
              <div className="template-media-heading">
                <div><strong>基础名片背景</strong><span>图片仅作底层，身份字段继续来自真实资料。</span></div>
              </div>
              {block.presentation?.background?.assetUrl ? (
                <figure className="template-cover-preview template-background-preview upload-drop">
                  <img src={resolveApiResourceUrl(block.presentation.background.assetUrl)} alt="基础名片背景预览" />
                  <Button
                    appearance="subtle"
                    size="small"
                    icon={<Delete24Regular />}
                    aria-label="移除基础名片背景"
                    disabled={busy}
                    onClick={() => onUpdate({
                      presentation: {
                        ...block.presentation,
                        background: {
                          ...block.presentation?.background,
                          assetUrl: undefined,
                        },
                      },
                    })}
                  />
                </figure>
              ) : <p className="template-inspector-empty">未设置背景时沿用项目的浅青品牌底色。</p>}
              <input
                ref={(node) => { backgroundInputRefs.current[block.id] = node; }}
                className="visually-hidden"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                aria-label="选择基础名片背景图片"
                disabled={busy}
                onChange={onBackgroundUpload}
              />
              <Button
                appearance="secondary"
                icon={<ArrowUpload24Regular />}
                disabled={busy}
                onClick={() => backgroundInputRefs.current[block.id]?.click()}
              >{backgroundUploading ? "上传中…" : block.presentation?.background?.assetUrl ? "更换背景" : "上传背景"}</Button>
            </div>

            {identityBackground?.assetUrl ? (
              <div className="template-background-crop-field field">
                <div className="template-background-crop-heading">
                  <div><strong>选择图片展示区域</strong><span>在图片上点击或拖动焦点，名片会优先保留这一部分。</span></div>
                  <output>{cropFocalX}% · {cropFocalY}%</output>
                </div>
                <div
                  className="template-background-crop-canvas"
                  role="application"
                  aria-label="拖动选择背景图片展示区域"
                  onPointerDown={updateBackgroundFocus}
                  onPointerMove={updateBackgroundFocus}
                  style={{
                    aspectRatio: cropAspectRatio,
                    backgroundImage: `url(${JSON.stringify(resolveApiResourceUrl(identityBackground.assetUrl))})`,
                    backgroundPosition: `${cropFocalX}% ${cropFocalY}%`,
                    backgroundSize: identityBackground.fit === "custom"
                      ? `${Math.round((identityBackground.scale ?? 1) * 100)}% auto`
                      : identityBackground.fit ?? "cover",
                  }}
                >
                  <span className="template-background-crop-focus" style={{ left: `${cropFocalX}%`, top: `${cropFocalY}%` }} aria-hidden="true" />
                  <span className="template-background-crop-frame" aria-hidden="true" />
                </div>
                <div className="template-background-ratio-options" role="radiogroup" aria-label="背景图片比例">
                  {backgroundRatioOptions.map(([value, label]) => (
                    <button
                      type="button"
                      role="radio"
                      aria-checked={backgroundAspectRatio === value}
                      className={backgroundAspectRatio === value ? "is-active" : undefined}
                      key={value}
                      disabled={busy}
                      onClick={() => onUpdate({
                        presentation: {
                          ...block.presentation,
                          background: { ...identityBackground, aspectRatio: value },
                        },
                      })}
                    >{label}</button>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="template-control-grid">
              <Field label="图片适配">
                <Select
                  value={block.presentation?.background?.fit ?? "cover"}
                  disabled={busy || !block.presentation?.background?.assetUrl}
                  onChange={(_, data) => onUpdate({
                    presentation: {
                      ...block.presentation,
                      background: {
                        ...block.presentation?.background,
                        fit: data.value as "cover" | "contain" | "custom",
                      },
                    },
                  })}
                >
                  <option value="cover">铺满裁切</option>
                  <option value="contain">完整显示</option>
                  <option value="custom">自定义比例</option>
                </Select>
              </Field>
              <Field label="图片位置">
                <Select
                  value={block.presentation?.background?.position ?? "center"}
                  disabled={busy || !block.presentation?.background?.assetUrl}
                  onChange={(_, data) => {
                    const position = data.value as keyof typeof backgroundPositionFocal;
                    const [focalX, focalY] = backgroundPositionFocal[position];
                    onUpdate({
                      presentation: {
                        ...block.presentation,
                        background: { ...block.presentation?.background, position, focalX, focalY },
                      },
                    });
                  }}
                >
                  <option value="center">居中</option>
                  <option value="top">顶部</option>
                  <option value="bottom">底部</option>
                  <option value="left">左侧</option>
                  <option value="right">右侧</option>
                  <option value="topLeft">左上</option>
                  <option value="topRight">右上</option>
                  <option value="bottomLeft">左下</option>
                  <option value="bottomRight">右下</option>
                </Select>
              </Field>
            </div>
            <Field label={`图片缩放 ${Math.round((block.presentation?.background?.scale ?? 1) * 100)}%`}>
              <Slider
                min={50}
                max={200}
                step={1}
                value={Math.round((block.presentation?.background?.scale ?? 1) * 100)}
                disabled={busy || !block.presentation?.background?.assetUrl}
                onChange={(_, data) => onUpdate({
                  presentation: {
                    ...block.presentation,
                    background: { ...block.presentation?.background, scale: data.value / 100 },
                  },
                })}
              />
            </Field>
            <Field label={`图片透明度 ${backgroundOpacityPercent}%`}>
              <Slider
                min={8}
                max={100}
                value={backgroundOpacityPercent}
                disabled={busy || !block.presentation?.background?.assetUrl}
                onChange={(_, data) => onUpdate({
                  presentation: {
                    ...block.presentation,
                    background: { ...block.presentation?.background, opacity: data.value / 100 },
                  },
                })}
              />
            </Field>
            <Field label="内容遮罩">
              <Select
                value={block.presentation?.background?.overlay ?? "light"}
                disabled={busy || !block.presentation?.background?.assetUrl}
                onChange={(_, data) => onUpdate({
                  presentation: {
                    ...block.presentation,
                    background: {
                      ...block.presentation?.background,
                      overlay: data.value as "none" | "light" | "dark" | "brand",
                    },
                  },
                })}
              >
                <option value="none">无遮罩</option>
                <option value="light">浅色提亮</option>
                <option value="dark">深色压暗</option>
                <option value="brand">品牌色融合</option>
              </Select>
            </Field>
          </section>
        </>
      ) : (
        <Field label="模块标题">
          <Input
            value={block.title ?? ""}
            disabled={busy}
            onChange={(_, data) => onUpdate({ title: data.value, showTitle: Boolean(data.value.trim()) })}
          />
        </Field>
      )}

      {availableLayouts ? (
        <section className="template-layout-controls" aria-label={`${labels[block.type]}排布设置`}>
          <fieldset className="template-layout-choice-fieldset">
            <legend>展示样式</legend>
            <div className="template-layout-choice-grid" role="radiogroup" aria-label={`${labels[block.type]}展示样式`}>
              {availableLayouts.map((option) => {
                const active = (block.layoutVariant ?? availableLayouts[0]?.value ?? "auto") === option.value;
                return <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  className={`template-layout-choice ${active ? "is-active" : ""}`}
                  disabled={busy}
                  onClick={() => onUpdate({ layoutVariant: option.value })}
                >
                  <span className={`template-layout-choice-preview is-${option.value}`} aria-hidden="true"><i/><i/><i/><i/></span>
                  <span><strong>{option.label}</strong><small>{option.detail}</small></span>
                </button>;
              })}
            </div>
          </fieldset>
          <Field label={`最多展示 ${block.itemLimit ?? 4} 项`}>
            <Slider
              min={1}
              max={12}
              value={block.itemLimit ?? 4}
              disabled={busy}
              onChange={(_, data) => onUpdate({ itemLimit: data.value })}
            />
          </Field>
          <p>样式和数量只控制展示，内容仍从已发布数据或企业素材中读取。</p>
        </section>
      ) : null}

      {block.type === "rich_text" || block.type === "ai_assistant" ? (
        <Field label={block.type === "ai_assistant" ? "引导文案" : "内容"}>
          <Textarea
            value={block.body ?? ""}
            rows={5}
            resize="vertical"
            disabled={busy}
            onChange={(_, data) => onUpdate({ body: data.value })}
          />
        </Field>
      ) : null}

      {block.type === "image_gallery" ? (
        <div className="template-media-field">
          <div className="template-media-heading">
            <div><strong>展示图片</strong><span>企业素材，最多 12 张。</span></div>
          </div>
          {galleryItems.length ? (
            <div className="template-collection-item-list">
              {galleryItems.map((item, imageIndex) => (
                <details className="template-collection-item" key={item.id} open={imageIndex === 0}>
                  <summary><img src={resolveApiResourceUrl(item.imageUrl)} alt=""/><span><strong>{item.title || `图片 ${imageIndex + 1}`}</strong><small>点击编辑角标与说明</small></span></summary>
                  <div className="template-collection-fields">
                    <a
                      className="template-test-action-link"
                      href={resolveApiResourceUrl(item.imageUrl)}
                      target="_blank"
                      rel="noreferrer"
                    >预览原图 <Open24Regular aria-hidden="true" /></a>
                    <Field label="图片标题"><Input value={item.title ?? ""} onChange={(_, data) => onUpdate({ galleryItems: galleryItems.map((current) => current.id === item.id ? { ...current, title: data.value } : current) })}/></Field>
                    <Field label="图片说明"><Textarea rows={3} value={item.description ?? ""} onChange={(_, data) => onUpdate({ galleryItems: galleryItems.map((current) => current.id === item.id ? { ...current, description: data.value } : current) })}/></Field>
                    <div className="template-inline-fields"><Field label="时间"><Input value={item.timeLabel ?? ""} placeholder="2026.08" onChange={(_, data) => onUpdate({ galleryItems: galleryItems.map((current) => current.id === item.id ? { ...current, timeLabel: data.value } : current) })}/></Field><Field label="阶段"><Input value={item.periodLabel ?? ""} placeholder="项目交付期" onChange={(_, data) => onUpdate({ galleryItems: galleryItems.map((current) => current.id === item.id ? { ...current, periodLabel: data.value } : current) })}/></Field></div>
                    <Field label="右下角角标"><Select value={item.badgeMode} onChange={(_, data) => onUpdate({ galleryItems: galleryItems.map((current) => current.id === item.id ? { ...current, badgeMode: data.value as typeof item.badgeMode } : current) })}><option value="title">图片标题</option><option value="time">时间</option><option value="period">阶段</option><option value="custom">自定义</option><option value="none">不显示</option></Select></Field>
                    {item.badgeMode === "custom" ? <Field label="自定义角标"><Input value={item.badgeText ?? ""} onChange={(_, data) => onUpdate({ galleryItems: galleryItems.map((current) => current.id === item.id ? { ...current, badgeText: data.value } : current) })}/></Field> : null}
                    <Field label="无障碍说明"><Input value={item.altText ?? ""} onChange={(_, data) => onUpdate({ galleryItems: galleryItems.map((current) => current.id === item.id ? { ...current, altText: data.value } : current) })}/></Field>
                    <Field label="可选跳转网址"><Input value={item.linkUrl ?? ""} placeholder="https://" onChange={(_, data) => onUpdate({ galleryItems: galleryItems.map((current) => current.id === item.id ? { ...current, linkUrl: data.value } : current) })}/></Field>
                    <Button appearance="subtle" icon={<Delete24Regular />} disabled={busy} onClick={() => { const next = galleryItems.filter((current) => current.id !== item.id); onUpdate({ galleryItems: next, imageUrls: next.map((current) => current.imageUrl) }); }}>移除图片</Button>
                  </div>
                </details>
              ))}
            </div>
          ) : <p className="template-inspector-empty">上传图片后会立即出现在中间页面中。</p>}
          <input
            ref={(node) => { galleryInputRefs.current[block.id] = node; }}
            className="visually-hidden"
            type="file"
            multiple
            accept="image/png,image/jpeg,image/webp"
            aria-label={`选择${block.title || "图片画廊"}图片`}
            disabled={busy}
            onChange={onGalleryUpload}
          />
          <Button
            appearance="secondary"
            icon={<ArrowUpload24Regular />}
            disabled={busy || galleryItems.length >= 12}
            onClick={() => galleryInputRefs.current[block.id]?.click()}
          >{galleryUploading ? "上传中…" : "上传图片"}</Button>
        </div>
      ) : null}

      {block.type === "video_link" ? (
        <>
          <div className="template-media-field">
            <div className="template-media-heading">
              <div><strong>上传视频文件</strong><span>推荐 MP4；也支持 WebM，最大 50 MiB。</span></div>
            </div>
            <input
              ref={(node) => { videoInputRefs.current[block.id] = node; }}
              className="visually-hidden"
              type="file"
              accept="video/mp4,video/webm"
              aria-label={`选择${block.title || "视频"}文件`}
              disabled={busy}
              onChange={onVideoUpload}
            />
            <Button
              appearance="secondary"
              icon={<ArrowUpload24Regular />}
              disabled={busy}
              onClick={() => videoInputRefs.current[block.id]?.click()}
            >{videoUploading ? "上传中…" : block.videoUrl?.startsWith("/api/v1/public/card-video-assets/") ? "更换已上传视频" : "上传视频"}</Button>
            {block.videoUrl?.startsWith("/api/v1/public/card-video-assets/") ? (
              <p className="template-upload-success" role="status">视频文件已上传并写入当前模块。</p>
            ) : null}
          </div>
          <Field
            label="外部视频地址（高级）"
            required
            hint="上传文件后会自动填入站内地址；也可手动填写公开 HTTPS 视频地址。"
            validationState={block.videoUrl && !isPlayableVideoUrl(block.videoUrl) ? "error" : "none"}
            validationMessage={block.videoUrl && !isPlayableVideoUrl(block.videoUrl) ? "请上传视频或输入 HTTPS 地址。" : undefined}
          >
            <Input
              type="url"
              value={block.videoUrl ?? ""}
              disabled={busy}
              onChange={(_, data) => onUpdate({ videoUrl: data.value })}
            />
          </Field>
          {isPlayableVideoUrl(block.videoUrl) ? (
            <a
              className="template-test-action-link"
              href={resolveApiResourceUrl(block.videoUrl)}
              target="_blank"
              rel="noreferrer"
            >测试播放 <Open24Regular aria-hidden="true" /></a>
          ) : <span className="template-test-action-link is-disabled">上传视频或补齐地址后可测试播放</span>}
          <div className="template-media-field">
            <div className="template-media-heading"><div><strong>视频封面</strong><span>使用企业素材上传。</span></div></div>
            {block.videoCoverUrl ? (
              <figure className="template-cover-preview">
                <img src={resolveApiResourceUrl(block.videoCoverUrl)} alt="视频封面" />
                <Button
                  appearance="subtle"
                  size="small"
                  icon={<Delete24Regular />}
                  aria-label="移除视频封面"
                  disabled={busy}
                  onClick={() => onUpdate({ videoCoverUrl: undefined })}
                />
              </figure>
            ) : null}
            <input
              ref={(node) => { coverInputRefs.current[block.id] = node; }}
              className="visually-hidden"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              aria-label={`选择${block.title || "视频"}封面`}
              disabled={busy}
              onChange={onCoverUpload}
            />
            <Button
              appearance="secondary"
              icon={<ArrowUpload24Regular />}
              disabled={busy}
              onClick={() => coverInputRefs.current[block.id]?.click()}
            >{coverUploading ? "上传中…" : block.videoCoverUrl ? "更换封面" : "上传封面"}</Button>
          </div>
        </>
      ) : null}

      {block.type === "business_collection" ? (
        <fieldset className="template-case-picker template-source-editor">
          <legend>选择并调整已发布产品与服务</legend>
          <p className="template-source-note"><strong>业务库是主数据</strong><span>这里的修改只影响当前名片展示，不会覆盖业务库原文。</span></p>
          {products.length ? products.map((item) => {
            const checked = block.productIds?.includes(item.id) ?? false;
            const override = block.productOverrides?.find((current) => current.id === item.id);
            return (
              <details className="template-source-item" key={item.id} open={checked && item.id === block.productIds?.[0]}>
                <summary><Checkbox checked={checked} disabled={busy} label={`${item.name}${item.category ? ` · ${item.category}` : ""}`} onChange={(_, data) => onUpdate({ productIds: data.checked ? [...(block.productIds ?? []), item.id] : block.productIds?.filter((id) => id !== item.id), productOverrides: data.checked ? block.productOverrides : block.productOverrides?.filter((current) => current.id !== item.id) })}/><small>{checked ? "已加入 · 可调整当前名片文案" : "来自业务库"}</small></summary>
                {checked ? <div className="template-collection-fields">
                  <Field label="展示标题"><Input value={override?.title ?? ""} placeholder={item.name} onChange={(_, data) => updateProductOverride(item.id, { title: data.value })}/></Field>
                  <Field label="分类标签"><Input value={override?.category ?? ""} placeholder={item.category} onChange={(_, data) => updateProductOverride(item.id, { category: data.value })}/></Field>
                  <Field label="展示摘要"><Textarea rows={3} value={override?.summary ?? ""} placeholder={item.summary} onChange={(_, data) => updateProductOverride(item.id, { summary: data.value })}/></Field>
                  <div className="template-item-cover-control">{override?.imageUrl || item.imageUrl ? <img src={resolveApiResourceUrl(override?.imageUrl || item.imageUrl)} alt="当前业务图片"/> : null}<input ref={(node) => { collectionCoverInputRefs.current[`product:${item.id}`] = node; }} className="visually-hidden" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => onCollectionCoverUpload("product", item.id, event)}/><Button appearance="secondary" icon={<ArrowUpload24Regular/>} onClick={() => collectionCoverInputRefs.current[`product:${item.id}`]?.click()}>{uploadingKey === `${block.id}:product:${item.id}` ? "上传中…" : override?.imageUrl ? "更换当前名片图片" : "上传当前名片图片"}</Button></div>
                  <Field label="行动文字"><Input value={override?.ctaLabel ?? ""} placeholder="查看业务" onChange={(_, data) => updateProductOverride(item.id, { ctaLabel: data.value })}/></Field>
                </div> : null}
              </details>
            );
          }) : <p>暂无已发布产品，请先到产品管理发布产品。</p>}
        </fieldset>
      ) : null}

      {block.type === "case_collection" ? (
        <fieldset className="template-case-picker template-source-editor">
          <legend>选择并调整已发布案例</legend>
          <p className="template-source-note"><strong>案例库是主数据</strong><span>标题、行业、过程、成果和图片可针对当前名片做展示覆盖。</span></p>
          {cases.length ? cases.map((item) => {
            const checked = block.caseIds?.includes(item.id) ?? false;
            const override = block.caseOverrides?.find((current) => current.id === item.id);
            return (
              <details className="template-source-item" key={item.id} open={checked && item.id === block.caseIds?.[0]}>
                <summary><Checkbox checked={checked} disabled={busy} label={`${item.title}${item.industry ? ` · ${item.industry}` : ""}`} onChange={(_, data) => onUpdate({ caseIds: data.checked ? [...(block.caseIds ?? []), item.id] : block.caseIds?.filter((id) => id !== item.id), caseOverrides: data.checked ? block.caseOverrides : block.caseOverrides?.filter((current) => current.id !== item.id) })}/><small>{checked ? "已加入 · 可编辑全部展示字段" : "来自案例库"}</small></summary>
                {checked ? <div className="template-collection-fields">
                  <Field label="案例标题"><Input value={override?.title ?? ""} placeholder={item.title} onChange={(_, data) => updateCaseOverride(item.id, { title: data.value })}/></Field>
                  <div className="template-inline-fields"><Field label="行业"><Input value={override?.industry ?? ""} placeholder={item.industry} onChange={(_, data) => updateCaseOverride(item.id, { industry: data.value })}/></Field><Field label="客户名称"><Input value={override?.clientName ?? ""} placeholder={item.clientDisplayName} onChange={(_, data) => updateCaseOverride(item.id, { clientName: data.value })}/></Field></div>
                  <Field label="项目背景"><Textarea rows={3} value={override?.background ?? ""} placeholder={item.background} onChange={(_, data) => updateCaseOverride(item.id, { background: data.value })}/></Field>
                  <Field label="解决方案"><Textarea rows={3} value={override?.solution ?? ""} placeholder={item.solution} onChange={(_, data) => updateCaseOverride(item.id, { solution: data.value, summary: data.value })}/></Field>
                  <Field label="项目成果"><Textarea rows={3} value={override?.result ?? ""} placeholder={item.result} onChange={(_, data) => updateCaseOverride(item.id, { result: data.value })}/></Field>
                  <div className="template-metric-editor"><strong>成果指标（最多 3 项）</strong>{[0, 1, 2].map((metricIndex) => <div className="template-inline-fields" key={metricIndex}><Field label={`指标 ${metricIndex + 1} 数值`}><Input value={override?.metrics?.[metricIndex]?.value ?? ""} placeholder={metricIndex === 0 ? "+68%" : ""} onChange={(_, data) => updateCaseMetric(item.id, metricIndex, "value", data.value)}/></Field><Field label="指标说明"><Input value={override?.metrics?.[metricIndex]?.label ?? ""} placeholder={metricIndex === 0 ? "转化提升" : ""} onChange={(_, data) => updateCaseMetric(item.id, metricIndex, "label", data.value)}/></Field></div>)}</div>
                  <div className="template-item-cover-control">{override?.imageUrl || item.imageUrl ? <img src={resolveApiResourceUrl(override?.imageUrl || item.imageUrl)} alt="当前案例图片"/> : null}<input ref={(node) => { collectionCoverInputRefs.current[`case:${item.id}`] = node; }} className="visually-hidden" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => onCollectionCoverUpload("case", item.id, event)}/><Button appearance="secondary" icon={<ArrowUpload24Regular/>} onClick={() => collectionCoverInputRefs.current[`case:${item.id}`]?.click()}>{uploadingKey === `${block.id}:case:${item.id}` ? "上传中…" : override?.imageUrl ? "更换当前名片图片" : "上传当前名片图片"}</Button></div>
                  <Field label="行动文字"><Input value={override?.ctaLabel ?? ""} placeholder="查看案例" onChange={(_, data) => updateCaseOverride(item.id, { ctaLabel: data.value })}/></Field>
                </div> : null}
              </details>
            );
          }) : <p>暂无已发布案例，请先到案例管理发布案例。</p>}
        </fieldset>
      ) : null}

      {block.type === "action_collection" ? (
        <section className="template-action-collection-editor" aria-labelledby={`action-collection-${block.id}`}>
          <div className="template-data-source-heading">
            <div>
              <strong id={`action-collection-${block.id}`}>内容块即入口</strong>
              <span>公开页整块可点击；编辑画布只负责选中，跳转请在这里测试。</span>
            </div>
            <Button
              appearance="secondary"
              size="small"
              icon={<Add24Regular />}
              disabled={busy || (block.actionItems?.length ?? 0) >= 12}
              onClick={() => onUpdate({ actionItems: [...(block.actionItems ?? []), nextActionItem()] })}
            >添加入口</Button>
          </div>

          <Field label="入口组件形态">
            <div className="option-grid template-options">
              {actionTemplateOptions.map(([value, title, detail]) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={(block.actionTemplate ?? "shortcuts") === value}
                  className={`option-card ${(block.actionTemplate ?? "shortcuts") === value ? "active" : ""}`}
                  disabled={busy}
                  onClick={() => onUpdate({ actionTemplate: value })}
                ><strong>{title}</strong><small>{detail}</small></button>
              ))}
            </div>
          </Field>

          {(block.actionItems ?? []).length ? (
            <ol className="template-action-item-list">
              {(block.actionItems ?? []).map((item, itemIndex) => {
                const updateItem = (patch: Partial<EnterpriseTemplateActionItem>) => onUpdate({
                  actionItems: block.actionItems?.map((current) => (
                    current.id === item.id ? { ...current, ...patch } : current
                  )),
                });
                const testHref = actionTestHref(item);
                const actionUploading = uploadingKey === `${block.id}:action:${item.id}`;
                return (
                  <li key={item.id}>
                    <header>
                      <div><span>{String(itemIndex + 1).padStart(2, "0")}</span><strong>{item.title || "未命名入口"}</strong></div>
                      <Button
                        appearance="subtle"
                        size="small"
                        icon={<Delete24Regular />}
                        aria-label={`删除行动入口：${item.title || itemIndex + 1}`}
                        disabled={busy}
                        onClick={() => onUpdate({ actionItems: block.actionItems?.filter((current) => current.id !== item.id) })}
                      />
                    </header>
                    <div className="template-inspector-fields">
                      <Field label="入口标题" required>
                        <Input value={item.title} disabled={busy} onChange={(_, data) => updateItem({ title: data.value })} />
                      </Field>
                      <Field label="摘要">
                        <Textarea value={item.summary ?? ""} rows={2} resize="vertical" disabled={busy} onChange={(_, data) => updateItem({ summary: data.value })} />
                      </Field>
                      <Field label="行动文字">
                        <Input value={item.label ?? ""} placeholder="例如：查看大会详情" disabled={busy} onChange={(_, data) => updateItem({ label: data.value })} />
                      </Field>
                      <Field label="标签">
                        <Input value={item.tag ?? ""} placeholder="例如：行业大会" disabled={busy} onChange={(_, data) => updateItem({ tag: data.value })} />
                      </Field>
                      <div className="template-control-grid">
                        <Field label="跳转类型">
                          <Select
                            value={item.targetType}
                            disabled={busy}
                            onChange={(event) => updateItem({ targetType: event.target.value as EnterpriseTemplateActionItem["targetType"] })}
                          >
                            <option value="external_url">外部网址</option>
                            <option value="internal_path">站内页面</option>
                            <option value="phone">电话</option>
                            <option value="map">地图位置</option>
                          </Select>
                        </Field>
                        <Field label="打开方式">
                          <Select
                            value={item.openMode}
                            disabled={busy}
                            onChange={(event) => updateItem({ openMode: event.target.value === "new_tab" ? "new_tab" : "self" })}
                          >
                            <option value="self">当前页面</option>
                            <option value="new_tab">新窗口</option>
                          </Select>
                        </Field>
                      </div>
                      <Field
                        label="目标地址"
                        required
                        validationState={item.targetValue && !testHref ? "error" : "none"}
                        validationMessage={item.targetValue && !testHref ? "当前目标格式无效。" : undefined}
                      >
                        <Input
                          value={item.targetValue}
                          placeholder={item.targetType === "external_url" ? "https://" : item.targetType === "internal_path" ? "/products" : item.targetType === "phone" ? "+86 138…" : "地点或地址"}
                          disabled={busy}
                          onChange={(_, data) => updateItem({ targetValue: data.value })}
                        />
                      </Field>
                    </div>

                    <details className="advanced-details">
                      <summary>活动、文章或视频信息</summary>
                      <div className="template-control-grid">
                        <Field label="入口图标">
                          <Select value={item.icon ?? "external"} disabled={busy} onChange={(event) => updateItem({ icon: event.target.value as NonNullable<EnterpriseTemplateActionItem["icon"]> })}>
                            <option value="external">外部链接</option>
                            <option value="building">企业 / 大会</option>
                            <option value="calendar">活动日历</option>
                            <option value="file">资料文件</option>
                            <option value="play">视频播放</option>
                          </Select>
                        </Field>
                        <Field label="日期或时长">
                          <Input value={item.date ?? item.duration ?? ""} placeholder="2026.08.18 或 02:36" disabled={busy} onChange={(_, data) => updateItem(block.actionTemplate === "video" ? { duration: data.value } : { date: data.value })} />
                        </Field>
                      </div>
                      <div className="template-control-grid">
                        <Field label="地点 / 来源">
                          <Input value={block.actionTemplate === "articles" ? item.source ?? "" : item.location ?? ""} placeholder={block.actionTemplate === "articles" ? "例如：企业动态" : "例如：杭州国际博览中心"} disabled={busy} onChange={(_, data) => updateItem(block.actionTemplate === "articles" ? { source: data.value } : { location: data.value })} />
                        </Field>
                        <Field label="活动状态">
                          <Input value={item.status ?? ""} placeholder="例如：报名中" disabled={busy} onChange={(_, data) => updateItem({ status: data.value })} />
                        </Field>
                      </div>
                    </details>

                    <div className="template-action-cover-row">
                      {item.imageUrl ? <img src={resolveApiResourceUrl(item.imageUrl)} alt={`${item.title || "行动入口"}封面`} /> : <i aria-hidden="true">图</i>}
                      <div>
                        <input
                          ref={(node) => { actionCoverInputRefs.current[`${block.id}:${item.id}`] = node; }}
                          className="visually-hidden"
                          type="file"
                          accept="image/png,image/jpeg,image/webp"
                          aria-label={`选择行动入口封面：${item.title || itemIndex + 1}`}
                          disabled={busy}
                          onChange={(event) => onActionCoverUpload(item.id, event)}
                        />
                        <Button
                          appearance="secondary"
                          size="small"
                          icon={<ArrowUpload24Regular />}
                          disabled={busy}
                          onClick={() => actionCoverInputRefs.current[`${block.id}:${item.id}`]?.click()}
                        >{actionUploading ? "上传中…" : item.imageUrl ? "更换封面" : "上传封面"}</Button>
                        {item.imageUrl ? (
                          <Button appearance="subtle" size="small" disabled={busy} onClick={() => updateItem({ imageUrl: undefined })}>移除</Button>
                        ) : null}
                      </div>
                    </div>

                    {testHref ? (
                      <a
                        className="template-test-action-link"
                        href={testHref}
                        target={item.openMode === "new_tab" ? "_blank" : undefined}
                        rel={item.openMode === "new_tab" ? "noreferrer" : undefined}
                      >测试跳转 <Open24Regular aria-hidden="true" /></a>
                    ) : <span className="template-test-action-link is-disabled">补齐目标后可测试跳转</span>}
                  </li>
                );
              })}
            </ol>
          ) : (
            <div className="template-inspector-empty">
              <strong>还没有行动入口</strong>
              <p>可添加官网、活动、产品中心、电话或地图入口；不保存模拟点击量。</p>
            </div>
          )}
        </section>
      ) : null}

      {block.type === "faq" ? (
        <section className="template-faq-inspector" aria-labelledby={`faq-source-${block.id}`}>
          <div className="template-data-source-heading">
            <div>
              <strong id={`faq-source-${block.id}`}>数据来源：知识 FAQ</strong>
              <span>这里只配置展示范围；问题和答案在知识 FAQ 中统一维护。</span>
            </div>
            <a href={appHref(APP_PATHS.knowledge)} target="_blank" rel="noreferrer">
              前往管理 <Open24Regular aria-hidden="true" />
            </a>
          </div>
          <RadioGroup
            aria-label="FAQ 展示方式"
            value={block.faqMode === "selected" ? "selected" : "all_published"}
            onChange={(_, data) => onUpdate({
              faqMode: data.value === "selected" ? "selected" : "all_published",
            })}
          >
            <Radio value="all_published" label={`自动同步全部公开 FAQ（${selectableFaqs.length}）`} disabled={busy} />
            <Radio value="selected" label="精选展示" disabled={busy} />
          </RadioGroup>

          {block.faqMode === "selected" ? (
            selectableFaqs.length ? (
              <ol className="template-faq-picker" aria-label="选择并排序公开 FAQ">
                {orderedFaqs.map((item) => {
                  const checked = selectedFaqIds.includes(item.id);
                  const selectedPosition = selectedFaqIds.indexOf(item.id);
                  return (
                    <li key={item.id} className={checked ? "is-selected" : undefined}>
                      <Checkbox
                        checked={checked}
                        disabled={busy}
                        label={item.title}
                        onChange={(_, data) => onUpdate({
                          faqDocumentIds: data.checked
                            ? [...selectedFaqIds, item.id]
                            : selectedFaqIds.filter((id) => id !== item.id),
                        })}
                      />
                      <p>{item.answer}</p>
                      {checked ? (
                        <div aria-label={`${item.title}顺序`}>
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<ArrowUp24Regular />}
                            aria-label={`上移 FAQ：${item.title}`}
                            disabled={busy || selectedPosition === 0}
                            onClick={() => onUpdate({ faqDocumentIds: moveItem(selectedFaqIds, item.id, -1) })}
                          />
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<ArrowDown24Regular />}
                            aria-label={`下移 FAQ：${item.title}`}
                            disabled={busy || selectedPosition === selectedFaqIds.length - 1}
                            onClick={() => onUpdate({ faqDocumentIds: moveItem(selectedFaqIds, item.id, 1) })}
                          />
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            ) : (
              <div className="template-inspector-empty">
                <strong>暂无可展示的 FAQ</strong>
                <p>只有已发布且公开的知识 FAQ 才能被名片引用。</p>
                <a href={appHref(APP_PATHS.knowledge)} target="_blank" rel="noreferrer">前往知识 FAQ 管理</a>
              </div>
            )
          ) : (
            <p className="template-faq-sync-note">
              之后新发布的公开 FAQ 会自动出现在名片中；撤回或改为内部后会自动停止展示。
            </p>
          )}
        </section>
      ) : null}

      {block.type === "cta" ? (
        <div className="template-inspector-fields">
          <Field label="按钮文案" required>
            <Input
              value={block.ctaLabel ?? ""}
              disabled={busy}
              onChange={(_, data) => onUpdate({ ctaLabel: data.value })}
            />
          </Field>
          <Field
            label="跳转 HTTPS 地址"
            required
            validationState={block.ctaUrl && !isHttpsUrl(block.ctaUrl) ? "error" : "none"}
            validationMessage={block.ctaUrl && !isHttpsUrl(block.ctaUrl) ? "请输入 HTTPS 地址。" : undefined}
          >
            <Input
              type="url"
              value={block.ctaUrl ?? ""}
              disabled={busy}
              onChange={(_, data) => onUpdate({ ctaUrl: data.value })}
            />
          </Field>
        </div>
      ) : null}

      {issue ? <p className="template-block-error" role="alert">{issue}</p> : null}
      </StudioInspectorSection>
    </div>
  );
}

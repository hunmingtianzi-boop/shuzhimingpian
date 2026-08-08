import {
  Button,
  Checkbox,
  Field,
  Input,
  Radio,
  RadioGroup,
  Slider,
  Textarea,
} from "@fluentui/react-components";
import {
  ArrowDown24Regular,
  ArrowUp24Regular,
  ArrowUpload24Regular,
  Copy24Regular,
  Delete24Regular,
  Open24Regular,
} from "@fluentui/react-icons";
import type { ChangeEvent, MutableRefObject } from "react";

import type {
  CaseStudy,
  EnterpriseTemplateBlock,
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
  galleryInputRefs: MutableRefObject<Record<string, HTMLInputElement | null>>;
  coverInputRefs: MutableRefObject<Record<string, HTMLInputElement | null>>;
  backgroundInputRefs: MutableRefObject<Record<string, HTMLInputElement | null>>;
  contentImageInputRefs: MutableRefObject<Record<string, HTMLInputElement | null>>;
  onUpdate: (patch: Partial<EnterpriseTemplateBlock>) => void;
  onMove: (direction: -1 | 1) => void;
  onDuplicate: () => void;
  onRemove: () => void;
  onGalleryUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onCoverUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onBackgroundUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onContentImageUpload: (event: ChangeEvent<HTMLInputElement>) => void;
};

function isHttpsUrl(value?: string) {
  if (!value) return false;
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}

function moveItem(items: string[], id: string, direction: -1 | 1) {
  const index = items.indexOf(id);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
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
  galleryInputRefs,
  coverInputRefs,
  backgroundInputRefs,
  contentImageInputRefs,
  onUpdate,
  onMove,
  onDuplicate,
  onRemove,
  onGalleryUpload,
  onCoverUpload,
  onBackgroundUpload,
  onContentImageUpload,
}: Props) {
  const isIdentity = block.type === "identity";
  const galleryUploading = uploadingKey === `${block.id}:gallery`;
  const coverUploading = uploadingKey === `${block.id}:cover`;
  const backgroundUploading = uploadingKey === `${block.id}:background`;
  const contentImageUploading = uploadingKey === `${block.id}:content-image`;
  const background = block.background ?? {
    kind: "none" as const,
    color: "#eef3f4",
    fit: "cover" as const,
    positionX: 50,
    positionY: 50,
    overlayColor: "#000000",
    overlayOpacity: 0,
  };
  const selectedFaqIds = block.faqDocumentIds ?? [];
  const faqById = new Map(selectableFaqs.map((item) => [item.id, item]));
  const orderedFaqs = [
    ...selectedFaqIds.flatMap((id) => {
      const item = faqById.get(id);
      return item ? [item] : [];
    }),
    ...selectableFaqs.filter((item) => !selectedFaqIds.includes(item.id)),
  ];
  const contentImageIsSide = block.contentImage?.placement === "left" || block.contentImage?.placement === "right";
  const contentImageWidthMax = contentImageIsSide ? 60 : 100;
  const contentImageWidth = Math.min(
    contentImageWidthMax,
    Math.max(30, block.contentImage?.widthPercent ?? (contentImageIsSide ? 46 : 100)),
  );

  return (
    <div className="template-inspector-content">
      <div className="template-inspector-title-row">
        <div>
          <span>{String(index + 1).padStart(2, "0")}</span>
          <strong>{labels[block.type]}</strong>
        </div>
        {isIdentity ? <span className="template-source-badge">企业/员工资料</span> : null}
      </div>

      <section className="template-layout-inspector" aria-labelledby={`block-layout-${block.id}`}>
        <div className="template-media-heading">
          <div>
            <strong id={`block-layout-${block.id}`}>板块尺寸</strong>
            <span>设置最小高度和上下留白；内容增加时仍会自动撑开。</span>
          </div>
        </div>
        <RadioGroup
          aria-label="板块最小高度"
          value={block.sizePreset ?? "auto"}
          layout="horizontal"
          onChange={(_, data) => onUpdate({
            sizePreset: data.value === "compact" || data.value === "standard" || data.value === "tall"
              ? data.value
              : "auto",
          })}
        >
          <Radio value="auto" label="自动" disabled={busy} />
          <Radio value="compact" label="紧凑" disabled={busy} />
          <Radio value="standard" label="标准" disabled={busy} />
          <Radio value="tall" label="高版" disabled={busy} />
        </RadioGroup>
        <RadioGroup
          aria-label="板块上下留白"
          value={block.paddingY ?? "auto"}
          layout="horizontal"
          onChange={(_, data) => onUpdate({
            paddingY: data.value === "compact" || data.value === "standard" || data.value === "spacious"
              ? data.value
              : "auto",
          })}
        >
          <Radio value="auto" label="原始" disabled={busy} />
          <Radio value="compact" label="少" disabled={busy} />
          <Radio value="standard" label="中" disabled={busy} />
          <Radio value="spacious" label="多" disabled={busy} />
        </RadioGroup>
      </section>

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
        <Checkbox
          checked={block.directoryEnabled !== false}
          label="加入页面目录"
          disabled={busy}
          onChange={(_, data) => onUpdate({ directoryEnabled: data.checked === true })}
        />
      </div>

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
        <div className="template-identity-note">
          <strong>基础名片信息自动同步</strong>
          <p>企业名片读取企业资料；员工名片读取企业员工资料。这里仅控制页面位置与目录展示。</p>
        </div>
      ) : (
        <Field label="模块标题">
          <Input
            value={block.title ?? ""}
            disabled={busy}
            onChange={(_, data) => onUpdate({ title: data.value })}
          />
        </Field>
      )}

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

      {block.type === "rich_text" ? (
        <section className="template-visual-inspector" aria-labelledby={`content-image-${block.id}`}>
          <div className="template-media-heading">
            <div>
              <strong id={`content-image-${block.id}`}>内容图片</strong>
              <span>作为图文内容的一部分，移动端会自动改为上下布局。</span>
            </div>
          </div>
          {block.contentImage ? (
            <figure className="template-cover-preview template-content-image-preview">
              <img src={resolveApiResourceUrl(block.contentImage.url)} alt={block.contentImage.alt || "内容图片预览"} />
              <Button
                appearance="subtle"
                size="small"
                icon={<Delete24Regular />}
                aria-label="移除内容图片"
                disabled={busy}
                onClick={() => onUpdate({ contentImage: undefined })}
              />
            </figure>
          ) : <p className="template-inspector-empty">上传后可选择图片位于文字上方、下方、左侧或右侧。</p>}
          <input
            ref={(node) => { contentImageInputRefs.current[block.id] = node; }}
            className="visually-hidden"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            aria-label={`选择${block.title || "图文介绍"}内容图片`}
            disabled={busy}
            onChange={onContentImageUpload}
          />
          <Button
            appearance="secondary"
            icon={<ArrowUpload24Regular />}
            disabled={busy}
            onClick={() => contentImageInputRefs.current[block.id]?.click()}
          >{contentImageUploading ? "上传中…" : block.contentImage ? "更换图片" : "上传内容图片"}</Button>
          {block.contentImage ? (
            <>
              <RadioGroup
                aria-label="内容图片位置"
                value={block.contentImage.placement}
                layout="horizontal"
                onChange={(_, data) => onUpdate({
                  contentImage: {
                    ...block.contentImage!,
                    placement: data.value as NonNullable<EnterpriseTemplateBlock["contentImage"]>["placement"],
                    widthPercent: data.value === "left" || data.value === "right"
                      ? Math.min(block.contentImage?.widthPercent ?? 46, 60)
                      : block.contentImage?.widthPercent ?? 100,
                  },
                })}
              >
                <Radio value="top" label="上方" disabled={busy} />
                <Radio value="bottom" label="下方" disabled={busy} />
                <Radio value="left" label="左侧" disabled={busy} />
                <Radio value="right" label="右侧" disabled={busy} />
              </RadioGroup>
              <RadioGroup
                aria-label="内容图片适配"
                value={block.contentImage.fit ?? "cover"}
                layout="horizontal"
                onChange={(_, data) => onUpdate({
                  contentImage: {
                    ...block.contentImage!,
                    fit: data.value === "contain" ? "contain" : "cover",
                  },
                })}
              >
                <Radio value="cover" label="铺满裁切" disabled={busy} />
                <Radio value="contain" label="完整显示" disabled={busy} />
              </RadioGroup>
              <RadioGroup
                aria-label="内容图片比例"
                value={block.contentImage.aspectRatio ?? "wide"}
                layout="horizontal"
                onChange={(_, data) => onUpdate({
                  contentImage: {
                    ...block.contentImage!,
                    aspectRatio: ["auto", "square", "standard"].includes(data.value)
                      ? data.value as NonNullable<EnterpriseTemplateBlock["contentImage"]>["aspectRatio"]
                      : "wide",
                  },
                })}
              >
                <Radio value="auto" label="原始" disabled={busy} />
                <Radio value="square" label="1:1" disabled={busy} />
                <Radio value="standard" label="4:3" disabled={busy} />
                <Radio value="wide" label="16:9" disabled={busy} />
              </RadioGroup>
              <Field label={`内容图片宽度 ${contentImageWidth}%`}>
                <Slider
                  min={30}
                  max={contentImageWidthMax}
                  value={contentImageWidth}
                  disabled={busy}
                  onChange={(_, data) => onUpdate({
                    contentImage: { ...block.contentImage!, widthPercent: data.value },
                  })}
                />
              </Field>
              {block.contentImage.fit !== "contain" ? (
                <div className="template-image-focus-controls">
                  <Field label={`内容图片水平焦点 ${block.contentImage.positionX ?? 50}%`}>
                    <Slider
                      min={0}
                      max={100}
                      value={block.contentImage.positionX ?? 50}
                      disabled={busy}
                      onChange={(_, data) => onUpdate({
                        contentImage: { ...block.contentImage!, positionX: data.value },
                      })}
                    />
                  </Field>
                  <Field label={`内容图片垂直焦点 ${block.contentImage.positionY ?? 50}%`}>
                    <Slider
                      min={0}
                      max={100}
                      value={block.contentImage.positionY ?? 50}
                      disabled={busy}
                      onChange={(_, data) => onUpdate({
                        contentImage: { ...block.contentImage!, positionY: data.value },
                      })}
                    />
                  </Field>
                </div>
              ) : null}
              <Field label="图片替代文本" hint="用于无障碍阅读；装饰图片可以留空。">
                <Input
                  value={block.contentImage.alt ?? ""}
                  disabled={busy}
                  onChange={(_, data) => onUpdate({
                    contentImage: { ...block.contentImage!, alt: data.value },
                  })}
                />
              </Field>
            </>
          ) : null}
        </section>
      ) : null}

      <section className="template-visual-inspector" aria-labelledby={`block-background-${block.id}`}>
        <div className="template-media-heading">
          <div>
            <strong id={`block-background-${block.id}`}>板块背景</strong>
            <span>背景不会改变内容来源，只影响当前板块的展示。</span>
          </div>
        </div>
        <RadioGroup
          aria-label="背景类型"
          value={background.kind}
          layout="horizontal"
          onChange={(_, data) => {
            const kind = data.value === "color" || data.value === "image" ? data.value : "none";
            onUpdate({
              background: {
                ...background,
                kind,
                color: background.color ?? "#eef3f4",
                overlayColor: background.overlayColor ?? "#000000",
                overlayOpacity: kind === "image" && !block.background ? 0.42 : background.overlayOpacity ?? 0,
              },
            });
          }}
        >
          <Radio value="none" label="无" disabled={busy} />
          <Radio value="color" label="纯色" disabled={busy} />
          <Radio value="image" label="图片" disabled={busy} />
        </RadioGroup>

        {background.kind === "color" ? (
          <Field label="背景颜色">
            <input
              className="template-color-input"
              type="color"
              value={background.color ?? "#eef3f4"}
              disabled={busy}
              onChange={(event) => onUpdate({
                background: { ...background, kind: "color", color: event.target.value },
              })}
            />
          </Field>
        ) : null}

        {background.kind === "image" ? (
          <div className="template-background-image-controls">
            {background.imageUrl ? (
              <figure className="template-cover-preview template-background-preview">
                <img src={resolveApiResourceUrl(background.imageUrl)} alt="板块背景预览" />
                <Button
                  appearance="subtle"
                  size="small"
                  icon={<Delete24Regular />}
                  aria-label="移除板块背景"
                  disabled={busy}
                  onClick={() => onUpdate({ background: { ...background, kind: "none", imageUrl: undefined } })}
                />
              </figure>
            ) : <p className="template-inspector-empty">上传背景图片后可继续调整裁切、焦点与遮罩。</p>}
            <input
              ref={(node) => { backgroundInputRefs.current[block.id] = node; }}
              className="visually-hidden"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              aria-label={`选择${block.title || labels[block.type]}背景图片`}
              disabled={busy}
              onChange={onBackgroundUpload}
            />
            <Button
              appearance="secondary"
              icon={<ArrowUpload24Regular />}
              disabled={busy}
              onClick={() => backgroundInputRefs.current[block.id]?.click()}
            >{backgroundUploading ? "上传中…" : background.imageUrl ? "更换背景" : "上传背景图片"}</Button>
            <RadioGroup
              aria-label="背景图片适配"
              value={background.fit ?? "cover"}
              layout="horizontal"
              onChange={(_, data) => onUpdate({
                background: { ...background, fit: data.value === "contain" ? "contain" : "cover" },
              })}
            >
              <Radio value="cover" label="铺满裁切" disabled={busy} />
              <Radio value="contain" label="完整显示" disabled={busy} />
            </RadioGroup>
            <Field label={`水平焦点 ${background.positionX ?? 50}%`}>
              <Slider
                min={0}
                max={100}
                value={background.positionX ?? 50}
                disabled={busy}
                onChange={(_, data) => onUpdate({ background: { ...background, positionX: data.value } })}
              />
            </Field>
            <Field label={`垂直焦点 ${background.positionY ?? 50}%`}>
              <Slider
                min={0}
                max={100}
                value={background.positionY ?? 50}
                disabled={busy}
                onChange={(_, data) => onUpdate({ background: { ...background, positionY: data.value } })}
              />
            </Field>
            <div className="template-overlay-controls">
              <Field label="遮罩颜色">
                <input
                  className="template-color-input"
                  type="color"
                  value={background.overlayColor ?? "#000000"}
                  disabled={busy}
                  onChange={(event) => onUpdate({ background: { ...background, overlayColor: event.target.value } })}
                />
              </Field>
              <Field label={`遮罩强度 ${Math.round((background.overlayOpacity ?? 0) * 100)}%`}>
                <Slider
                  min={0}
                  max={85}
                  value={Math.round((background.overlayOpacity ?? 0) * 100)}
                  disabled={busy}
                  onChange={(_, data) => onUpdate({ background: { ...background, overlayOpacity: data.value / 100 } })}
                />
              </Field>
            </div>
          </div>
        ) : null}

        {background.kind !== "none" ? (
          <RadioGroup
            aria-label="背景文字颜色"
            value={block.textTone ?? "auto"}
            layout="horizontal"
            onChange={(_, data) => onUpdate({
              textTone: data.value === "light" || data.value === "dark" ? data.value : "auto",
            })}
          >
            <Radio value="auto" label="自动" disabled={busy} />
            <Radio value="dark" label="深色字" disabled={busy} />
            <Radio value="light" label="浅色字" disabled={busy} />
          </RadioGroup>
        ) : null}
      </section>

      {block.type === "image_gallery" ? (
        <div className="template-media-field">
          <div className="template-media-heading">
            <div><strong>展示图片</strong><span>企业素材，最多 12 张。</span></div>
          </div>
          {block.imageUrls?.length ? (
            <div className="template-media-grid">
              {block.imageUrls.map((url, imageIndex) => (
                <figure key={`${url}-${imageIndex}`}>
                  <img src={resolveApiResourceUrl(url)} alt={`展示图片 ${imageIndex + 1}`} />
                  <Button
                    appearance="subtle"
                    size="small"
                    icon={<Delete24Regular />}
                    aria-label={`移除展示图片 ${imageIndex + 1}`}
                    disabled={busy}
                    onClick={() => onUpdate({
                      imageUrls: block.imageUrls?.filter((_, position) => position !== imageIndex),
                    })}
                  />
                </figure>
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
            disabled={busy || (block.imageUrls?.length ?? 0) >= 12}
            onClick={() => galleryInputRefs.current[block.id]?.click()}
          >{galleryUploading ? "上传中…" : "上传图片"}</Button>
        </div>
      ) : null}

      {block.type === "video_link" ? (
        <>
          <Field
            label="视频 HTTPS 地址"
            required
            validationState={block.videoUrl && !isHttpsUrl(block.videoUrl) ? "error" : "none"}
            validationMessage={block.videoUrl && !isHttpsUrl(block.videoUrl) ? "请输入 HTTPS 地址。" : undefined}
          >
            <Input
              type="url"
              value={block.videoUrl ?? ""}
              disabled={busy}
              onChange={(_, data) => onUpdate({ videoUrl: data.value })}
            />
          </Field>
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
        <fieldset className="template-case-picker">
          <legend>选择已发布产品与服务</legend>
          {products.length ? products.map((item) => {
            const checked = block.productIds?.includes(item.id) ?? false;
            return (
              <Checkbox
                key={item.id}
                checked={checked}
                disabled={busy}
                label={`${item.name}${item.category ? ` · ${item.category}` : ""}`}
                onChange={(_, data) => onUpdate({
                  productIds: data.checked
                    ? [...(block.productIds ?? []), item.id]
                    : block.productIds?.filter((id) => id !== item.id),
                })}
              />
            );
          }) : <p>暂无已发布产品，请先到产品管理发布产品。</p>}
        </fieldset>
      ) : null}

      {block.type === "case_collection" ? (
        <fieldset className="template-case-picker">
          <legend>选择已发布案例</legend>
          {cases.length ? cases.map((item) => {
            const checked = block.caseIds?.includes(item.id) ?? false;
            return (
              <Checkbox
                key={item.id}
                checked={checked}
                disabled={busy}
                label={`${item.title}${item.industry ? ` · ${item.industry}` : ""}`}
                onChange={(_, data) => onUpdate({
                  caseIds: data.checked
                    ? [...(block.caseIds ?? []), item.id]
                    : block.caseIds?.filter((id) => id !== item.id),
                })}
              />
            );
          }) : <p>暂无已发布案例，请先到案例管理发布案例。</p>}
        </fieldset>
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
    </div>
  );
}

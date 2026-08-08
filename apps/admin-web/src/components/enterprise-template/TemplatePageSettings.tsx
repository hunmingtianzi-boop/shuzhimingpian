import {
  Button,
  Field,
  Radio,
  RadioGroup,
  Slider,
} from "@fluentui/react-components";
import {
  ArrowUpload24Regular,
  ChevronDown24Regular,
  Delete24Regular,
} from "@fluentui/react-icons";
import type { ChangeEvent, MutableRefObject } from "react";
import { useState } from "react";

import type { EnterpriseTemplateBlockBackground } from "../../api/types";
import { resolveApiResourceUrl } from "../../lib/resourceUrl";

type Props = {
  background?: EnterpriseTemplateBlockBackground;
  textTone: "auto" | "light" | "dark";
  busy: boolean;
  uploading: boolean;
  inputRef: MutableRefObject<HTMLInputElement | null>;
  onChange: (background: EnterpriseTemplateBlockBackground | undefined, textTone?: "auto" | "light" | "dark") => void;
  onUpload: (event: ChangeEvent<HTMLInputElement>) => void;
};

const emptyBackground: EnterpriseTemplateBlockBackground = {
  kind: "none",
  color: "#eef3f4",
  fit: "cover",
  positionX: 50,
  positionY: 50,
  overlayColor: "#000000",
  overlayOpacity: 0,
};

export function TemplatePageSettings({
  background,
  textTone,
  busy,
  uploading,
  inputRef,
  onChange,
  onUpload,
}: Props) {
  const [expanded, setExpanded] = useState(true);
  const value = background ?? emptyBackground;

  return (
    <section className="template-page-settings" aria-labelledby="template-page-settings-title">
      <button
        type="button"
        className="template-page-settings-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        <span><strong id="template-page-settings-title">页面外观</strong><small>整体背景与文字颜色</small></span>
        <ChevronDown24Regular aria-hidden="true" />
      </button>
      {expanded ? (
        <div className="template-page-settings-content">
          <RadioGroup
            aria-label="整体背景类型"
            value={value.kind}
            layout="horizontal"
            onChange={(_, data) => {
              const kind = data.value === "color" || data.value === "image" ? data.value : "none";
              onChange({
                ...value,
                kind,
                overlayOpacity: kind === "image" && !background ? 0.42 : value.overlayOpacity ?? 0,
              });
            }}
          >
            <Radio value="none" label="无" disabled={busy} />
            <Radio value="color" label="纯色" disabled={busy} />
            <Radio value="image" label="图片" disabled={busy} />
          </RadioGroup>

          {value.kind === "color" ? (
            <Field label="整体背景颜色">
              <input
                className="template-color-input"
                type="color"
                value={value.color ?? "#eef3f4"}
                disabled={busy}
                onChange={(event) => onChange({ ...value, kind: "color", color: event.target.value })}
              />
            </Field>
          ) : null}

          {value.kind === "image" ? (
            <div className="template-background-image-controls">
              {value.imageUrl ? (
                <figure className="template-cover-preview template-page-background-preview">
                  <img src={resolveApiResourceUrl(value.imageUrl)} alt="整体背景预览" />
                  <Button
                    appearance="subtle"
                    size="small"
                    icon={<Delete24Regular />}
                    aria-label="移除整体背景"
                    disabled={busy}
                    onClick={() => onChange(undefined, "auto")}
                  />
                </figure>
              ) : <p className="template-inspector-empty">上传后可调整铺满方式、焦点和遮罩。</p>}
              <input
                ref={(node) => { inputRef.current = node; }}
                className="visually-hidden"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                aria-label="选择整体背景图片"
                disabled={busy}
                onChange={onUpload}
              />
              <Button
                appearance="secondary"
                icon={<ArrowUpload24Regular />}
                disabled={busy}
                onClick={() => inputRef.current?.click()}
              >{uploading ? "上传中…" : value.imageUrl ? "更换背景" : "上传背景图片"}</Button>
              <RadioGroup
                aria-label="整体背景图片适配"
                value={value.fit ?? "cover"}
                layout="horizontal"
                onChange={(_, data) => onChange({ ...value, fit: data.value === "contain" ? "contain" : "cover" })}
              >
                <Radio value="cover" label="铺满裁切" disabled={busy} />
                <Radio value="contain" label="完整显示" disabled={busy} />
              </RadioGroup>
              <Field label={`整体背景水平焦点 ${value.positionX ?? 50}%`}>
                <Slider
                  min={0}
                  max={100}
                  value={value.positionX ?? 50}
                  disabled={busy}
                  onChange={(_, data) => onChange({ ...value, positionX: data.value })}
                />
              </Field>
              <Field label={`整体背景垂直焦点 ${value.positionY ?? 50}%`}>
                <Slider
                  min={0}
                  max={100}
                  value={value.positionY ?? 50}
                  disabled={busy}
                  onChange={(_, data) => onChange({ ...value, positionY: data.value })}
                />
              </Field>
              <div className="template-overlay-controls">
                <Field label="遮罩颜色">
                  <input
                    className="template-color-input"
                    type="color"
                    value={value.overlayColor ?? "#000000"}
                    disabled={busy}
                    onChange={(event) => onChange({ ...value, overlayColor: event.target.value })}
                  />
                </Field>
                <Field label={`遮罩强度 ${Math.round((value.overlayOpacity ?? 0) * 100)}%`}>
                  <Slider
                    min={0}
                    max={85}
                    value={Math.round((value.overlayOpacity ?? 0) * 100)}
                    disabled={busy}
                    onChange={(_, data) => onChange({ ...value, overlayOpacity: data.value / 100 })}
                  />
                </Field>
              </div>
            </div>
          ) : null}

          {value.kind !== "none" ? (
            <RadioGroup
              aria-label="整体背景文字颜色"
              value={textTone}
              layout="horizontal"
              onChange={(_, data) => onChange(
                value,
                data.value === "light" || data.value === "dark" ? data.value : "auto",
              )}
            >
              <Radio value="auto" label="自动" disabled={busy} />
              <Radio value="dark" label="深色字" disabled={busy} />
              <Radio value="light" label="浅色字" disabled={busy} />
            </RadioGroup>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

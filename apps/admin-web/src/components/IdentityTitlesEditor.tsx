import { Button, Input } from "@fluentui/react-components";
import { Add24Regular, ArrowDown24Regular, ArrowUp24Regular, Delete24Regular } from "@fluentui/react-icons";
import { useEffect, useRef, useState } from "react";

type IdentityTitlesEditorProps = {
  values: string[];
  onChange: (values: string[]) => void;
  disabled?: boolean;
  maxItems?: number;
  kind?: "enterprise" | "employee";
  itemLabel?: string;
  addButtonLabel?: string;
  emptyExample?: string;
  maxItemLength?: number;
};

function IdentityValueInput({
  value,
  label,
  maxLength,
  disabled,
  onCommit,
  onBlur,
}: {
  value: string;
  label: string;
  maxLength: number;
  disabled: boolean;
  onCommit: (value: string) => void;
  onBlur: () => void;
}) {
  const [draft, setDraft] = useState(value);
  const composing = useRef(false);

  useEffect(() => {
    if (!composing.current) setDraft(value);
  }, [value]);

  return <Input
    value={draft}
    maxLength={maxLength}
    disabled={disabled}
    aria-label={label}
    onCompositionStart={() => { composing.current = true; }}
    onCompositionEnd={(event) => {
      composing.current = false;
      const next = event.currentTarget.value;
      setDraft(next);
      onCommit(next);
    }}
    onChange={(_, data) => {
      setDraft(data.value);
      if (!composing.current) onCommit(data.value);
    }}
    onBlur={onBlur}
  />;
}

export function IdentityTitlesEditor({ values, onChange, disabled = false, maxItems = 8, kind = "employee", itemLabel, addButtonLabel, emptyExample, maxItemLength = 80 }: IdentityTitlesEditorProps) {
  const [draft, setDraft] = useState("");
  const titles = values.slice(0, maxItems);
  const itemName = itemLabel ?? (kind === "enterprise" ? "企业标签" : "身份头衔");
  const resolvedAddLabel = addButtonLabel ?? (kind === "enterprise" ? "添加标签" : "添加身份");
  const titlesRef = useRef(titles);
  titlesRef.current = titles;
  const commitTitles = (updater: (current: string[]) => string[]) => {
    const next = updater(titlesRef.current).slice(0, maxItems);
    titlesRef.current = next;
    onChange(next);
  };

  const addTitle = () => {
    const title = draft.trim();
    if (!title || titles.length >= maxItems) return;
    if (titles.some((value) => value.toLocaleLowerCase() === title.toLocaleLowerCase())) {
      setDraft("");
      return;
    }
    commitTitles((current) => [...current, title]);
    setDraft("");
  };

  const moveTitle = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= titles.length) return;
    const next = [...titlesRef.current];
    [next[index], next[target]] = [next[target], next[index]];
    commitTitles(() => next);
  };

  return (
    <div className="identity-title-editor">
      <div className="identity-title-add-row">
        <Input
          value={draft}
          maxLength={maxItemLength}
          disabled={disabled || titles.length >= maxItems}
          placeholder={titles.length
            ? `继续添加下一个${itemName}`
            : emptyExample ?? (kind === "enterprise" ? "例如：高新技术企业" : "例如：创始人 / 总经理")}
          aria-label={`新增${itemName}`}
          onChange={(_, data) => setDraft(data.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addTitle();
            }
          }}
        />
        <Button type="button" appearance="secondary" icon={<Add24Regular />} disabled={disabled || !draft.trim() || titles.length >= maxItems} onClick={addTitle}>
          {resolvedAddLabel}
        </Button>
      </div>
      {titles.length ? (
        <ol className="identity-title-list" aria-label={`已添加的${itemName}`}>
          {titles.map((title, index) => (
            <li key={index} className="identity-title-row">
              <span className="identity-title-index">{String(index + 1).padStart(2, "0")}</span>
              <IdentityValueInput
                value={title}
                maxLength={maxItemLength}
                disabled={disabled}
                label={`第 ${index + 1} 个${itemName}`}
                onCommit={(nextValue) => commitTitles((current) => current.map((value, currentIndex) => currentIndex === index ? nextValue : value))}
                onBlur={() => commitTitles((current) => current.map((value) => value.trim()).filter(Boolean))}
              />
              <div className="identity-title-actions">
                <Button type="button" appearance="subtle" size="small" icon={<ArrowUp24Regular />} aria-label={`上移${title}`} disabled={disabled || index === 0} onClick={() => moveTitle(index, -1)} />
                <Button type="button" appearance="subtle" size="small" icon={<ArrowDown24Regular />} aria-label={`下移${title}`} disabled={disabled || index === titles.length - 1} onClick={() => moveTitle(index, 1)} />
                <Button type="button" appearance="subtle" size="small" icon={<Delete24Regular />} aria-label={`删除${title}`} disabled={disabled} onClick={() => commitTitles((current) => current.filter((_, currentIndex) => currentIndex !== index))} />
              </div>
            </li>
          ))}
        </ol>
      ) : <p className="identity-title-empty">尚未添加{itemName}。输入一项后点击“{resolvedAddLabel}”，每项会独立成行。</p>}
      <span className="identity-title-count">已添加 {titles.length}/{maxItems} 个{itemName}</span>
    </div>
  );
}

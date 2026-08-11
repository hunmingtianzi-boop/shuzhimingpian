import { Button, Input } from "@fluentui/react-components";
import { Add24Regular, ArrowDown24Regular, ArrowUp24Regular, Delete24Regular } from "@fluentui/react-icons";
import { useState } from "react";

type IdentityTitlesEditorProps = {
  values: string[];
  onChange: (values: string[]) => void;
  disabled?: boolean;
  maxItems?: number;
};

export function IdentityTitlesEditor({ values, onChange, disabled = false, maxItems = 8 }: IdentityTitlesEditorProps) {
  const [draft, setDraft] = useState("");
  const titles = values.slice(0, maxItems);

  const addTitle = () => {
    const title = draft.trim();
    if (!title || titles.length >= maxItems) return;
    if (titles.some((value) => value.toLocaleLowerCase() === title.toLocaleLowerCase())) {
      setDraft("");
      return;
    }
    onChange([...titles, title]);
    setDraft("");
  };

  const moveTitle = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= titles.length) return;
    const next = [...titles];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  return (
    <div className="identity-title-editor">
      <div className="identity-title-add-row">
        <Input
          value={draft}
          maxLength={80}
          disabled={disabled || titles.length >= maxItems}
          placeholder={titles.length ? "继续添加下一个身份" : "例如：创始人 / 总经理"}
          aria-label="新增身份头衔"
          onChange={(_, data) => setDraft(data.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addTitle();
            }
          }}
        />
        <Button type="button" appearance="secondary" icon={<Add24Regular />} disabled={disabled || !draft.trim() || titles.length >= maxItems} onClick={addTitle}>
          添加身份
        </Button>
      </div>
      {titles.length ? (
        <ol className="identity-title-list" aria-label="已添加的身份头衔">
          {titles.map((title, index) => (
            <li key={index} className="identity-title-row">
              <span className="identity-title-index">{String(index + 1).padStart(2, "0")}</span>
              <Input
                value={title}
                maxLength={80}
                disabled={disabled}
                aria-label={`第 ${index + 1} 个身份头衔`}
                onChange={(_, data) => onChange(titles.map((value, currentIndex) => currentIndex === index ? data.value : value))}
                onBlur={() => onChange(titles.map((value) => value.trim()).filter(Boolean))}
              />
              <div className="identity-title-actions">
                <Button type="button" appearance="subtle" size="small" icon={<ArrowUp24Regular />} aria-label={`上移${title}`} disabled={disabled || index === 0} onClick={() => moveTitle(index, -1)} />
                <Button type="button" appearance="subtle" size="small" icon={<ArrowDown24Regular />} aria-label={`下移${title}`} disabled={disabled || index === titles.length - 1} onClick={() => moveTitle(index, 1)} />
                <Button type="button" appearance="subtle" size="small" icon={<Delete24Regular />} aria-label={`删除${title}`} disabled={disabled} onClick={() => onChange(titles.filter((_, currentIndex) => currentIndex !== index))} />
              </div>
            </li>
          ))}
        </ol>
      ) : <p className="identity-title-empty">尚未添加身份。输入一项后点击“添加身份”，每项会独立成行。</p>}
      <span className="identity-title-count">已添加 {titles.length}/{maxItems} 个身份</span>
    </div>
  );
}

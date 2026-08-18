import { Fragment, cloneElement, isValidElement, useEffect, useMemo, useRef, useState, type CSSProperties, type HTMLAttributes, type MouseEvent, type ReactElement, type ReactNode } from "react";
import { StudioCaseCollection, StudioGallery, StudioServiceCollection } from "./CardStudioCollections";

export type StudioIconName = "arrowLeft" | "share" | "phone" | "mail" | "message" | "map" | "check" | "user" | "briefcase" | "image" | "play" | "help" | "grid" | "building" | "external" | "save" | "plus" | "eye" | "eyeOff" | "grip" | "settings" | "calendar" | "file";

const iconPaths: Record<StudioIconName, ReactNode> = {
  arrowLeft: <path d="m15 18-6-6 6-6" />,
  share: <><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5 8.6 10.5"/></>,
  phone: <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.69 2.8a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.9.33 1.84.56 2.8.69A2 2 0 0 1 22 16.92z"/>,
  mail: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></>,
  message: <><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 10h.01M12 10h.01M16 10h.01"/></>,
  map: <><path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  user: <><circle cx="12" cy="8" r="4"/><path d="M4 22a8 8 0 0 1 16 0"/></>,
  briefcase: <><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2"/></>,
  image: <><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></>,
  play: <><circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4Z"/></>,
  help: <><circle cx="12" cy="12" r="9"/><path d="M9.6 9a2.6 2.6 0 1 1 4.63 1.63c-.95.93-2.23 1.25-2.23 3.37M12 18h.01"/></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  building: <path d="M4 22V4l10-2v20M14 8h6v14M8 6h2M8 10h2M8 14h2M8 18h2M17 12h1M17 16h1M2 22h20"/>,
  external: <><path d="M14 3h7v7M10 14 21 3"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/></>,
  save: <><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z"/><path d="M17 21v-8H7v8M7 3v5h8"/></>,
  plus: <path d="M12 5v14M5 12h14"/>,
  eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></>,
  eyeOff: <><path d="m3 3 18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.4 5.2A11 11 0 0 1 12 5c6.5 0 10 7 10 7a16.5 16.5 0 0 1-2 3M6.2 6.2C3.5 8.1 2 12 2 12s3.5 7 10 7a10.5 10.5 0 0 0 3.4-.6"/></>,
  grip: <><circle cx="9" cy="6" r="1" fill="currentColor" stroke="none"/><circle cx="15" cy="6" r="1" fill="currentColor" stroke="none"/><circle cx="9" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="15" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="9" cy="18" r="1" fill="currentColor" stroke="none"/><circle cx="15" cy="18" r="1" fill="currentColor" stroke="none"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34A1.7 1.7 0 0 0 14 20.92V21h-4v-.08A1.7 1.7 0 0 0 9 19.37a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.63 15 1.7 1.7 0 0 0 3.08 14H3v-4h.08A1.7 1.7 0 0 0 4.63 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.63h.01A1.7 1.7 0 0 0 10 3.08V3h4v.08A1.7 1.7 0 0 0 15 4.63a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.37 9c.22.61.8 1.02 1.55 1.02H21v4h-.08A1.7 1.7 0 0 0 19.4 15Z"/></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></>,
  file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8M8 17h6"/></>,
};

export function StudioIcon({ name, label }: { name: StudioIconName; label?: string }) {
  return <svg className="icon" data-icon={name} viewBox="0 0 24 24" aria-hidden={label ? undefined : true}>{label ? <title>{label}</title> : null}{iconPaths[name]}</svg>;
}

export type StudioIdentity = {
  kind: "enterprise" | "employee";
  variant?: "legacy" | "v2";
  name: string;
  headline?: string;
  titles?: string[];
  companyName?: string;
  summary?: string;
  imageUrl?: string;
  verificationLabel?: string;
  meta?: string[];
  facts?: Array<{ label: string; value: string }>;
  tags?: string[];
  contacts?: Array<{ id?: string; kind?: "phone" | "wechat" | "email" | "location" | "website" | "other"; label: string; value: string; href?: string }>;
  layout?: "horizontal" | "vertical";
  background?: { imageUrl?: string; fit?: "cover" | "contain" | "custom"; position?: string; aspectRatio?: "auto" | "16:9" | "4:3" | "3:2" | "1:1"; focalX?: number; focalY?: number; scale?: number; opacity?: number; overlay?: "none" | "light" | "dark" | "brand" };
};

export type StudioModule = {
  id: string;
  type: "identity" | "overview" | "intro" | "services" | "cases" | "gallery" | "video" | "faq" | "contact" | "actions" | "trust" | "cta" | "ai";
  title: string;
  source: string;
  visible?: boolean;
  directoryEnabled?: boolean;
  showTitle?: boolean;
  layout?: string;
  actionTemplate?: "shortcuts" | "media" | "event" | "banner" | "articles" | "video" | "buttons" | "quick";
  body?: string;
  identity?: StudioIdentity;
  items?: Array<Record<string, unknown>>;
  imageUrls?: string[];
  galleryItems?: Array<{ id: string; imageUrl: string; title?: string; description?: string; timeLabel?: string; periodLabel?: string; badgeMode?: "title" | "time" | "period" | "custom" | "none"; badgeText?: string; altText?: string; linkUrl?: string }>;
  videoUrl?: string;
  videoCoverUrl?: string;
  ctaLabel?: string;
  ctaUrl?: string;
  ctaIcon?: "external" | "phone" | "mail" | "message" | "map" | "building" | "calendar" | "file" | "play";
};

export type StudioCardPageProps = {
  modules: StudioModule[];
  title: string;
  editor?: boolean;
  className?: string;
  selectedModuleId?: string | null;
  onSelectModule?: (id: string) => void;
  renderModuleHandle?: (module: StudioModule) => ReactNode;
  onBack?: () => void;
  onShare?: () => void;
  switchTarget?: { href: string; label: string; ariaLabel: string };
  contentAriaLabel?: string;
  onOpenItem?: (module: StudioModule, item: Record<string, unknown>) => void;
  onAction?: (item: Record<string, unknown>) => void;
  primaryAction?: { label: string; onClick: () => void; disabled?: boolean };
  secondaryAction?: { label: string; onClick: () => void; disabled?: boolean };
  directoryAriaLabel?: string;
  onAssistant?: (question?: string) => void;
};

const initials = (name: string) => name.trim().replace(/\s+/g, "").slice(0, 2).toUpperCase() || "名片";
const contactIcon = (kind?: string): StudioIconName => ({ phone: "phone", wechat: "message", email: "mail", location: "map", website: "external" } as Record<string, StudioIconName>)[kind || ""] || "external";

const moduleHeadingIcon = (type: StudioModule["type"]): StudioIconName => ({
  overview: "grid",
  intro: "user",
  services: "briefcase",
  cases: "building",
  gallery: "image",
  video: "play",
  faq: "help",
  contact: "phone",
  actions: "external",
  trust: "check",
  cta: "external",
  ai: "message",
  identity: "user",
} satisfies Record<StudioModule["type"], StudioIconName>)[type];

function ModuleHeading({ module, more = false }: { module: StudioModule; more?: boolean }) {
  if (module.showTitle === false) return null;
  return <div className={`module-heading module-heading--${module.type}`}>
    <div className="module-heading-leading">
      <span className="module-heading-icon" aria-hidden="true"><StudioIcon name={moduleHeadingIcon(module.type)}/></span>
      <div className="module-heading-copy">{module.source ? <span className="module-eyebrow">{module.source}</span> : null}<h2>{module.title}</h2></div>
    </div>
    {more ? <button className="module-more" type="button">查看全部 <span aria-hidden="true">→</span></button> : null}
  </div>;
}

function StudioIdentityBlock({ identity }: { identity?: StudioIdentity }) {
  if (!identity) return <section className="identity-block layout-horizontal"><div className="identity-content"><div className="empty-state"><strong>基础名片信息待同步</strong><p>选择企业或企业员工后，这里会自动读取身份资料。</p></div></div></section>;
  const background = identity.background;
  const presetPosition = ({ topLeft: "top left", topRight: "top right", bottomLeft: "bottom left", bottomRight: "bottom right" } as Record<string, string>)[background?.position || ""] || background?.position || "center";
  const position = typeof background?.focalX === "number" && typeof background?.focalY === "number"
    ? `${Math.max(0, Math.min(100, background.focalX))}% ${Math.max(0, Math.min(100, background.focalY))}%`
    : presetPosition;
  const scale = Math.max(.5, Math.min(2, background?.scale ?? 1));
  const style: CSSProperties = {
    backgroundImage: background?.imageUrl ? `url(${JSON.stringify(background.imageUrl)})` : undefined,
    backgroundSize: background?.fit === "custom" ? `${scale * 100}% auto` : background?.fit || "cover",
    backgroundPosition: position,
    opacity: Math.max(0, Math.min(1, background?.opacity ?? .18)),
  };
  const cardStyle: CSSProperties = background?.aspectRatio && background.aspectRatio !== "auto"
    ? { aspectRatio: background.aspectRatio.replace(":", " / ") }
    : {};
  const contacts = (identity.contacts || []).filter((item) => item.label.trim() && item.value.trim());
  if (identity.variant === "v2") {
    const visibleContacts = contacts.slice(0, 4);
    const visibleTitles = (identity.titles || []).filter(Boolean).slice(0, 5);
    const visibleFacts = (identity.facts || []).filter((item) => item.label.trim() && item.value.trim()).slice(0, 4);
    return <section style={cardStyle} className={`identity-v2 identity-v2--${identity.kind} ${background?.imageUrl ? "identity-v2--has-background" : ""}`} aria-label={identity.kind === "employee" ? "员工基础名片" : "企业基础名片"}>
      <div className="identity-background cpr-identity-background" style={style} aria-hidden="true"/>
      <div className={`identity-wash cpr-identity-overlay cpr-identity-overlay--${background?.overlay || "light"} overlay-${background?.overlay || "light"}`} aria-hidden="true"/>
      <div className="identity-v2-content">
        <div className="identity-v2-main">
          <div className="identity-v2-visual">
            {identity.imageUrl ? <img src={identity.imageUrl} alt={`${identity.name}${identity.kind === "employee" ? "的职业头像" : "企业标识"}`}/> : <span>{initials(identity.name)}</span>}
            {identity.kind === "employee" ? <i className="availability-dot" title="当前可联系"/> : null}
          </div>
          <div className="identity-v2-copy">
            <div className="identity-v2-kicker">{identity.kind === "employee" ? "员工数字名片" : "企业官方名片"}</div>
            <div className="identity-v2-name-row"><h1>{identity.name}</h1>{identity.verificationLabel ? <span className="verified"><StudioIcon name="check"/>{identity.verificationLabel}</span> : null}</div>
            {identity.headline ? <p className="identity-v2-headline">{identity.headline}</p> : null}
            {identity.kind === "employee" && visibleTitles.length ? <div className="identity-v2-title-lines" aria-label="身份头衔">{visibleTitles.map((title) => <span key={title}>{title}</span>)}</div> : null}
            {identity.kind === "employee" && identity.companyName ? <p className="identity-v2-company"><StudioIcon name="building"/>{identity.companyName}</p> : null}
            {identity.kind === "enterprise" && visibleFacts.length ? <dl className={`identity-v2-facts count-${visibleFacts.length}`}>{visibleFacts.map((fact) => <div key={`${fact.label}-${fact.value}`}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl> : null}
            {identity.tags?.length ? <div className="identity-v2-tags">{identity.tags.slice(0, 6).map((tag) => <span key={tag}>{tag}</span>)}</div> : null}
          </div>
        </div>
        {visibleContacts.length ? <div className={`identity-v2-contacts count-${visibleContacts.length}`} aria-label="快捷联系方式">{visibleContacts.map((item, index) => { const content = <><StudioIcon name={contactIcon(item.kind)}/><span>{item.label}</span></>; return item.href ? <a href={item.href} key={item.id || index}>{content}</a> : <button type="button" key={item.id || index}>{content}</button>; })}</div> : null}
      </div>
    </section>;
  }
  return <section style={cardStyle} className={`identity-block cpr-identity cpr-identity--${identity.kind} cpr-identity--${identity.layout || "horizontal"} ${background?.imageUrl ? "cpr-identity--has-background" : ""} layout-${identity.layout || "horizontal"}`} aria-label="基础名片">
    <div className="identity-background cpr-identity-background" style={style} aria-hidden="true"/><div className={`identity-wash cpr-identity-overlay cpr-identity-overlay--${background?.overlay || "light"} overlay-${background?.overlay || "light"}`} aria-hidden="true"/>
    <div className="identity-content"><div className="identity-main">
      <div className="portrait-wrap">{identity.imageUrl ? <img className="portrait" src={identity.imageUrl} alt={`${identity.name}${identity.kind === "employee" ? "的职业头像" : "标识"}`}/> : <span className="portrait portrait-fallback">{initials(identity.name)}</span>}{identity.kind === "employee" ? <span className="availability-dot" title="当前可联系"/> : null}</div>
      <div className="identity-copy">
        <div className="identity-kicker">{identity.kind === "employee" ? "员工名片 · 资料已同步" : "企业官方名片"}</div>
        <div className="identity-name-row"><h1 className="identity-name">{identity.name}</h1>{identity.verificationLabel ? <span className="verified"><StudioIcon name="check"/>{identity.verificationLabel}</span> : null}</div>
        {identity.headline ? <p className="identity-role">{identity.headline}</p> : null}
        {identity.titles?.length ? <div className="identity-titles" aria-label={identity.kind === "enterprise" ? "企业标签与资质" : "身份头衔"}>{identity.titles.slice(0, 8).map((title) => <span key={title}>{title}</span>)}</div> : null}
        {identity.companyName ? <p className="identity-company">{identity.companyName}</p> : null}
        {identity.kind === "employee" && identity.summary ? <p className="identity-summary">{identity.summary}</p> : null}
        {identity.meta?.length ? <small className="identity-meta">{identity.meta.join(" · ")}</small> : null}
        {identity.kind === "employee" && contacts.length ? <div className="identity-contact-lines">{contacts.slice(0, 3).map((item, index) => <span key={item.id || index}><StudioIcon name={contactIcon(item.kind)}/>{item.value}</span>)}</div> : null}
        {identity.tags?.length ? <div className="identity-tags">{identity.tags.map((tag) => <span key={tag}>{tag}</span>)}</div> : null}
      </div>
    </div>{contacts.length ? <div className={`quick-actions count-${contacts.length}`} data-item-count={contacts.length} aria-label="快捷联系方式">{contacts.map((item, index) => { const content = <><StudioIcon name={contactIcon(item.kind)}/><span>{identity.kind === "enterprise" && item.kind === "website" ? `访问${item.label}` : item.label}</span>{identity.kind === "enterprise" ? <StudioIcon name="external"/> : null}</>; return item.href ? <a className="quick-action" href={item.href} key={item.id || index}>{content}</a> : <button className="quick-action" type="button" key={item.id || index}>{content}</button>; })}</div> : null}</div>
  </section>;
}

function QuickEntryModule({
  module,
  editor,
  onAction,
  className,
  children,
  ...sectionProps
}: {
  module: StudioModule;
  editor: boolean;
  onAction?: StudioCardPageProps["onAction"];
} & HTMLAttributes<HTMLElement>) {
  const [moreOpen, setMoreOpen] = useState(false);
  const items = (module.items || []).filter((item) => String(item.title || "").trim());
  const overflow = items.length > 4;
  const visibleItems = overflow ? items.slice(0, 3) : items.slice(0, 4);
  const remainingItems = overflow ? items.slice(3) : [];
  const activate = (event: MouseEvent<HTMLAnchorElement>, item: Record<string, unknown>) => {
    if (editor || !item.href || item.href === "#") event.preventDefault();
    onAction?.(item);
  };
  const entry = (item: Record<string, unknown>, index: number, compact = false) => <a
    className={compact ? "quick-link-overflow-item" : "quick-link-item"}
    href={String(item.href || "#")}
    target={!editor && item.openMode === "new_tab" ? "_blank" : undefined}
    rel="noreferrer"
    key={String(item.id || index)}
    onClick={(event) => activate(event, item)}
  >
    <span className="quick-link-icon">{item.imageUrl ? <img src={String(item.imageUrl)} alt=""/> : <StudioIcon name={contactIcon(String(item.icon || "website"))}/>}</span>
    <span className="quick-link-copy"><strong>{String(item.title)}</strong>{item.subtitle ? <small>{String(item.subtitle)}</small> : null}</span>
    <StudioIcon name="external"/>
  </a>;
  return <section {...sectionProps} className={["content-module quick-links-module", className].filter(Boolean).join(" ")}>
    {children}
    <ModuleHeading module={module}/>
    {items.length ? <>
      <div className={`quick-links ${items.length === 1 ? "is-single" : "is-multiple"} ${module.layout === "horizontal" ? "is-horizontal" : "is-adaptive"} count-${Math.min(4, visibleItems.length + (overflow ? 1 : 0))}`}>
        {visibleItems.map((item, index) => entry(item, index))}
        {overflow ? <button className="quick-link-item quick-link-more" type="button" aria-expanded={moreOpen} onClick={() => setMoreOpen((current) => !current)}><span className="quick-link-icon"><StudioIcon name="grid"/></span><span className="quick-link-copy"><strong>更多</strong><small>其余 {remainingItems.length} 个入口</small></span><StudioIcon name="external"/></button> : null}
      </div>
      {overflow && moreOpen ? <div className="quick-link-overflow" aria-label="更多快捷入口"><div className="quick-link-overflow-heading"><strong>更多快捷入口</strong><button type="button" onClick={() => setMoreOpen(false)} aria-label="收起更多快捷入口">×</button></div>{remainingItems.map((item, index) => entry(item, index + 3, true))}</div> : null}
    </> : <div className="empty-state"><strong>快捷入口待添加</strong><p>添加名称、图标和跳转地址。</p></div>}
  </section>;
}

function StudioModuleContent({ module, editor = false, onOpenItem, onAction, onAssistant, onSelectModule }: { module: StudioModule; editor?: boolean; onOpenItem?: StudioCardPageProps["onOpenItem"]; onAction?: StudioCardPageProps["onAction"]; onAssistant?: StudioCardPageProps["onAssistant"]; onSelectModule?: StudioCardPageProps["onSelectModule"] }) {
  const items = module.items || [];
  if (module.type === "identity") return StudioIdentityBlock({ identity: module.identity });
  if (module.type === "overview") return <section className="content-module"><div className="overview-panel"><small>我能帮助你</small><p>{module.body || "把企业的业务经验变成可复用的 AI 能力，让销售更懂客户，让服务更快抵达。"}</p></div></section>;
  if (module.type === "intro") return <section className="content-module"><ModuleHeading module={module}/><div className="intro-copy"><p>{module.body || "内容待补充"}</p></div></section>;
  if (module.type === "services") {
    return <section className="content-module"><ModuleHeading module={module} more/><StudioServiceCollection items={items} layout={module.layout} onOpenItem={(item) => onOpenItem?.(module, item)}/></section>;
  }
  if (module.type === "cases") return <section className="content-module"><ModuleHeading module={module} more/><StudioCaseCollection items={items} layout={module.layout} onOpenItem={(item) => onOpenItem?.(module, item)}/></section>;
  if (module.type === "gallery") return <section className="content-module"><ModuleHeading module={module} more/><StudioGallery items={module.galleryItems || (module.imageUrls || []).map((imageUrl, index) => ({ id: `legacy-${index}`, imageUrl }))} layout={module.layout} title={module.title} interactive={!editor}/></section>;
  if (module.type === "video") return <VideoModule module={module} editor={editor} onModuleSelect={() => onSelectModule?.(module.id)}/>;
  if (module.type === "faq") return <FaqModule module={module}/>;
  if (module.type === "actions" && module.actionTemplate === "quick") return <QuickEntryModule module={module} editor={editor} onAction={onAction}/>;
  if (module.type === "actions") {
    const template = module.actionTemplate || (items.some((item) => item.imageUrl) ? "media" : "shortcuts");
    const actionIcon = (item: Record<string, unknown>): StudioIconName => ["external", "phone", "mail", "message", "map", "building", "calendar", "file", "play"].includes(String(item.icon)) ? String(item.icon) as StudioIconName : "external";
    return <section className="content-module action-module"><ModuleHeading module={module}/><div className={`action-collection template-${template} layout-${module.layout || "grid"}`}>{items.length ? items.map((item, index) => <a className={`action-entry ${item.imageUrl ? "has-image" : "no-image"}`} href={String(item.href || "#")} target={!editor && item.openMode === "new_tab" ? "_blank" : undefined} rel="noreferrer" key={String(item.id || index)} onClick={(event) => { if (editor || !item.href || item.href === "#") event.preventDefault(); onAction?.(item); }}><div className="action-visual">{item.imageUrl ? <img src={String(item.imageUrl)} alt=""/> : null}<span className="action-icon"><StudioIcon name={actionIcon(item)}/></span>{template === "video" ? <><span className="action-play"><StudioIcon name="play"/></span><span className="action-duration">{String(item.duration || "02:36")}</span></> : null}</div><div className="action-copy"><div className="action-topline"><span className="action-number">{String(index + 1).padStart(2, "0")}</span>{item.tag ? <span className="action-tag">{String(item.tag)}</span> : null}{template === "event" ? <span className="action-status">{String(item.status || "进行中")}</span> : null}</div><h3>{String(item.title || "未命名入口")}</h3>{template === "event" ? <div className="action-meta">{item.date ? <span><StudioIcon name="calendar"/>{String(item.date)}</span> : null}{item.location ? <span><StudioIcon name="map"/>{String(item.location)}</span> : null}</div> : template === "articles" ? <div className="action-meta">{item.source ? <span>{String(item.source)}</span> : null}{item.date ? <span>{String(item.date)}</span> : null}</div> : null}{item.summary ? <p>{String(item.summary)}</p> : null}<span className="action-cta">{String(item.label || "查看详情")} <StudioIcon name="external"/></span></div></a>) : <div className="empty-state"><strong>行动入口待配置</strong><p>添加官网、电话、地图或站内入口。</p></div>}</div></section>;
  }
  if (module.type === "contact") return <section className="content-module"><ModuleHeading module={module}/><div className="contact-panel">{items.map((item, index) => <div className="contact-row" key={String(item.id || index)}><span className="contact-icon"><StudioIcon name={contactIcon(String(item.kind || "other"))}/></span><div><small>{String(item.label || "联系方式")}</small><strong>{String(item.value || "")}</strong></div><button type="button">{String(item.action || "使用")}</button></div>)}</div></section>;
  if (module.type === "trust") return <section className="content-module"><ModuleHeading module={module}/><div className="contact-panel"><div className="contact-row"><span className="contact-icon"><StudioIcon name="check"/></span><div><small>资料状态</small><strong>{module.body || "企业公开资料已确认"}</strong></div></div></div></section>;
  if (module.type === "ai") return <section className="content-module"><ModuleHeading module={module}/><div className="overview-panel"><small>AI 接待</small><p>{module.body || "基于企业已审核资料，为访客介绍业务并整理合作需求。"}</p>{onAssistant ? <button type="button" className="module-more" onClick={() => onAssistant()}>开始咨询</button> : null}</div></section>;
  if (module.type === "cta") return <section className="content-module"><ModuleHeading module={module}/><div className="intro-copy">{module.body?.trim() ? <p>{module.body}</p> : null}{module.ctaUrl ? <a className="module-more cta-button-with-icon" href={module.ctaUrl}><StudioIcon name={module.ctaIcon || "external"}/><span>{module.ctaLabel || "查看详情"}</span></a> : module.ctaLabel ? <span className="module-more cta-button-with-icon" aria-disabled="true"><StudioIcon name={module.ctaIcon || "external"}/><span>{module.ctaLabel}</span></span> : <p>行动按钮待配置</p>}</div></section>;
  return <section className="content-module"><ModuleHeading module={module}/><div className="intro-copy"><p>{module.body || "内容待补充"}</p>{module.ctaUrl ? <a className="module-more" href={module.ctaUrl}>{module.ctaLabel || "了解更多"} →</a> : null}</div></section>;
}

function VideoModule({
  module,
  editor,
  onModuleSelect,
  className,
  children,
  ...sectionProps
}: {
  module: StudioModule;
  editor: boolean;
  onModuleSelect?: () => void;
} & HTMLAttributes<HTMLElement>) {
  const [playing, setPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (!playing) return;
    const playResult = videoRef.current?.play();
    void playResult?.catch(() => undefined);
  }, [playing]);
  const sectionClassName = ["content-module", className].filter(Boolean).join(" ");
  if (!module.videoUrl) return <section {...sectionProps} className={sectionClassName}>{children}<ModuleHeading module={module}/><div className="empty-state"><strong>视频待配置</strong><p>请上传视频或添加安全的视频地址。</p></div></section>;
  return <section {...sectionProps} className={sectionClassName}>{children}<ModuleHeading module={module}/>{playing && !editor
    ? <div className="video-card is-playing"><video ref={videoRef} src={module.videoUrl} poster={module.videoCoverUrl} controls playsInline preload="metadata">当前浏览器无法播放该视频。</video><a className="video-fallback-link" href={module.videoUrl} target="_blank" rel="noreferrer">在新窗口打开视频</a></div>
    : <button className="video-card video-card-trigger" type="button" aria-label={editor ? `选中${module.title}模块` : `播放${module.title}`} onClick={(event) => { if (editor) { event.stopPropagation(); onModuleSelect?.(); } else setPlaying(true); }}>{module.videoCoverUrl ? <img src={module.videoCoverUrl} alt={`${module.title}封面`}/> : null}<span className="video-play"><StudioIcon name="play"/></span><span className="video-caption"><strong>{module.title}</strong><span>{editor ? "在右侧测试播放" : "点击播放"}</span></span></button>}</section>;
}

function FaqModule({ module, className, ...sectionProps }: { module: StudioModule } & HTMLAttributes<HTMLElement>) {
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set(module.items?.[0] ? [String(module.items[0].id)] : []));
  return <section {...sectionProps} className={["content-module", className].filter(Boolean).join(" ")}><ModuleHeading module={module} more/><div className="faq-list cpr-faq-list">{module.items?.length ? module.items.map((item, index) => { const id = String(item.id || index); const open = openIds.has(id); return <div className={`faq-item ${open ? "open" : ""}`} key={id}><button className="faq-question" type="button" aria-expanded={open} onClick={() => setOpenIds((current) => { const next = new Set(current); next.has(id) ? next.delete(id) : next.add(id); return next; })}><strong>{String(item.question || "未命名问题")}</strong><span className="chevron">⌄</span></button><div className="faq-answer"><div><p>{String(item.answer || "")}</p>{item.sourceLabel ? <small className="faq-source"><span>来源</span>{String(item.sourceLabel)}</small> : null}</div></div></div>; }) : <div className="empty-state"><strong>常见问题待补充</strong><p>已发布且公开的 FAQ 会同步到这里。</p></div>}</div></section>;
}

function hasPublicModuleContent(module: StudioModule) {
  const items = module.items || [];
  if (module.type === "identity" || module.type === "trust") return true;
  if (module.type === "overview" || module.type === "intro" || module.type === "ai") return Boolean(module.body?.trim());
  if (module.type === "services" || module.type === "cases" || module.type === "faq" || module.type === "actions" || module.type === "contact") return items.length > 0;
  if (module.type === "gallery") return Boolean(module.galleryItems?.length || module.imageUrls?.length);
  if (module.type === "video") return Boolean(module.videoUrl);
  if (module.type === "cta") return Boolean(module.ctaLabel || module.ctaUrl);
  return true;
}

export function StudioCardPage({ modules, title, editor = false, className, selectedModuleId, onSelectModule, renderModuleHandle, onBack, onShare, switchTarget, contentAriaLabel, onOpenItem, onAction, primaryAction, secondaryAction, directoryAriaLabel = "名片目录", onAssistant }: StudioCardPageProps) {
  const hostRef = useRef<HTMLElement>(null);
  const directoryRef = useRef<HTMLElement>(null);
  const visible = useMemo(
    () => modules.filter((module) => module.visible !== false && (editor || hasPublicModuleContent(module))),
    [editor, modules],
  );
  const directory = useMemo(() => visible.filter((module) => module.type !== "identity" && module.directoryEnabled !== false), [visible]);
  const [activeId, setActiveId] = useState(directory[0]?.id);
  useEffect(() => { if (!directory.some((item) => item.id === activeId)) setActiveId(directory[0]?.id); }, [activeId, directory]);
  useEffect(() => {
    if (editor || !directory.length) return;
    const updateActiveDirectory = () => {
      const stickyOffset = 64;
      let nextId = directory[0]?.id;
      for (const module of directory) {
        const target = hostRef.current?.querySelector<HTMLElement>(`[data-module-id="${CSS.escape(module.id)}"]`);
        if (!target || target.getBoundingClientRect().top > stickyOffset) break;
        nextId = module.id;
      }
      if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) {
        nextId = directory[directory.length - 1]?.id;
      }
      if (nextId) setActiveId((current) => current === nextId ? current : nextId);
    };
    updateActiveDirectory();
    window.addEventListener("scroll", updateActiveDirectory, { passive: true });
    window.addEventListener("resize", updateActiveDirectory);
    return () => {
      window.removeEventListener("scroll", updateActiveDirectory);
      window.removeEventListener("resize", updateActiveDirectory);
    };
  }, [directory, editor]);
  const scrollEditorTarget = (target: HTMLElement) => {
    const scroller = target.closest<HTMLElement>(".canvas-stage");
    if (!scroller) return;
    const targetRect = target.getBoundingClientRect();
    const scrollerRect = scroller.getBoundingClientRect();
    const targetTop = targetRect.top - scrollerRect.top + scroller.scrollTop;
    const stickySafeTop = 92;
    const availableHeight = Math.max(120, scroller.clientHeight - stickySafeTop - 20);
    const targetViewportTop = targetRect.height >= availableHeight
      ? stickySafeTop
      : stickySafeTop + (availableHeight - targetRect.height) / 2;
    const nextScrollTop = Math.max(0, targetTop - targetViewportTop);
    if (typeof scroller.scrollTo === "function") scroller.scrollTo({ top: nextScrollTop, behavior: "smooth" });
    else scroller.scrollTop = nextScrollTop;
  };
  const directoryNode = directory.length ? <nav ref={directoryRef} className="card-directory" aria-label={directoryAriaLabel}>{directory.map((module) => <button className={`directory-link ${activeId === module.id ? "active" : ""}`} type="button" key={module.id} onClick={() => { setActiveId(module.id); const target = hostRef.current?.querySelector<HTMLElement>(`[data-module-id="${CSS.escape(module.id)}"]`); if (target) { if (editor) scrollEditorTarget(target); else { const directoryHeight = directoryRef.current?.getBoundingClientRect().height || 50; window.scrollTo({ top: Math.max(0, window.scrollY + target.getBoundingClientRect().top - directoryHeight - 8), behavior: "smooth" }); } } onSelectModule?.(module.id); }}>{module.title.replace("个人", "")}</button>)}</nav> : null;
  let directoryRendered = false;
  const content = visible.map((module) => {
    const inner = StudioModuleContent({ module, editor, onOpenItem, onAction, onAssistant, onSelectModule });
    const element = inner as ReactElement<{ className?: string; children?: ReactNode }>;
    const exactModule = isValidElement(element) ? cloneElement(element, {
      id: `bp-template-block-${module.id}`,
      className: [element.props.className, editor ? "is-editor" : "", selectedModuleId === module.id ? "is-selected" : ""].filter(Boolean).join(" "),
      "data-module-id": module.id,
      "data-card-page-block": module.id,
      "data-template-block": module.type,
      tabIndex: -1,
      onClick: () => onSelectModule?.(module.id),
      children: <>{renderModuleHandle ? <div className="studio-editor-affordance">{renderModuleHandle(module)}</div> : null}{element.props.children}</>,
    } as Record<string, unknown>) : inner;
    if (module.type === "identity") { directoryRendered = true; return <Fragment key={module.id}>{exactModule}{directoryNode}</Fragment>; }
    return <div className="card-content" key={module.id}>{exactModule}</div>;
  });
  return <main ref={hostRef} className={["card-page", className].filter(Boolean).join(" ")} data-card-page-experience>
    <header className="card-topbar">{onBack ? <button className="icon-button" type="button" onClick={onBack}><StudioIcon name="arrowLeft"/><span className="sr-only">返回</span></button> : <span className="icon-button card-topbar-placeholder" aria-hidden="true"/>}<strong>{title}</strong><button className="icon-button" type="button" onClick={onShare}><StudioIcon name="share"/><span className="sr-only">分享名片</span></button></header>
    {switchTarget ? <a className="card-page-switch" href={switchTarget.href} aria-label={switchTarget.ariaLabel}>{switchTarget.label}</a> : null}
    <section className="card-page-content-region" aria-label={contentAriaLabel}>
      {!directoryRendered ? directoryNode : null}{content}
    </section>
    {primaryAction || secondaryAction ? <div className="sticky-actions">{primaryAction ? <button className="action-primary" type="button" disabled={primaryAction.disabled} onClick={primaryAction.onClick}>{primaryAction.label}</button> : null}{secondaryAction ? <button className="action-secondary" type="button" disabled={secondaryAction.disabled} onClick={secondaryAction.onClick}>{secondaryAction.label}</button> : null}</div> : null}
  </main>;
}

export type StudioEditorShellProps = {
  topbar?: ReactNode;
  leftTabs?: ReactNode;
  leftPanel?: ReactNode;
  canvasToolbar?: ReactNode;
  canvas?: ReactNode;
  rightTabs?: ReactNode;
  rightPanel?: ReactNode;
  className?: string;
  children?: ReactNode;
};

export function StudioEditorShell({ topbar, leftTabs, leftPanel, canvasToolbar, canvas, rightTabs, rightPanel, className, children }: StudioEditorShellProps) {
  if (children) return <div className={["studio-shell", className].filter(Boolean).join(" ")}>{children}</div>;
  return <div className={["studio-shell", className].filter(Boolean).join(" ")}>
    <header className="studio-topbar">{topbar}</header>
    <div className="studio-grid">
      <aside className="studio-panel left"><div className="panel-tabs">{leftTabs}</div><div className="panel-scroll">{leftPanel}</div></aside>
      <section className="studio-canvas"><div className="canvas-toolbar">{canvasToolbar}</div><div className="canvas-stage">{canvas}</div></section>
      <aside className="studio-panel right"><div className="panel-tabs">{rightTabs}</div><div className="panel-scroll">{rightPanel}</div></aside>
    </div>
  </div>;
}

export function StudioModuleRow({ title, source, icon = "grid", selected, required, hidden, dragHandle, onSelect, actions, ariaLabel }: { title: string; source: string; icon?: StudioIconName; selected?: boolean; required?: boolean; hidden?: boolean; dragHandle?: ReactNode; onSelect?: () => void; actions?: ReactNode; ariaLabel?: string }) {
  return <div className={`module-row ${selected ? "selected" : ""}`}><span className="drag-handle">{dragHandle || <StudioIcon name="grip"/>}</span><span className="module-icon"><StudioIcon name={icon}/></span><span className="module-name" role="button" aria-label={ariaLabel} tabIndex={0} onClick={onSelect} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect?.(); } }}><strong>{title}</strong><small>{source}{required ? " · 必需模块" : ""}</small></span><span className="module-actions">{required ? <span className="required-badge">必需</span> : actions || <span className="required-badge">{hidden ? "隐藏" : "显示"}</span>}</span></div>;
}

export function StudioInspectorTitle({ icon = "settings", title, description }: { icon?: StudioIconName; title: string; description: string }) {
  return <div className="inspector-title"><span className="module-icon"><StudioIcon name={icon}/></span><div><h2>{title}</h2><p>{description}</p></div></div>;
}

export function StudioInspectorSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="inspector-section"><h3>{title}</h3>{children}</section>;
}

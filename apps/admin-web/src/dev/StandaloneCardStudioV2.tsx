import {
  StudioCardPage,
  StudioEditorShell,
  StudioIcon,
  StudioInspectorSection,
  StudioInspectorTitle,
  StudioModuleRow,
  type StudioIdentity,
  type StudioModule,
} from "@cf/card-page-renderer";
import { useMemo, useState, type ChangeEvent } from "react";

import { CardStudioEditorSurface } from "../components/enterprise-template/CardStudioEditorSurface";
import employeePortraitUrl from "../../../card-web/public/tenants/template/assets/card-ui/demo-owner-1024.webp";
import employeeBackgroundUrl from "../../../card-web/public/tenants/template/assets/template-hero.webp";
import enterpriseBackgroundUrl from "../../../card-web/public/tenants/template/assets/card-ui/enterprise-city-1600.webp";
import enterpriseLogoUrl from "../../../card-web/public/tenants/tuotu/assets/tuotu-logo.webp";
import caseImageUrl from "./assets/preview-case.svg";
import productImageUrl from "./assets/preview-smart-card.svg";
import "./StandaloneCardStudioV2.css";

type CardKind = "employee" | "enterprise";
type IdentityFact = { id: string; label: string; value: string };
type QuickEntryDraft = { id: string; title: string; target: string; imageUrl?: string };

const employeeContacts = [
  { id: "phone", kind: "phone" as const, label: "电话", value: "138 8888 6666", href: "tel:13888886666" },
  { id: "wechat", kind: "wechat" as const, label: "微信", value: "xusongbo_cbiz" },
  { id: "email", kind: "email" as const, label: "邮箱", value: "xusongbo@tuozhe.com", href: "mailto:xusongbo@tuozhe.com" },
  { id: "location", kind: "location" as const, label: "地址", value: "浙江杭州", href: "https://maps.example.com/hangzhou" },
];

const initialEnterpriseFacts: IdentityFact[] = [
  { id: "founded", label: "成立时间", value: "2016 年" },
  { id: "headquarters", label: "总部地点", value: "杭州" },
  { id: "scale", label: "企业规模", value: "500–1000 人" },
  { id: "industry", label: "行业领域", value: "人工智能与企业服务" },
];

const initialQuickEntries: QuickEntryDraft[] = [
  { id: "official", title: "企业官网", target: "https://tuozhe.ai", imageUrl: enterpriseLogoUrl },
];

function readFile(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => typeof reader.result === "string" ? resolve(reader.result) : reject(new Error("图片读取失败")));
    reader.addEventListener("error", () => reject(reader.error ?? new Error("图片读取失败")));
    reader.readAsDataURL(file);
  });
}

function moveItem<T>(items: T[], index: number, direction: -1 | 1) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= items.length) return items;
  const next = [...items];
  [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
  return next;
}

function targetSummary(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "尚未填写地址";
  try {
    const url = new URL(trimmed);
    return `访问 ${url.hostname.replace(/^www\./, "")}`;
  } catch {
    return trimmed.length > 24 ? `${trimmed.slice(0, 24)}…` : trimmed;
  }
}

function StringListEditor({
  items,
  onChange,
  itemLabel,
  addLabel,
  max,
}: {
  items: string[];
  onChange: (items: string[]) => void;
  itemLabel: string;
  addLabel: string;
  max: number;
}) {
  return <div className="v2-lab-repeat-editor">
    {items.map((item, index) => <div className="v2-lab-repeat-row" key={`${itemLabel}-${index}`}>
      <span className="v2-lab-order-actions">
        <button type="button" aria-label={`上移${itemLabel}${index + 1}`} disabled={index === 0} onClick={() => onChange(moveItem(items, index, -1))}>↑</button>
        <button type="button" aria-label={`下移${itemLabel}${index + 1}`} disabled={index === items.length - 1} onClick={() => onChange(moveItem(items, index, 1))}>↓</button>
      </span>
      <input aria-label={`${itemLabel}${index + 1}`} value={item} maxLength={24} onChange={(event) => onChange(items.map((value, itemIndex) => itemIndex === index ? event.target.value : value))}/>
      <button className="v2-lab-delete" type="button" aria-label={`删除${itemLabel}${index + 1}`} onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))}>删除</button>
    </div>)}
    <button className="v2-lab-add" type="button" disabled={items.length >= max} onClick={() => onChange([...items, ""])}>＋ {addLabel}</button>
    <small className="v2-lab-limit">最多 {max} 项，拖动语义由上移/下移按钮保证键盘也可操作。</small>
  </div>;
}

function FactsEditor({ facts, onChange }: { facts: IdentityFact[]; onChange: (facts: IdentityFact[]) => void }) {
  return <div className="v2-lab-repeat-editor">
    {facts.map((fact, index) => <div className="v2-lab-fact-row" key={fact.id}>
      <span className="v2-lab-order-actions">
        <button type="button" aria-label={`上移企业信息项${index + 1}`} disabled={index === 0} onClick={() => onChange(moveItem(facts, index, -1))}>↑</button>
        <button type="button" aria-label={`下移企业信息项${index + 1}`} disabled={index === facts.length - 1} onClick={() => onChange(moveItem(facts, index, 1))}>↓</button>
      </span>
      <div className="v2-lab-fact-fields">
        <label><span>小标题</span><input aria-label={`企业信息项${index + 1}小标题`} value={fact.label} maxLength={8} onChange={(event) => onChange(facts.map((value) => value.id === fact.id ? { ...value, label: event.target.value } : value))}/></label>
        <label><span>内容</span><input aria-label={`企业信息项${index + 1}内容`} value={fact.value} maxLength={24} onChange={(event) => onChange(facts.map((value) => value.id === fact.id ? { ...value, value: event.target.value } : value))}/></label>
      </div>
      <button className="v2-lab-delete" type="button" aria-label={`删除企业信息项${index + 1}`} onClick={() => onChange(facts.filter((value) => value.id !== fact.id))}>删除</button>
    </div>)}
    <button className="v2-lab-add" type="button" disabled={facts.length >= 4} onClick={() => onChange([...facts, { id: `fact-${Date.now()}`, label: "新信息", value: "待填写" }])}>＋ 添加企业信息项</button>
    <small className="v2-lab-limit">最多 4 项；标题和内容都可自定义。</small>
  </div>;
}

function identityFixture({
  kind,
  employeePositioning,
  employeeTitles,
  employeeTags,
  enterprisePositioning,
  enterpriseFacts,
  enterpriseTags,
}: {
  kind: CardKind;
  employeePositioning: string;
  employeeTitles: string[];
  employeeTags: string[];
  enterprisePositioning: string;
  enterpriseFacts: IdentityFact[];
  enterpriseTags: string[];
}): StudioIdentity {
  if (kind === "employee") {
    return {
      variant: "v2",
      kind,
      name: "徐松波",
      imageUrl: employeePortraitUrl,
      verificationLabel: "已认证",
      headline: employeePositioning,
      titles: employeeTitles.filter(Boolean),
      companyName: "拓浙 AI 集团",
      tags: employeeTags.filter(Boolean),
      contacts: employeeContacts,
      background: { imageUrl: employeeBackgroundUrl, fit: "cover", position: "center", opacity: .13, overlay: "light" },
    };
  }
  return {
    variant: "v2",
    kind,
    name: "拓浙 AI 集团",
    imageUrl: enterpriseLogoUrl,
    verificationLabel: "已认证企业",
    headline: enterprisePositioning,
    facts: enterpriseFacts.filter((item) => item.label.trim() && item.value.trim()),
    tags: enterpriseTags.filter(Boolean),
    contacts: [
      { id: "website", kind: "website", label: "官网", value: "tuozhe.ai", href: "https://tuozhe.ai" },
      { id: "phone", kind: "phone", label: "电话", value: "400-888-8888", href: "tel:4008888888" },
      { id: "location", kind: "location", label: "地址", value: "浙江杭州", href: "https://maps.example.com/hangzhou" },
      { id: "wechat", kind: "wechat", label: "企业微信", value: "拓浙 AI" },
    ],
    background: { imageUrl: enterpriseBackgroundUrl, fit: "cover", position: "center", opacity: .11, overlay: "light" },
  };
}

export function StandaloneCardStudioV2() {
  const [kind, setKind] = useState<CardKind>("employee");
  const [selectedModuleId, setSelectedModuleId] = useState("identity");
  const [wide, setWide] = useState(false);
  const [employeePositioning, setEmployeePositioning] = useState("AI 人才与产业项目共创");
  const [employeeTitles, setEmployeeTitles] = useState(["创始人", "总经理", "企业 AI 顾问"]);
  const [employeeTags, setEmployeeTags] = useState(["企业 AI", "产品战略", "人才共创"]);
  const [enterprisePositioning, setEnterprisePositioning] = useState("AI 人才发展与产业场景服务");
  const [enterpriseFacts, setEnterpriseFacts] = useState(initialEnterpriseFacts);
  const [enterpriseTags, setEnterpriseTags] = useState(["高新技术企业", "产学研共创"]);
  const [entryTitle, setEntryTitle] = useState("快捷入口");
  const [showEntryTitle, setShowEntryTitle] = useState(true);
  const [entryLayout, setEntryLayout] = useState<"auto" | "horizontal">("auto");
  const [quickEntries, setQuickEntries] = useState(initialQuickEntries);
  const [notice, setNotice] = useState("真实生产组件 · 当前仅使用本地 fixture 数据");

  const modules = useMemo<StudioModule[]>(() => [
    {
      id: "identity",
      type: "identity",
      title: "基础名片",
      source: kind === "employee" ? "企业员工" : "企业资料",
      identity: identityFixture({ kind, employeePositioning, employeeTitles, employeeTags, enterprisePositioning, enterpriseFacts, enterpriseTags }),
      directoryEnabled: false,
    },
    { id: "overview", type: "overview", title: "概览", source: kind === "employee" ? "员工信息" : "企业资料", body: kind === "employee" ? "连接企业真实场景、高校创新资源与青年 AI 人才，让项目更快发生。" : "把企业公开资料、业务能力与合作入口整理成可信、清晰的数字名片。" },
    { id: "services", type: "services", title: "核心业务", source: "业务库", layout: "grid", items: [
      { id: "service-ai", title: "企业 AI 服务", summary: "业务诊断、方案设计与工程落地", imageUrl: productImageUrl },
      { id: "service-talent", title: "人才项目共创", summary: "连接高校人才与产业真实需求" },
      { id: "service-event", title: "品牌赛事", summary: "AI + X 主题黑客松与成果转化" },
    ] },
    {
      id: "quick",
      type: "actions",
      title: entryTitle || "快捷入口",
      source: "自定义链接",
      actionTemplate: "quick",
      showTitle: showEntryTitle,
      layout: entryLayout,
      items: quickEntries.map((entry) => ({ id: entry.id, title: entry.title, subtitle: targetSummary(entry.target), href: entry.target || "#", imageUrl: entry.imageUrl })),
    },
    { id: "cases", type: "cases", title: "代表案例", source: "案例库", layout: "stack", items: [
      { id: "case-1", title: "旅游企业智能化服务", summary: "从录入审核到经营分析，逐步建立可信数据与业务自动化。", imageUrl: caseImageUrl, result: "一线操作更轻，管理决策更快" },
    ] },
    { id: "faq", type: "faq", title: "常见问题", source: "真实问答库", items: [
      { id: "faq-1", question: "如何开始企业 AI 合作？", answer: "先从真实业务问题和现有资料开始，共同确认目标、数据边界与验证方式。" },
    ] },
  ], [employeePositioning, employeeTags, employeeTitles, enterpriseFacts, enterprisePositioning, enterpriseTags, entryLayout, entryTitle, kind, quickEntries, showEntryTitle]);

  const selected = modules.find((module) => module.id === selectedModuleId) ?? modules[0];

  const uploadQuickIcon = async (entryId: string, event: ChangeEvent<HTMLInputElement>) => {
    const [file] = event.target.files ?? [];
    if (!file) return;
    const imageUrl = await readFile(file);
    setQuickEntries((items) => items.map((item) => item.id === entryId ? { ...item, imageUrl } : item));
    setNotice("快捷入口图片已更新；名称和跳转地址保持不变。");
  };

  const leftPanel = <>
    <p className="panel-hint">此页面直接运行生产 renderer；切换的只有 fixture 数据和 opt-in V2 variant。</p>
    <div className="module-list">{modules.map((module) => <StudioModuleRow
      key={module.id}
      title={module.title}
      source={module.source}
      icon={module.type === "identity" ? (kind === "employee" ? "user" : "building") : module.type === "actions" ? "external" : module.type === "services" ? "briefcase" : module.type === "cases" ? "image" : module.type === "faq" ? "help" : "grid"}
      selected={selectedModuleId === module.id}
      required={module.type === "identity"}
      onSelect={() => setSelectedModuleId(module.id)}
    />)}</div>
    <div className="v2-lab-fixed-region"><span>页面固定区域</span><StudioModuleRow title="底部行动栏" source="电话 · 微信 · 咨询 AI" icon="grid" onSelect={() => setNotice("底部行动栏始终固定，不参与正文模块排序。")}/></div>
  </>;

  const identityInspector = <>
    <StudioInspectorTitle icon={kind === "employee" ? "user" : "building"} title={kind === "employee" ? "员工基础名片 V2" : "企业基础名片 V2"} description="资料字段直接编辑，展示设置留在名片模板"/>
    <StudioInspectorSection title="名片类型">
      <div className="v2-lab-choice-grid">
        <button className={kind === "employee" ? "active" : ""} type="button" onClick={() => setKind("employee")}><StudioIcon name="user"/><strong>员工名片</strong><small>突出个人身份与联系方式</small></button>
        <button className={kind === "enterprise" ? "active" : ""} type="button" onClick={() => setKind("enterprise")}><StudioIcon name="building"/><strong>企业名片</strong><small>突出企业事实与品牌</small></button>
      </div>
    </StudioInspectorSection>
    <StudioInspectorSection title="真实数据来源">
      <div className="source-card"><strong>{kind === "employee" ? "企业员工" : "企业资料"}</strong><span>当前为类型一致的 fixture</span></div>
      <p className="v2-lab-note">{kind === "employee" ? "正式接入后，这里的修改写回企业员工，所有关联名片同步。" : "正式接入后，这里的修改写回企业资料，所有企业名片同步。"}</p>
    </StudioInspectorSection>
    {kind === "employee" ? <>
      <StudioInspectorSection title="个人定位"><label className="field"><span>一句话定位</span><input aria-label="个人定位" value={employeePositioning} maxLength={24} onChange={(event) => setEmployeePositioning(event.target.value)}/></label></StudioInspectorSection>
      <StudioInspectorSection title="身份头衔"><StringListEditor items={employeeTitles} onChange={setEmployeeTitles} itemLabel="身份头衔" addLabel="添加身份" max={5}/></StudioInspectorSection>
      <StudioInspectorSection title="专业标签"><StringListEditor items={employeeTags} onChange={setEmployeeTags} itemLabel="专业标签" addLabel="添加标签" max={3}/></StudioInspectorSection>
    </> : <>
      <StudioInspectorSection title="企业定位"><label className="field"><span>一句话定位</span><input aria-label="企业定位" value={enterprisePositioning} maxLength={24} onChange={(event) => setEnterprisePositioning(event.target.value)}/></label></StudioInspectorSection>
      <StudioInspectorSection title="企业信息项"><FactsEditor facts={enterpriseFacts} onChange={setEnterpriseFacts}/></StudioInspectorSection>
      <StudioInspectorSection title="企业标签"><StringListEditor items={enterpriseTags} onChange={setEnterpriseTags} itemLabel="企业标签" addLabel="添加标签" max={3}/></StudioInspectorSection>
    </>}
  </>;

  const quickInspector = <>
    <StudioInspectorTitle icon="external" title="快捷入口" description="只保留图标、名称和跳转地址"/>
    <StudioInspectorSection title="区块设置">
      <label className="field"><span>区块标题</span><input aria-label="快捷入口区块标题" value={entryTitle} maxLength={20} onChange={(event) => setEntryTitle(event.target.value)}/></label>
      <label className="v2-lab-switch"><span><strong>显示区块标题</strong><small>关闭后只显示入口内容</small></span><input type="checkbox" checked={showEntryTitle} onChange={(event) => setShowEntryTitle(event.target.checked)}/></label>
    </StudioInspectorSection>
    <StudioInspectorSection title="排列方式">
      <div className="v2-lab-segmented"><button className={entryLayout === "auto" ? "active" : ""} type="button" onClick={() => setEntryLayout("auto")}>自动</button><button className={entryLayout === "horizontal" ? "active" : ""} type="button" onClick={() => setEntryLayout("horizontal")}>横向滑动</button></div>
      <p className="v2-lab-note">1 个为轻量单行；2–4 个自适应；超过 4 个显示前三项和“更多”。</p>
    </StudioInspectorSection>
    <StudioInspectorSection title="入口内容">
      <div className="v2-lab-quick-editor">{quickEntries.map((entry, index) => <div className="v2-lab-quick-row" key={entry.id}>
        <label className="v2-lab-quick-upload">
          <span>{entry.imageUrl ? <img src={entry.imageUrl} alt={`${entry.title || "快捷入口"}图标`}/> : <StudioIcon name="external"/>}</span>
          <small>更换图标</small>
          <input type="file" accept="image/png,image/jpeg,image/webp" aria-label={`上传快捷入口${index + 1}图标`} onChange={(event) => void uploadQuickIcon(entry.id, event)}/>
        </label>
        <div className="v2-lab-quick-fields">
          <label><span>名称</span><input aria-label={`快捷入口${index + 1}名称`} value={entry.title} maxLength={12} onChange={(event) => setQuickEntries((items) => items.map((item) => item.id === entry.id ? { ...item, title: event.target.value } : item))}/></label>
          <label><span>跳转地址</span><input aria-label={`快捷入口${index + 1}跳转地址`} value={entry.target} onChange={(event) => setQuickEntries((items) => items.map((item) => item.id === entry.id ? { ...item, target: event.target.value } : item))}/></label>
        </div>
        <span className="v2-lab-quick-actions">
          <button type="button" aria-label={`上移快捷入口${index + 1}`} disabled={index === 0} onClick={() => setQuickEntries((items) => moveItem(items, index, -1))}>↑</button>
          <button type="button" aria-label={`下移快捷入口${index + 1}`} disabled={index === quickEntries.length - 1} onClick={() => setQuickEntries((items) => moveItem(items, index, 1))}>↓</button>
          <button type="button" aria-label={`删除快捷入口${index + 1}`} onClick={() => setQuickEntries((items) => items.filter((item) => item.id !== entry.id))}>删除</button>
        </span>
      </div>)}</div>
      <button className="v2-lab-add" type="button" disabled={quickEntries.length >= 8} onClick={() => setQuickEntries((items) => [...items, { id: `entry-${Date.now()}`, title: "新入口", target: "https://example.com" }])}>＋ 添加快捷入口</button>
      <small className="v2-lab-limit">最多 8 个；公开名片始终只占 4 个位置。</small>
    </StudioInspectorSection>
  </>;

  return <CardStudioEditorSurface>
    <StudioEditorShell
      className="v2-lab-shell"
      topbar={<><div className="studio-brand"><span className="document-title">基础名片 V2 · 生产组件预览</span><span className="autosave"><StudioIcon name="check"/>{notice}</span></div><div className="studio-history"><span className="v2-lab-contract">React / TypeScript / 共享 Renderer</span></div><div className="studio-actions"><button className="toolbar-button" type="button" onClick={() => setNotice("fixture 恢复请刷新页面；正式数据未被修改。")}>恢复说明</button><button className="toolbar-button primary" type="button" onClick={() => setNotice("当前前端方案已标记；尚未写入正式 API。")}>标记方案</button></div></>}
      leftTabs={<><button className="panel-tab active" type="button">页面结构</button><button className="panel-tab" type="button">假数据说明</button></>}
      leftPanel={leftPanel}
      canvasToolbar={<><div className="segmented"><button className={!wide ? "active" : ""} type="button" aria-label="手机预览" onClick={() => setWide(false)}><StudioIcon name="user"/></button><button className={wide ? "active" : ""} type="button" aria-label="宽屏预览" onClick={() => setWide(true)}><StudioIcon name="grid"/></button></div><div className="v2-lab-kind-switch"><button className={kind === "employee" ? "active" : ""} type="button" onClick={() => { setKind("employee"); setSelectedModuleId("identity"); }}>员工</button><button className={kind === "enterprise" ? "active" : ""} type="button" onClick={() => { setKind("enterprise"); setSelectedModuleId("identity"); }}>企业</button></div></>}
      canvas={<div className={`editor-preview ${wide ? "wide" : ""}`}><div className="public-frame"><StudioCardPage modules={modules} title={kind === "employee" ? "徐松波的数字名片" : "拓浙 AI 集团企业名片"} editor selectedModuleId={selectedModuleId} onSelectModule={setSelectedModuleId} primaryAction={{ label: "咨询 AI", onClick: () => setNotice("底部咨询 AI 已触发。") }} secondaryAction={{ label: kind === "employee" ? "联系本人" : "联系企业", onClick: () => setNotice("底部联系入口已触发。") }}/></div></div>}
      rightTabs={<><button className="panel-tab active" type="button">内容与展示</button><button className="panel-tab" type="button">样式设置</button></>}
      rightPanel={selected?.type === "actions" ? quickInspector : identityInspector}
    />
  </CardStudioEditorSurface>;
}

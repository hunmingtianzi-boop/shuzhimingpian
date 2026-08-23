import {
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  Field,
  Input,
  MessageBar,
  MessageBarBody,
  ProgressBar,
  Textarea,
} from "@fluentui/react-components";
import {
  ArrowClockwise24Regular,
  ArrowUpload24Regular,
  CheckmarkCircle24Regular,
  Copy24Regular,
  Dismiss24Regular,
  Sparkle24Regular,
} from "@fluentui/react-icons";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import type {
  ConfirmPlatformOnboardingInput,
  PlatformOnboardingSession,
  PlatformOnboardingCandidate,
  PlatformOnboardingCandidateCategory,
  PlatformOnboardingSuggestion,
  StartPlatformOnboardingInput,
} from "../api/types";
import { validateKnowledgeImportFiles } from "../components/KnowledgeImportPanel";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import {
  buildOnboardingDeliveryUrls,
  ONBOARDING_CONFIRM_UNCERTAIN_CODE,
} from "../utils/platformOnboarding";

import styles from "./PlatformOnboardingPage.module.css";

export type PlatformOnboardingImportItem = {
  id: string;
  fileName: string;
  status: "pending" | "processing" | "completed" | "failed" | "dead_letter";
  errorCode?: string;
  errorMessage?: string;
};

export type PlatformOnboardingOperationError = {
  status?: number;
  code?: string;
  message: string;
  requestId?: string;
};

export type PlatformOnboardingAdminSummary = {
  account: string;
  displayName: string;
};

type ReviewValues = {
  legalName: string;
  shortName: string;
  subjectType: "domestic_enterprise" | "association" | "overseas" | "pending_registration";
  socialCreditCode: string;
  industry: string;
  summary: string;
  website: string;
};

type ReviewSeed = Partial<ReviewValues> & {
  tenantName?: string;
  companyName?: string;
  initialCardDisplayName?: string;
  initialCardTitle?: string;
  assistantName?: string;
  welcomeMessage?: string;
};

type StartIdentityValues = {
  displayName: string;
  legalName: string;
  shortName: string;
  subjectType: ReviewValues["subjectType"];
  socialCreditCode: string;
  industry: string;
  adminAccount: string;
  adminDisplayName: string;
};

export type PlatformOnboardingPageProps = {
  session?: PlatformOnboardingSession | null;
  sessions?: PlatformOnboardingSession[];
  importItems?: PlatformOnboardingImportItem[];
  adminSummary?: PlatformOnboardingAdminSummary;
  initialReview?: ReviewSeed;
  llmAvailability: "ready" | "unavailable" | "failed";
  resourceStatus?: "ready" | "loading" | "permission" | "error";
  resourceError?: PlatformOnboardingOperationError;
  onStart: (input: StartPlatformOnboardingInput) => Promise<void>;
  onOpenSession?: (onboardingSessionId: string) => void;
  onRename?: (
    onboardingSessionId: string,
    expectedVersion: number,
    displayName: string,
  ) => Promise<void>;
  onUpload: (onboardingSessionId: string, files: File[]) => Promise<void>;
  onGenerate: (onboardingSessionId: string, expectedVersion: number) => Promise<void>;
  onUpdateCandidate?: (
    onboardingSessionId: string,
    candidate: PlatformOnboardingCandidate,
  ) => Promise<void>;
  onIgnoreCandidate?: (
    onboardingSessionId: string,
    candidate: PlatformOnboardingCandidate,
  ) => Promise<void>;
  onConfirm: (
    onboardingSessionId: string,
    input: ConfirmPlatformOnboardingInput,
  ) => Promise<PlatformOnboardingSession | void>;
  onCancel: (
    onboardingSessionId: string,
    reason: string,
    expectedVersion: number,
  ) => Promise<void>;
  onRegenerateTemporaryCredential?: (
    onboardingSessionId: string,
    expectedVersion: number,
  ) => Promise<PlatformOnboardingSession | void>;
  onRefresh?: () => void;
  onStartAnother?: () => void;
  onOpenEnterprises?: () => void;
};

type BusyOperation =
  | "start"
  | "rename"
  | "upload"
  | "generate"
  | "confirm"
  | "cancel"
  | "regenerate";

const emptyStart: StartIdentityValues = {
  displayName: "",
  legalName: "",
  shortName: "",
  subjectType: "domestic_enterprise",
  socialCreditCode: "",
  industry: "",
  adminAccount: "",
  adminDisplayName: "",
};

const emptyReview: ReviewValues = {
  legalName: "",
  shortName: "",
  subjectType: "domestic_enterprise",
  socialCreditCode: "",
  industry: "",
  summary: "",
  website: "",
};

const socialCreditCodePattern = /^[0-9A-Z]{18}$/;

const reviewFieldMeta: Array<{
  key: keyof ReviewValues;
  label: string;
  area?: boolean;
  required?: boolean;
  group: "identity" | "presentation";
}> = [
  { key: "legalName", label: "企业正式名称", required: true, group: "identity" },
  { key: "shortName", label: "企业简称", group: "identity" },
  { key: "subjectType", label: "主体类型", required: true, group: "identity" },
  { key: "socialCreditCode", label: "统一社会信用代码", group: "identity" },
  { key: "industry", label: "行业", group: "identity" },
  { key: "website", label: "企业网站", group: "presentation" },
  { key: "summary", label: "企业简介", area: true, group: "presentation" },
];

const suggestionFieldMap: Record<string, keyof ReviewValues> = {
  legal_name: "legalName",
  legalName: "legalName",
  company_name: "legalName",
  companyName: "legalName",
  short_name: "shortName",
  shortName: "shortName",
  tenant_name: "shortName",
  tenantName: "shortName",
  subject_type: "subjectType",
  subjectType: "subjectType",
  social_credit_code: "socialCreditCode",
  socialCreditCode: "socialCreditCode",
  industry: "industry",
  website: "website",
  summary: "summary",
};

const businessProfileLabels: Record<string, string> = {
  business_positioning: "业务定位",
  products_services: "产品与服务",
  target_customers: "目标客户与场景",
  customer_pain_points: "客户痛点",
  core_capabilities: "核心能力",
  business_model: "业务与交付模式",
  differentiators: "可验证差异点",
  business_directions: "明确业务方向",
  sales_opening: "建议业务开场",
  evidence_conflicts: "资料冲突与待确认项",
  missing_information: "待补资料",
};

const candidateCategoryLabels: Record<PlatformOnboardingCandidateCategory, string> = {
  enterprise_profile: "企业资料",
  products: "核心业务",
  case_studies: "案例",
  faqs: "知识 FAQ",
  unclassified: "待判断",
};

const candidateFieldLabels: Record<string, string> = {
  company_name: "企业名称",
  summary: "摘要",
  industry: "行业",
  region: "地区",
  website: "官网",
  name: "名称",
  category: "分类",
  detail: "详细内容",
  audience: "适用对象",
  price_boundary: "价格边界",
  title: "标题",
  client_display_name: "客户名称",
  background: "项目背景",
  solution: "解决方案",
  result: "项目成果",
  question: "问题",
  answer: "答案",
  text: "原始内容",
  reason: "待判断原因",
};

const candidatePayloadDefaults: Record<
  PlatformOnboardingCandidateCategory,
  Record<string, string>
> = {
  enterprise_profile: { company_name: "", summary: "", industry: "", region: "", website: "" },
  products: { name: "", category: "", summary: "", detail: "", audience: "", price_boundary: "" },
  case_studies: { title: "", industry: "", client_display_name: "", background: "", solution: "", result: "" },
  faqs: { question: "", answer: "" },
  unclassified: { text: "", reason: "" },
};

function candidateTitle(candidate: PlatformOnboardingCandidate): string {
  return candidate.payload.title
    || candidate.payload.name
    || candidate.payload.question
    || candidate.payload.company_name
    || "未命名候选";
}

const candidateRequiredFields: Partial<
  Record<PlatformOnboardingCandidateCategory, string[]>
> = {
  enterprise_profile: ["company_name"],
  products: ["name", "summary", "detail"],
  case_studies: ["title", "background", "solution", "result"],
  faqs: ["question", "answer"],
};

function candidateComplete(candidate: PlatformOnboardingCandidate): boolean {
  return (candidateRequiredFields[candidate.category] ?? []).every((field) =>
    Boolean(candidate.payload[field]?.trim()),
  );
}

function candidateSelectedByDefault(candidate: PlatformOnboardingCandidate): boolean {
  return candidate.status === "pending_review"
    && candidate.category !== "unclassified"
    && candidateComplete(candidate);
}

function candidateApplyFields(candidate: PlatformOnboardingCandidate): string[] {
  return candidate.category === "enterprise_profile"
    ? Object.entries(candidate.payload)
        .filter(([, value]) => Boolean(value.trim()))
        .map(([field]) => field)
    : [];
}

const onboardingStatusLabels: Record<PlatformOnboardingSession["status"], string> = {
  draft: "待上传",
  processing: "处理中",
  review: "待复核",
  manual_required: "需人工处理",
  ready_to_confirm: "待确认",
  confirmed: "已确认",
  cancelled: "已取消",
  expired: "已过期",
  failed: "失败",
};

function formatDateTime(value?: string): string {
  if (!value) return "未设置";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
}

function normalizeSocialCreditCode(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

function reviewSeedFromSession(
  session: PlatformOnboardingSession,
  initialReview?: ReviewSeed,
): ReviewValues {
  const socialCreditCode = normalizeSocialCreditCode(initialReview?.socialCreditCode ?? "");
  const legalName = initialReview?.legalName
    ?? initialReview?.companyName
    ?? session.legalName
    ?? session.tenantName
    ?? "";
  const shortName = initialReview?.shortName
    ?? session.shortName
    ?? initialReview?.tenantName
    ?? "";
  return {
    ...emptyReview,
    ...initialReview,
    legalName,
    shortName,
    socialCreditCode,
    subjectType:
      initialReview?.subjectType
      ?? session.subjectType
      ?? (socialCreditCode ? "domestic_enterprise" : "pending_registration"),
    industry: initialReview?.industry ?? session.industry ?? "",
  };
}

function confirmationPayload(
  review: ReviewValues,
  sessionVersion: number,
  candidateSelections: Array<{ id: string; expectedVersion: number; applyFields: string[] }>,
): ConfirmPlatformOnboardingInput {
  const legalName = review.legalName.trim();
  const shortName = review.shortName.trim();
  const subjectType = review.subjectType;
  const socialCreditCode = normalizeSocialCreditCode(review.socialCreditCode);
  return {
    expectedVersion: sessionVersion,
    candidateSelections,
    legalName,
    shortName: shortName || undefined,
    subjectType,
    socialCreditCode: socialCreditCode || undefined,
    industry: review.industry.trim() || undefined,
    summary: review.summary.trim() || undefined,
    website: review.website.trim() || undefined,
  };
}

const stepLabels = ["基础信息", "上传解析", "智能分析", "人工确认", "完成"];

function sessionStep(session?: PlatformOnboardingSession | null): number {
  if (!session) return 0;
  if (session.status === "confirmed") return 4;
  if (["review", "manual_required", "ready_to_confirm"].includes(session.status)) return 3;
  if (session.suggestions.length > 0) return 2;
  return 1;
}

function asOperationError(value: unknown): PlatformOnboardingOperationError {
  const error = value as Partial<PlatformOnboardingOperationError>;
  if (error?.code === "VERSION_CONFLICT") {
    return {
      status: 409,
      code: error.code ?? "VERSION_CONFLICT",
      message: "开通会话已被其他操作更新。请刷新后重新复核，避免覆盖最新版本。",
      requestId: error.requestId,
    };
  }
  if (error?.status === 403 || error?.code === "FORBIDDEN") {
    return {
      status: 403,
      code: error.code ?? "FORBIDDEN",
      message: "当前账号不能操作该开通会话，且未对临时企业授予任何访问权。",
      requestId: error.requestId,
    };
  }
  return {
    status: error?.status,
    code: error?.code ?? "ONBOARDING_OPERATION_FAILED",
    message: error?.message || "服务暂时无法完成此操作，请稍后重试。",
    requestId: error?.requestId,
  };
}

async function copyDeliveryUrl(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("copy failed");
}

function OperationError({
  error,
  onRecover,
}: {
  error: PlatformOnboardingOperationError;
  onRecover?: () => void;
}) {
  return (
    <MessageBar intent={error.code === "VERSION_CONFLICT" ? "warning" : "error"}>
      <MessageBarBody>
        <strong>{error.code === "VERSION_CONFLICT" ? "会话版本冲突" : "操作未完成"}</strong>
        <div>{error.message}</div>
        {(error.code || error.requestId) && (
          <div className={styles.errorReference}>
            {error.code && <span>错误代码：{error.code}</span>}
            {error.requestId && <span>请求编号：{error.requestId}</span>}
          </div>
        )}
        {onRecover && (
          <Button
            appearance="secondary"
            className={styles.recoveryButton}
            onClick={onRecover}
          >
            核对开通结果
          </Button>
        )}
      </MessageBarBody>
    </MessageBar>
  );
}

function StartPanel({
  busy,
  onStart,
  onPrepared,
}: {
  busy: boolean;
  onStart: (input: StartPlatformOnboardingInput) => Promise<void>;
  onPrepared?: (draft: StartIdentityValues) => void;
}) {
  const [input, setInput] = useState(emptyStart);
  const [attempted, setAttempted] = useState(false);
  const normalizedCreditCode = normalizeSocialCreditCode(input.socialCreditCode);
  const valid =
    Boolean(input.legalName.trim()) &&
    Boolean(input.adminAccount.trim()) &&
    Boolean(input.adminDisplayName.trim()) &&
    (!input.shortName || input.shortName.trim().length >= 2) &&
    (input.subjectType !== "domestic_enterprise" || socialCreditCodePattern.test(normalizedCreditCode));

  const update = <K extends keyof StartIdentityValues>(
    key: K,
    value: StartIdentityValues[K],
  ) => setInput((current) => ({ ...current, [key]: value }));

  return (
    <section className={styles.startPanel} aria-labelledby="onboarding-start-title">
      <div className={styles.sectionHeading}>
        <span>步骤 1 / 5</span>
        <h2 id="onboarding-start-title">填写开通基础信息</h2>
        <p>
          先锁定企业身份和管理员交付信息。企业确认前，管理员不能登录，也不会创建任何名片。
        </p>
      </div>
      <form
        className={styles.startForm}
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          setAttempted(true);
          if (valid && !busy) {
            onPrepared?.(input);
            void onStart({
              displayName: input.displayName.trim() || input.shortName.trim() || input.legalName.trim(),
              legalName: input.legalName.trim(),
              shortName: input.shortName.trim() || undefined,
              subjectType: input.subjectType,
              socialCreditCode: normalizedCreditCode || undefined,
              industry: input.industry.trim() || undefined,
              adminAccount: input.adminAccount.trim(),
              adminDisplayName: input.adminDisplayName.trim(),
            });
          }
        }}
      >
        <Field label="任务名称（可选）" hint="留空时系统会按企业名称、日期和序号生成。">
          <Input
            value={input.displayName ?? ""}
            onChange={(_, data) => update("displayName", data.value)}
          />
        </Field>
        <Field
          label="企业正式名称"
          required
          validationState={attempted && !input.legalName.trim() ? "error" : "none"}
          validationMessage={attempted && !input.legalName.trim() ? "请输入企业正式名称。" : undefined}
        >
          <Input
            value={input.legalName}
            onChange={(_, data) => update("legalName", data.value)}
          />
        </Field>
        <Field label="企业简称" hint="用于运营展示；留空时沿用正式名称。">
          <Input
            value={input.shortName}
            onChange={(_, data) => update("shortName", data.value)}
          />
        </Field>
        <Field label="主体类型" required>
          <select
            aria-label="主体类型"
            className={styles.nativeSelect}
            value={input.subjectType}
            onChange={(event) =>
              update(
                "subjectType",
                event.target.value as StartIdentityValues["subjectType"],
              )
            }
          >
            <option value="domestic_enterprise">国内企业</option>
            <option value="association">协会 / 机构</option>
            <option value="overseas">境外主体</option>
            <option value="pending_registration">筹备中</option>
          </select>
        </Field>
        <Field
          label="统一社会信用代码"
          validationState={
            attempted && input.subjectType === "domestic_enterprise" && !socialCreditCodePattern.test(normalizedCreditCode)
              ? "error"
              : "none"
          }
          validationMessage={
            attempted && input.subjectType === "domestic_enterprise" && !socialCreditCodePattern.test(normalizedCreditCode)
              ? "国内企业必须填写 18 位统一社会信用代码。"
              : input.subjectType === "domestic_enterprise"
                ? "将作为唯一业务租户标识，底层隔离仍使用不可变 UUID。"
                : "协会、境外主体和筹备企业可以留空，由服务端生成稳定标识。"
          }
        >
          <Input
            value={input.socialCreditCode}
            onChange={(_, data) => update("socialCreditCode", normalizeSocialCreditCode(data.value))}
          />
        </Field>
        <Field label="行业">
          <Input
            value={input.industry}
            onChange={(_, data) => update("industry", data.value)}
          />
        </Field>
        <Field label="管理员账号" required>
          <Input
            value={input.adminAccount}
            autoComplete="off"
            onChange={(_, data) => update("adminAccount", data.value)}
          />
        </Field>
        <Field label="管理员姓名" required>
          <Input
            value={input.adminDisplayName}
            onChange={(_, data) => update("adminDisplayName", data.value)}
          />
        </Field>
        <div className={styles.credentialNotice}>
          <strong>初始密码由系统在确认建企时生成</strong>
          <span>当前初始化只创建隔离企业与管理员交付信息，不创建任何名片或公开链接。</span>
        </div>
        <div className={styles.startActions}>
          <Button appearance="primary" type="submit" disabled={busy || (attempted && !valid)}>
            {busy ? "正在准备" : "进入资料导入"}
          </Button>
        </div>
      </form>
    </section>
  );
}

function Steps({ current }: { current: number }) {
  return (
    <nav className={styles.steps} aria-label="资料辅助建企进度">
      <ol>
        {stepLabels.map((label, index) => (
          <li key={label} aria-current={current === index ? "step" : undefined}>
            <span>{index + 1}</span>
            <strong>{label}</strong>
          </li>
        ))}
      </ol>
    </nav>
  );
}

type AnalysisPhaseState = "complete" | "active" | "pending";

function AnalysisProgress({
  hasImports,
  importsProcessing,
  generating,
  hasInsights,
  insightCount,
}: {
  hasImports: boolean;
  importsProcessing: boolean;
  generating: boolean;
  hasInsights: boolean;
  insightCount: number;
}) {
  const phases: Array<{ label: string; detail: string; state: AnalysisPhaseState }> = [
    {
      label: "接收资料",
      detail: hasImports ? "资料已进入隔离导入范围" : "等待选择企业资料",
      state: hasImports ? "complete" : "pending",
    },
    {
      label: "解析内容",
      detail: importsProcessing ? "正在提取可引用的文本与表格" : hasImports ? "解析结果可供归纳" : "上传后自动开始",
      state: importsProcessing ? "active" : hasImports ? "complete" : "pending",
    },
    {
      label: "归纳业务",
      detail: generating
        ? "正在识别业务定位、产品服务、客户与资料缺口"
        : hasInsights
          ? `已形成 ${insightCount} 项带来源结论`
          : "解析完成后由你手动启动",
      state: generating ? "active" : hasInsights ? "complete" : "pending",
    },
    {
      label: "人工复核",
      detail: hasInsights ? "请核对来源、冲突和低置信内容" : "不会自动写入或发布",
      state: hasInsights ? "active" : "pending",
    },
  ];

  const active = phases.find((phase) => phase.state === "active");
  return (
    <section className={styles.analysisProgress} aria-label="资料分析进度" aria-live="polite">
      <div className={styles.analysisLead}>
        <div>
          <span>{generating || importsProcessing ? "正在处理" : hasInsights ? "分析完成，等待复核" : "分析准备"}</span>
          <strong>{active?.detail ?? (hasImports ? "资料已准备，可以开始业务归纳" : "上传后会在这里显示真实处理进度")}</strong>
        </div>
        {(generating || importsProcessing) && <i aria-hidden />}
      </div>
      <ol>
        {phases.map((phase, index) => (
          <li key={phase.label} data-state={phase.state}>
            <span aria-hidden>{phase.state === "complete" ? "✓" : index + 1}</span>
            <div><strong>{phase.label}</strong><small>{phase.detail}</small></div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function confidenceText(value?: number): string {
  if (value === undefined) return "未提供置信提示";
  if (value >= 0.8) return "高置信";
  if (value >= 0.55) return "中等置信";
  return "低置信，建议重点核对";
}

function SuggestionCard({
  suggestion,
  onApply,
  label: explicitLabel,
  readOnly = false,
}: {
  suggestion: PlatformOnboardingSuggestion;
  onApply: () => void;
  label?: string;
  readOnly?: boolean;
}) {
  const field = suggestionFieldMap[suggestion.field];
  const label = explicitLabel ?? reviewFieldMeta.find((item) => item.key === field)?.label ?? suggestion.field;
  return (
    <article className={styles.suggestionCard} aria-label={`${label}建议`}>
      <header>
        <div>
          <strong>{label}</strong>
          <span>{confidenceText(suggestion.confidence)} · 生成版本 {suggestion.generationVersion}</span>
        </div>
        {!readOnly && <Button appearance="subtle" size="small" onClick={onApply} disabled={!field}>采用建议</Button>}
      </header>
      <p className={styles.suggestionValue}>{suggestion.value}</p>
      <details>
        <summary>查看来源（{suggestion.sources.length}）</summary>
        <ul className={styles.sourceList}>
          {suggestion.sources.map((source) => (
            <li key={`${source.importItemId}-${source.documentId ?? source.fileName}`}>
              <strong>{source.fileName}</strong>
              {source.excerpt && <blockquote>{source.excerpt}</blockquote>}
              <span>导入项：{source.importItemId}</span>
            </li>
          ))}
        </ul>
      </details>
    </article>
  );
}

export function PlatformOnboardingPage({
  session,
  sessions = [],
  importItems = [],
  adminSummary,
  initialReview,
  llmAvailability,
  resourceStatus = "ready",
  resourceError,
  onStart,
  onOpenSession,
  onRename,
  onUpload,
  onGenerate,
  onUpdateCandidate,
  onIgnoreCandidate,
  onConfirm,
  onCancel,
  onRegenerateTemporaryCredential,
  onRefresh,
  onStartAnother,
  onOpenEnterprises,
}: PlatformOnboardingPageProps) {
  const [busy, setBusy] = useState<BusyOperation>();
  const [operationError, setOperationError] = useState<PlatformOnboardingOperationError>();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string>();
  const [review, setReview] = useState<ReviewValues>(emptyReview);
  const [reviewed, setReviewed] = useState({ identity: false, admin: false });
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [confirmedSession, setConfirmedSession] = useState<PlatformOnboardingSession>();
  const [copyNotice, setCopyNotice] = useState<string>();
  const [copyError, setCopyError] = useState<string>();
  const [selectedCandidateId, setSelectedCandidateId] = useState<string>();
  const [candidateDrafts, setCandidateDrafts] = useState<Record<string, PlatformOnboardingCandidate>>({});
  const [candidateSelections, setCandidateSelections] = useState<Record<string, boolean>>({});
  const [renameValue, setRenameValue] = useState("");
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [confirmedDraftCount, setConfirmedDraftCount] = useState(0);
  const [activeWorkspaceStep, setActiveWorkspaceStep] = useState<"analysis" | "review">("analysis");
  const [localIdentitySeed, setLocalIdentitySeed] = useState<ReviewSeed>();
  const cancelOpenerRef = useRef<HTMLButtonElement>(null);
  const previousSessionId = useRef<string | undefined>(undefined);
  const candidateSelectionSessionId = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!session || previousSessionId.current === session.id) return;
    previousSessionId.current = session.id;
    setReview(
      reviewSeedFromSession(session, {
        ...initialReview,
        ...localIdentitySeed,
      }),
    );
    setReviewed({ identity: false, admin: false });
    setSelectedFiles([]);
    setFileError(undefined);
    setOperationError(undefined);
    setConfirmedSession(
      session.status === "confirmed" && session.confirmedEnterprise
        ? session
        : undefined,
    );
    setCopyNotice(undefined);
    setCopyError(undefined);
    setRenameValue(session.displayName);
    setRegenerateOpen(false);
    setActiveWorkspaceStep("analysis");
    setConfirmedDraftCount(
      session.contentReview?.candidates.filter((candidate) => candidate.status === "accepted").length ?? 0,
    );
  }, [initialReview, localIdentitySeed, session]);

  useEffect(() => {
    if (session?.status === "confirmed" && session.confirmedEnterprise) {
      setConfirmedSession(session);
    }
  }, [session]);

  useEffect(() => {
    const candidates = session?.contentReview?.candidates ?? [];
    setCandidateDrafts(Object.fromEntries(candidates.map((candidate) => [candidate.id, candidate])));
    setCandidateSelections((current) => {
      const sameSession = candidateSelectionSessionId.current === session?.id;
      candidateSelectionSessionId.current = session?.id;
      return Object.fromEntries(
        candidates.map((candidate) => [
          candidate.id,
          sameSession && current[candidate.id] !== undefined
            ? current[candidate.id]
            : candidateSelectedByDefault(candidate),
        ]),
      );
    });
    setSelectedCandidateId((current) =>
      current && candidates.some((candidate) => candidate.id === current)
        ? current
        : candidates[0]?.id,
    );
  }, [session?.contentReview]);

  const activeError = operationError ?? resourceError;
  const completedSession =
    confirmedSession?.id === session?.id
      ? confirmedSession
      : session?.status === "confirmed" && session.confirmedEnterprise
        ? session
        : undefined;
  const completedEnterprise = completedSession?.confirmedEnterprise;
  const confirmationComplete = Boolean(completedEnterprise);
  const currentStep = confirmationComplete ? 4 : sessionStep(session);
  const deliveryUrls = useMemo(
    () =>
      completedEnterprise
        ? buildOnboardingDeliveryUrls(completedEnterprise.initialCardSlug || completedEnterprise.tenantSlug)
        : undefined,
    [completedEnterprise],
  );
  const completedItems = importItems.filter((item) => item.status === "completed").length;
  const processedItems = importItems.filter((item) =>
    ["completed", "failed", "dead_letter"].includes(item.status),
  ).length;
  const importProgress = importItems.length ? processedItems / importItems.length : 0;
  const reviewValid = useMemo(
    () =>
      Boolean(
        review.legalName.trim() &&
          review.subjectType &&
          (review.subjectType !== "domestic_enterprise"
            || socialCreditCodePattern.test(normalizeSocialCreditCode(review.socialCreditCode))),
      ),
    [review],
  );
  const terminal = session && ["cancelled", "expired", "failed"].includes(session.status);
  const hasImports = importItems.length > 0 || Boolean(session?.importBatchIds.length);
  const importsProcessing =
    busy === "upload" ||
    (importItems.length > 0
      ? importItems.some((item) => ["pending", "processing"].includes(item.status))
      : session?.status === "processing");
  const confirmationReady =
    reviewValid &&
    reviewed.identity &&
    reviewed.admin &&
    !importsProcessing;
  const insightCount = (session?.businessProfile?.length ?? 0) + (session?.suggestions.length ?? 0);
  const hasInsights = insightCount > 0;
  // Review is a separate, user-controlled step. Parsed files do not require
  // AI output: the operator can always continue with manual fields once no
  // upload or analysis request is actively running.
  const canEnterReview = !importsProcessing && busy !== "generate";
  const confirmationNeedsRecovery =
    operationError?.code === ONBOARDING_CONFIRM_UNCERTAIN_CODE;
  const candidates = session?.contentReview?.candidates.map(
    (candidate) => candidateDrafts[candidate.id] ?? candidate,
  ) ?? [];
  const selectedCandidates = candidates.filter(
    (candidate) =>
      candidateSelections[candidate.id] === true
      && candidate.status === "pending_review"
      && candidate.category !== "unclassified"
      && candidateComplete(candidate),
  );
  const ignoredCandidateCount = candidates.filter(
    (candidate) => candidate.status === "ignored",
  ).length;
  const unselectedCandidateCount = candidates.length
    - selectedCandidates.length
    - ignoredCandidateCount;

  const run = async (operation: BusyOperation, action: () => Promise<void>) => {
    if (busy) return;
    setBusy(operation);
    setOperationError(undefined);
    try {
      await action();
    } catch (caught) {
      setOperationError(asOperationError(caught));
    } finally {
      setBusy(undefined);
    }
  };

  const updateReview = <K extends keyof ReviewValues>(key: K, value: ReviewValues[K]) => {
    setReview((current) => ({
      ...current,
      [key]: key === "socialCreditCode" ? normalizeSocialCreditCode(String(value)) : value,
    }));
    setReviewed((current) => ({ ...current, identity: false }));
  };

  const chooseFiles = (files: File[]) => {
    const error = validateKnowledgeImportFiles(files);
    setFileError(error);
    setSelectedFiles(error ? [] : files);
  };

  const submitUpload = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!session) return;
    const error = validateKnowledgeImportFiles(selectedFiles);
    setFileError(error);
    if (!error) {
      void run("upload", async () => {
        await onUpload(session.id, selectedFiles);
        setSelectedFiles([]);
      });
    }
  };

  const closeCancel = () => {
    setCancelOpen(false);
    setCancelReason("");
    window.setTimeout(() => cancelOpenerRef.current?.focus(), 0);
  };

  const copyUrl = async (value: string, label: string) => {
    setCopyNotice(undefined);
    setCopyError(undefined);
    try {
      await copyDeliveryUrl(value);
      setCopyNotice(`${label}已复制。`);
    } catch {
      setCopyError("浏览器未允许自动复制，请手动选择网址。");
    }
  };

  if (resourceStatus !== "ready") {
    return (
      <main className="page-stack">
        <PageHeader
          title="资料辅助建企"
          description="复用当前资料导入链路，生成带来源建议，并由平台管理员最终确认。"
        />
        <section className="content-panel">
          <ResourceState
            status={resourceStatus}
            description={resourceError?.message}
            errorCode={resourceError?.code}
            requestId={resourceError?.requestId}
            onRetry={resourceStatus === "error" ? onRefresh : undefined}
          />
        </section>
      </main>
    );
  }

  return (
    <main className={`page-stack ${styles.page}`}>
      <PageHeader
        title="资料辅助建企"
        description="上传后可看到解析和智能分析进度；所有结论带来源，人工复核后才会激活企业。"
        actions={
          session && onRefresh ? (
            <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={onRefresh}>
              {confirmationComplete ? "刷新结果" : "刷新进度"}
            </Button>
          ) : undefined
        }
      />

      {sessions.length > 0 && (
        <section className={styles.historyPanel} aria-labelledby="onboarding-history-title">
          <div className={styles.historyHeading}>
            <div>
              <span>最近任务</span>
              <h2 id="onboarding-history-title">可继续或回看已结束任务</h2>
            </div>
            <small>保留期内可重新打开已确认、已取消和已过期任务。</small>
          </div>
          <div className={styles.historyList}>
            {sessions.map((item) => (
              <button
                type="button"
                key={item.id}
                aria-current={item.id === session?.id ? "true" : undefined}
                onClick={() => onOpenSession?.(item.id)}
              >
                <strong>{item.displayName}</strong>
                <span>{onboardingStatusLabels[item.status]}</span>
                <small>
                  {item.status === "confirmed"
                    ? `完成于 ${formatDateTime(item.updatedAt)}`
                    : `到期 ${formatDateTime(item.expiresAt)}`}
                </small>
              </button>
            ))}
          </div>
        </section>
      )}

      {session && (
        <section className={styles.currentTask} aria-labelledby="onboarding-current-task-title">
          <div>
            <span>当前任务</span>
            <h2 id="onboarding-current-task-title">{session.displayName}</h2>
            <p>
              {onboardingStatusLabels[session.status]}
              {session.status !== "confirmed" && ` · 到期 ${formatDateTime(session.expiresAt)}`}
              {` · 版本 ${session.version}`}
            </p>
          </div>
          {onRename && (
            <div className={styles.renameControl}>
              <Field label="任务名称">
                <Input
                  value={renameValue}
                  maxLength={120}
                  disabled={busy === "rename"}
                  onChange={(_, data) => setRenameValue(data.value)}
                />
              </Field>
              <Button
                appearance="secondary"
                disabled={
                  busy === "rename"
                  || !renameValue.trim()
                  || renameValue.trim() === session.displayName
                }
                onClick={() =>
                  void run("rename", async () => {
                    try {
                      await onRename(session.id, session.version, renameValue.trim());
                    } catch (caught) {
                      if ((caught as PlatformOnboardingOperationError)?.code === "VERSION_CONFLICT") {
                        onRefresh?.();
                      }
                      throw caught;
                    }
                  })
                }
              >
                {busy === "rename" ? "正在保存" : "保存名称"}
              </Button>
            </div>
          )}
        </section>
      )}

      {(!session || confirmationComplete || terminal) && <Steps current={currentStep} />}
      {activeError && (
        <OperationError
          error={activeError}
          onRecover={
            confirmationNeedsRecovery && onRefresh
              ? () => {
                  setOperationError(undefined);
                  onRefresh();
                }
              : undefined
          }
        />
      )}

      {!session && (
        <StartPanel
          busy={busy === "start"}
          onPrepared={(draft) =>
            setLocalIdentitySeed({
              legalName: draft.legalName,
              shortName: draft.shortName,
              subjectType: draft.subjectType,
              socialCreditCode: normalizeSocialCreditCode(draft.socialCreditCode),
              industry: draft.industry,
            })
          }
          onStart={(input) => run("start", () => onStart(input))}
        />
      )}

      {session && completedEnterprise && deliveryUrls && (
        <section className={styles.resultPanel} aria-labelledby="onboarding-result-title">
          <CheckmarkCircle24Regular aria-hidden />
          <div>
            <span>步骤 5 / 5</span>
            <h2 id="onboarding-result-title">企业已由服务端确认激活</h2>
            <p>
              {completedEnterprise.companyName} 已生成唯一企业与管理员身份；本轮按新方案交付为零名片起步，企业登录后再自行创建内容和名片。
            </p>
            <p className={styles.draftResultSummary}>
              本次已接收 {confirmedDraftCount} 条资料草稿；企业可在后台继续审核资料、核心业务、案例与 FAQ，系统没有自动发布任何对外内容。
            </p>
            <dl>
              <div><dt>企业 ID</dt><dd>{completedEnterprise.companyId}</dd></div>
              <div><dt>企业状态</dt><dd><StatusBadge status={completedEnterprise.status} /></dd></div>
              <div><dt>当前名片交付</dt><dd>0 张</dd></div>
              {adminSummary?.account && (
                <div><dt>企业管理员账号</dt><dd>{adminSummary.account}</dd></div>
              )}
            </dl>
            {(completedEnterprise.initialCardId || completedEnterprise.initialCardSlug) && (
              <details className={styles.technicalDetails}>
                <summary>查看 legacy 兼容回执</summary>
                <dl>
                  {completedEnterprise.initialCardId && (
                    <div><dt>旧初始名片 ID</dt><dd>{completedEnterprise.initialCardId}</dd></div>
                  )}
                  {completedEnterprise.initialCardSlug && (
                    <div><dt>旧初始名片标识</dt><dd>{completedEnterprise.initialCardSlug}</dd></div>
                  )}
                </dl>
              </details>
            )}
            {completedSession.credentialDelivery && (
              <section className={styles.credentialDelivery} aria-label="一次性企业管理员凭证">
                <div>
                  <strong>一次性登录凭证</strong>
                  <span>
                    仅此页面展示，有效至 {formatDateTime(completedSession.credentialDelivery.expiresAt)}；首次登录后必须修改密码。
                  </span>
                </div>
                <Field label="管理员账号">
                  <div className={styles.deliveryUrlField}>
                    <Input value={completedSession.credentialDelivery.account} readOnly />
                    <Button
                      icon={<Copy24Regular />}
                      aria-label="复制管理员账号"
                      onClick={() => void copyUrl(completedSession.credentialDelivery!.account, "管理员账号")}
                    />
                  </div>
                </Field>
                <Field label="临时密码">
                  <div className={styles.deliveryUrlField}>
                    <Input
                      type="password"
                      value={completedSession.credentialDelivery.temporaryPassword}
                      readOnly
                      aria-label="一次性临时密码"
                    />
                    <Button
                      icon={<Copy24Regular />}
                      aria-label="复制临时密码"
                      onClick={() =>
                        void copyUrl(completedSession.credentialDelivery!.temporaryPassword, "临时密码")
                      }
                    />
                  </div>
                </Field>
              </section>
            )}
            {completedSession.temporaryCredentialResetAvailable
              && onRegenerateTemporaryCredential && (
                <div className={styles.credentialActions}>
                  <Button
                    appearance="secondary"
                    disabled={busy === "regenerate"}
                    onClick={() => setRegenerateOpen(true)}
                  >
                    重新生成临时密码
                  </Button>
                  <span>仅在企业管理员尚未完成首次改密时可用。</span>
                </div>
              )}
            <section className={styles.deliveryPanel} aria-labelledby="onboarding-delivery-title">
              <div>
                <h3 id="onboarding-delivery-title">网址与交付入口</h3>
                <p>请将企业后台和一次性凭据交给管理员。当前不会提供公开名片网址，因为企业还没有创建名片。</p>
              </div>
              <Field label="企业管理后台">
                <div className={styles.deliveryUrlField}>
                  <Input value={deliveryUrls.adminUrl} readOnly />
                  <Button
                    icon={<Copy24Regular />}
                    aria-label="复制企业管理后台网址"
                    onClick={() => void copyUrl(deliveryUrls.adminUrl, "企业管理后台网址")}
                  />
                </div>
              </Field>
              <a
                className={styles.deliveryOpenLink}
                href={deliveryUrls.adminUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                打开企业管理后台
              </a>
              <span className={styles.deliveryPendingLink} aria-label="企业尚无公开名片">
                当前没有公开名片网址；企业管理员登录后创建并发布名片，才会生成对外访问链接。
              </span>
              {copyNotice && (
                <MessageBar intent="success"><MessageBarBody>{copyNotice}</MessageBarBody></MessageBar>
              )}
              {copyError && (
                <MessageBar intent="error"><MessageBarBody>{copyError}</MessageBarBody></MessageBar>
              )}
            </section>
            <div className={styles.resultActions} aria-label="建企完成后操作">
              {onStartAnother && (
                <Button appearance="primary" onClick={onStartAnother}>
                  继续开通新企业
                </Button>
              )}
              {onOpenEnterprises && (
                <Button appearance="secondary" onClick={onOpenEnterprises}>
                  前往企业中心
                </Button>
              )}
            </div>
          </div>
        </section>
      )}

      {terminal && (
        <section className="content-panel">
          <ResourceState
            status="empty"
            title={
              session.status === "cancelled"
                ? "开通会话已取消"
                : session.status === "failed"
                  ? "开通会话未完成"
                  : "开通会话已过期"
            }
            description="该临时范围不能继续上传、生成或确认，管理员仍不可登录，名片仍不可公开。"
            emptyAction={
              onStartAnother ? (
                <Button appearance="primary" onClick={onStartAnother}>
                  开通新企业
                </Button>
              ) : undefined
            }
          />
        </section>
      )}

      {session && !confirmationComplete && !terminal && (
        <>
          {llmAvailability !== "ready" && (
            <MessageBar intent="warning">
              <MessageBarBody>
                <strong>LLM 当前不可用，已切换为人工填写</strong>
                <div>
                  已成功解析的资料草稿不会回滚。你仍可查看逐文件结果并手工填写全部企业和名片字段。
                </div>
              </MessageBarBody>
            </MessageBar>
          )}

          <div className={styles.workflowLayout}>
            <nav className={styles.workspaceNav} aria-label="资料辅助建企步骤">
              <button
                type="button"
                aria-current={activeWorkspaceStep === "analysis" ? "step" : undefined}
                onClick={() => setActiveWorkspaceStep("analysis")}
              >
                <span>步骤 2–3</span>
                <strong>资料与智能候选</strong>
                <small>{hasInsights ? `${insightCount} 项结论待复核` : hasImports ? "资料处理中" : "可选上传资料"}</small>
              </button>
              <button
                type="button"
                aria-current={activeWorkspaceStep === "review" ? "step" : undefined}
                disabled={!canEnterReview}
                onClick={() => setActiveWorkspaceStep("review")}
              >
                <span>步骤 4</span>
                <strong>人工复核与确认</strong>
                <small>{canEnterReview ? "确认字段与草稿去向" : "完成解析后进入"}</small>
              </button>
              <div>
                <span>步骤 5</span>
                <strong>完成与交付</strong>
                <small>服务端确认后显示</small>
              </div>
            </nav>

            <div className={styles.workspace}>
            {activeWorkspaceStep === "analysis" && (
              <section className={styles.sourcesPanel} aria-labelledby="onboarding-sources-title">
              <div className={styles.panelHeading}>
                <div>
                  <span>步骤 2–3</span>
                  <h2 id="onboarding-sources-title">资料分析与业务归纳</h2>
                </div>
              </div>

              <AnalysisProgress
                hasImports={hasImports}
                importsProcessing={importsProcessing}
                generating={busy === "generate"}
                hasInsights={hasInsights}
                insightCount={insightCount}
              />

              <form className={styles.uploadBox} onSubmit={submitUpload}>
                <Field
                  label="选择建企资料"
                  validationState={fileError ? "error" : "none"}
                  validationMessage={fileError}
                >
                  <input
                    className={styles.fileInput}
                    aria-label="选择建企资料"
                    type="file"
                    multiple
                    accept=".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.html,.htm,.png,.jpg,.jpeg,.webp,.tiff,.bmp"
                    disabled={busy === "upload"}
                    onChange={(event) => chooseFiles(Array.from(event.target.files ?? []))}
                  />
                </Field>
                <p>
                  可一次选择多个文件，不限制单文件或批次大小。目标企业只由服务端会话推导。
                </p>
                <Button
                  appearance="primary"
                  icon={<ArrowUpload24Regular />}
                  type="submit"
                  disabled={selectedFiles.length === 0 || busy === "upload"}
                >
                  {busy === "upload" ? "正在上传" : `上传并解析${selectedFiles.length ? `（${selectedFiles.length}）` : ""}`}
                </Button>
              </form>

              {importItems.length > 0 && (
                <div className={styles.importResults} aria-label="逐文件解析结果">
                  <div className={styles.progressCopy}>
                    <strong>{processedItems}/{importItems.length} 个文件已处理</strong>
                    <span>成功草稿 {completedItems} 个</span>
                  </div>
                  <ProgressBar value={importProgress} aria-label="资料解析进度" />
                  <ul>
                    {importItems.map((item) => (
                      <li key={item.id}>
                        <div>
                          <strong>{item.fileName}</strong>
                          {item.errorMessage && <span>{item.errorMessage}</span>}
                          {item.errorCode && <code>{item.errorCode}</code>}
                        </div>
                        <StatusBadge status={item.status} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className={styles.generateBox}>
                <div>
                  <strong>智能归纳企业业务</strong>
                  <p>从已解析资料识别业务、客户、能力、方向和缺口；所有结论保留来源。</p>
                </div>
                <Button
                  appearance="secondary"
                  icon={<Sparkle24Regular />}
                  disabled={
                    (completedItems === 0 && session.importBatchIds.length === 0) ||
                    importsProcessing ||
                    llmAvailability !== "ready" ||
                    busy === "generate"
                  }
                  onClick={() =>
                    void run("generate", () => onGenerate(session.id, session.version))
                  }
                >
                  {busy === "generate" ? "正在分析企业资料" : "开始智能分析"}
                </Button>
              </div>

              <details className={styles.technicalDetails}>
                <summary>查看处理编号</summary>
                <dl>
                  <div><dt>会话编号</dt><dd>{session.id}</dd></div>
                  <div><dt>结果版本</dt><dd>{session.version}</dd></div>
                </dl>
              </details>

              <div className={styles.suggestions} aria-live="polite">
                {(session.contentReview?.candidates.length ?? 0) > 0 && (
                  <section className={styles.candidateWorkspace} aria-labelledby="onboarding-candidate-title">
                    <div className={styles.candidateSummary}>
                      <div>
                        <span>智能候选</span>
                        <h3 id="onboarding-candidate-title">逐条确认资料归类</h3>
                        <p>左侧选择候选，右侧编辑；保存只更新草稿，不会发布内容。</p>
                      </div>
                      <strong>{session.contentReview?.candidates.length} 条</strong>
                    </div>
                    <div className={styles.candidateColumns}>
                      <nav className={styles.candidateList} aria-label="资料候选列表">
                        {session.contentReview?.candidates.map((original) => {
                          const candidate = candidateDrafts[original.id] ?? original;
                          return (
                            <button
                              type="button"
                              key={candidate.id}
                              className={candidate.id === selectedCandidateId ? styles.candidateActive : undefined}
                              onClick={() => setSelectedCandidateId(candidate.id)}
                            >
                              <span>{candidateCategoryLabels[candidate.category]}</span>
                              <strong>{candidateTitle(candidate)}</strong>
                              <small>置信度 {Math.round(candidate.confidence * 100)}%</small>
                            </button>
                          );
                        })}
                      </nav>
                      {selectedCandidateId && candidateDrafts[selectedCandidateId] && (() => {
                        const candidate = candidateDrafts[selectedCandidateId];
                        const updateCandidate = (next: PlatformOnboardingCandidate) =>
                          setCandidateDrafts((current) => ({ ...current, [next.id]: next }));
                        return (
                          <article className={styles.candidateEditor}>
                            <div className={styles.candidateEditorHeading}>
                              <label>
                                <span>候选分类</span>
                                <select
                                  aria-label="候选分类"
                                  value={candidate.category}
                                  onChange={(event) => {
                                    const category = event.target.value as PlatformOnboardingCandidateCategory;
                                    const nextCandidate = {
                                      ...candidate,
                                      category,
                                      payload: { ...candidatePayloadDefaults[category] },
                                    };
                                    updateCandidate(nextCandidate);
                                    setCandidateSelections((current) => ({
                                      ...current,
                                      [candidate.id]: candidateSelectedByDefault(nextCandidate),
                                    }));
                                  }}
                                >
                                  {Object.entries(candidateCategoryLabels).map(([value, label]) => (
                                    <option key={value} value={value}>{label}</option>
                                  ))}
                                </select>
                              </label>
                              <Checkbox
                                checked={candidateSelections[candidate.id] === true}
                                disabled={
                                  candidate.status !== "pending_review"
                                  || candidate.category === "unclassified"
                                  || !candidateComplete(candidate)
                                }
                                label="创建为草稿"
                                onChange={(_, data) =>
                                  setCandidateSelections((current) => ({
                                    ...current,
                                    [candidate.id]: data.checked === true,
                                  }))
                                }
                              />
                              <span>
                                {candidate.status === "pending_review"
                                  ? "待确认"
                                  : candidate.status === "ignored"
                                    ? "已忽略"
                                    : candidate.status === "accepted"
                                      ? "已确认"
                                      : candidate.status}
                              </span>
                            </div>
                            <div className={styles.candidateFields}>
                              {Object.entries(candidate.payload).map(([field, value]) => {
                                const multiline = ["summary", "detail", "background", "solution", "result", "answer", "text", "reason"].includes(field);
                                const update = (nextValue: string) => updateCandidate({
                                  ...candidate,
                                  payload: { ...candidate.payload, [field]: nextValue },
                                });
                                return (
                                  <Field key={field} label={candidateFieldLabels[field] ?? field}>
                                    {multiline ? (
                                      <Textarea value={value} resize="vertical" onChange={(_, data) => update(data.value)} />
                                    ) : (
                                      <Input value={value} onChange={(_, data) => update(data.value)} />
                                    )}
                                  </Field>
                                );
                              })}
                            </div>
                            {!candidateComplete(candidate) && candidate.category !== "unclassified" && (
                              <p className={styles.candidateSelectionHint}>
                                补齐必填字段后才能选择“创建为草稿”。
                              </p>
                            )}
                            {candidate.status === "ignored" && (
                              <p className={styles.candidateSelectionHint}>
                                已忽略候选保留在导入历史中，不会创建草稿。
                              </p>
                            )}
                            <details className={styles.candidateEvidence}>
                              <summary>查看原文证据</summary>
                              <blockquote>{candidate.sourceText}</blockquote>
                            </details>
                            <div className={styles.candidateActions}>
                              <Button
                                appearance="subtle"
                                disabled={!onIgnoreCandidate || Boolean(busy) || candidate.status !== "pending_review"}
                                onClick={() => onIgnoreCandidate
                                  ? void run("generate", () => onIgnoreCandidate(session.id, candidate))
                                  : undefined}
                              >
                                忽略此候选
                              </Button>
                              <Button
                                appearance="primary"
                                disabled={!onUpdateCandidate || Boolean(busy)}
                                onClick={() => onUpdateCandidate
                                  ? void run("generate", () => onUpdateCandidate(session.id, candidate))
                                  : undefined}
                              >
                                保存候选修改
                              </Button>
                            </div>
                          </article>
                        );
                      })()}
                    </div>
                  </section>
                )}
                {(session.businessProfile?.length ?? 0) > 0 && (
                  <section className={styles.businessProfile} aria-labelledby="business-profile-title">
                    <div>
                      <span>资料归纳</span>
                      <h3 id="business-profile-title">企业业务画像（待审核）</h3>
                      <p>只整理有资料依据的业务线索；不会自动写入企业公开页、AI 知识库或名片。</p>
                    </div>
                    {session.businessProfile?.map((insight, index) => (
                      <SuggestionCard
                        key={`business-${insight.field}-${insight.generationVersion}-${index}`}
                        suggestion={insight}
                        label={businessProfileLabels[insight.field] ?? insight.field}
                        onApply={() => undefined}
                        readOnly
                      />
                    ))}
                  </section>
                )}
                {session.suggestions.length === 0 ? (
                  <div className={styles.emptySuggestions}>
                    <strong>{llmAvailability === "ready" ? "暂无建议" : "当前使用人工填写"}</strong>
                    <p>任何字段都不会因为上传或生成而自动写入右侧确认表单。</p>
                  </div>
                ) : (
                  session.suggestions.map((suggestion, index) => (
                    <SuggestionCard
                      key={`${suggestion.field}-${suggestion.generationVersion}-${index}`}
                      suggestion={suggestion}
                      onApply={() => {
                        const field = suggestionFieldMap[suggestion.field];
                        if (field) updateReview(field, suggestion.value);
                      }}
                    />
                  ))
                )}
              </div>
              <div className={styles.stepAdvance}>
                <div>
                  <strong>{canEnterReview ? "资料与候选已可复核" : "先完成当前处理"}</strong>
                  <span>{hasInsights ? "进入下一步确认企业字段和草稿去向。" : "不上传资料也可以进入人工填写。"}</span>
                </div>
                <Button
                  appearance="primary"
                  disabled={!canEnterReview}
                  onClick={() => setActiveWorkspaceStep("review")}
                >
                  下一步：人工复核
                </Button>
              </div>
              </section>
            )}

            {activeWorkspaceStep === "review" && (
              <section className={styles.reviewPanel} aria-labelledby="onboarding-review-title">
              <div className={styles.panelHeading}>
                <div>
                  <span>步骤 4 / 5</span>
                  <h2 id="onboarding-review-title">人工复核与确认</h2>
                  <p>采用建议后仍可编辑；任一字段变化都会撤销对应复核勾选。</p>
                </div>
              </div>

              <form
                className={styles.reviewForm}
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!confirmationReady) return;
                  void run("confirm", async () => {
                    const confirmed = await onConfirm(
                      session.id,
                      confirmationPayload(
                        review,
                        session.version,
                        selectedCandidates.map((candidate) => ({
                          id: candidate.id,
                          expectedVersion: candidate.version,
                          applyFields: candidateApplyFields(candidate),
                        })),
                      ),
                    );
                    if (
                      confirmed?.status === "confirmed" &&
                      confirmed.confirmedEnterprise
                    ) {
                      setConfirmedSession(confirmed);
                      setConfirmedDraftCount(selectedCandidates.length);
                    }
                  });
                }}
              >
                <fieldset>
                  <legend>企业身份</legend>
                  <div className={styles.formGrid}>
                    {reviewFieldMeta.filter((field) => field.group === "identity").map((field) => (
                      <Field key={field.key} label={field.label} required={field.required}>
                        {field.key === "subjectType" ? (
                          <select
                            aria-label={field.label}
                            className={styles.nativeSelect}
                            value={review.subjectType}
                            onChange={(event) =>
                              updateReview(
                                "subjectType",
                                event.target.value as ReviewValues["subjectType"],
                              )
                            }
                          >
                            <option value="domestic_enterprise">国内企业</option>
                            <option value="association">协会 / 机构</option>
                            <option value="overseas">境外主体</option>
                            <option value="pending_registration">筹备中</option>
                          </select>
                        ) : field.area ? (
                          <Textarea
                            aria-label={field.label}
                            value={review[field.key]}
                            resize="vertical"
                            onChange={(_, data) => updateReview(field.key, data.value)}
                          />
                        ) : (
                          <Input
                            aria-label={field.label}
                            value={review[field.key]}
                            type="text"
                            onChange={(_, data) => updateReview(field.key, data.value)}
                          />
                        )}
                      </Field>
                    ))}
                  </div>
                </fieldset>

                <fieldset>
                  <legend>对外展示补充</legend>
                  <div className={styles.formGrid}>
                    {reviewFieldMeta.filter((field) => field.group === "presentation").map((field) => (
                      <Field key={field.key} label={field.label} required={field.required}>
                        {field.area ? (
                          <Textarea
                            aria-label={field.label}
                            value={review[field.key]}
                            resize="vertical"
                            onChange={(_, data) => updateReview(field.key, data.value)}
                          />
                        ) : (
                          <Input
                            aria-label={field.label}
                            value={review[field.key]}
                            type={field.key === "website" ? "url" : "text"}
                            onChange={(_, data) => updateReview(field.key, data.value)}
                          />
                        )}
                      </Field>
                    ))}
                  </div>
                </fieldset>

                <fieldset>
                  <legend>管理员交付</legend>
                  <dl className={styles.adminSummary}>
                    <div><dt>管理员账号</dt><dd>{adminSummary?.account ?? "由初始化步骤锁定"}</dd></div>
                    <div><dt>管理员姓名</dt><dd>{adminSummary?.displayName ?? "由初始化步骤锁定"}</dd></div>
                    <div><dt>确认前状态</dt><dd>不可登录</dd></div>
                  </dl>
                </fieldset>

                {(session.initialCardDisplayName || session.initialCardTitle) && (
                  <fieldset>
                    <legend>Legacy 兼容字段（只读）</legend>
                    <div className={styles.legacyReviewNotice}>
                      <strong>旧会话仍携带初始名片字段</strong>
                      <span>本轮不再要求确认或编辑这些字段；它们只作为兼容读值保留，平台确认不会再把“初始名片”视为正式交付结果。</span>
                    </div>
                    <dl className={styles.adminSummary}>
                      {session.initialCardDisplayName && (
                        <div><dt>旧初始名片姓名</dt><dd>{session.initialCardDisplayName}</dd></div>
                      )}
                      {session.initialCardTitle && (
                        <div><dt>旧初始名片职位</dt><dd>{session.initialCardTitle}</dd></div>
                      )}
                    </dl>
                  </fieldset>
                )}

                {candidates.length > 0 && (
                  <section className={styles.candidateConfirmationSummary} aria-label="候选导入确认摘要">
                    <strong>候选导入确认</strong>
                    <div>
                      <span>创建为草稿 {selectedCandidates.length} 条</span>
                      <span>本次不创建 {unselectedCandidateCount} 条</span>
                      <span>已忽略 {ignoredCandidateCount} 条</span>
                    </div>
                    <p>选中内容只会进入企业后台草稿；未选、未分类和已忽略候选继续保留在导入历史，不会自动发布。</p>
                  </section>
                )}

                <fieldset className={styles.confirmationGate}>
                  <legend>显式确认门</legend>
                  <Checkbox
                    checked={reviewed.identity}
                    onChange={(_, data) =>
                      setReviewed((current) => ({ ...current, identity: data.checked === true }))
                    }
                    label="我已逐项复核企业身份与对外展示信息"
                  />
                  <Checkbox
                    checked={reviewed.admin}
                    onChange={(_, data) =>
                      setReviewed((current) => ({ ...current, admin: data.checked === true }))
                    }
                    label="我已核对管理员账号与交付对象"
                  />
                </fieldset>

                <div className={styles.stickyActions} aria-label="开通会话主操作">
                  <div>
                    <strong>
                      {importsProcessing
                        ? "资料仍在解析，暂不能确认"
                        : confirmationReady
                          ? "可以提交确认"
                          : "尚未满足确认条件"}
                    </strong>
                    <span>
                      {importsProcessing
                        ? "请等待所有资料解析完成后再复核激活"
                        : `将提交服务端会话版本 ${session.version}`}
                    </span>
                  </div>
                  <Button
                    ref={cancelOpenerRef}
                    appearance="subtle"
                    icon={<Dismiss24Regular />}
                    type="button"
                    disabled={Boolean(busy)}
                    onClick={() => setCancelOpen(true)}
                  >
                    取消会话
                  </Button>
                  <Button appearance="primary" type="submit" disabled={!confirmationReady || Boolean(busy)}>
                    {busy === "confirm" ? "正在确认" : "确认并激活企业"}
                  </Button>
                </div>
              </form>
              </section>
            )}
            </div>
          </div>

          <Dialog
            open={cancelOpen}
            onOpenChange={(_, data) => {
              if (!data.open && busy !== "cancel") closeCancel();
            }}
          >
            <DialogSurface>
              <DialogBody>
                <DialogTitle>取消资料辅助建企会话</DialogTitle>
                <DialogContent>
                  <p>取消是软锁定，不会激活临时企业，也不会删除审计记录。请填写原因。</p>
                  <Field label="取消原因" required>
                    <Textarea
                      aria-label="取消原因"
                      value={cancelReason}
                      resize="vertical"
                      onChange={(_, data) => setCancelReason(data.value)}
                    />
                  </Field>
                </DialogContent>
                <DialogActions>
                  <Button appearance="secondary" disabled={busy === "cancel"} onClick={closeCancel}>
                    返回复核
                  </Button>
                  <Button
                    appearance="primary"
                    disabled={!cancelReason.trim() || busy === "cancel"}
                    onClick={() =>
                      void run("cancel", async () => {
                        await onCancel(session.id, cancelReason.trim(), session.version);
                        closeCancel();
                      })
                    }
                  >
                    {busy === "cancel" ? "正在取消" : "确认取消会话"}
                  </Button>
                </DialogActions>
              </DialogBody>
            </DialogSurface>
          </Dialog>
        </>
      )}
      {completedSession && onRegenerateTemporaryCredential && (
        <Dialog
          open={regenerateOpen}
          onOpenChange={(_, data) => {
            if (!data.open && busy !== "regenerate") setRegenerateOpen(false);
          }}
        >
          <DialogSurface>
            <DialogBody>
              <DialogTitle>重新生成临时密码</DialogTitle>
              <DialogContent>
                <p>
                  旧临时密码会立即失效。新密码只在本次响应展示，并重新计算七天有效期。
                </p>
              </DialogContent>
              <DialogActions>
                <Button
                  appearance="secondary"
                  disabled={busy === "regenerate"}
                  onClick={() => setRegenerateOpen(false)}
                >
                  取消
                </Button>
                <Button
                  appearance="primary"
                  disabled={busy === "regenerate"}
                  onClick={() =>
                    void run("regenerate", async () => {
                      const updated = await onRegenerateTemporaryCredential(
                        completedSession.id,
                        completedSession.version,
                      );
                      if (updated?.credentialDelivery) setConfirmedSession(updated);
                      setRegenerateOpen(false);
                    })
                  }
                >
                  {busy === "regenerate" ? "正在生成" : "确认重新生成"}
                </Button>
              </DialogActions>
            </DialogBody>
          </DialogSurface>
        </Dialog>
      )}
    </main>
  );
}

import {
  Badge,
  Button,
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
  Select,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Textarea,
} from "@fluentui/react-components";
import {
  Add24Regular,
  ArrowClockwise24Regular,
  ArrowUpload24Regular,
  Edit24Regular,
  KeyReset24Regular,
  LockClosed24Regular,
  LockOpen24Regular,
} from "@fluentui/react-icons";
import { type FormEvent, useMemo, useRef, useState } from "react";

import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { ApiError } from "../api/client";
import { adminApi } from "../api/adminApi";
import {
  memberApi,
  MEMBER_ROLE_LABELS,
  MEMBER_STATUS_LABELS,
} from "../api/memberApi";
import type {
  BulkMemberResult,
  CompanyMember,
  MemberCreateInput,
  MemberRole,
  MemberStatus,
} from "../api/types";
import { ActionConfirmDialog } from "../components/ActionConfirmDialog";
import { FormFeedback } from "../components/FormFeedback";
import { IdentityTitlesEditor } from "../components/IdentityTitlesEditor";
import { OperationFeedback } from "../components/OperationFeedback";
import { PageHeader } from "../components/PageHeader";
import { PaginationBar } from "../components/PaginationBar";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

const PAGE_SIZE = 50;

const PERMISSION_OPTIONS = [
  ["members.manage", "企业员工管理"],
  ["company.manage", "企业治理"],
  ["card.manage", "名片管理"],
  ["catalog.manage", "产品与案例"],
  ["knowledge.manage", "知识库管理"],
  ["forbidden_topic.manage", "禁答主题"],
  ["analytics.read", "经营分析"],
  ["conversations.read", "AI 对话"],
  ["leads.write", "线索跟进"],
  ["privacy.manage", "隐私请求"],
] as const;

const emptyCreate: MemberCreateInput = {
  account: "",
  displayName: "",
  password: "",
  email: "",
  mobile: "",
  jobTitle: "",
  avatarUrl: "",
  businessSummary: "",
  publicPositioning: "",
  identityTitles: [],
  professionalTags: [],
  role: "card_owner",
  permissions: [],
  status: "active",
  rotatePassword: false,
};

type ImportMode = "csv" | "json";
type ConfirmAction = { member: CompanyMember; status: MemberStatus };

function apiError(value: unknown, fallback: string): ApiError {
  return value instanceof ApiError
    ? value
    : new ApiError(fallback, { code: "UNKNOWN_ERROR" });
}

function friendlyMemberError(error: ApiError): ApiError {
  const messages: Record<string, string> = {
    LAST_COMPANY_ADMIN_REQUIRED: "至少需要保留一位启用中的企业管理员，请先提升其他成员后再操作。",
    MEMBER_CONFLICT: "账号、邮箱或手机号已被企业中的其他用户使用。",
    MEMBER_NOT_FOUND: "该用户已不存在或不属于当前企业，请刷新列表。",
    SELF_DISABLE_FORBIDDEN: "不能停用当前登录账号，请由其他企业管理员执行。",
    SELF_ROLE_CHANGE_FORBIDDEN: "不能降低当前登录账号的管理员角色，请由其他企业管理员执行。",
  };
  return messages[error.code]
    ? new ApiError(messages[error.code], {
        code: error.code,
        status: error.status,
        requestId: error.requestId,
      })
    : error;
}

function PermissionPicker({
  values,
  onChange,
  disabled,
}: {
  values: string[];
  onChange: (permissions: string[]) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset className="member-permission-fieldset">
      <legend>权限</legend>
      <p>企业管理员始终拥有完整治理能力；名片成员按业务需要授权。</p>
      <div className="member-permission-grid">
        {PERMISSION_OPTIONS.map(([permission, label]) => (
          <Switch
            key={permission}
            checked={values.includes(permission)}
            label={label}
            disabled={disabled}
            onChange={(_, data) =>
              onChange(
                data.checked
                  ? [...values, permission].sort()
                  : values.filter((value) => value !== permission),
              )
            }
          />
        ))}
      </div>
    </fieldset>
  );
}

function MemberEditor({
  member,
  onClose,
  onSaved,
}: {
  member?: CompanyMember;
  onClose: () => void;
  onSaved: (notice: string) => void;
}) {
  const [form, setForm] = useState<MemberCreateInput>(
    member
      ? {
          ...emptyCreate,
          account: member.account,
          displayName: member.displayName,
          jobTitle: member.jobTitle ?? "",
          avatarUrl: member.avatarUrl ?? "",
          businessSummary: member.businessSummary ?? "",
          publicPositioning: member.publicPositioning ?? "",
      identityTitles: member.identityTitles ?? [],
      professionalTags: member.professionalTags ?? [],
          email: member.email ?? "",
          mobile: member.mobile ?? "",
          role: member.role,
          permissions: member.permissions,
          status: member.status === "active" ? "active" : "disabled",
        }
      : emptyCreate,
  );
  const [attempted, setAttempted] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError>();
  const [avatarFile, setAvatarFile] = useState<File>();
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const valid =
    Boolean(form.displayName.trim()) &&
    (member ? true : Boolean(form.account.trim()) && form.password.length >= 12);
  const roleChangeIsDangerous = Boolean(
    member?.role === "company_admin" && form.role !== "company_admin",
  );
  const [confirmRoleChange, setConfirmRoleChange] = useState(false);

  const save = async (confirmedRoleChange = false) => {
    setAttempted(true);
    setError(undefined);
    if (!valid || pending) return;
    if (roleChangeIsDangerous && !confirmedRoleChange) {
      setConfirmRoleChange(true);
      return;
    }
    setPending(true);
    try {
      const avatarUrl = avatarFile
        ? (await adminApi.uploadCardAsset(avatarFile)).url
        : form.avatarUrl;
      if (member) {
        await memberApi.updateMember(member.membershipId, {
          displayName: form.displayName,
          jobTitle: form.jobTitle,
          avatarUrl,
          businessSummary: form.businessSummary,
          publicPositioning: form.publicPositioning,
          identityTitles: form.identityTitles,
          professionalTags: form.professionalTags,
          email: form.email,
          mobile: form.mobile,
          role: form.role,
          permissions: form.permissions,
        });
        onSaved(`用户 ${form.displayName.trim()} 的角色和权限已更新。`);
      } else {
        const created = await memberApi.createMember({ ...form, avatarUrl });
        onSaved(`用户 ${created.displayName} 已创建，可使用 ${created.account} 登录。`);
      }
      onClose();
    } catch (caught) {
      setError(friendlyMemberError(apiError(caught, "保存企业员工时发生未知错误。")));
    } finally {
      setPending(false);
    }
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void save();
  };

  return (
    <>
      <Dialog open onOpenChange={(_, data) => !data.open && !pending && onClose()}>
      <DialogSurface className="member-dialog-surface">
        <form onSubmit={submit} noValidate>
          <DialogBody>
            <DialogTitle>{member ? "编辑企业员工" : "创建企业员工"}</DialogTitle>
            <DialogContent className="member-dialog-content">
              <FormFeedback error={error} />
              <div className="form-grid two-columns">
                <Field
                  label="登录账号"
                  required={!member}
                  hint={member ? "登录账号创建后不可在此修改。" : "支持邮箱、手机号或企业内唯一账号。"}
                >
                  <Input
                    value={form.account}
                    disabled={Boolean(member) || pending}
                    autoComplete="off"
                    onChange={(_, data) => setForm((value) => ({ ...value, account: data.value }))}
                  />
                </Field>
                <Field
                  label="显示姓名"
                  required
                  validationState={attempted && !form.displayName.trim() ? "error" : "none"}
                  validationMessage={attempted && !form.displayName.trim() ? "请输入显示姓名。" : undefined}
                >
                  <Input
                    value={form.displayName}
                    disabled={pending}
                    onChange={(_, data) => setForm((value) => ({ ...value, displayName: data.value }))}
                  />
                </Field>
                {!member && (
                  <Field
                    label="初始密码"
                    required
                    hint="至少 12 个字符，请通过安全渠道交付。"
                    validationState={attempted && form.password.length < 12 ? "error" : "none"}
                    validationMessage={attempted && form.password.length < 12 ? "密码至少需要 12 个字符。" : undefined}
                  >
                    <Input
                      type="password"
                      autoComplete="new-password"
                      value={form.password}
                      disabled={pending}
                      onChange={(_, data) => setForm((value) => ({ ...value, password: data.value }))}
                    />
                  </Field>
                )}
                <Field label="角色">
                  <Select
                    value={form.role}
                    disabled={pending}
                    onChange={(_, data) => setForm((value) => ({ ...value, role: data.value as MemberRole }))}
                  >
                    <option value="card_owner">名片成员</option>
                    <option value="company_admin">企业管理员</option>
                  </Select>
                </Field>
                <Field label="职位" hint="员工名片会直接使用这里的职位。">
                  <Input value={form.jobTitle} disabled={pending} onChange={(_, data) => setForm((value) => ({ ...value, jobTitle: data.value }))} />
                </Field>
                <Field label="员工头像" hint="上传后员工名片会自动同步，无需在名片里重复维护。">
                  <div className="member-avatar-field">
                    {(avatarFile || form.avatarUrl) && <span>{avatarFile?.name || "已设置头像"}</span>}
                    <input ref={avatarInputRef} hidden type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => setAvatarFile(event.target.files?.[0])} />
                    <Button type="button" appearance="secondary" icon={<ArrowUpload24Regular />} disabled={pending} onClick={() => avatarInputRef.current?.click()}>选择图片</Button>
                  </div>
                </Field>
                <Field label="个人业务摘要" hint="用于员工名片的业务介绍；不改变企业公共资料。" className="form-field-span-2">
                  <Textarea value={form.businessSummary} disabled={pending} onChange={(_, data) => setForm((value) => ({ ...value, businessSummary: data.value }))} />
                </Field>
                <Field label="个人定位" hint="基础名片姓名下方的一句话定位，建议控制在 24 个字内。" className="form-field-span-2">
                  <Input value={form.publicPositioning ?? ""} maxLength={240} disabled={pending} onChange={(_, data) => setForm((value) => ({ ...value, publicPositioning: data.value }))} />
                </Field>
                <Field label="身份头衔" hint="逐项显示在员工基础名片中，最多 5 项。" className="form-field-span-2">
                  <IdentityTitlesEditor values={form.identityTitles ?? []} maxItems={5} disabled={pending} onChange={(identityTitles) => setForm((value) => ({ ...value, identityTitles }))} />
                </Field>
                <Field label="专业标签" hint="基础名片最多展示 3 个短标签。" className="form-field-span-2">
                  <IdentityTitlesEditor values={form.professionalTags ?? []} maxItems={3} maxItemLength={40} kind="enterprise" itemLabel="专业标签" addButtonLabel="添加标签" emptyExample="例如：企业 AI" disabled={pending} onChange={(professionalTags) => setForm((value) => ({ ...value, professionalTags }))} />
                </Field>
                <>
                    <Field label="邮箱" hint="可选；邮箱账号会自动作为邮箱。">
                      <Input
                        type="email"
                        value={form.email}
                        disabled={pending}
                        onChange={(_, data) => setForm((value) => ({ ...value, email: data.value }))}
                      />
                    </Field>
                    <Field label="手机号" hint="可选；支持国际区号。">
                      <Input
                        value={form.mobile}
                        disabled={pending}
                        onChange={(_, data) => setForm((value) => ({ ...value, mobile: data.value }))}
                      />
                    </Field>
                    {!member ? <Field label="初始状态">
                      <Select
                        value={form.status}
                        disabled={pending}
                        onChange={(_, data) => setForm((value) => ({ ...value, status: data.value as MemberStatus }))}
                      >
                        <option value="active">启用</option>
                        <option value="disabled">停用</option>
                      </Select>
                    </Field> : null}
                    {!member ? <Switch
                      checked={Boolean(form.rotatePassword)}
                      label="首次登录后提醒轮换密码"
                      disabled={pending}
                      onChange={(_, data) => setForm((value) => ({ ...value, rotatePassword: data.checked }))}
                    /> : null}
                  </>
              </div>
              <PermissionPicker
                values={form.permissions}
                onChange={(permissions) => setForm((value) => ({ ...value, permissions }))}
                disabled={pending || form.role === "company_admin"}
              />
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={onClose} disabled={pending}>取消</Button>
              <Button appearance="primary" type="submit" disabled={pending || (attempted && !valid)}>
                {pending ? "正在保存" : member ? "保存员工" : "创建员工"}
              </Button>
            </DialogActions>
          </DialogBody>
        </form>
      </DialogSurface>
      </Dialog>
      {confirmRoleChange && member ? (
        <ActionConfirmDialog
          open
          title="移除企业管理员角色"
          description={`确认将 ${member.displayName} 调整为名片成员。若这是最后一位启用中的企业管理员，服务端会拒绝该操作。`}
          confirmLabel="确认调整角色"
          pendingLabel="正在保存"
          pending={pending}
          error={error}
          destructive
          onCancel={() => setConfirmRoleChange(false)}
          onConfirm={() => {
            setConfirmRoleChange(false);
            void save(true);
          }}
        />
      ) : null}
    </>
  );
}

function PasswordDialog({
  member,
  onClose,
  onSaved,
}: {
  member: CompanyMember;
  onClose: () => void;
  onSaved: (notice: string) => void;
}) {
  const [password, setPassword] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError>();

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    setError(undefined);
    if (password.length < 12 || pending) return;
    setPending(true);
    try {
      const result = await memberApi.resetPassword(member.membershipId, password);
      onSaved(`已重置 ${member.displayName} 的密码，并撤销 ${result.sessionsRevoked} 个会话。`);
      onClose();
    } catch (caught) {
      setError(friendlyMemberError(apiError(caught, "重置密码时发生未知错误。")));
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open onOpenChange={(_, data) => !data.open && !pending && onClose()}>
      <DialogSurface>
        <form onSubmit={submit} noValidate>
          <DialogBody>
            <DialogTitle>重置用户密码</DialogTitle>
            <DialogContent className="member-dialog-content">
              <p className="member-dialog-description">新密码生效后，{member.displayName} 的现有登录会话会立即撤销。</p>
              <FormFeedback error={error} />
              <Field
                label="新密码"
                required
                hint="至少 12 个字符，请不要通过公开渠道发送。"
                validationState={attempted && password.length < 12 ? "error" : "none"}
                validationMessage={attempted && password.length < 12 ? "密码至少需要 12 个字符。" : undefined}
              >
                <Input type="password" autoComplete="new-password" value={password} disabled={pending} onChange={(_, data) => setPassword(data.value)} />
              </Field>
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={onClose} disabled={pending}>取消</Button>
              <Button appearance="primary" type="submit" disabled={pending || (attempted && password.length < 12)}>
                {pending ? "正在重置" : "确认重置"}
              </Button>
            </DialogActions>
          </DialogBody>
        </form>
      </DialogSurface>
    </Dialog>
  );
}

function ImportDialog({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: (result: BulkMemberResult) => void;
}) {
  const [mode, setMode] = useState<ImportMode>("csv");
  const [content, setContent] = useState("");
  const [fileName, setFileName] = useState<string>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError>();
  const fileRef = useRef<HTMLInputElement>(null);

  const readFile = async (file?: File) => {
    if (!file) return;
    setError(undefined);
    try {
      setContent(await file.text());
      setFileName(file.name);
    } catch {
      setError(new ApiError("无法读取所选文件，请确认文件编码为 UTF-8。", { code: "FILE_READ_ERROR" }));
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(undefined);
    if (!content.trim() || pending) return;
    setPending(true);
    try {
      let result: BulkMemberResult;
      if (mode === "csv") {
        result = await memberApi.bulkCsv(content);
      } else {
        const parsed = JSON.parse(content) as unknown;
        const rows = Array.isArray(parsed)
          ? parsed
          : typeof parsed === "object" && parsed !== null && "rows" in parsed
            ? (parsed as { rows: unknown }).rows
            : undefined;
        if (!Array.isArray(rows) || !rows.every((row) => typeof row === "object" && row !== null && !Array.isArray(row))) {
          throw new ApiError("JSON 必须是成员对象数组，或包含 rows 数组。", { code: "JSON_ROWS_INVALID" });
        }
        result = await memberApi.bulkJson(rows as Array<Record<string, unknown>>);
      }
      onImported(result);
      onClose();
    } catch (caught) {
      setError(
        caught instanceof SyntaxError
          ? new ApiError("JSON 文本无法解析，请检查括号、引号和逗号。", { code: "JSON_INVALID" })
          : friendlyMemberError(apiError(caught, "批量导入时发生未知错误。")),
      );
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open onOpenChange={(_, data) => !data.open && !pending && onClose()}>
      <DialogSurface className="member-dialog-surface wide">
        <form onSubmit={submit} noValidate>
          <DialogBody>
            <DialogTitle>批量导入企业员工</DialogTitle>
            <DialogContent className="member-dialog-content">
              <FormFeedback error={error} />
              <div className="member-import-toolbar">
                <Field label="导入格式">
                  <Select value={mode} disabled={pending} onChange={(_, data) => { setMode(data.value as ImportMode); setContent(""); setFileName(undefined); setError(undefined); }}>
                    <option value="csv">CSV</option>
                    <option value="json">JSON</option>
                  </Select>
                </Field>
                <div className="member-file-picker">
                  <input
                    ref={fileRef}
                    type="file"
                    hidden
                    accept={mode === "csv" ? ".csv,text/csv" : ".json,application/json"}
                    onChange={(event) => void readFile(event.target.files?.[0])}
                  />
                  <Button type="button" appearance="secondary" icon={<ArrowUpload24Regular />} onClick={() => fileRef.current?.click()} disabled={pending}>
                    读取文件
                  </Button>
                  <span>{fileName || "也可直接粘贴文本"}</span>
                </div>
              </div>
              <MessageBar intent="info">
                <MessageBarBody>
                  {mode === "csv"
                    ? "必需列：account、display_name、password。permissions 使用 | 分隔；最多 100 行。"
                    : "接受对象数组或 {\"rows\": [...]}。字段使用服务端 snake_case，例如 display_name、rotate_password。"}
                </MessageBarBody>
              </MessageBar>
              <Field label={mode === "csv" ? "CSV 文本" : "JSON 文本"} required>
                <Textarea
                  className="member-import-textarea"
                  resize="vertical"
                  value={content}
                  disabled={pending}
                  placeholder={
                    mode === "csv"
                      ? "account,display_name,password,role,permissions,status\nmember@example.com,张三,SecurePassword!2026,card_owner,card.read|leads.write,active"
                      : '[{"account":"member@example.com","display_name":"张三","password":"SecurePassword!2026"}]'
                  }
                  onChange={(_, data) => setContent(data.value)}
                />
              </Field>
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={onClose} disabled={pending}>取消</Button>
              <Button appearance="primary" type="submit" disabled={pending || !content.trim()}>
                {pending ? "正在导入" : "开始导入"}
              </Button>
            </DialogActions>
          </DialogBody>
        </form>
      </DialogSurface>
    </Dialog>
  );
}

const outcomeLabels: Record<string, string> = {
  created: "已创建",
  updated: "已更新",
  unchanged: "无变化",
  duplicate: "重复行",
  failed: "失败",
};

export function MembersPage() {
  const auth = useAuth();
  const allowed = hasPermission(auth.user, "members.manage");
  const [offset, setOffset] = useState(0);
  const [editor, setEditor] = useState<CompanyMember | "create">();
  const [resetMember, setResetMember] = useState<CompanyMember>();
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>();
  const [importOpen, setImportOpen] = useState(false);
  const [importResult, setImportResult] = useState<BulkMemberResult>();
  const [notice, setNotice] = useState<string>();
  const [actionError, setActionError] = useState<ApiError>();
  const [actionPending, setActionPending] = useState(false);
  const resource = useResource(
    () =>
      allowed
        ? memberApi.listMembers(PAGE_SIZE, offset)
        : Promise.reject(
            new ApiError("当前账号没有企业员工管理权限。", {
              code: "FORBIDDEN",
              status: 403,
            }),
          ),
    `${offset}:${allowed}`,
  );
  const currentMembershipId = auth.user?.membershipId;

  const counts = useMemo(() => {
    const items = resource.data?.items ?? [];
    return {
      active: items.filter((item) => item.status === "active").length,
      admins: items.filter((item) => item.role === "company_admin" && item.status === "active").length,
    };
  }, [resource.data]);

  const changed = (message: string) => {
    setNotice(message);
    setActionError(undefined);
    resource.reload();
  };

  const confirmStatus = async () => {
    if (!confirmAction || actionPending) return;
    setActionPending(true);
    setActionError(undefined);
    try {
      const updated = await memberApi.setStatus(confirmAction.member.membershipId, confirmAction.status);
      changed(`${updated.displayName} 已${MEMBER_STATUS_LABELS[updated.status]}。`);
      setConfirmAction(undefined);
    } catch (caught) {
      setActionError(friendlyMemberError(apiError(caught, "更新用户状态时发生未知错误。")));
    } finally {
      setActionPending(false);
    }
  };

  const imported = (result: BulkMemberResult) => {
    setImportResult(result);
    setNotice(`批量导入已处理 ${result.summary.total} 行，成功 ${result.summary.succeeded} 行，失败 ${result.summary.failed} 行。`);
    resource.reload();
  };

  return (
    <main className="page-stack members-page">
      <PageHeader
        title="企业员工"
        description="管理员工基础资料、登录、角色、权限和账号状态；员工名片会直接读取姓名、职位、头像和业务摘要。"
        actions={
          allowed ? <>
            <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>刷新</Button>
            <Button appearance="secondary" icon={<ArrowUpload24Regular />} onClick={() => setImportOpen(true)}>批量导入</Button>
            <Button appearance="primary" icon={<Add24Regular />} onClick={() => setEditor("create")}>创建员工</Button>
          </> : undefined
        }
      />

      <OperationFeedback notice={notice} error={actionError} onRetry={resource.reload} />

      {resource.status === "ready" && resource.data && (
        <section className="member-summary-strip" aria-label="企业员工摘要">
          <div><span>员工总数</span><strong>{resource.data.total}</strong></div>
          <div><span>本页启用</span><strong>{counts.active}</strong></div>
          <div><span>本页启用管理员</span><strong>{counts.admins}</strong></div>
          <p>停用用户会立即撤销登录会话；系统阻止停用或降级最后一位启用中的企业管理员。</p>
        </section>
      )}

      <section className="content-panel data-panel members-panel">
        {resource.status === "ready" && resource.data ? (
          resource.data.items.length === 0 ? (
            <ResourceState
              status="empty"
            title="尚未创建企业员工"
            description="创建企业管理员或名片成员后，可在这里维护员工资料、权限与登录状态。"
            emptyAction={<Button appearance="primary" icon={<Add24Regular />} onClick={() => setEditor("create")}>创建第一位员工</Button>}
            />
          ) : (
            <>
              <div className="table-scroll">
                <Table aria-label="企业员工列表" size="small">
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>企业员工</TableHeaderCell>
                      <TableHeaderCell>角色与权限</TableHeaderCell>
                      <TableHeaderCell>状态</TableHeaderCell>
                      <TableHeaderCell>更新时间</TableHeaderCell>
                      <TableHeaderCell>操作</TableHeaderCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resource.data.items.map((member) => {
                      const self = member.membershipId === currentMembershipId;
                      return (
                        <TableRow key={member.membershipId}>
                          <TableCell>
                            <div className="member-identity-cell">
                              <strong>{member.displayName}{self && <Badge appearance="outline" size="small">当前账号</Badge>}</strong>
                              <span>{member.account}</span>
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="member-access-cell">
                              <strong>{MEMBER_ROLE_LABELS[member.role]}</strong>
                              <span>{member.role === "company_admin" ? "完整企业治理权限" : member.permissions.length ? member.permissions.join("、") : "未分配额外权限"}</span>
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="member-status-cell">
                              <StatusBadge status={member.status} />
                              {!member.credentialEnabled && <span>凭据已禁用</span>}
                            </div>
                          </TableCell>
                          <TableCell className="updated-column">{formatTimestamp(member.updatedAt)}</TableCell>
                          <TableCell className="member-actions-column">
                            <div className="row-actions member-row-actions">
                              <Button appearance="subtle" size="small" icon={<Edit24Regular />} onClick={() => setEditor(member)} disabled={!allowed}>编辑</Button>
                              <Button appearance="subtle" size="small" icon={<KeyReset24Regular />} onClick={() => setResetMember(member)} disabled={!allowed}>重置密码</Button>
                              <Button
                                appearance="subtle"
                                size="small"
                                className={member.status === "active" ? "danger-outline-button" : undefined}
                                icon={member.status === "active" ? <LockClosed24Regular /> : <LockOpen24Regular />}
                                disabled={!allowed}
                                onClick={() => setConfirmAction({ member, status: member.status === "active" ? "disabled" : "active" })}
                              >
                                {member.status === "active" ? "停用" : "启用"}
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
              <PaginationBar total={resource.data.total} limit={resource.data.limit} offset={resource.data.offset} onOffsetChange={setOffset} />
            </>
          )
        ) : (
          <ResourceState
            status={resource.status === "ready" ? "empty" : resource.status}
            title={resource.status === "permission" ? "没有企业员工管理权限" : undefined}
            description={resource.error?.message}
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
          />
        )}
      </section>

      {importResult && (
        <section className="content-panel member-import-results" aria-label="最近一次批量导入结果">
          <div className="section-heading-inline">
            <div><h2>逐行导入结果</h2><p>批次 {importResult.batchId}，失败行可修正后再次导入。</p></div>
            <Button appearance="subtle" onClick={() => setImportResult(undefined)}>收起</Button>
          </div>
          <div className="member-import-summary">
            <span>总计 {importResult.summary.total}</span><span>创建 {importResult.summary.created}</span><span>更新 {importResult.summary.updated}</span><span>无变化 {importResult.summary.unchanged}</span><span>重复 {importResult.summary.duplicated}</span><span>失败 {importResult.summary.failed}</span>
          </div>
          <div className="table-scroll">
            <Table aria-label="批量导入逐行结果" size="small">
              <TableHeader><TableRow><TableHeaderCell>行号</TableHeaderCell><TableHeaderCell>账号</TableHeaderCell><TableHeaderCell>结果</TableHeaderCell><TableHeaderCell>反馈</TableHeaderCell></TableRow></TableHeader>
              <TableBody>
                {importResult.rows.map((row) => (
                  <TableRow key={row.rowNumber}>
                    <TableCell>{row.rowNumber}</TableCell>
                    <TableCell>{row.account || "未识别"}</TableCell>
                    <TableCell><Badge appearance="tint" color={row.outcome === "failed" ? "danger" : row.outcome === "duplicate" ? "warning" : "success"}>{outcomeLabels[row.outcome]}</Badge></TableCell>
                    <TableCell>{row.error ? `${row.error.message}${row.error.fields.length ? `（字段：${row.error.fields.join("、")}）` : ""}` : row.duplicateOfRow ? `与第 ${row.duplicateOfRow} 行重复` : row.member?.displayName || "处理完成"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </section>
      )}

      {editor && <MemberEditor key={editor === "create" ? "create" : editor.membershipId} member={editor === "create" ? undefined : editor} onClose={() => setEditor(undefined)} onSaved={changed} />}
      {resetMember && <PasswordDialog member={resetMember} onClose={() => setResetMember(undefined)} onSaved={changed} />}
      {importOpen && <ImportDialog onClose={() => setImportOpen(false)} onImported={imported} />}
      {confirmAction && (
        <ActionConfirmDialog
          open
          title={confirmAction.status === "disabled" ? "停用企业员工" : "启用企业员工"}
          description={confirmAction.status === "disabled" ? `停用 ${confirmAction.member.displayName} 后，其现有登录会话会立即撤销。` : `启用 ${confirmAction.member.displayName} 后，该账号可重新登录。`}
          detail={confirmAction.member.membershipId === currentMembershipId && confirmAction.status === "disabled" ? <MessageBar intent="warning"><MessageBarBody>这是当前登录账号。服务端可能拒绝自我停用，请确认已有其他企业管理员。</MessageBarBody></MessageBar> : undefined}
          confirmLabel={confirmAction.status === "disabled" ? "确认停用" : "确认启用"}
          pendingLabel={confirmAction.status === "disabled" ? "正在停用" : "正在启用"}
          pending={actionPending}
          error={actionError}
          destructive={confirmAction.status === "disabled"}
          onCancel={() => { if (!actionPending) { setConfirmAction(undefined); setActionError(undefined); } }}
          onConfirm={() => void confirmStatus()}
          onReload={resource.reload}
        />
      )}
    </main>
  );
}

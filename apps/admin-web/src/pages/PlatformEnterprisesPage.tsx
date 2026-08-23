import {
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
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import {
  Add24Regular,
  ArrowClockwise24Regular,
  Book24Regular,
  Dismiss24Regular,
  Search24Regular,
} from "@fluentui/react-icons";
import { type FormEvent, useMemo, useState } from "react";

import { ApiError } from "../api/client";
import { platformApi } from "../api/platformApi";
import type {
  PlatformCompanyAggregate,
  PlatformTaskProjection,
} from "../api/types";
import { FormFeedback } from "../components/FormFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import {
  APP_PATHS,
  navigate,
  platformEnterprisePath,
} from "../routing";
import { formatTimestamp } from "../utils/format";
import styles from "./PlatformEnterpriseDrawer.module.css";

type DirectEnterpriseFormValues = {
  legalName: string;
  shortName: string;
  subjectType: "domestic_enterprise" | "association" | "overseas" | "pending_registration";
  socialCreditCode: string;
  industry: string;
  adminAccount: string;
  adminDisplayName: string;
  defaultPlan: "starter" | "professional" | "enterprise";
};

type CredentialNotice = {
  companyName: string;
  account: string;
  temporaryPassword: string;
  expiresAt: string;
  subjectType: DirectEnterpriseFormValues["subjectType"];
  socialCreditCode?: string;
  defaultPlan: DirectEnterpriseFormValues["defaultPlan"];
};

const emptyInput: DirectEnterpriseFormValues = {
  legalName: "",
  shortName: "",
  subjectType: "domestic_enterprise",
  socialCreditCode: "",
  industry: "",
  adminAccount: "",
  adminDisplayName: "",
  defaultPlan: "starter",
};

const socialCreditCodePattern = /^[0-9A-Z]{18}$/;

function normalizeSocialCreditCode(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

function toApiError(value: unknown): ApiError {
  return value instanceof ApiError
    ? value
    : new ApiError("创建企业时发生未知错误。", { code: "UNKNOWN_ERROR" });
}

function taskAttentionCount(tasks: PlatformTaskProjection[] | undefined, companyId: string): number {
  return (
    tasks?.filter(
      (task) =>
        task.companyId === companyId &&
        ["pending", "queued", "processing", "running", "review", "manual_required", "failed", "error", "blocked", "expired"].includes(task.status),
    ).length ?? 0
  );
}

function lastActivityLabel(aggregate: PlatformCompanyAggregate | undefined): string {
  return aggregate?.lastVisitAt ? formatTimestamp(aggregate.lastVisitAt) : "暂无访问";
}

export function PlatformEnterprisesPage() {
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<
    "" | "active" | "suspended" | "disabled"
  >("");
  const enterpriseResource = useResource(
    () =>
      platformApi.listEnterprises({
        search: search || undefined,
        status: statusFilter || undefined,
        limit: 100,
      }),
    `${search}:${statusFilter}`,
  );
  const aggregateResource = useResource(
    () => platformApi.listCompanyAggregates(),
    `${search}:${statusFilter}`,
  );
  const taskResource = useResource(
    () => platformApi.listTasks(),
    `${search}:${statusFilter}`,
  );
  const overviewResource = useResource(
    () => platformApi.getOverview(),
    `${search}:${statusFilter}`,
  );
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState(emptyInput);
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();
  const [credentialNotice, setCredentialNotice] = useState<CredentialNotice>();
  const normalizedCreditCode = normalizeSocialCreditCode(input.socialCreditCode);
  const valid =
    Boolean(input.legalName.trim()) &&
    Boolean(input.adminAccount.trim()) &&
    Boolean(input.adminDisplayName.trim()) &&
    (input.subjectType !== "domestic_enterprise" || socialCreditCodePattern.test(normalizedCreditCode));

  const update = <K extends keyof DirectEnterpriseFormValues>(
    field: K,
    value: DirectEnterpriseFormValues[K],
  ) => setInput((current) => ({ ...current, [field]: value }));

  const aggregateMap = useMemo(
    () =>
      new Map(
        (aggregateResource.data ?? []).map((item) => [item.companyId, item] as const),
      ),
    [aggregateResource.data],
  );

  const showCreate = () => {
    setInput(emptyInput);
    setAttempted(false);
    setError(undefined);
    setOpen(true);
  };

  const reloadAll = () => {
    enterpriseResource.reload();
    aggregateResource.reload();
    taskResource.reload();
    overviewResource.reload();
  };

  const applyFilters = () => {
    const next = searchDraft.trim();
    if (next === search) reloadAll();
    setSearch(next);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    setError(undefined);
    if (!valid || saving) return;
    setSaving(true);
    try {
      const created = await platformApi.createEnterprise({
        legalName: input.legalName.trim(),
        shortName: input.shortName.trim() || undefined,
        subjectType: input.subjectType,
        socialCreditCode: normalizedCreditCode || undefined,
        industry: input.industry,
        adminAccount: input.adminAccount,
        adminDisplayName: input.adminDisplayName,
        defaultPlanCode: input.defaultPlan,
      });
      if (!created.credentialDelivery) {
        throw new ApiError("企业已创建，但服务端未返回一次性管理员凭据。", {
          code: "CREDENTIAL_DELIVERY_MISSING",
        });
      }
      setNotice(`企业 ${created.companyName} 已开通，当前为零名片状态。`);
      setCredentialNotice({
        companyName: created.companyName,
        account: created.credentialDelivery.account,
        temporaryPassword: created.credentialDelivery.temporaryPassword,
        expiresAt: created.credentialDelivery.expiresAt,
        subjectType: input.subjectType,
        socialCreditCode: normalizedCreditCode || undefined,
        defaultPlan: input.defaultPlan,
      });
      setInput(emptyInput);
      setOpen(false);
      reloadAll();
    } catch (caught) {
      setError(toApiError(caught));
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="page-stack platform-console">
      <PageHeader
        title="企业中心"
        description="企业列表连接独立详情页；平台只开通企业身份、管理员与隔离空间，名片由企业自行创建。"
        actions={
          enterpriseResource.status === "permission" ? undefined : (
            <>
              <Button
                appearance="subtle"
                icon={<ArrowClockwise24Regular />}
                onClick={reloadAll}
              >
                刷新
              </Button>
              <Button
                appearance="secondary"
                icon={<Book24Regular />}
                onClick={() => navigate(APP_PATHS.platformOnboarding)}
              >
                从甲方资料创建
              </Button>
              <Button appearance="primary" icon={<Add24Regular />} onClick={showCreate}>
                直接开通企业
              </Button>
            </>
          )
        }
      />

      {notice && (
        <MessageBar intent="success">
          <MessageBarBody>{notice}</MessageBarBody>
        </MessageBar>
      )}

      {credentialNotice && (
        <section className="content-panel">
          <div className={styles.sectionTitle}>
            <div>
              <strong>一次性管理员凭据</strong>
              <p>
                本次只创建企业与管理员，不创建名片。当前旧 API 不返回凭据有效期，以下密码仅在此提示中显示一次。
              </p>
            </div>
          </div>
          <div className={styles.credentialGrid}>
            <div>
              <span>企业</span>
              <strong>{credentialNotice.companyName}</strong>
            </div>
            <div>
              <span>管理员账号</span>
              <strong>{credentialNotice.account}</strong>
            </div>
            <div>
              <span>一次性密码</span>
              <strong>{credentialNotice.temporaryPassword}</strong>
            </div>
            <div>
              <span>名片交付</span>
              <strong>0 张</strong>
            </div>
          </div>
          <div className={styles.legacyNotice}>
            <strong>企业身份已由服务端确认</strong>
            <p>
              默认套餐 {credentialNotice.defaultPlan}；一次性密码有效至
              {formatTimestamp(credentialNotice.expiresAt)}。平台没有创建名片或公开链接。
            </p>
          </div>
        </section>
      )}

      {overviewResource.status === "ready" && overviewResource.data && (
        <section className={styles.summaryStrip} aria-label="企业中心摘要">
          <article>
            <span>已启用企业</span>
            <strong>{overviewResource.data.activeEnterpriseCount}</strong>
            <p>共 {overviewResource.data.enterpriseCount} 家企业</p>
          </article>
          <article>
            <span>近 30 天访问</span>
            <strong>{overviewResource.data.visits30d}</strong>
            <p>对话 {overviewResource.data.conversations30d} · 留资 {overviewResource.data.leads30d}</p>
          </article>
          <article>
            <span>需处理任务</span>
            <strong>{overviewResource.data.failedTaskCount + overviewResource.data.onboardingCount}</strong>
            <p>待建企 {overviewResource.data.onboardingCount} · 异常 {overviewResource.data.failedTaskCount}</p>
          </article>
        </section>
      )}

      <section className="content-panel filter-panel" aria-label="企业筛选">
        <Select
          aria-label="企业状态"
          value={statusFilter}
          onChange={(_, data) =>
            setStatusFilter(
              data.value as "" | "active" | "suspended" | "disabled",
            )
          }
        >
          <option value="">全部状态</option>
          <option value="active">正常运营</option>
          <option value="suspended">已暂停</option>
          <option value="disabled">已停用</option>
        </Select>
        <Input
          aria-label="搜索企业"
          placeholder="企业名称、工作区名称或技术标识"
          value={searchDraft}
          onChange={(_, data) => setSearchDraft(data.value)}
          onKeyDown={(event) => event.key === "Enter" && applyFilters()}
        />
        <Button icon={<Search24Regular />} onClick={applyFilters}>
          搜索
        </Button>
        {(search || statusFilter) && (
          <Button
            appearance="subtle"
            icon={<Dismiss24Regular />}
            onClick={() => {
              setSearchDraft("");
              setSearch("");
              setStatusFilter("");
            }}
          >
            清除
          </Button>
        )}
      </section>

      <section className="content-panel catalog-panel">
        {enterpriseResource.status !== "ready" && (
          <ResourceState
            status={enterpriseResource.status}
            title={
              enterpriseResource.status === "empty"
                ? search || statusFilter
                  ? "没有符合条件的企业"
                  : "尚未开通企业"
                : undefined
            }
            description={
              enterpriseResource.status === "empty"
                ? search || statusFilter
                  ? "调整关键词或状态后重新搜索。"
                  : "开通后，企业管理员可登录并维护自己的资料和名片。"
                : enterpriseResource.error?.message
            }
            errorCode={enterpriseResource.error?.code}
            requestId={enterpriseResource.error?.requestId}
            onRetry={enterpriseResource.status === "error" ? enterpriseResource.reload : undefined}
            emptyAction={
              <Button appearance="primary" icon={<Add24Regular />} onClick={showCreate}>
                开通第一家企业
              </Button>
            }
          />
        )}

        {enterpriseResource.status === "ready" && enterpriseResource.data && (
          <div className={`table-scroll ${styles.desktopTable}`}>
            <Table aria-label="平台企业列表" size="small">
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>企业</TableHeaderCell>
                  <TableHeaderCell>工作区</TableHeaderCell>
                  <TableHeaderCell>状态</TableHeaderCell>
                  <TableHeaderCell>成员 / 访问</TableHeaderCell>
                  <TableHeaderCell>最近活动</TableHeaderCell>
                  <TableHeaderCell>任务</TableHeaderCell>
                  <TableHeaderCell>操作</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {enterpriseResource.data.map((item) => {
                  const aggregate = aggregateMap.get(item.companyId);
                  const attentionCount = taskAttentionCount(taskResource.data, item.companyId);
                  return (
                    <TableRow key={item.companyId}>
                      <TableCell>
                        <button
                          className={styles.entityLink}
                          onClick={() => navigate(platformEnterprisePath(item.companyId, "overview"))}
                          type="button"
                        >
                          {item.companyName}
                        </button>
                        <div className="cell-secondary">开通于 {formatTimestamp(item.createdAt)}</div>
                      </TableCell>
                      <TableCell>
                        <strong>{item.tenantName}</strong>
                        <div className="cell-secondary">{item.tenantSlug}</div>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={item.status} />
                      </TableCell>
                      <TableCell>
                        {aggregate ? `${aggregate.employeeCount} 人 / ${aggregate.visits30d} 次` : "聚合中"}
                      </TableCell>
                      <TableCell>{lastActivityLabel(aggregate)}</TableCell>
                      <TableCell>{attentionCount > 0 ? `${attentionCount} 项待处理` : "正常"}</TableCell>
                      <TableCell>
                        <Button
                          appearance="secondary"
                          size="small"
                          onClick={() => navigate(platformEnterprisePath(item.companyId, "overview"))}
                        >
                          进入详情
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}

        {enterpriseResource.status === "ready" && enterpriseResource.data && (
          <div className={styles.mobileRecords} aria-label="平台企业列表">
            {enterpriseResource.data.map((item) => {
              const aggregate = aggregateMap.get(item.companyId);
              const attentionCount = taskAttentionCount(taskResource.data, item.companyId);
              return (
                <article className={styles.recordCard} key={item.companyId}>
                  <div className={styles.recordHeader}>
                    <div className={styles.recordTitle}>
                      <button
                        className={styles.entityLink}
                        onClick={() => navigate(platformEnterprisePath(item.companyId, "overview"))}
                        type="button"
                      >
                        {item.companyName}
                      </button>
                      <p>
                        {item.tenantName} · {item.tenantSlug}
                      </p>
                    </div>
                    <StatusBadge status={item.status} />
                  </div>
                  <dl className={styles.recordFacts}>
                    <div>
                      <dt>成员 / 访问</dt>
                      <dd>{aggregate ? `${aggregate.employeeCount} / ${aggregate.visits30d}` : "聚合中"}</dd>
                    </div>
                    <div>
                      <dt>最近活动</dt>
                      <dd>{lastActivityLabel(aggregate)}</dd>
                    </div>
                    <div>
                      <dt>任务</dt>
                      <dd>{attentionCount > 0 ? `${attentionCount} 项待处理` : "正常"}</dd>
                    </div>
                  </dl>
                  <div className={styles.recordActions}>
                    <span className="cell-secondary">{formatTimestamp(item.createdAt)}</span>
                    <Button
                      appearance="secondary"
                      size="small"
                      onClick={() => navigate(platformEnterprisePath(item.companyId, "overview"))}
                    >
                      进入详情
                    </Button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <Dialog
        open={open}
        onOpenChange={(_, data) => {
          if (!data.open && !saving) setOpen(false);
        }}
      >
        <DialogSurface>
          <form onSubmit={submit} noValidate>
            <DialogBody>
              <DialogTitle>直接开通企业</DialogTitle>
              <DialogContent className="catalog-editor-form">
                <FormFeedback error={error} />
                <div className="form-grid two-column">
                  <Field label="企业正式名称" required>
                    <Input
                      value={input.legalName}
                      onChange={(_, data) => update("legalName", data.value)}
                    />
                  </Field>
                  <Field label="企业简称">
                    <Input
                      value={input.shortName}
                      onChange={(_, data) => update("shortName", data.value)}
                    />
                  </Field>
                  <Field label="主体类型" required>
                    <Select
                      value={input.subjectType}
                      onChange={(_, data) => update("subjectType", data.value as DirectEnterpriseFormValues["subjectType"])}
                    >
                      <option value="domestic_enterprise">国内企业</option>
                      <option value="association">协会 / 机构</option>
                      <option value="overseas">境外主体</option>
                      <option value="pending_registration">筹备中</option>
                    </Select>
                  </Field>
                  <Field
                    label="统一社会信用代码"
                    validationState={attempted && input.subjectType === "domestic_enterprise" && !socialCreditCodePattern.test(normalizedCreditCode) ? "error" : "none"}
                    validationMessage={
                      attempted && input.subjectType === "domestic_enterprise" && !socialCreditCodePattern.test(normalizedCreditCode)
                        ? "国内企业必须填写 18 位统一社会信用代码。"
                        : input.subjectType === "domestic_enterprise"
                          ? "该代码将作为唯一业务租户标识，底层隔离仍使用不可变 UUID。"
                          : "协会、境外主体和筹备企业可留空，由系统生成稳定业务标识。"
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
                      onChange={(_, data) => update("adminAccount", data.value)}
                      autoComplete="off"
                    />
                  </Field>
                  <Field label="管理员姓名" required>
                    <Input
                      value={input.adminDisplayName}
                      onChange={(_, data) => update("adminDisplayName", data.value)}
                    />
                  </Field>
                  <Field label="默认套餐">
                    <Select
                      value={input.defaultPlan}
                      onChange={(_, data) => update("defaultPlan", data.value as DirectEnterpriseFormValues["defaultPlan"])}
                    >
                      <option value="starter">Starter</option>
                      <option value="professional">Professional</option>
                      <option value="enterprise">Enterprise</option>
                    </Select>
                  </Field>
                </div>
              </DialogContent>
              <DialogActions>
                <Button appearance="secondary" onClick={() => setOpen(false)} disabled={saving}>
                  取消
                </Button>
                <Button appearance="primary" type="submit" disabled={saving || (attempted && !valid)}>
                  {saving ? "正在开通" : "确认开通"}
                </Button>
              </DialogActions>
            </DialogBody>
          </form>
        </DialogSurface>
      </Dialog>
    </main>
  );
}

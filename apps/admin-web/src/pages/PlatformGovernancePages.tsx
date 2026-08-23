import {
  Badge,
  Button,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import { ArrowClockwise24Regular, Search24Regular } from "@fluentui/react-icons";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { platformApi } from "../api/platformApi";
import type {
  PlatformAuditProjection,
  PlatformServiceHealth,
  PlatformTaskProjection,
} from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import {
  APP_PATHS,
  appHref,
  navigate,
  platformEnterprisePath,
  replaceBrowserHref,
} from "../routing";
import { formatTimestamp, knowledgeStatusLabel } from "../utils/format";
import styles from "./PlatformGovernancePages.module.css";

function PageState<T>({
  resource,
  emptyTitle,
  children,
}: {
  resource: ReturnType<typeof useResource<T[]>>;
  emptyTitle: string;
  children: (data: T[]) => ReactNode;
}) {
  if (resource.status !== "ready" || !resource.data) {
    return (
      <section className="content-panel">
        <ResourceState
          status={resource.status === "ready" ? "empty" : resource.status}
          title={resource.status === "empty" ? emptyTitle : undefined}
          description={resource.error?.message}
          errorCode={resource.error?.code}
          requestId={resource.error?.requestId}
          onRetry={resource.status === "error" ? resource.reload : undefined}
        />
      </section>
    );
  }
  return <>{children(resource.data)}</>;
}

function Refresh({ onClick }: { onClick: () => void }) {
  return (
    <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={onClick}>
      刷新
    </Button>
  );
}

function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <Input
      className={styles.search}
      contentBefore={<Search24Regular />}
      value={value}
      placeholder={placeholder}
      onChange={(_, data) => onChange(data.value)}
    />
  );
}

function Summary({
  items,
}: {
  items: Array<[string, number, string?]>;
}) {
  return (
    <div className={styles.summary} aria-label="运营摘要">
      {items.map(([label, value, tone]) => (
        <div key={label} className={tone ? styles[tone] : undefined}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function normalizedTaskType(taskType: string): {
  type: "onboarding" | "knowledge_import" | "content_review" | "enterprise_risk" | "service_validity";
  label: string;
} {
  const value = taskType.toLowerCase();
  if (value.includes("onboarding")) return { type: "onboarding", label: "建企开通" };
  if (value.includes("import") || value.includes("knowledge")) return { type: "knowledge_import", label: "资料导入" };
  if (value.includes("review") || value.includes("content")) return { type: "content_review", label: "内容复核" };
  if (value.includes("service") || value.includes("expiry") || value.includes("validity")) {
    return { type: "service_validity", label: "服务有效期" };
  }
  return { type: "enterprise_risk", label: "企业风险" };
}

function normalizedTaskState(status: string): "attention" | "active" | "resolved" {
  if (["failed", "error", "blocked", "expired"].includes(status)) return "attention";
  if (["pending", "queued", "processing", "running", "review", "manual_required", "in_progress"].includes(status)) {
    return "active";
  }
  return "resolved";
}

function taskViewTitle(kind: ReturnType<typeof normalizedTaskType>["type"]): string {
  return {
    onboarding: "建企开通",
    knowledge_import: "资料导入",
    content_review: "内容复核",
    enterprise_risk: "企业风险",
    service_validity: "服务有效期",
  }[kind];
}

function RedirectToOverview({
  hash,
  title,
  description,
}: {
  hash: string;
  title: string;
  description: string;
}) {
  useEffect(() => {
    replaceBrowserHref(`${appHref(APP_PATHS.platformOverview)}${hash}`);
  }, [hash]);

  return (
    <main className="page-stack">
      <section className="content-panel">
        <ResourceState
          status="loading"
          title={title}
          description={description}
        />
      </section>
    </main>
  );
}

export function PlatformEmployeesPage() {
  return (
    <RedirectToOverview
      hash="#overview-enterprise-coverage"
      title="正在跳转到运营概览"
      description="员工概览已并入平台运营概览的企业覆盖区域。"
    />
  );
}

export function PlatformVisitorsPage() {
  return (
    <RedirectToOverview
      hash="#overview-traffic"
      title="正在跳转到运营概览"
      description="访客概览已并入平台运营概览的 30 天活跃区域。"
    />
  );
}

export function PlatformTasksPage() {
  const resource = useResource<PlatformTaskProjection[]>(() => platformApi.listTasks());
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "attention" | "resolved">("all");
  const [typeFilter, setTypeFilter] = useState<"all" | "onboarding" | "knowledge_import" | "content_review" | "enterprise_risk" | "service_validity">("all");
  const [view, setView] = useState<"timeline" | "company">("timeline");

  return (
    <main className="page-stack">
      <PageHeader
        title="任务中心"
        description="只展示可处理的运营事项；成功 outbox 投递与原始系统事件码不会进入这里。"
        actions={<Refresh onClick={resource.reload} />}
      />
      <PageState resource={resource} emptyTitle="当前没有运营任务">
        {(data) => {
          const filtered = data
            .filter((item) => {
              const status = normalizedTaskState(item.status);
              const type = normalizedTaskType(item.taskType).type;
              const queryText = `${item.businessLabel} ${item.companyName ?? ""} ${type}`.toLocaleLowerCase();
              return (
                (statusFilter === "all" || statusFilter === status) &&
                (typeFilter === "all" || typeFilter === type) &&
                queryText.includes(query.trim().toLocaleLowerCase())
              );
            })
            .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));

          const companyGroups = Object.values(
            filtered.reduce<Record<string, {
              companyId?: string;
              companyName: string;
              items: PlatformTaskProjection[];
            }>>((accumulator, item) => {
              const key = item.companyId ?? item.companyName ?? "platform";
              const label = item.companyName ?? "平台级事项";
              const current = accumulator[key] ?? {
                companyId: item.companyId,
                companyName: label,
                items: [],
              };
              current.items.push(item);
              accumulator[key] = current;
              return accumulator;
            }, {}),
          ).sort((left, right) => right.items.length - left.items.length);

          const attention = data.filter((item) => normalizedTaskState(item.status) === "attention").length;
          const active = data.filter((item) => normalizedTaskState(item.status) === "active").length;
          return (
            <>
              <Summary items={[["全部任务", data.length], ["处理中", active], ["需处理", attention, "danger"]]} />

              <section className="content-panel data-panel">
                <div className={styles.toolbar}>
                  <SearchBox value={query} onChange={setQuery} placeholder="搜索企业、任务或来源类型" />
                  <div className={styles.filterGroup}>
                    <Button appearance={view === "timeline" ? "primary" : "secondary"} size="small" onClick={() => setView("timeline")}>时间流</Button>
                    <Button appearance={view === "company" ? "primary" : "secondary"} size="small" onClick={() => setView("company")}>按企业</Button>
                  </div>
                </div>
                <div className={styles.toolbar}>
                  <div className={styles.filterGroup}>
                    <Button appearance={statusFilter === "all" ? "primary" : "secondary"} size="small" onClick={() => setStatusFilter("all")}>全部状态</Button>
                    <Button appearance={statusFilter === "active" ? "primary" : "secondary"} size="small" onClick={() => setStatusFilter("active")}>处理中</Button>
                    <Button appearance={statusFilter === "attention" ? "primary" : "secondary"} size="small" onClick={() => setStatusFilter("attention")}>需处理</Button>
                    <Button appearance={statusFilter === "resolved" ? "primary" : "secondary"} size="small" onClick={() => setStatusFilter("resolved")}>已归档</Button>
                  </div>
                  <div className={styles.filterGroup}>
                    <Button appearance={typeFilter === "all" ? "primary" : "secondary"} size="small" onClick={() => setTypeFilter("all")}>全部类型</Button>
                    <Button appearance={typeFilter === "onboarding" ? "primary" : "secondary"} size="small" onClick={() => setTypeFilter("onboarding")}>建企</Button>
                    <Button appearance={typeFilter === "knowledge_import" ? "primary" : "secondary"} size="small" onClick={() => setTypeFilter("knowledge_import")}>导入</Button>
                    <Button appearance={typeFilter === "content_review" ? "primary" : "secondary"} size="small" onClick={() => setTypeFilter("content_review")}>复核</Button>
                    <Button appearance={typeFilter === "enterprise_risk" ? "primary" : "secondary"} size="small" onClick={() => setTypeFilter("enterprise_risk")}>风险</Button>
                    <Button appearance={typeFilter === "service_validity" ? "primary" : "secondary"} size="small" onClick={() => setTypeFilter("service_validity")}>有效期</Button>
                  </div>
                </div>

                {view === "timeline" ? (
                  <Table className={styles.table} aria-label="平台任务时间流">
                    <TableHeader>
                      <TableRow>
                        <TableHeaderCell>事项</TableHeaderCell>
                        <TableHeaderCell>企业</TableHeaderCell>
                        <TableHeaderCell>状态</TableHeaderCell>
                        <TableHeaderCell>更新时间</TableHeaderCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filtered.map((item) => {
                        const type = normalizedTaskType(item.taskType);
                        return (
                          <TableRow key={item.id}>
                            <TableCell data-label="事项">
                              <strong>{item.businessLabel}</strong>
                              <small>
                                {type.label}
                                {item.errorCode ? ` · ${item.errorCode}` : ""}
                              </small>
                            </TableCell>
                            <TableCell data-label="企业">{item.companyName ?? "平台"}</TableCell>
                            <TableCell data-label="状态">
                              <StatusBadge status={item.status} />
                            </TableCell>
                            <TableCell data-label="更新时间">{formatTimestamp(item.updatedAt)}</TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                ) : (
                  <div className={styles.companyTaskGrid} aria-label="按企业查看平台任务">
                    {companyGroups.map((group) => {
                      const attentionCount = group.items.filter((item) => normalizedTaskState(item.status) === "attention").length;
                      const activeCount = group.items.filter((item) => normalizedTaskState(item.status) === "active").length;
                      return (
                        <article className={styles.companyTaskCard} key={`${group.companyId ?? "platform"}-${group.companyName}`}>
                          <div className={styles.companyTaskHeader}>
                            <div>
                              <strong>{group.companyName}</strong>
                              <span>
                                {group.items.length} 项 · 处理中 {activeCount} · 需处理 {attentionCount}
                              </span>
                            </div>
                            {group.companyId ? (
                              <Button
                                appearance="secondary"
                                size="small"
                                onClick={() => navigate(platformEnterprisePath(group.companyId as string, "tasks"))}
                              >
                                打开企业任务
                              </Button>
                            ) : null}
                          </div>
                          <ul>
                            {group.items.slice(0, 4).map((item) => (
                              <li key={item.id}>
                                <div>
                                  <strong>{item.businessLabel}</strong>
                                  <span>{taskViewTitle(normalizedTaskType(item.taskType).type)}</span>
                                </div>
                                <StatusBadge status={item.status} />
                              </li>
                            ))}
                          </ul>
                        </article>
                      );
                    })}
                  </div>
                )}

                {filtered.length === 0 && (
                  <p className={styles.noResults}>没有符合当前筛选条件的任务。</p>
                )}
              </section>
            </>
          );
        }}
      </PageState>
    </main>
  );
}

export function PlatformAuditPage() {
  const resource = useResource<PlatformAuditProjection[]>(() => platformApi.listAudit());
  const [query, setQuery] = useState("");
  return (
    <main className="page-stack">
      <PageHeader
        title="审计记录"
        description="受保护的诊断深链。业务动作优先可读，原始动作码仅作为次级排障信息。"
        actions={<Refresh onClick={resource.reload} />}
      />
      <PageState resource={resource} emptyTitle="当前没有审计记录">
        {(data) => {
          const filtered = data.filter((item) =>
            `${item.businessLabel} ${item.actorDisplayName} ${item.action} ${item.resourceType}`
              .toLocaleLowerCase()
              .includes(query.trim().toLocaleLowerCase()),
          );
          return (
            <>
              <Summary items={[["可追溯记录", data.length], ["操作者", new Set(data.map((item) => item.actorDisplayName)).size], ["失败记录", data.filter((item) => ["failed", "error"].includes(item.result)).length, "danger"]]} />
              <section className="content-panel data-panel">
                <div className={styles.toolbar}>
                  <SearchBox value={query} onChange={setQuery} placeholder="搜索操作、操作者或资源" />
                  <span>仅在诊断和审计场景使用</span>
                </div>
                <Table className={styles.table} aria-label="平台审计记录">
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>操作</TableHeaderCell>
                      <TableHeaderCell>操作者</TableHeaderCell>
                      <TableHeaderCell>结果</TableHeaderCell>
                      <TableHeaderCell>时间</TableHeaderCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filtered.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell data-label="操作">
                          <strong>{item.businessLabel}</strong>
                          <small>{item.action} · {item.resourceType}</small>
                        </TableCell>
                        <TableCell data-label="操作者">{item.actorDisplayName}</TableCell>
                        <TableCell data-label="结果"><StatusBadge status={item.result} /></TableCell>
                        <TableCell data-label="时间">{formatTimestamp(item.createdAt)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </section>
            </>
          );
        }}
      </PageState>
    </main>
  );
}

export function PlatformHealthPage() {
  const resource = useResource<PlatformServiceHealth[]>(() => platformApi.getServiceHealth());
  return (
    <main className="page-stack">
      <PageHeader
        title="服务健康"
        description="优先看异常项与检查时间，不将单项异常掩盖为整体正常。"
        actions={<Refresh onClick={resource.reload} />}
      />
      <PageState resource={resource} emptyTitle="暂时没有健康检查结果">
        {(data) => {
          const attention = data.filter((item) => item.status !== "healthy").length;
          return (
            <>
              <Summary items={[["检查服务", data.length], ["健康", data.length - attention], ["需处理", attention, "danger"]]} />
              <section className={styles.healthGrid} aria-label="平台服务健康">
                {data.map((item) => (
                  <article key={item.service} className="content-panel">
                    <header>
                      <strong>{item.service}</strong>
                      <StatusBadge status={item.status} />
                    </header>
                    <p>{item.latencyMs === undefined ? "未配置直接探针" : `响应 ${item.latencyMs} ms`}</p>
                    <dl className={styles.healthMeta}>
                      <div>
                        <dt>检查时间</dt>
                        <dd>{formatTimestamp(item.checkedAt)}</dd>
                      </div>
                      <div>
                        <dt>建议</dt>
                        <dd>{item.status === "healthy" ? "继续观察" : "核对服务日志与运行配置"}</dd>
                      </div>
                    </dl>
                    {item.errorCode && <code>{item.errorCode}</code>}
                  </article>
                ))}
              </section>
            </>
          );
        }}
      </PageState>
    </main>
  );
}

import { Badge, Button, Table, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow } from "@fluentui/react-components";
import {
  Add24Regular,
  ArrowClockwise24Regular,
  Building24Regular,
  CheckmarkCircle24Regular,
  ClipboardTask24Regular,
  Settings24Regular,
} from "@fluentui/react-icons";
import { useMemo } from "react";

import { platformApi } from "../api/platformApi";
import type { PlatformCompanyAggregate, PlatformTaskProjection } from "../api/types";
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

function normalizedTaskType(taskType: string): string {
  const value = taskType.toLowerCase();
  if (value.includes("onboarding")) return "建企开通";
  if (value.includes("import") || value.includes("knowledge")) return "资料导入";
  if (value.includes("review") || value.includes("content")) return "内容复核";
  if (value.includes("service") || value.includes("expiry") || value.includes("validity")) {
    return "服务有效期";
  }
  return "企业风险";
}

function taskState(status: string): "attention" | "active" | "resolved" {
  if (["failed", "error", "blocked", "expired"].includes(status)) return "attention";
  if (["pending", "queued", "processing", "running", "review", "manual_required", "in_progress"].includes(status)) {
    return "active";
  }
  return "resolved";
}

export function PlatformOverviewPage() {
  const overviewResource = useResource(() => platformApi.getOverview());
  const aggregateResource = useResource(() => platformApi.listCompanyAggregates());
  const tasksResource = useResource(() => platformApi.listTasks());
  const healthResource = useResource(() => platformApi.getServiceHealth());

  const topEnterprises = useMemo(
    () =>
      [...(aggregateResource.data ?? [])]
        .sort((left, right) => right.visits30d - left.visits30d)
        .slice(0, 5),
    [aggregateResource.data],
  );
  const importantTasks = useMemo(
    () =>
      [...(tasksResource.data ?? [])]
        .filter((task) => taskState(task.status) !== "resolved")
        .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
        .slice(0, 6),
    [tasksResource.data],
  );

  const reloadAll = () => {
    overviewResource.reload();
    aggregateResource.reload();
    tasksResource.reload();
    healthResource.reload();
  };

  if (overviewResource.status !== "ready" || !overviewResource.data) {
    return (
      <main className="page-stack platform-console">
        <PageHeader
          title="平台运营概览"
          description="先看可行动的企业状态、运营任务和服务健康，再进入独立企业详情页。"
          actions={
            <>
              <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={reloadAll}>
                刷新状态
              </Button>
              <Button appearance="primary" icon={<Add24Regular />} onClick={() => navigate(APP_PATHS.platformEnterprises)}>
                开通企业
              </Button>
            </>
          }
        />
        <section className="content-panel">
          <ResourceState
            status={overviewResource.status === "ready" ? "empty" : overviewResource.status}
            title={overviewResource.status === "empty" ? "平台总览暂不可用" : undefined}
            description={
              overviewResource.status === "empty"
                ? "平台服务尚未返回运营聚合数据。"
                : overviewResource.error?.message
            }
            errorCode={overviewResource.error?.code}
            requestId={overviewResource.error?.requestId}
            onRetry={overviewResource.status === "error" ? reloadAll : undefined}
            emptyAction={
              <Button appearance="primary" onClick={() => navigate(APP_PATHS.platformEnterprises)}>
                进入企业中心
              </Button>
            }
          />
        </section>
      </main>
    );
  }

  const overview = overviewResource.data;
  const activeTasks = tasksResource.data?.filter((task) => taskState(task.status) === "active").length ?? 0;
  const attentionTasks = tasksResource.data?.filter((task) => taskState(task.status) === "attention").length ?? 0;
  const unhealthyServices = healthResource.data?.filter((item) => item.status !== "healthy").length ?? 0;

  return (
    <main className="page-stack platform-console">
      <PageHeader
        title="平台运营概览"
        description="员工/访客聚合已并入概览；审计保留为深链诊断。日常只看企业覆盖、30 天活跃、运营任务和服务健康。"
        actions={
          <>
            <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={reloadAll}>
              刷新状态
            </Button>
            <Button appearance="secondary" icon={<Settings24Regular />} onClick={() => navigate(APP_PATHS.platformLlmSettings)}>
              平台 AI 设置
            </Button>
            <Button appearance="primary" icon={<Add24Regular />} onClick={() => navigate(APP_PATHS.platformEnterprises)}>
              开通企业
            </Button>
          </>
        }
      />

      <section className="platform-status-grid" aria-label="平台企业概览">
        <article className="platform-status-primary">
          <span>待处理运营事项</span>
          <strong>{activeTasks + attentionTasks}</strong>
          <p>
            {activeTasks} 项处理中，{attentionTasks} 项需要立即处理。
          </p>
        </article>
        <article className="platform-status-item">
          <span>已启用企业</span>
          <strong>{overview.activeEnterpriseCount}</strong>
          <p>总计 {overview.enterpriseCount} 家企业。</p>
        </article>
        <article className="platform-status-item">
          <span>已发布名片</span>
          <strong>{overview.publishedCardCount}</strong>
          <p>只统计已可公开访问的企业与员工名片。</p>
        </article>
      </section>

      <section className="platform-operations-panel" id="overview-traffic">
        <div>
          <Badge appearance="tint" color={overview.llmReady && overview.importReady ? "success" : "warning"}>
            {overview.llmReady && overview.importReady ? "平台关键能力已就绪" : "平台关键能力待配置"}
          </Badge>
          <h2>30 天活跃与平台依赖</h2>
          <p>
            近 30 天访问 {overview.visits30d}，对话 {overview.conversations30d}，授权留资 {overview.leads30d}。
            LLM {overview.llmReady ? "已就绪" : "待配置"}，资料导入 {overview.importReady ? "已就绪" : "待配置"}。
          </p>
        </div>
        <Button
          appearance="primary"
          icon={overview.llmReady && overview.importReady ? <ClipboardTask24Regular /> : <Settings24Regular />}
          onClick={() => navigate(overview.llmReady && overview.importReady ? APP_PATHS.platformTasks : APP_PATHS.platformLlmSettings)}
        >
          {overview.llmReady && overview.importReady ? "查看运营任务" : "配置平台 AI"}
        </Button>
      </section>

      <section className="content-panel" id="overview-enterprise-coverage">
        <div className="page-header">
          <div>
            <h2>企业覆盖与最近活动</h2>
            <p>企业列表和独立详情页使用同一聚合口径；点击企业直接进入八分区详情页。</p>
          </div>
          <Button appearance="secondary" icon={<Building24Regular />} onClick={() => navigate(APP_PATHS.platformEnterprises)}>
            查看全部企业
          </Button>
        </div>
        {aggregateResource.status === "ready" && topEnterprises.length > 0 ? (
          <Table aria-label="企业覆盖与活跃度">
            <TableHeader>
              <TableRow>
                <TableHeaderCell>企业</TableHeaderCell>
                <TableHeaderCell>成员</TableHeaderCell>
                <TableHeaderCell>访问 / 独立访客</TableHeaderCell>
                <TableHeaderCell>最近活动</TableHeaderCell>
                <TableHeaderCell>操作</TableHeaderCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {topEnterprises.map((item: PlatformCompanyAggregate) => (
                <TableRow key={item.companyId}>
                  <TableCell>
                    <strong>{item.companyName}</strong>
                  </TableCell>
                  <TableCell>{item.employeeCount}</TableCell>
                  <TableCell>{item.visits30d} / {item.uniqueVisitors30d}</TableCell>
                  <TableCell>{item.lastVisitAt ? formatTimestamp(item.lastVisitAt) : "暂无访问"}</TableCell>
                  <TableCell>
                    <Button
                      appearance="secondary"
                      size="small"
                      onClick={() => navigate(platformEnterprisePath(item.companyId, "operations"))}
                    >
                      打开详情
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <ResourceState
            compact
            status={aggregateResource.status === "ready" ? "empty" : aggregateResource.status}
            title="企业覆盖暂不可用"
            description={aggregateResource.error?.message ?? "企业聚合数据返回后，这里会展示最近活动最高的企业。"}
            errorCode={aggregateResource.error?.code}
            requestId={aggregateResource.error?.requestId}
            onRetry={aggregateResource.status === "error" ? aggregateResource.reload : undefined}
          />
        )}
      </section>

      <section className="content-panel">
        <div className="page-header">
          <div>
            <h2>运营任务中心</h2>
            <p>成功 outbox 事件不会出现在这里；这里只保留建企、导入、内容复核、企业风险和服务有效期事项。</p>
          </div>
          <Button appearance="secondary" icon={<ClipboardTask24Regular />} onClick={() => navigate(APP_PATHS.platformTasks)}>
            打开任务中心
          </Button>
        </div>
        {importantTasks.length > 0 ? (
          <div className="dashboard-metrics platform-compact-metrics">
            {importantTasks.map((task: PlatformTaskProjection) => (
              <article className="dashboard-metric" key={task.id}>
                <div style={{ display: "grid", gap: 6 }}>
                  <strong>{task.businessLabel}</strong>
                  <span>{normalizedTaskType(task.taskType)} · {task.companyName ?? "平台级事项"}</span>
                  <StatusBadge status={task.status} />
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="resource-state compact">
            <CheckmarkCircle24Regular aria-hidden />
            <div>
              <h3>当前没有待处理运营任务</h3>
              <p>平台任务中心会在出现建企、导入、复核和风险事项时显示它们。</p>
            </div>
          </div>
        )}
      </section>

      <section className="content-panel">
        <div className="page-header">
          <div>
            <h2>服务健康</h2>
            <p>日常导航只保留服务健康，不把审计列表和技术事件作为首页主入口。</p>
          </div>
          <Button appearance="secondary" onClick={() => navigate(APP_PATHS.platformHealth)}>
            打开服务健康
          </Button>
        </div>
        {healthResource.status === "ready" && healthResource.data ? (
          <div className="dashboard-metrics platform-compact-metrics" aria-label="平台健康探针">
            {healthResource.data.map((item) => (
              <article className="dashboard-metric" key={item.service}>
                <strong>{item.service}</strong>
                <span>{item.latencyMs === undefined ? "未配置探针" : `响应 ${item.latencyMs} ms`}</span>
                <StatusBadge status={item.status} />
              </article>
            ))}
          </div>
        ) : (
          <ResourceState
            compact
            status={healthResource.status === "ready" ? "empty" : healthResource.status}
            title="服务健康暂不可用"
            description={healthResource.error?.message ?? "服务探针返回后，这里会显示健康摘要。"}
            errorCode={healthResource.error?.code}
            requestId={healthResource.error?.requestId}
            onRetry={healthResource.status === "error" ? healthResource.reload : undefined}
          />
        )}

      <p className="dashboard-generated">
        聚合数据生成于 {formatTimestamp(overview.generatedAt)}，当前异常服务 {unhealthyServices} 项。
      </p>
      </section>
    </main>
  );
}

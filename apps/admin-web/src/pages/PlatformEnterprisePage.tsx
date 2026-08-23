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
  ProgressBar,
  Textarea,
} from "@fluentui/react-components";
import {
  ArrowClockwise24Regular,
  ArrowLeft24Regular,
  Open24Regular,
} from "@fluentui/react-icons";
import { useMemo, useState } from "react";

import { ApiError } from "../api/client";
import { platformApi } from "../api/platformApi";
import type {
  PlatformCompanyAggregate,
  PlatformEnterpriseDetail,
  PlatformTaskProjection,
} from "../api/types";
import { CommercialEntitlementPanel } from "../components/CommercialEntitlementPanel";
import { FormFeedback } from "../components/FormFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import {
  APP_PATHS,
  navigate,
  platformEnterprisePath,
  type PlatformEnterpriseSection,
} from "../routing";
import { formatTimestamp, knowledgeStatusLabel } from "../utils/format";
import styles from "./PlatformEnterprisePage.module.css";

type PlatformEnterprisePageProps = {
  companyId: string;
  section?: PlatformEnterpriseSection;
};

const sectionDefinitions: Array<{
  id: PlatformEnterpriseSection;
  label: string;
  description: string;
}> = [
  { id: "overview", label: "概览", description: "企业身份、状态与关键指标。" },
  { id: "operations", label: "运营", description: "开通进度、风险和运营建议。" },
  { id: "members-cards", label: "成员与名片", description: "员工覆盖与名片公开状态。" },
  { id: "content", label: "内容", description: "资料归纳与内容控制面的当前可见信息。" },
  { id: "tasks", label: "任务", description: "该企业相关的近期运营事项。" },
  { id: "ai", label: "AI 状态", description: "平台 AI 依赖状态与当前边界。" },
  { id: "entitlements", label: "套餐授权", description: "套餐与功能开关。" },
  { id: "activity", label: "活动", description: "30 天访问与对话活跃度。" },
] as const;

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

function onboardingLabel(status: string): string {
  if (["completed", "active", "confirmed"].includes(status)) return "已完成入驻";
  if (["review", "ready_to_confirm"].includes(status)) return "待确认";
  if (["manual_required", "content_pending"].includes(status)) return "待人工处理";
  if (status === "initialized") return "空间已初始化";
  return knowledgeStatusLabel(status);
}

function normalizedTaskType(taskType: string): {
  type: "onboarding" | "knowledge_import" | "content_review" | "enterprise_risk" | "service_validity";
  label: string;
} {
  const value = taskType.toLowerCase();
  if (value.includes("onboarding")) {
    return { type: "onboarding", label: "建企开通" };
  }
  if (value.includes("import") || value.includes("knowledge")) {
    return { type: "knowledge_import", label: "资料导入" };
  }
  if (value.includes("review") || value.includes("content")) {
    return { type: "content_review", label: "内容复核" };
  }
  if (value.includes("service") || value.includes("expiry") || value.includes("validity")) {
    return { type: "service_validity", label: "服务有效期" };
  }
  return { type: "enterprise_risk", label: "企业风险" };
}

function taskUrgency(status: string): "danger" | "warning" | "neutral" {
  if (["failed", "error", "blocked", "expired"].includes(status)) return "danger";
  if (["pending", "queued", "processing", "running", "review", "manual_required", "in_progress"].includes(status)) {
    return "warning";
  }
  return "neutral";
}

function taskUrgencyLabel(status: string): string {
  if (taskUrgency(status) === "danger") return "需处理";
  if (taskUrgency(status) === "warning") return "处理中";
  return "已归档";
}

function availabilityCopy(status: ReturnType<typeof taskUrgency>) {
  if (status === "danger") return "风险";
  if (status === "warning") return "关注";
  return "完成";
}

function Facts({
  items,
}: {
  items: Array<{ label: string; value: string | number; hint?: string }>;
}) {
  return (
    <dl className={styles.metricGrid}>
      {items.map((item) => (
        <div className={styles.metricCard} key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
          {item.hint && <span>{item.hint}</span>}
        </div>
      ))}
    </dl>
  );
}

function InsightNote({
  title,
  children,
  tone = "neutral",
}: {
  title: string;
  children: React.ReactNode;
  tone?: "neutral" | "warning";
}) {
  return (
    <article
      className={tone === "warning" ? `${styles.note} ${styles.noteWarning}` : styles.note}
    >
      <strong>{title}</strong>
      <p>{children}</p>
    </article>
  );
}

function CardGroups({ detail }: { detail: PlatformEnterpriseDetail }) {
  const enterpriseCards = detail.cards.filter((card) => card.cardKind === "enterprise");
  const employeeCards = detail.cards.filter((card) => card.cardKind === "employee");
  const groups = [
    { label: "企业官方名片", cards: enterpriseCards },
    { label: "员工名片", cards: employeeCards },
  ];
  return (
    <div className={styles.cardGroups}>
      {groups.map((group) => (
        <section className={styles.sectionBlock} key={group.label}>
          <div className={styles.sectionBlockHeader}>
            <h3>{group.label}</h3>
            <span>{group.cards.length} 张</span>
          </div>
          {group.cards.length > 0 ? (
            <div className={styles.cardList}>
              {group.cards.map((card) => (
                <article className={styles.cardItem} key={card.id}>
                  <div className={styles.cardCopy}>
                    <strong>{card.displayName}</strong>
                    <p>{card.title || "尚未填写对外标题"}</p>
                    <div className={styles.metaRow}>
                      <StatusBadge status={card.status} />
                      <span>{formatTimestamp(card.updatedAt)}</span>
                    </div>
                  </div>
                  {card.status === "published" && card.shareUrl ? (
                    <Button
                      as="a"
                      appearance="secondary"
                      href={card.shareUrl}
                      icon={<Open24Regular />}
                      rel="noreferrer"
                      target="_blank"
                    >
                      打开名片
                    </Button>
                  ) : (
                    <span className={styles.placeholderText}>发布后可公开访问</span>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <p className={styles.placeholderText}>当前没有该类型名片。</p>
          )}
        </section>
      ))}
    </div>
  );
}

function TaskList({
  tasks,
  emptyCopy,
}: {
  tasks: PlatformTaskProjection[];
  emptyCopy: string;
}) {
  if (tasks.length === 0) {
    return <p className={styles.placeholderText}>{emptyCopy}</p>;
  }
  return (
    <div className={styles.taskList}>
      {tasks.map((task) => {
        const type = normalizedTaskType(task.taskType);
        const urgency = taskUrgency(task.status);
        return (
          <article className={styles.taskItem} key={task.id}>
            <div className={styles.taskHeader}>
              <div>
                <strong>{task.businessLabel}</strong>
                <p>
                  {type.label} · {task.companyName ?? "平台级事项"}
                </p>
              </div>
              <Badge appearance="tint" color={urgency === "danger" ? "danger" : urgency === "warning" ? "warning" : "informative"}>
                {taskUrgencyLabel(task.status)}
              </Badge>
            </div>
            <div className={styles.metaRow}>
              <StatusBadge status={task.status} />
              <span>更新时间 {formatTimestamp(task.updatedAt)}</span>
              {task.errorCode && <span>代码 {task.errorCode}</span>}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function renderSection(
  section: PlatformEnterpriseSection,
  detail: PlatformEnterpriseDetail,
  aggregate: PlatformCompanyAggregate | undefined,
  tasksResource: ReturnType<typeof useResource<PlatformTaskProjection[]>>,
  overviewResource: ReturnType<typeof useResource<{
    llmReady: boolean;
    importReady: boolean;
    generatedAt: string;
  }>>,
  onOpenLifecycle: () => void,
) {
  const relatedTasks = tasksResource.data?.filter((task) => task.companyId === detail.companyId) ?? [];
  const activeTasks = relatedTasks.filter(
    (task) => taskUrgency(task.status) !== "neutral",
  );
  if (section === "overview") {
    return (
      <>
        <section className="content-panel">
          <div className={styles.sectionBlockHeader}>
            <div>
              <h2>企业状态总览</h2>
              <p>当前详情只使用白名单运营字段，不读取访客、对话或线索正文。</p>
            </div>
            {detail.status !== "disabled" && (
              <Button appearance="secondary" onClick={onOpenLifecycle}>
                {detail.status === "active" ? "暂停企业" : "恢复企业"}
              </Button>
            )}
          </div>
          <Facts
            items={[
              { label: "企业状态", value: knowledgeStatusLabel(detail.status) },
              { label: "入驻进度", value: onboardingLabel(detail.onboardingStatus) },
              { label: "资料完善度", value: `${detail.profileCompletion}%` },
              { label: "企业成员", value: detail.employeeCount },
              { label: "全部名片", value: detail.cardCount },
              { label: "已发布名片", value: detail.publishedCardCount },
            ]}
          />
          <div className={styles.progressBlock}>
            <div className={styles.progressHeader}>
              <strong>资料完善度</strong>
              <span>{detail.profileCompletion}%</span>
            </div>
            <ProgressBar
              aria-label={`资料完善度 ${detail.profileCompletion}%`}
              value={detail.profileCompletion / 100}
            />
          </div>
        </section>

        <section className="content-panel">
          <div className={styles.sectionBlockHeader}>
            <div>
              <h2>企业身份与时间戳</h2>
              <p>当前平台详情接口尚未拆出正式名称、简称和信用代码，先展示现有稳定字段。</p>
            </div>
          </div>
          <div className={styles.identityGrid}>
            <div>
              <span>企业名称</span>
              <strong>{detail.companyName}</strong>
            </div>
            <div>
              <span>企业工作区</span>
              <strong>{detail.tenantName}</strong>
              <small>{detail.tenantSlug}</small>
            </div>
            <div>
              <span>开通时间</span>
              <strong>{formatTimestamp(detail.createdAt)}</strong>
            </div>
            <div>
              <span>最近更新</span>
              <strong>{formatTimestamp(detail.updatedAt)}</strong>
            </div>
          </div>
        </section>
      </>
    );
  }

  if (section === "operations") {
    return (
      <>
        <section className="content-panel">
          <div className={styles.sectionBlockHeader}>
            <div>
              <h2>运营信号</h2>
              <p>以是否可行动为主，而不是展示原始事件码。</p>
            </div>
          </div>
          <Facts
            items={[
              { label: "近 30 天访问", value: detail.visits30d },
              { label: "近 30 天对话", value: detail.conversations30d },
              { label: "近 30 天留资", value: detail.leads30d },
              {
                label: "独立访客",
                value: aggregate?.uniqueVisitors30d ?? "未返回",
                hint: aggregate ? "来自企业聚合视图" : "当前聚合接口未返回该企业数据",
              },
              {
                label: "最近访问",
                value: aggregate?.lastVisitAt ? formatTimestamp(aggregate.lastVisitAt) : "暂无访问",
              },
              { label: "待跟进事项", value: activeTasks.length },
            ]}
          />
        </section>

        <div className={styles.splitGrid}>
          <section className="content-panel">
            <div className={styles.sectionBlockHeader}>
              <h2>当前风险与建议</h2>
            </div>
            <div className={styles.noteStack}>
              {detail.publishedCardCount === 0 && (
                <InsightNote title="尚无公开名片" tone="warning">
                  企业已开通，但还没有已发布名片；管理员登录后仍需自行创建并发布对外入口。
                </InsightNote>
              )}
              {detail.profileCompletion < 70 && (
                <InsightNote title="资料仍不完整" tone="warning">
                  资料完善度低于 70%，建议先补企业身份、对外介绍和核心内容。
                </InsightNote>
              )}
              {activeTasks.length > 0 && (
                <InsightNote title="存在待处理运营事项" tone="warning">
                  当前有 {activeTasks.length} 项建企、导入或风险任务仍在处理中或失败。
                </InsightNote>
              )}
              {detail.publishedCardCount > 0 && detail.profileCompletion >= 70 && activeTasks.length === 0 && (
                <InsightNote title="当前状态稳定">
                  企业已具备基础运营条件，可继续关注内容更新和近 30 天活跃度。
                </InsightNote>
              )}
            </div>
          </section>

          <section className="content-panel">
            <div className={styles.sectionBlockHeader}>
              <h2>近期事项</h2>
            </div>
            {tasksResource.status === "ready" ? (
              <TaskList tasks={relatedTasks.slice(0, 4)} emptyCopy="当前没有关联到该企业的运营事项。" />
            ) : (
              <ResourceState
                compact
                status={tasksResource.status}
                title="近期事项暂不可用"
                description={tasksResource.error?.message}
                errorCode={tasksResource.error?.code}
                requestId={tasksResource.error?.requestId}
                onRetry={tasksResource.status === "error" ? tasksResource.reload : undefined}
              />
            )}
          </section>
        </div>
      </>
    );
  }

  if (section === "members-cards") {
    return (
      <>
        <section className="content-panel">
          <div className={styles.sectionBlockHeader}>
            <div>
              <h2>成员覆盖</h2>
              <p>平台只看成员数量、角色与名片状态，不展示联系方式。</p>
            </div>
          </div>
          <Facts
            items={[
              { label: "企业成员", value: detail.employeeCount },
              { label: "员工名片", value: detail.cards.filter((card) => card.cardKind === "employee").length },
              { label: "企业官方名片", value: detail.cards.filter((card) => card.cardKind === "enterprise").length },
              { label: "已发布名片", value: detail.publishedCardCount },
            ]}
          />
        </section>
        <section className="content-panel">
          <CardGroups detail={detail} />
        </section>
      </>
    );
  }

  if (section === "content") {
    return (
      <>
        <section className="content-panel">
          <div className={styles.sectionBlockHeader}>
            <div>
              <h2>资料归纳画像</h2>
              <p>来自建企资料解析，仅用于运营复核，不代表已公开承诺。</p>
            </div>
            <span>{detail.businessProfile.length} 项</span>
          </div>
          {detail.businessProfile.length > 0 ? (
            <div className={styles.profileList}>
              {detail.businessProfile.map((item, index) => (
                <article key={`${item.field}-${index}`}>
                  <div className={styles.profileHeading}>
                    <strong>{businessProfileLabels[item.field] ?? item.field}</strong>
                    <span>
                      {item.confidence === undefined
                        ? "待核验"
                        : `${Math.round(item.confidence * 100)}% 置信`}
                    </span>
                  </div>
                  <p>{item.value}</p>
                  <small>
                    来源：
                    {item.sources.map((source) => source.fileName).join("、") || "未标注"}
                  </small>
                </article>
              ))}
            </div>
          ) : (
            <p className={styles.placeholderText}>当前没有可展示的资料归纳画像。</p>
          )}
        </section>

        <section className="content-panel">
          <div className={styles.sectionBlockHeader}>
            <div>
              <h2>内容控制面边界</h2>
              <p>产品、案例、FAQ 引用数和版本历史仍需后端详情扩展后才能进入平台独立页。</p>
            </div>
          </div>
          <div className={styles.noteStack}>
            <InsightNote title="当前可见内容">
              平台详情目前只能看到资料归纳和名片公开状态，不能直接读取企业知识正文、产品正文或线索正文。
            </InsightNote>
            <InsightNote title="已预留后续挂载点">
              `/products/new`、`/products/:id`、访问详情和对话/线索详情路由已在共享合同冻结，待 App 路由与后端详情投影接线后再开放下钻。
            </InsightNote>
          </div>
        </section>
      </>
    );
  }

  if (section === "tasks") {
    const grouped = relatedTasks.reduce<Record<string, PlatformTaskProjection[]>>((accumulator, task) => {
      const label = normalizedTaskType(task.taskType).label;
      accumulator[label] = accumulator[label] ?? [];
      accumulator[label].push(task);
      return accumulator;
    }, {});
    return (
      <>
        <section className="content-panel">
          <div className={styles.sectionBlockHeader}>
            <div>
              <h2>企业相关任务</h2>
              <p>只保留可处理的运营事项，不展示成功投递的通用 outbox 事件。</p>
            </div>
          </div>
          {tasksResource.status === "ready" ? (
            <>
              <Facts
                items={[
                  { label: "关联任务", value: relatedTasks.length },
                  { label: "处理中", value: relatedTasks.filter((task) => taskUrgency(task.status) === "warning").length },
                  { label: "需处理", value: relatedTasks.filter((task) => taskUrgency(task.status) === "danger").length },
                ]}
              />
              <TaskList tasks={relatedTasks} emptyCopy="当前没有与该企业关联的运营事项。" />
            </>
          ) : (
            <ResourceState
              status={tasksResource.status}
              title="企业任务暂不可用"
              description={tasksResource.error?.message}
              errorCode={tasksResource.error?.code}
              requestId={tasksResource.error?.requestId}
              onRetry={tasksResource.status === "error" ? tasksResource.reload : undefined}
            />
          )}
        </section>
        {tasksResource.status === "ready" && relatedTasks.length > 0 && (
          <section className="content-panel">
            <div className={styles.sectionBlockHeader}>
              <h2>按事项类型查看</h2>
            </div>
            <div className={styles.groupList}>
              {Object.entries(grouped).map(([label, items]) => (
                <article className={styles.groupCard} key={label}>
                  <div className={styles.groupHeader}>
                    <strong>{label}</strong>
                    <span>{items.length} 项</span>
                  </div>
                  <ul>
                    {items.slice(0, 3).map((item) => (
                      <li key={item.id}>
                        <span>{item.businessLabel}</span>
                        <Badge
                          appearance="tint"
                          color={taskUrgency(item.status) === "danger" ? "danger" : taskUrgency(item.status) === "warning" ? "warning" : "informative"}
                        >
                          {availabilityCopy(taskUrgency(item.status))}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </section>
        )}
      </>
    );
  }

  if (section === "ai") {
    return (
      <>
        <section className="content-panel">
          <div className={styles.sectionBlockHeader}>
            <div>
              <h2>平台 AI 依赖</h2>
              <p>企业级 BYOK 和模型接入尚未在 P0/P1 实现，当前只展示平台主配置依赖状态。</p>
            </div>
            <Button appearance="secondary" onClick={() => navigate(APP_PATHS.platformLlmSettings)}>
              前往平台 AI 设置
            </Button>
          </div>
          {overviewResource.status === "ready" && overviewResource.data ? (
            <Facts
              items={[
                {
                  label: "平台 LLM",
                  value: overviewResource.data.llmReady ? "已就绪" : "待配置",
                },
                {
                  label: "资料导入",
                  value: overviewResource.data.importReady ? "已就绪" : "待配置",
                },
                {
                  label: "状态生成时间",
                  value: formatTimestamp(overviewResource.data.generatedAt),
                },
              ]}
            />
          ) : (
            <ResourceState
              compact
              status={overviewResource.status === "ready" ? "empty" : overviewResource.status}
              title="平台 AI 状态暂不可用"
              description={overviewResource.error?.message}
              errorCode={overviewResource.error?.code}
              requestId={overviewResource.error?.requestId}
              onRetry={overviewResource.status === "error" ? overviewResource.reload : undefined}
            />
          )}
        </section>

        <section className="content-panel">
          <div className={styles.noteStack}>
            <InsightNote title="当前企业侧边界">
              该详情页不会显示模型提供商、密钥提示或任何企业私有配置，因为企业级模型接入/BYOK 仍明确延后到 P2。
            </InsightNote>
            <InsightNote title="运营可见信号">
              现阶段只能结合资料导入就绪度、企业资料完整度和是否有已发布名片，判断该企业是否具备基本 AI 接待前置条件。
            </InsightNote>
          </div>
        </section>
      </>
    );
  }

  if (section === "entitlements") {
    return (
      <>
        <section className="content-panel">
          <div className={styles.sectionBlockHeader}>
            <div>
              <h2>套餐与功能授权</h2>
              <p>当前支持按企业覆盖套餐、功能开关和额度；服务有效期字段仍待后端补充。</p>
            </div>
          </div>
          <CommercialEntitlementPanel companyId={detail.companyId} />
        </section>
        <section className="content-panel">
          <div className={styles.noteStack}>
            <InsightNote title="仍待补充">
              服务有效期、到期风险分层和续费动作需要后端详情新字段；本页暂不伪造日期或到期结论。
            </InsightNote>
          </div>
        </section>
      </>
    );
  }

  return (
    <>
      <section className="content-panel">
        <div className={styles.sectionBlockHeader}>
          <div>
            <h2>30 天活动概览</h2>
            <p>跨对象详情路由已冻结，但平台详情 API 目前还没有返回访问、对话和线索的可下钻对象 ID。</p>
          </div>
        </div>
        <Facts
          items={[
            { label: "访问", value: detail.visits30d },
            {
              label: "独立访客",
              value: aggregate?.uniqueVisitors30d ?? "未返回",
            },
            { label: "对话", value: detail.conversations30d },
            { label: "授权留资", value: detail.leads30d },
            {
              label: "最近访问",
              value: aggregate?.lastVisitAt ? formatTimestamp(aggregate.lastVisitAt) : "暂无访问",
            },
          ]}
        />
      </section>
      <section className="content-panel">
        <div className={styles.noteStack}>
          <InsightNote title="当前可下钻边界">
            `/visits/:visitId`、`/conversations/:conversationId`、`/leads/:leadId` 等详情路由已经在共享合同冻结，但当前企业详情接口还未返回这些对象的关联 ID。
          </InsightNote>
          <InsightNote title="活跃度解释">
            现阶段只能依据聚合访问、独立访客、对话和授权留资判断 30 天活跃度，不能在此页直接打开单次访问或长期访客档案。
          </InsightNote>
        </div>
      </section>
    </>
  );
}

export function PlatformEnterprisePage({
  companyId,
  section = "overview",
}: PlatformEnterprisePageProps) {
  const detailResource = useResource(
    () => platformApi.getEnterpriseDetail(companyId),
    companyId,
  );
  const aggregateResource = useResource(
    () => platformApi.listCompanyAggregates(),
    companyId,
  );
  const tasksResource = useResource(() => platformApi.listTasks(), companyId);
  const overviewResource = useResource(
    async () => {
      const overview = await platformApi.getOverview();
      return {
        llmReady: overview.llmReady,
        importReady: overview.importReady,
        generatedAt: overview.generatedAt,
      };
    },
    companyId,
  );
  const [lifecycleOpen, setLifecycleOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [lifecycleError, setLifecycleError] = useState<ApiError>();

  const currentSection = useMemo(
    () => sectionDefinitions.find((item) => item.id === section) ?? sectionDefinitions[0],
    [section],
  );
  const detail = detailResource.data;
  const aggregate = aggregateResource.data?.find((item) => item.companyId === companyId);
  const targetStatus = detail?.status === "active" ? "suspended" : "active";
  const lifecycleLabel = targetStatus === "suspended" ? "暂停企业" : "恢复企业";

  const reloadAll = () => {
    detailResource.reload();
    aggregateResource.reload();
    tasksResource.reload();
    overviewResource.reload();
  };

  const transition = async () => {
    if (!detail || saving || reason.trim().length < 3) return;
    setSaving(true);
    setLifecycleError(undefined);
    try {
      await platformApi.transitionEnterprise(detail.companyId, {
        expectedVersion: detail.version,
        targetStatus,
        reason,
      });
      setLifecycleOpen(false);
      setReason("");
      reloadAll();
    } catch (caught) {
      setLifecycleError(
        caught instanceof ApiError
          ? caught
          : new ApiError("企业状态变更失败。", { code: "UNKNOWN_ERROR" }),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="page-stack platform-console">
      <PageHeader
        title={detail?.companyName ?? "企业详情"}
        description={
          detail
            ? `${currentSection.label} · ${currentSection.description}`
            : "独立企业详情页使用白名单运营字段，刷新后保留当前分区。"
        }
        actions={
          <>
            <Button
              appearance="secondary"
              icon={<ArrowLeft24Regular />}
              onClick={() => navigate(APP_PATHS.platformEnterprises)}
            >
              返回企业中心
            </Button>
            <Button
              appearance="subtle"
              icon={<ArrowClockwise24Regular />}
              onClick={reloadAll}
            >
              刷新
            </Button>
          </>
        }
      />

      {detailResource.status === "ready" && detail ? (
        <>
          <section className={styles.hero}>
            <div className={styles.heroPrimary}>
              <div className={styles.badgeRow}>
                <StatusBadge status={detail.status} />
                <Badge appearance="outline">{onboardingLabel(detail.onboardingStatus)}</Badge>
              </div>
              <h2>{detail.companyName}</h2>
              <p>
                {detail.tenantName} · {detail.tenantSlug}
              </p>
              <div className={styles.metaRow}>
                <span>开通于 {formatTimestamp(detail.createdAt)}</span>
                <span>更新于 {formatTimestamp(detail.updatedAt)}</span>
              </div>
            </div>
            <div className={styles.heroSide}>
              <div>
                <span>近 30 天访问</span>
                <strong>{detail.visits30d}</strong>
              </div>
              <div>
                <span>已发布名片</span>
                <strong>{detail.publishedCardCount}</strong>
              </div>
              <div>
                <span>相关任务</span>
                <strong>{tasksResource.data?.filter((task) => task.companyId === detail.companyId).length ?? "..."}</strong>
              </div>
            </div>
          </section>

          <nav aria-label="企业详情分区" className={styles.sectionNav}>
            {sectionDefinitions.map((item) => {
              const active = item.id === currentSection.id;
              return (
                <Button
                  key={item.id}
                  appearance={active ? "primary" : "secondary"}
                  className={styles.sectionNavButton}
                  onClick={() => navigate(platformEnterprisePath(companyId, item.id))}
                >
                  {item.label}
                </Button>
              );
            })}
          </nav>

          {renderSection(
            currentSection.id,
            detail,
            aggregate,
            tasksResource,
            overviewResource,
            () => {
              setLifecycleError(undefined);
              setLifecycleOpen(true);
            },
          )}
        </>
      ) : (
        <section className="content-panel">
          <ResourceState
            status={detailResource.status === "ready" ? "empty" : detailResource.status}
            title={detailResource.status === "empty" ? "企业详情暂不可用" : undefined}
            description={detailResource.error?.message}
            errorCode={detailResource.error?.code}
            requestId={detailResource.error?.requestId}
            onRetry={detailResource.status === "error" ? detailResource.reload : undefined}
          />
        </section>
      )}

      <Dialog
        open={lifecycleOpen}
        onOpenChange={(_, data) => !saving && setLifecycleOpen(data.open)}
      >
        <DialogSurface>
          <DialogBody>
            <DialogTitle>{lifecycleLabel}</DialogTitle>
            <DialogContent>
              <FormFeedback error={lifecycleError} />
              <p>
                将 {detail?.companyName} 变更为
                {targetStatus === "suspended" ? "暂停" : "正常运营"}状态。
              </p>
              <Field
                label="操作原因"
                required
                validationState={reason.length > 0 && reason.trim().length < 3 ? "error" : "none"}
                validationMessage={
                  reason.length > 0 && reason.trim().length < 3
                    ? "请至少填写 3 个字符。"
                    : undefined
                }
              >
                <Textarea
                  maxLength={500}
                  resize="vertical"
                  value={reason}
                  onChange={(_, data) => setReason(data.value)}
                />
              </Field>
            </DialogContent>
            <DialogActions>
              <Button
                appearance="secondary"
                disabled={saving}
                onClick={() => {
                  setLifecycleOpen(false);
                  setReason("");
                }}
              >
                取消
              </Button>
              <Button
                appearance="primary"
                disabled={saving || reason.trim().length < 3}
                onClick={() => void transition()}
              >
                {saving ? "正在提交" : `确认${lifecycleLabel}`}
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </main>
  );
}

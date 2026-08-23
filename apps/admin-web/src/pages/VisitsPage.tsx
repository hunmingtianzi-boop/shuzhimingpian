import {
  Badge,
  Button,
  Input,
  ProgressBar,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import {
  ArrowClockwise24Regular,
  ArrowLeft24Regular,
  ArrowRight24Regular,
  Chat24Regular,
  Dismiss24Regular,
  Filter24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { workflowApi } from "../api/workflowApi";
import { PageHeader } from "../components/PageHeader";
import { PaginationBar } from "../components/PaginationBar";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import {
  APP_PATHS,
  appHref,
  navigate,
  visitDetailPath,
  visitorProfileDetailPath,
} from "../routing";
import { formatTimestamp } from "../utils/format";
import "./VisitsPage.css";

const PAGE_SIZE = 20;

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} 秒`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分`;
}

function formatVisitDuration(visit: {
  activityStatus: "active" | "ended" | "estimated" | "unknown";
  durationSeconds?: number;
}): string {
  if (visit.activityStatus === "active") return "访问中";
  if (visit.activityStatus === "unknown" || visit.durationSeconds === undefined) {
    return "时长未知";
  }
  const duration = formatDuration(visit.durationSeconds);
  return visit.activityStatus === "estimated" ? `${duration}（估算）` : duration;
}

function visitorChannelLabel(channel: "web" | "wechat" | "wecom") {
  if (channel === "wecom") return "企业微信";
  if (channel === "wechat") return "微信";
  return "网页";
}

function answerStatusLabel(status?: string) {
  if (status === "completed") return "已回答";
  if (status === "refused") return "已安全拒答";
  if (status === "failed") return "回答失败";
  if (status === "pending") return "回答中";
  return "暂无回答";
}

function levelLabel(level: "low" | "medium" | "high") {
  return { low: "较低", medium: "中等", high: "较高" }[level];
}

function signalCategoryLabel(category: "engagement" | "interest" | "intent") {
  return { engagement: "参与度", interest: "兴趣", intent: "意向" }[category];
}

function exitReasonLabel(reason: "navigation" | "background" | "leave" | "timeout" | "active") {
  return {
    navigation: "切换页面",
    background: "切到后台后恢复",
    leave: "正常离开",
    timeout: "无活动结束",
    active: "正在浏览",
  }[reason];
}

function visitorIdentitySummary(
  type: "anonymous" | "wecom_member" | "wechat_openid" | "wecom_external",
) {
  if (type === "anonymous") {
    return {
      masking: "匿名脱敏访客",
      authorization: "当前访问详情未返回长期画像授权状态",
      relatedVisits: "需从访客档案继续核对",
    };
  }
  return {
    masking: "已按管理端当前策略脱敏展示",
    authorization: "当前访问详情未返回长期画像授权状态",
    relatedVisits: "可从访客档案查看关联访问",
  };
}

function leadStatusSummary(conversationCount: number) {
  if (conversationCount > 0) {
    return "本次访问触发了 AI 对话，留资与后续跟进状态需在访客档案或机会页核对。";
  }
  return "当前 API 未返回留资结果；如需确认转化，请继续查看访客档案或机会页。";
}

export function VisitDetailPage({
  visitId,
  onBack,
}: {
  visitId: string;
  onBack?: () => void;
}) {
  const resource = useResource(() => workflowApi.getVisit(visitId), visitId);

  return (
    <main className="page-stack">
      <PageHeader
        title="访问详情"
        description="这里严格只描述一次访问，不把它混成长期访客档案。长期画像、同意状态和关联访问请进入访客档案查看。"
        actions={
          <>
            {onBack && (
              <Button appearance="secondary" icon={<ArrowLeft24Regular />} onClick={onBack}>
                返回访问列表
              </Button>
            )}
            <Button
              appearance="subtle"
              icon={<ArrowClockwise24Regular />}
              onClick={resource.reload}
            >
              刷新
            </Button>
          </>
        }
      />

      {resource.status === "ready" && resource.data ? (
        <>
          <section className="content-panel">
            <div className="visit-detail-summary">
              <div className="visit-detail-heading">
                <div>
                  <span className="eyebrow">单次访问</span>
                  <h2>{resource.data.cardDisplayName}</h2>
                  <p>
                    {resource.data.visitorIdentityLabel} · {visitorChannelLabel(resource.data.visitorChannel)}
                  </p>
                </div>
                <div className="visit-detail-actions">
                  <Button
                    appearance="secondary"
                    icon={<ArrowRight24Regular />}
                    onClick={() => navigate(visitorProfileDetailPath(resource.data!.visitorId))}
                  >
                    查看访客档案
                  </Button>
                  <Button
                    appearance="secondary"
                    icon={<Chat24Regular />}
                    onClick={() => navigate(APP_PATHS.conversations)}
                  >
                    查看对话列表
                  </Button>
                </div>
              </div>
              <dl className="detail-grid two-columns">
                <div>
                  <dt>访问开始</dt>
                  <dd>{formatTimestamp(resource.data.startedAt)}</dd>
                </div>
                <div>
                  <dt>停留时长</dt>
                  <dd>{formatVisitDuration(resource.data)}</dd>
                </div>
                <div>
                  <dt>来源</dt>
                  <dd>{resource.data.source || "直接访问"}</dd>
                </div>
                <div>
                  <dt>对话数量</dt>
                  <dd>{resource.data.conversationCount}</dd>
                </div>
                <div>
                  <dt>访客标识</dt>
                  <dd>
                    <code>{resource.data.visitorId}</code>
                  </dd>
                </div>
                <div>
                  <dt>最后活动</dt>
                  <dd>{resource.data.lastActivityAt ? formatTimestamp(resource.data.lastActivityAt) : "未记录"}</dd>
                </div>
              </dl>
            </div>
          </section>

          <section className="content-panel data-panel">
            <div className="visit-metrics">
              <div>
                <span>参与度评分</span>
                <strong>{resource.data.behaviorAnalysis.engagementScore}</strong>
              </div>
              <div>
                <span>浏览页面</span>
                <strong>{resource.data.behaviorAnalysis.uniquePages}</strong>
              </div>
              <div>
                <span>页面操作</span>
                <strong>{resource.data.behaviorAnalysis.totalActions}</strong>
              </div>
              <div>
                <span>AI 提问</span>
                <strong>{resource.data.behaviorAnalysis.questionCount}</strong>
              </div>
              <div>
                <span>参与程度</span>
                <strong>{levelLabel(resource.data.behaviorAnalysis.engagementLevel)}</strong>
              </div>
              <div>
                <span>咨询意向</span>
                <strong>{levelLabel(resource.data.behaviorAnalysis.intentLevel)}</strong>
              </div>
            </div>
          </section>

          <section className="content-panel">
            <div className="visit-detail-summary-cards">
              <article className="visit-summary-card">
                <span className="eyebrow">转化结果</span>
                <strong>留资 / 跟进状态</strong>
                <p>{leadStatusSummary(resource.data.conversationCount)}</p>
              </article>
              <article className="visit-summary-card">
                <span className="eyebrow">身份与脱敏</span>
                <strong>{visitorIdentitySummary(resource.data.visitorIdentityType).masking}</strong>
                <p>{visitorIdentitySummary(resource.data.visitorIdentityType).relatedVisits}</p>
              </article>
              <article className="visit-summary-card">
                <span className="eyebrow">授权边界</span>
                <strong>一次访问详情不等于长期访客档案</strong>
                <p>{visitorIdentitySummary(resource.data.visitorIdentityType).authorization}</p>
              </article>
            </div>
          </section>

          <section className="content-panel data-panel visit-analysis">
            <div className="visit-analysis-heading">
              <div>
                <span className="eyebrow">基于本次访问证据</span>
                <h3>智能行为分析</h3>
              </div>
              <div className="visit-analysis-score">
                <strong>{resource.data.behaviorAnalysis.engagementScore}</strong>
                <span>参与度评分</span>
              </div>
            </div>
            <ProgressBar
              value={resource.data.behaviorAnalysis.engagementScore / 100}
              aria-label={`参与度 ${resource.data.behaviorAnalysis.engagementScore} 分`}
            />
            <p className="visit-analysis-summary">{resource.data.behaviorAnalysis.summary}</p>
            {resource.data.behaviorAnalysis.signals.length > 0 ? (
              <div className="visit-signal-list">
                {resource.data.behaviorAnalysis.signals.map((signal, index) => (
                  <article className="visit-signal" key={`${signal.category}:${signal.label}:${index}`}>
                    <div>
                      <Badge appearance="tint" color={signal.category === "intent" ? "brand" : "informative"}>
                        {signalCategoryLabel(signal.category)}
                      </Badge>
                      <Badge appearance="outline">{signal.basis === "observed" ? "实际记录" : "系统推断"}</Badge>
                    </div>
                    <strong>{signal.label}</strong>
                    <p>{signal.evidence}</p>
                    <span>置信度 {Math.round(signal.confidence * 100)}%</span>
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted-value">记录较少，暂未形成有效行为信号。</p>
            )}
          </section>

          <section className="content-panel data-panel visit-report-section" aria-labelledby="visit-page-summary">
            <div className="visit-section-heading">
              <div>
                <span className="eyebrow">页面汇总</span>
                <h3 id="visit-page-summary">每个页面停留多久</h3>
              </div>
              <span>同一页面多次进入会累计计算</span>
            </div>
            <div className="table-scroll">
              <Table aria-label="页面停留明细">
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>页面</TableHeaderCell>
                    <TableHeaderCell>进入次数</TableHeaderCell>
                    <TableHeaderCell>累计停留</TableHeaderCell>
                    <TableHeaderCell>最后浏览</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resource.data.pageDurations.map((page) => (
                    <TableRow key={page.pageKey}>
                      <TableCell>
                        <strong>{page.pageTitle}</strong>
                        <br />
                        <code>{page.pageKey}</code>
                      </TableCell>
                      <TableCell>{page.viewCount}</TableCell>
                      <TableCell>{formatDuration(page.durationSeconds)}</TableCell>
                      <TableCell>{formatTimestamp(page.lastViewedAt)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            {resource.data.pageDurations.length === 0 && (
              <ResourceState status="empty" title="尚无页面停留事件" description="新版本上线后的访问会自动记录。" />
            )}
          </section>

          <section className="content-panel data-panel visit-report-section" aria-labelledby="visit-timeline">
            <div className="visit-section-heading">
              <div>
                <span className="eyebrow">访问路径</span>
                <h3 id="visit-timeline">逐段页面时间线</h3>
              </div>
              <span>按真实发生顺序排列</span>
            </div>
            <div className="table-scroll">
              <Table aria-label="逐段页面访问时间线">
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>顺序</TableHeaderCell>
                    <TableHeaderCell>页面</TableHeaderCell>
                    <TableHeaderCell>进入时间</TableHeaderCell>
                    <TableHeaderCell>本段停留</TableHeaderCell>
                    <TableHeaderCell>结束方式</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resource.data.pageTimeline.map((item) => (
                    <TableRow key={`${item.sequence}:${item.enteredAt}`}>
                      <TableCell>#{item.sequence}</TableCell>
                      <TableCell>
                        <strong>{item.pageTitle}</strong>
                        <br />
                        <code>{item.pageKey}</code>
                      </TableCell>
                      <TableCell>{formatTimestamp(item.enteredAt)}</TableCell>
                      <TableCell>{formatDuration(item.durationSeconds)}</TableCell>
                      <TableCell>{exitReasonLabel(item.exitReason)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            {resource.data.pageTimeline.length === 0 && <ResourceState status="empty" title="暂无页面时间线" compact />}
          </section>

          <section className="content-panel data-panel visit-report-section" aria-labelledby="visit-ai-questions">
            <div className="visit-section-heading">
              <div>
                <span className="eyebrow">AI 对话</span>
                <h3 id="visit-ai-questions">访客向 AI 提了什么</h3>
              </div>
              <span>{resource.data.behaviorAnalysis.answeredCount}/{resource.data.questions.length} 个问题已回答</span>
            </div>
            <div className="visit-question-list">
              {resource.data.questions.map((question, index) => (
                <article className="visit-question" key={question.messageId}>
                  <header>
                    <span>问题 {index + 1} · {formatTimestamp(question.askedAt)}</span>
                    <Badge appearance="tint">{answerStatusLabel(question.answerStatus)}</Badge>
                  </header>
                  <div className="visit-question-copy">
                    <span>访客</span>
                    <p>{question.question}</p>
                  </div>
                  <div className="visit-answer-copy">
                    <span>企业 AI</span>
                    <p>{question.answer || "本次回答未完成，系统已保留原始问题。"}</p>
                  </div>
                  {question.responseSeconds !== undefined && (
                    <footer>响应用时 {formatDuration(question.responseSeconds)}</footer>
                  )}
                </article>
              ))}
            </div>
            {resource.data.questions.length === 0 && (
              <ResourceState status="empty" title="本次访问尚未提问" />
            )}
          </section>

          <section className="content-panel data-panel visit-report-section" aria-labelledby="visit-actions">
            <div className="visit-section-heading">
              <div>
                <span className="eyebrow">关键操作</span>
                <h3 id="visit-actions">点击、查看与分享</h3>
              </div>
              <span>共 {resource.data.actions.length} 次</span>
            </div>
            <div className="table-scroll">
              <Table aria-label="访客关键操作">
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>时间</TableHeaderCell>
                    <TableHeaderCell>操作</TableHeaderCell>
                    <TableHeaderCell>对象</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resource.data.actions.map((action) => (
                    <TableRow key={action.eventId}>
                      <TableCell>{formatTimestamp(action.occurredAt)}</TableCell>
                      <TableCell>{action.actionLabel}</TableCell>
                      <TableCell>{action.objectId || action.objectType || "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            {resource.data.actions.length === 0 && <ResourceState status="empty" title="本次访问没有关键操作" compact />}
          </section>
        </>
      ) : (
        <section className="content-panel">
          <ResourceState
            status={resource.status === "ready" ? "empty" : resource.status}
            description={resource.error?.message}
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
          />
        </section>
      )}
    </main>
  );
}

export function VisitsPage() {
  const [offset, setOffset] = useState(0);
  const [cardDraft, setCardDraft] = useState("");
  const [cardId, setCardId] = useState("");
  const resource = useResource(
    () =>
      workflowApi.listVisits({
        limit: PAGE_SIZE,
        offset,
        cardId: cardId || undefined,
      }),
    `${offset}:${cardId}`,
    { refreshIntervalMs: 5_000, refreshOnVisible: true },
  );

  const applyFilter = () => {
    const next = cardDraft.trim();
    if (next === cardId && offset === 0) resource.reload();
    setOffset(0);
    setCardId(next);
  };

  const clearFilter = () => {
    setCardDraft("");
    setOffset(0);
    setCardId("");
  };

  return (
    <main className="page-stack">
      <PageHeader
        title="访问记录"
        description="列表只做筛选与转化线索观察；单次路径、停留、对话与授权边界进入访问详情页查看。"
        actions={
          <Button
            appearance="subtle"
            icon={<ArrowClockwise24Regular />}
            onClick={resource.reload}
          >
            刷新
          </Button>
        }
      />

      <section className="content-panel filter-panel" aria-label="访问筛选">
        <Input
          aria-label="名片 ID"
          placeholder="输入名片 ID"
          value={cardDraft}
          onChange={(_, data) => setCardDraft(data.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") applyFilter();
          }}
        />
        <Button icon={<Filter24Regular />} onClick={applyFilter}>
          筛选
        </Button>
        {cardId && (
          <Button appearance="subtle" icon={<Dismiss24Regular />} onClick={clearFilter}>
            清除
          </Button>
        )}
      </section>

      <section className="content-panel data-panel">
        {resource.status === "ready" && resource.data ? (
          resource.data.items.length === 0 ? (
            <ResourceState
              status="empty"
              title="没有匹配的访问记录"
              description="可以清除名片筛选，或等待新访客进入公开名片。"
            />
          ) : (
            <>
              <div className="table-scroll">
                <Table aria-label="访问记录列表">
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>名片</TableHeaderCell>
                      <TableHeaderCell>访客</TableHeaderCell>
                      <TableHeaderCell>来源</TableHeaderCell>
                      <TableHeaderCell>开始时间</TableHeaderCell>
                      <TableHeaderCell>停留时长</TableHeaderCell>
                      <TableHeaderCell>转化线索</TableHeaderCell>
                      <TableHeaderCell>明细</TableHeaderCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resource.data.items.map((visit) => (
                      <TableRow key={visit.id}>
                        <TableCell>
                          <div className="entity-title-cell compact-cell">
                            <strong>{visit.cardDisplayName}</strong>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="entity-title-cell compact-cell">
                            <strong>{visit.visitorIdentityLabel}</strong>
                            <span>{visitorChannelLabel(visit.visitorChannel)} · {visit.visitorId.slice(0, 8)}</span>
                          </div>
                        </TableCell>
                        <TableCell>{visit.source || "直接访问"}</TableCell>
                        <TableCell className="updated-column">
                          {formatTimestamp(visit.startedAt)}
                        </TableCell>
                        <TableCell>{formatVisitDuration(visit)}</TableCell>
                        <TableCell>{visit.conversationCount > 0 ? `${visit.conversationCount} 次 AI 对话` : "暂未产生对话"}</TableCell>
                        <TableCell>
                          <a href={appHref(visitDetailPath(visit.id))}>查看详情</a>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div className="panel-footer-row">
                <Button
                  appearance="subtle"
                  icon={<Chat24Regular />}
                  onClick={() => navigate(APP_PATHS.conversations)}
                >
                  查看对话
                </Button>
                <PaginationBar
                  total={resource.data.total}
                  limit={resource.data.limit}
                  offset={resource.data.offset}
                  onOffsetChange={setOffset}
                />
              </div>
            </>
          )
        ) : (
          <ResourceState
            status={resource.status === "ready" ? "empty" : resource.status}
            description={resource.error?.message}
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
          />
        )}
      </section>
    </main>
  );
}

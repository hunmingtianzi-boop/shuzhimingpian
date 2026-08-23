import {
  Badge,
  Button,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import {
  ArrowClockwise24Regular,
  Dismiss24Regular,
  Eye24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { visitorProfilesApi } from "../api/visitorProfilesApi";
import type {
  VisitorProfileDetail,
  VisitorProfileSignal,
  VisitorProfileSource,
} from "../api/visitorProfilesApi";
import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { PageHeader } from "../components/PageHeader";
import { PaginationBar } from "../components/PaginationBar";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import { appHref } from "../routing";
import { formatTimestamp } from "../utils/format";
import "./VisitorProfilesPage.css";

const PAGE_SIZE = 20;

function formatScore(value: number): string {
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

function EvidenceIdentifiers({ source }: { source: VisitorProfileSource }) {
  const identifiers = [
    ["访问", source.visitId],
    ["对话", source.conversationId],
    ["审核摘要", source.summaryId],
    ["消息", source.messageId],
  ].filter((entry): entry is [string, string] => Boolean(entry[1]));

  return (
    <dl className="visitor-profile-source-ids">
      {identifiers.length > 0 ? identifiers.map(([label, id]) => (
        <div key={`${label}:${id}`}>
          <dt>{label}</dt>
          <dd><code>{id}</code></dd>
        </div>
      )) : (
        <div><dt>来源</dt><dd>仅保留聚合证据</dd></div>
      )}
    </dl>
  );
}

function SignalCard({ signal }: { signal: VisitorProfileSignal }) {
  return (
    <article className="visitor-profile-signal">
      <header>
        <div>
          <Badge appearance="tint" color={signal.kind === "intent" ? "brand" : "informative"}>
            {signal.kind === "intent" ? "意图" : "兴趣"}
          </Badge>
          <h4>{signal.label}</h4>
        </div>
        <span>{signal.evidenceCount} 条证据</span>
      </header>
      <div className="visitor-profile-scores" aria-label={`${signal.label}评分`}>
        <div><span>强度</span><strong>{formatScore(signal.strength)}</strong></div>
        <div><span>置信度</span><strong>{formatScore(signal.confidence)}</strong></div>
      </div>
      <dl className="visitor-profile-dates">
        <div><dt>首次出现</dt><dd>{formatTimestamp(signal.firstSeenAt)}</dd></div>
        <div><dt>最后出现</dt><dd>{formatTimestamp(signal.lastSeenAt)}</dd></div>
        <div><dt>保留期限</dt><dd>{formatTimestamp(signal.retentionExpiresAt)}</dd></div>
      </dl>
      <details className="visitor-profile-evidence">
        <summary>查看证据来源（{signal.sources.length}）</summary>
        {signal.sources.length === 0 ? (
          <p>该信号仅保留聚合证据计数。</p>
        ) : (
          <ul>
            {signal.sources.map((source) => (
              <li key={source.id}>
                <EvidenceIdentifiers source={source} />
                <div className="visitor-profile-source-meta">
                  <span>贡献 {formatScore(source.contribution)}</span>
                  <span>置信度 {formatScore(source.confidence)}</span>
                  <time dateTime={source.observedAt}>{formatTimestamp(source.observedAt)}</time>
                </div>
              </li>
            ))}
          </ul>
        )}
      </details>
    </article>
  );
}

function ProfileDetail({ visitorId, onClose }: { visitorId: string; onClose: () => void }) {
  const resource = useResource(() => visitorProfilesApi.getOverview(visitorId), visitorId);
  const overview = resource.data;
  const detail: VisitorProfileDetail | undefined = overview?.profile;

  return (
    <aside className="content-panel visitor-profile-detail" aria-label="访客画像详情">
      <div className="visitor-profile-detail-heading">
        <div>
          <span className="eyebrow">已授权画像</span>
          <h2>访客画像详情</h2>
          <code>{visitorId}</code>
        </div>
        <Button appearance="subtle" icon={<Dismiss24Regular />} onClick={onClose}>
          关闭
        </Button>
      </div>
      {resource.status === "ready" && overview && detail ? (
        <>
          <div className="visitor-profile-detail-summary">
            <div><span>首次识别</span><strong>{formatTimestamp(detail.firstSeenAt)}</strong></div>
            <div><span>最近识别</span><strong>{formatTimestamp(detail.lastSeenAt)}</strong></div>
            <div><span>有效信号</span><strong>{detail.signals.length}</strong></div>
          </div>
          {detail.signals.length === 0 ? (
            <ResourceState
              status="empty"
              title="暂无有效画像信号"
              description="授权仍有效，但当前没有未过期的兴趣或意图信号。"
              compact
            />
          ) : (
            <div className="visitor-profile-signal-list">
              {detail.signals.map((signal) => <SignalCard key={signal.id} signal={signal} />)}
            </div>
          )}
          <section className="visitor-profile-overview-section">
            <h3>已授权留资</h3>
            <p className="visitor-profile-overview-note">仅显示已脱敏的联系方式；原始联系方式仍在受权限控制的线索页面内。</p>
            {overview.leads.length === 0 ? (
              <p className="muted-value">该访客尚未主动留资。</p>
            ) : (
              <div className="visitor-profile-overview-list">
                {overview.leads.map((lead) => (
                  <article key={lead.id}>
                    <strong>{lead.maskedName} · {lead.maskedContact}</strong>
                    <span>{lead.cardDisplayName} · {lead.status} / {lead.priority}</span>
                    <time>{formatTimestamp(lead.createdAt)}</time>
                  </article>
                ))}
              </div>
            )}
          </section>
          <section className="visitor-profile-overview-section">
            <div className="visitor-profile-overview-heading">
              <h3>关联 AI 对话</h3>
              <a href={appHref(`/conversations?visitorId=${encodeURIComponent(visitorId)}`)}>查看完整消息与引用</a>
            </div>
            {overview.conversations.length === 0 ? (
              <p className="muted-value">暂无可见对话。</p>
            ) : (
              <div className="visitor-profile-overview-list">
                {overview.conversations.map((conversation) => (
                  <article key={conversation.id}>
                    <strong>{conversation.cardDisplayName} · {conversation.primaryIntent || "未识别意图"}</strong>
                    <span>{conversation.messageCount} 条消息 · {conversation.status} · 风险 {conversation.riskLevel}</span>
                    <time>{formatTimestamp(conversation.lastActivityAt)}</time>
                  </article>
                ))}
              </div>
            )}
          </section>
          <section className="visitor-profile-overview-section">
            <h3>该访客触发的知识缺口</h3>
            {overview.knowledgeGaps.length === 0 ? (
              <p className="muted-value">当前没有待处理或历史知识缺口。</p>
            ) : (
              <div className="visitor-profile-overview-list">
                {overview.knowledgeGaps.map((gap) => (
                  <article key={gap.id}>
                    <strong>{gap.question}</strong>
                    <span>{gap.reason} · {gap.status} · 已出现 {gap.occurrenceCount} 次</span>
                    <time>{formatTimestamp(gap.lastSeenAt)}</time>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      ) : (
        <ResourceState
          status={resource.status === "ready" ? "empty" : resource.status}
          description={resource.error?.message}
          errorCode={resource.error?.code}
          requestId={resource.error?.requestId}
          onRetry={resource.status === "error" ? resource.reload : undefined}
        />
      )}
    </aside>
  );
}

export function VisitorProfilesPage({
  initialVisitorId,
}: {
  initialVisitorId?: string;
} = {}) {
  const { user } = useAuth();
  const [offset, setOffset] = useState(0);
  const [selectedVisitorId, setSelectedVisitorId] = useState<string | undefined>(
    initialVisitorId,
  );
  const canRead = hasPermission(user, "visits.read", { allowCardOwner: true });
  const resource = useResource(
    () => canRead
      ? visitorProfilesApi.list({ limit: PAGE_SIZE, offset })
      : Promise.resolve({ items: [], total: 0, limit: PAGE_SIZE, offset: 0 }),
    `${canRead}:${offset}`,
  );

  if (!canRead) {
    return (
      <main className="page-stack">
        <PageHeader
          title="长期访客画像"
          description="仅展示访客明确授权、尚未撤回且未过期的企业内画像。"
        />
        <section className="content-panel data-panel">
          <ResourceState
            status="permission"
            description="当前账号没有访客数据读取权限。"
          />
        </section>
      </main>
    );
  }

  return (
    <main className="page-stack visitor-profiles-page">
      <PageHeader
        title="长期访客画像"
        description="仅展示访客明确授权、尚未撤回且未过期的企业内画像；撤回后不会继续关联。"
        actions={
          <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>
            刷新
          </Button>
        }
      />
      <section className="visitor-profile-privacy-note" aria-label="画像隐私说明">
        页面不展示原始联系方式、消息正文或摘要正文；360° 视图仅展示已脱敏留资和受租户隔离的关联记录。
      </section>
      <section className="content-panel data-panel">
        {resource.status === "ready" && resource.data ? (
          resource.data.items.length === 0 ? (
            <ResourceState
              status="empty"
              title="暂无已授权访客画像"
              description="访客明确同意企业内个性化后，未过期的画像会显示在这里。"
            />
          ) : (
            <>
              <div className="table-scroll">
                <Table aria-label="长期访客画像列表">
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>匿名访客</TableHeaderCell>
                      <TableHeaderCell>主要兴趣</TableHeaderCell>
                      <TableHeaderCell>有效信号</TableHeaderCell>
                      <TableHeaderCell>首次识别</TableHeaderCell>
                      <TableHeaderCell>最近识别</TableHeaderCell>
                      <TableHeaderCell />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resource.data.items.map((profile) => (
                      <TableRow key={profile.visitorId}>
                        <TableCell><code>{profile.visitorId}</code></TableCell>
                        <TableCell>
                          <div className="visitor-profile-tags">
                            {profile.topInterests.length > 0
                              ? profile.topInterests.map((interest) => (
                                <Badge key={interest.label} appearance="tint" color="informative">
                                  {interest.label} · {formatScore(interest.confidence)}
                                </Badge>
                              ))
                              : <span className="muted-value">暂无兴趣信号</span>}
                          </div>
                        </TableCell>
                        <TableCell>{profile.signalCount}</TableCell>
                        <TableCell>{formatTimestamp(profile.firstSeenAt)}</TableCell>
                        <TableCell>{formatTimestamp(profile.lastSeenAt)}</TableCell>
                        <TableCell className="actions-column">
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<Eye24Regular />}
                            aria-label={`查看访客 ${profile.visitorId} 画像详情`}
                            onClick={() => setSelectedVisitorId(profile.visitorId)}
                          >
                            查看详情
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div className="panel-footer-row">
                <span className="visitor-profile-scope">企业内授权画像</span>
                <PaginationBar
                  total={resource.data.total}
                  limit={resource.data.limit}
                  offset={resource.data.offset}
                  onOffsetChange={(nextOffset) => {
                    setSelectedVisitorId(undefined);
                    setOffset(nextOffset);
                  }}
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
      {selectedVisitorId && (
        <ProfileDetail visitorId={selectedVisitorId} onClose={() => setSelectedVisitorId(undefined)} />
      )}
    </main>
  );
}

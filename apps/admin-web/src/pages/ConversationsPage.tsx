import {
  Badge,
  Button,
  DrawerBody,
  DrawerHeader,
  DrawerHeaderTitle,
  Input,
  OverlayDrawer,
  Select,
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
  Filter24Regular,
  Sparkle24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { ApiError } from "../api/client";
import type {
  ConversationDetail,
  ConversationStatus,
  ConversationSummary,
} from "../api/types";
import { workflowApi } from "../api/workflowApi";
import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { OperationFeedback } from "../components/OperationFeedback";
import { PageHeader } from "../components/PageHeader";
import { PaginationBar } from "../components/PaginationBar";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

const PAGE_SIZE = 20;

function asApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("生成纪要时发生未知错误。", {
        code: "UNKNOWN_ERROR",
      });
}

function SummaryBlock({ summary }: { summary?: ConversationSummary }) {
  if (!summary) {
    return (
      <ResourceState
        compact
        status="empty"
        title="尚未生成纪要"
        description="生成后会提取需求、意向强度、下一步和风险备注。"
      />
    );
  }
  return (
    <div className="summary-detail">
      <p>{summary.summary}</p>
      {summary.interests.length > 0 && (
        <div className="tag-row">
          {summary.interests.map((interest) => (
            <Badge key={interest} appearance="outline">
              {interest}
            </Badge>
          ))}
        </div>
      )}
      <dl className="detail-grid">
        <div>
          <dt>意向强度</dt>
          <dd>{summary.strength || "未判定"}</dd>
        </div>
        <div>
          <dt>下一步</dt>
          <dd>{summary.nextStep || "暂无建议"}</dd>
        </div>
        <div>
          <dt>风险备注</dt>
          <dd>{summary.riskNotes || "未发现额外风险"}</dd>
        </div>
      </dl>
      <span className="detail-meta">
        基于 {summary.sourceMessageIds.length} 条消息，更新于 {formatTimestamp(summary.updatedAt)}
      </span>
      <Badge appearance="outline" color={summary.approvedAt ? "success" : "warning"}>
        {summary.approvedAt ? "已审核并可用于授权画像" : "待人工审核，不进入画像"}
      </Badge>
    </div>
  );
}

function ConversationBody({ detail }: { detail: ConversationDetail }) {
  return (
    <div className="drawer-section-stack">
      <section className="drawer-section">
        <h3>对话概况</h3>
        <dl className="detail-grid two-columns">
          <div>
            <dt>名片</dt>
            <dd>{detail.cardDisplayName}</dd>
          </div>
          <div>
            <dt>主要意图</dt>
            <dd>{detail.primaryIntent || "未识别"}</dd>
          </div>
          <div>
            <dt>风险等级</dt>
            <dd>{detail.riskLevel}</dd>
          </div>
          <div>
            <dt>最后活跃</dt>
            <dd>{formatTimestamp(detail.lastActivityAt)}</dd>
          </div>
        </dl>
      </section>
      <section className="drawer-section">
        <h3>对话纪要</h3>
        <SummaryBlock summary={detail.currentSummary} />
      </section>
      <section className="drawer-section">
        <h3>消息记录</h3>
        {detail.messages.length === 0 ? (
          <ResourceState compact status="empty" title="对话中暂无消息" />
        ) : (
          <div className="message-timeline">
            {detail.messages.map((message) => (
              <article key={message.id} className={`message-item ${message.role}`}>
                <header>
                  <strong>{message.role === "user" ? "访客" : "AI 助手"}</strong>
                  <span>{formatTimestamp(message.createdAt)}</span>
                </header>
                <p>{message.content}</p>
                {message.contentRedacted && <Badge appearance="outline">内容已脱敏</Badge>}
                {message.citations.length > 0 && (
                  <details>
                    <summary>查看 {message.citations.length} 条引用</summary>
                    <div className="citation-list">
                      {message.citations.map((citation) => (
                        <div key={citation.id}>
                          <strong>{citation.title}</strong>
                          <p>{citation.snapshotText}</p>
                          <span>相关度 {citation.score.toFixed(3)}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ConversationDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const auth = useAuth();
  const canSummarize = hasPermission(auth.user, "summaries.write", {
    allowCardOwner: true,
  });
  const resource = useResource(() => workflowApi.getConversation(id), id);
  const [generating, setGenerating] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();

  const generate = async () => {
    if (generating) return;
    setGenerating(true);
    setError(undefined);
    setNotice(undefined);
    try {
      await workflowApi.generateConversationSummary(id);
      setNotice("纪要已由服务端生成并保存。");
      resource.reload();
    } catch (caught) {
      setError(asApiError(caught));
    } finally {
      setGenerating(false);
    }
  };

  const approve = async () => {
    const summary = resource.data?.currentSummary;
    if (!summary || summary.approvedAt || approving) return;
    setApproving(true);
    setError(undefined);
    setNotice(undefined);
    try {
      await workflowApi.approveSummary(summary.id);
      setNotice("纪要已人工审核；仅在访客仍有效授权时更新长期画像。");
      resource.reload();
    } catch (caught) {
      setError(asApiError(caught));
    } finally {
      setApproving(false);
    }
  };

  return (
    <OverlayDrawer position="end" size="large" open onOpenChange={(_, data) => !data.open && onClose()}>
      <DrawerHeader>
        <DrawerHeaderTitle
          action={
            <Button
              appearance="subtle"
              icon={<Dismiss24Regular />}
              aria-label="关闭对话详情"
              onClick={onClose}
            />
          }
        >
          对话详情
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody>
        <div className="drawer-command-bar">
          <code>{id}</code>
          {canSummarize && (
            <Button
              appearance="primary"
              icon={<Sparkle24Regular />}
              disabled={generating || resource.status !== "ready"}
              onClick={() => void generate()}
            >
              {generating ? "正在生成" : "生成纪要"}
            </Button>
          )}
          {canSummarize && resource.data?.currentSummary && !resource.data.currentSummary.approvedAt && (
            <Button
              appearance="secondary"
              disabled={approving || generating}
              onClick={() => void approve()}
            >
              {approving ? "正在审核" : "审核通过并用于画像"}
            </Button>
          )}
        </div>
        <OperationFeedback notice={notice} error={error} onRetry={() => void generate()} />
        {resource.status === "ready" && resource.data ? (
          <ConversationBody detail={resource.data} />
        ) : (
          <ResourceState
            status={resource.status === "ready" ? "empty" : resource.status}
            description={resource.error?.message}
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
          />
        )}
      </DrawerBody>
    </OverlayDrawer>
  );
}

export function ConversationsPage({
  initialConversationId,
}: {
  initialConversationId?: string;
} = {}) {
  const initialVisitorId = new URLSearchParams(window.location.search).get("visitorId")?.trim() || "";
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState<ConversationStatus | "">("");
  const [cardDraft, setCardDraft] = useState("");
  const [cardId, setCardId] = useState("");
  const [visitorDraft, setVisitorDraft] = useState(initialVisitorId);
  const [visitorId, setVisitorId] = useState(initialVisitorId);
  const [selectedId, setSelectedId] = useState<string | undefined>(
    initialConversationId,
  );
  const resource = useResource(
    () =>
      workflowApi.listConversations({
        limit: PAGE_SIZE,
        offset,
        status: status || undefined,
        cardId: cardId || undefined,
        visitorId: visitorId || undefined,
      }),
    `${offset}:${status}:${cardId}:${visitorId}`,
  );

  const applyFilters = () => {
    const nextCard = cardDraft.trim();
    const nextVisitor = visitorDraft.trim();
    if (nextCard === cardId && nextVisitor === visitorId && offset === 0) resource.reload();
    setOffset(0);
    setCardId(nextCard);
    setVisitorId(nextVisitor);
  };

  return (
    <main className="page-stack">
      <PageHeader
        title="AI 对话与纪要"
        description="审阅真实对话、引用和风险信号，将对话生成可跟进的结构化纪要。"
        actions={
          <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>
            刷新
          </Button>
        }
      />

      <section className="content-panel filter-panel" aria-label="对话筛选">
        <Select
          aria-label="对话状态"
          value={status}
          onChange={(_, data) => {
            setOffset(0);
            setStatus(data.value as ConversationStatus | "");
          }}
        >
          <option value="">全部状态</option>
          <option value="active">进行中</option>
          <option value="closed">已结束</option>
          <option value="expired">已过期</option>
          <option value="blocked">已阻断</option>
        </Select>
        <Input
          aria-label="名片 ID"
          placeholder="按名片 ID 筛选"
          value={cardDraft}
          onChange={(_, data) => setCardDraft(data.value)}
          onKeyDown={(event) => event.key === "Enter" && applyFilters()}
        />
        <Input
          aria-label="访客 ID"
          placeholder="按访客 ID 筛选"
          value={visitorDraft}
          onChange={(_, data) => setVisitorDraft(data.value)}
          onKeyDown={(event) => event.key === "Enter" && applyFilters()}
        />
        <Button icon={<Filter24Regular />} onClick={applyFilters}>
          应用
        </Button>
        {(status || cardId || visitorId) && (
          <Button
            appearance="subtle"
            icon={<Dismiss24Regular />}
            onClick={() => {
              setStatus("");
              setCardDraft("");
              setCardId("");
              setVisitorDraft("");
              setVisitorId("");
              setOffset(0);
            }}
          >
            清除
          </Button>
        )}
      </section>

      <section className="content-panel data-panel">
        {resource.status === "ready" && resource.data ? (
          resource.data.items.length === 0 ? (
            <ResourceState
              status="empty"
              title="没有匹配的对话"
              description="调整状态或名片筛选后重试。"
            />
          ) : (
            <>
              <div className="table-scroll">
                <Table aria-label="AI 对话列表">
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>对话</TableHeaderCell>
                      <TableHeaderCell>状态</TableHeaderCell>
                      <TableHeaderCell>主要意图</TableHeaderCell>
                      <TableHeaderCell>消息</TableHeaderCell>
                      <TableHeaderCell>纪要</TableHeaderCell>
                      <TableHeaderCell>最后活跃</TableHeaderCell>
                      <TableHeaderCell />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resource.data.items.map((conversation) => (
                      <TableRow key={conversation.id}>
                        <TableCell>
                          <div className="entity-title-cell compact-cell">
                            <strong>{conversation.cardDisplayName}</strong>
                            <code>{conversation.id}</code>
                          </div>
                        </TableCell>
                        <TableCell><StatusBadge status={conversation.status} /></TableCell>
                        <TableCell>{conversation.primaryIntent || "未识别"}</TableCell>
                        <TableCell>{conversation.messageCount}</TableCell>
                        <TableCell>
                          {conversation.hasCurrentSummary ? "已生成" : "待生成"}
                        </TableCell>
                        <TableCell className="updated-column">
                          {formatTimestamp(conversation.lastActivityAt)}
                        </TableCell>
                        <TableCell className="actions-column">
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<Eye24Regular />}
                            onClick={() => setSelectedId(conversation.id)}
                          >
                            详情
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <PaginationBar
                total={resource.data.total}
                limit={resource.data.limit}
                offset={resource.data.offset}
                onOffsetChange={setOffset}
              />
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

      {selectedId && <ConversationDrawer id={selectedId} onClose={() => setSelectedId(undefined)} />}
    </main>
  );
}

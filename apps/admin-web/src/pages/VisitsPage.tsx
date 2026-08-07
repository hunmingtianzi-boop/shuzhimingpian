import {
  Button,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import {
  ArrowClockwise24Regular,
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
import { APP_PATHS, navigate } from "../routing";
import { formatTimestamp } from "../utils/format";

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

function VisitDetailPanel({ visitId, onClose }: { visitId: string; onClose: () => void }) {
  const resource = useResource(() => workflowApi.getVisit(visitId), visitId);
  return (
    <section className="content-panel data-panel" aria-label="访问行为明细">
      <PageHeader
        title="访问行为明细"
        description="按同一次访问汇总页面停留与访客提问。"
        actions={<Button appearance="subtle" icon={<Dismiss24Regular />} onClick={onClose}>关闭</Button>}
      />
      {resource.status === "ready" && resource.data ? (
        <div className="page-stack compact-stack">
          <div className="table-scroll">
            <Table aria-label="页面停留明细">
              <TableHeader><TableRow>
                <TableHeaderCell>页面</TableHeaderCell>
                <TableHeaderCell>进入次数</TableHeaderCell>
                <TableHeaderCell>累计停留</TableHeaderCell>
                <TableHeaderCell>最后浏览</TableHeaderCell>
              </TableRow></TableHeader>
              <TableBody>
                {resource.data.pageDurations.map((page) => (
                  <TableRow key={page.pageKey}>
                    <TableCell><strong>{page.pageTitle}</strong><br /><code>{page.pageKey}</code></TableCell>
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
          <div className="table-scroll">
            <Table aria-label="本次访问提问明细">
              <TableHeader><TableRow>
                <TableHeaderCell>提问时间</TableHeaderCell>
                <TableHeaderCell>访客问题</TableHeaderCell>
                <TableHeaderCell>回答状态</TableHeaderCell>
              </TableRow></TableHeader>
              <TableBody>
                {resource.data.questions.map((question) => (
                  <TableRow key={question.messageId}>
                    <TableCell>{formatTimestamp(question.askedAt)}</TableCell>
                    <TableCell>{question.question}</TableCell>
                    <TableCell>{answerStatusLabel(question.answerStatus)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {resource.data.questions.length === 0 && (
            <ResourceState status="empty" title="本次访问尚未提问" />
          )}
        </div>
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
  );
}

export function VisitsPage() {
  const [offset, setOffset] = useState(0);
  const [cardDraft, setCardDraft] = useState("");
  const [cardId, setCardId] = useState("");
  const [selectedVisitId, setSelectedVisitId] = useState<string>();
  const resource = useResource(
    () =>
      workflowApi.listVisits({
        limit: PAGE_SIZE,
        offset,
        cardId: cardId || undefined,
      }),
    `${offset}:${cardId}`,
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
        description="按名片查看访客来源、停留时长和对话转化，数据不含主观推断。"
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
                      <TableHeaderCell>对话数</TableHeaderCell>
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
                        <TableCell>{visit.conversationCount}</TableCell>
                        <TableCell>
                          <Button appearance="subtle" onClick={() => setSelectedVisitId(visit.id)}>
                            查看
                          </Button>
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
      {selectedVisitId && (
        <VisitDetailPanel visitId={selectedVisitId} onClose={() => setSelectedVisitId(undefined)} />
      )}
    </main>
  );
}

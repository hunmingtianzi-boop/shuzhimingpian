import {
  Button,
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
  MailRead24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { ApiError } from "../api/client";
import { workflowApi } from "../api/workflowApi";
import { OperationFeedback } from "../components/OperationFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import { APP_PATHS, appHref } from "../routing";
import { formatTimestamp } from "../utils/format";

export function NotificationsPage() {
  const [unreadOnly, setUnreadOnly] = useState(true);
  const [pendingId, setPendingId] = useState<string>();
  const [lastId, setLastId] = useState<string>();
  const [error, setError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();
  const resource = useResource(
    () => workflowApi.listNotifications({ limit: 100, unreadOnly }),
    unreadOnly,
    { refreshIntervalMs: 5_000, refreshOnVisible: true },
  );

  const markRead = async (id: string) => {
    if (pendingId) return;
    setPendingId(id);
    setLastId(id);
    setError(undefined);
    setNotice(undefined);
    try {
      await workflowApi.markNotificationRead(id);
      setNotice("通知已标记为已读。");
      resource.reload();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError("更新通知时发生未知错误。", {
              code: "UNKNOWN_ERROR",
            }),
      );
    } finally {
      setPendingId(undefined);
    }
  };

  return (
    <main className="page-stack">
      <PageHeader
        title="通知中心"
        description="集中处理访问报告、线索、知识缺口和业务异常通知，已读状态由服务端保存。"
        actions={
          <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>刷新</Button>
        }
      />
      <section className="content-panel filter-panel notification-filter" aria-label="通知筛选">
        <Select
          aria-label="通知范围"
          value={unreadOnly ? "unread" : "all"}
          onChange={(_, data) => setUnreadOnly(data.value === "unread")}
        >
          <option value="unread">仅未读</option>
          <option value="all">全部通知</option>
        </Select>
        {resource.status === "ready" && resource.data && (
          <span>未读 {resource.data.unread} 条，共 {resource.data.total} 条</span>
        )}
      </section>
      <OperationFeedback
        notice={notice}
        error={error}
        onRetry={lastId ? () => void markRead(lastId) : undefined}
      />
      <section className="content-panel data-panel">
        {resource.status === "ready" && resource.data ? (
          resource.data.items.length === 0 ? (
            <ResourceState
              status="empty"
              title={unreadOnly ? "没有未读通知" : "尚无通知"}
              description={unreadOnly ? "当前需要处理的通知已全部读取。" : "业务事件触发后会显示在这里。"}
            />
          ) : (
            <div className="table-scroll">
              <Table aria-label="通知列表">
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>通知</TableHeaderCell>
                    <TableHeaderCell>类型</TableHeaderCell>
                    <TableHeaderCell>资源</TableHeaderCell>
                    <TableHeaderCell>时间</TableHeaderCell>
                    <TableHeaderCell />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resource.data.items.map((item) => (
                    <TableRow key={item.id} className={item.readAt ? "notification-read" : "notification-unread"}>
                      <TableCell>
                        <div className="notification-copy">
                          <strong>{item.title}</strong>
                          <span>{item.body}</span>
                        </div>
                      </TableCell>
                      <TableCell>{item.notificationType}</TableCell>
                      <TableCell>{item.resourceType || "通用"}</TableCell>
                      <TableCell className="updated-column">{formatTimestamp(item.createdAt)}</TableCell>
                      <TableCell className="actions-column">
                        {item.resourceType === "visit" && item.resourceId && (
                          <a
                            href={appHref(`${APP_PATHS.visits}?visitId=${encodeURIComponent(item.resourceId)}`)}
                          >
                            查看报告
                          </a>
                        )}
                        {!item.readAt ? (
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<MailRead24Regular />}
                            disabled={Boolean(pendingId)}
                            onClick={() => void markRead(item.id)}
                          >
                            {pendingId === item.id ? "正在更新" : "标记已读"}
                          </Button>
                        ) : (
                          <span className="read-label">已读</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )
        ) : (
          <ResourceState status={resource.status === "ready" ? "empty" : resource.status} description={resource.error?.message} errorCode={resource.error?.code} requestId={resource.error?.requestId} onRetry={resource.status === "error" ? resource.reload : undefined} />
        )}
      </section>
    </main>
  );
}

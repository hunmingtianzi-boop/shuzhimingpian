import {
  Button,
  Checkbox,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import {
  ArrowClockwise24Regular,
  ArrowDownload24Regular,
} from "@fluentui/react-icons";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../api/client";
import { exportsApi } from "../api/exportsApi";
import type { DataExport, ExportAvailability, ExportType } from "../api/exportsApi";
import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { OperationFeedback } from "../components/OperationFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

const TYPE_LABELS: Record<ExportType, string> = {
  visitors: "访客",
  leads: "线索",
  conversations: "对话",
};
const TYPE_PERMISSIONS: Record<ExportType, string> = {
  visitors: "visits.read",
  leads: "leads.read",
  conversations: "conversations.read",
};
const STATUS_LABELS: Record<DataExport["status"], string> = {
  pending: "等待处理",
  processing: "生成中",
  completed: "可下载",
  failed: "生成失败",
  expired: "已过期",
};
const EXPORT_POLL_INTERVAL_MS = 1_000;
const EXPORT_POLL_ATTEMPTS = 45;

function asApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("导出操作发生未知错误。", { code: "UNKNOWN_ERROR" });
}

export function saveExportFile(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.append(anchor);
  anchor.click();
  window.setTimeout(() => {
    anchor.remove();
    URL.revokeObjectURL(url);
  }, 60_000);
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export function ExportsPage() {
  const { user } = useAuth();
  const [includeSensitive, setIncludeSensitive] = useState(false);
  const [pendingAction, setPendingAction] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [error, setError] = useState<ApiError>();
  const isAdmin = user?.role === "company_admin" || user?.role === "platform_admin";
  const allowedTypes = useMemo(
    () =>
      (Object.keys(TYPE_LABELS) as ExportType[]).filter((type) =>
        hasPermission(user, TYPE_PERMISSIONS[type], { allowCardOwner: true }),
    ),
    [user],
  );
  const resource = useResource(
    () => allowedTypes.length > 0
      ? exportsApi.list()
      : Promise.resolve({ items: [], total: 0, limit: 50, offset: 0 }),
    allowedTypes.join(","),
  );
  const availability = useResource<ExportAvailability>(
    () =>
      allowedTypes.length > 0
        ? exportsApi.availability()
        : Promise.resolve({
            visitors: 0,
            leads: 0,
            conversations: 0,
            generatedAt: new Date(0).toISOString(),
          }),
    allowedTypes.join(","),
  );

  useEffect(() => {
    const active = resource.data?.items.some(
      (item) => item.status === "pending" || item.status === "processing",
    );
    if (!active) return undefined;
    const timer = window.setInterval(resource.reload, 3000);
    return () => window.clearInterval(timer);
  }, [resource.data, resource.reload]);

  const createAndDownloadExport = async (exportType: ExportType) => {
    if (
      pendingAction ||
      !allowedTypes.includes(exportType) ||
      (availability.data?.[exportType] ?? 0) === 0
    ) return;
    setPendingAction(`create:${exportType}`);
    setNotice(`正在生成${TYPE_LABELS[exportType]} CSV，请稍候…`);
    setError(undefined);
    try {
      let current = await exportsApi.create(exportType, isAdmin && includeSensitive);
      resource.reload();

      for (
        let attempt = 0;
        attempt < EXPORT_POLL_ATTEMPTS &&
        (current.status === "pending" || current.status === "processing");
        attempt += 1
      ) {
        await wait(EXPORT_POLL_INTERVAL_MS);
        current = await exportsApi.get(current.id);
      }

      resource.reload();
      if (current.status === "completed") {
        const download = await exportsApi.download(current.id, current.fileName);
        saveExportFile(download.blob, download.fileName);
        setNotice(
          `${TYPE_LABELS[exportType]} CSV 已生成，下载已开始。若浏览器询问，请允许保存文件。`,
        );
        return;
      }
      if (current.status === "failed") {
        throw new ApiError("导出文件生成失败，请重试。", {
          code: current.failureCode || "EXPORT_FAILED",
        });
      }
      if (current.status === "expired") {
        throw new ApiError("导出文件已经过期，请重新生成。", {
          code: "EXPORT_EXPIRED",
        });
      }
      setNotice("任务仍在后台生成。完成后可在下方任务列表点击“下载 CSV”。");
    } catch (caught) {
      setError(asApiError(caught));
    } finally {
      setPendingAction(undefined);
    }
  };

  const downloadExport = async (item: DataExport) => {
    if (pendingAction) return;
    setPendingAction(item.id);
    setNotice(undefined);
    setError(undefined);
    try {
      const download = await exportsApi.download(item.id, item.fileName);
      saveExportFile(download.blob, download.fileName);
      setNotice("导出文件已开始下载。");
    } catch (caught) {
      setError(asApiError(caught));
      resource.reload();
    } finally {
      setPendingAction(undefined);
    }
  };

  if (allowedTypes.length === 0) {
    return (
      <main className="page-stack">
        <PageHeader title="数据导出" description="异步生成访客、线索和对话 CSV 文件。" />
        <section className="content-panel data-panel">
          <ResourceState
            status="permission"
            description="当前账号没有访客、线索或对话数据的读取权限。"
          />
        </section>
      </main>
    );
  }

  return (
    <main className="page-stack">
      <PageHeader
        title="数据导出"
        description="选择一类数据即可生成并下载 CSV。文件到期后自动清除。"
        actions={
          <Button
            appearance="subtle"
            icon={<ArrowClockwise24Regular />}
            onClick={() => {
              resource.reload();
              availability.reload();
            }}
          >
            刷新
          </Button>
        }
      />
      <section className="content-panel export-availability" aria-labelledby="export-availability-title">
        <div className="section-heading-inline">
          <div>
            <h2 id="export-availability-title">当前可导出数据</h2>
            <p>点击有数据的卡片，系统会自动生成并开始下载 CSV。</p>
          </div>
        </div>
        {availability.status === "ready" && availability.data ? (
          <div className="export-availability-grid">
            {(Object.keys(TYPE_LABELS) as ExportType[]).map((type) => {
              const count = availability.data?.[type] ?? 0;
              const allowed = allowedTypes.includes(type);
              const isCreating = pendingAction === `create:${type}`;
              return (
                <Button
                  key={type}
                  className="export-availability-item"
                  appearance="subtle"
                  disabled={!allowed || count === 0 || Boolean(pendingAction)}
                  aria-label={
                    count > 0
                      ? `导出${TYPE_LABELS[type]}数据，共 ${count} 条`
                      : `${TYPE_LABELS[type]}当前暂无数据`
                  }
                  onClick={() => void createAndDownloadExport(type)}
                >
                  <span className="export-availability-copy">
                    <span className="export-availability-label">{TYPE_LABELS[type]}</span>
                    <strong>{count}</strong>
                    <small>
                      {isCreating
                        ? "正在生成 CSV…"
                        : count > 0
                          ? "一键导出 CSV"
                          : "当前暂无数据"}
                    </small>
                  </span>
                  {count > 0 ? <ArrowDownload24Regular className="export-availability-icon" /> : null}
                </Button>
              );
            })}
          </div>
        ) : (
          <ResourceState
            compact
            status={availability.status === "ready" ? "empty" : availability.status}
            description={availability.error?.message}
            errorCode={availability.error?.code}
            requestId={availability.error?.requestId}
            onRetry={availability.status === "error" ? availability.reload : undefined}
          />
        )}
      </section>
      <section className="content-panel export-options" aria-label="导出设置">
        <div>
          <strong>导出设置</strong>
          <p>默认隐藏完整联系方式，管理员可按需导出未脱敏数据。</p>
        </div>
        <Checkbox
          label="包含未脱敏联系方式"
          checked={includeSensitive}
          disabled={!isAdmin}
          onChange={(_, data) => setIncludeSensitive(data.checked === true)}
        />
      </section>
      <OperationFeedback notice={notice} error={error} onRetry={resource.reload} />
      <section className="content-panel data-panel">
        {resource.status === "ready" && resource.data ? (
          resource.data.items.length === 0 ? (
            <ResourceState
              status="empty"
              title="尚无导出任务"
              description="选择数据类型后创建第一个导出任务。"
            />
          ) : (
            <div className="table-scroll">
              <Table aria-label="数据导出列表">
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>数据</TableHeaderCell>
                    <TableHeaderCell>状态</TableHeaderCell>
                    <TableHeaderCell>范围</TableHeaderCell>
                    <TableHeaderCell>行数</TableHeaderCell>
                    <TableHeaderCell>创建时间</TableHeaderCell>
                    <TableHeaderCell>到期时间</TableHeaderCell>
                    <TableHeaderCell />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resource.data.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{TYPE_LABELS[item.exportType]}</TableCell>
                      <TableCell>
                        {STATUS_LABELS[item.status]}
                        {item.failureCode ? `（${item.failureCode}）` : ""}
                      </TableCell>
                      <TableCell>{item.includeSensitive ? "含敏感字段" : "已脱敏"}</TableCell>
                      <TableCell>{item.rowCount ?? "—"}</TableCell>
                      <TableCell>{formatTimestamp(item.createdAt)}</TableCell>
                      <TableCell>{item.expiresAt ? formatTimestamp(item.expiresAt) : "—"}</TableCell>
                      <TableCell className="actions-column">
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<ArrowDownload24Regular />}
                          disabled={item.status !== "completed" || Boolean(pendingAction)}
                          onClick={() => void downloadExport(item)}
                        >
                          {pendingAction === item.id ? "下载中" : "下载 CSV"}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
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

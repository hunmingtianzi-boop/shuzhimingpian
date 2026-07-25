import {
  Button,
  Checkbox,
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
  ArrowDownload24Regular,
  DocumentAdd24Regular,
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
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ExportsPage() {
  const { user } = useAuth();
  const [exportType, setExportType] = useState<ExportType>("visitors");
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
    if (!allowedTypes.includes(exportType) && allowedTypes[0]) {
      setExportType(allowedTypes[0]);
      return;
    }
    if (!availability.data) return;
    const counts = availability.data;
    if (counts[exportType] > 0) return;
    const populatedType = allowedTypes.find((type) => counts[type] > 0);
    if (populatedType) {
      setExportType(populatedType);
    }
  }, [allowedTypes, availability.data, exportType]);

  useEffect(() => {
    const active = resource.data?.items.some(
      (item) => item.status === "pending" || item.status === "processing",
    );
    if (!active) return undefined;
    const timer = window.setInterval(resource.reload, 3000);
    return () => window.clearInterval(timer);
  }, [resource.data, resource.reload]);

  const createExport = async () => {
    if (
      pendingAction ||
      !allowedTypes.includes(exportType) ||
      (availability.data?.[exportType] ?? 0) === 0
    ) return;
    setPendingAction("create");
    setNotice(undefined);
    setError(undefined);
    try {
      await exportsApi.create(exportType, isAdmin && includeSensitive);
      setNotice("导出任务已创建，页面会自动更新处理状态。");
      resource.reload();
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
        description="先查看各类真实数据量，再异步生成 CSV。文件到期后自动清除。"
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
            <p>数量来自服务器实时统计。选择有数据的类型后再创建导出任务。</p>
          </div>
        </div>
        {availability.status === "ready" && availability.data ? (
          <div className="export-availability-grid">
            {(Object.keys(TYPE_LABELS) as ExportType[]).map((type) => {
              const count = availability.data?.[type] ?? 0;
              const allowed = allowedTypes.includes(type);
              return (
                <Button
                  key={type}
                  className={`export-availability-item${exportType === type ? " is-selected" : ""}`}
                  appearance="subtle"
                  disabled={!allowed || count === 0}
                  aria-pressed={exportType === type}
                  onClick={() => setExportType(type)}
                >
                  <span>{TYPE_LABELS[type]}</span>
                  <strong>{count}</strong>
                  <small>{count > 0 ? "条数据可导出" : "当前暂无数据"}</small>
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
      <section className="content-panel filter-panel" aria-label="创建导出">
        <Select
          aria-label="导出数据类型"
          value={exportType}
          onChange={(_, data) => setExportType(data.value as ExportType)}
        >
          {allowedTypes.map((type) => (
            <option
              key={type}
              value={type}
              disabled={(availability.data?.[type] ?? 0) === 0}
            >
              {TYPE_LABELS[type]}
              {(availability.data?.[type] ?? 0) === 0 ? "（无数据）" : ""}
            </option>
          ))}
        </Select>
        <Checkbox
          label="包含未脱敏联系方式"
          checked={includeSensitive}
          disabled={!isAdmin}
          onChange={(_, data) => setIncludeSensitive(data.checked === true)}
        />
        <Button
          appearance="primary"
          icon={<DocumentAdd24Regular />}
          disabled={Boolean(pendingAction) || (availability.data?.[exportType] ?? 0) === 0}
          onClick={() => void createExport()}
        >
          {pendingAction === "create"
            ? "正在创建"
            : (availability.data?.[exportType] ?? 0) === 0
              ? "当前类型无数据"
              : "创建导出"}
        </Button>
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
                          {pendingAction === item.id ? "下载中" : "下载"}
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

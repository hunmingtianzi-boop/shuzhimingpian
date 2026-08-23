import {
  Button,
  DrawerBody,
  DrawerHeader,
  DrawerHeaderTitle,
  Field,
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
  ArrowRight24Regular,
  Dismiss24Regular,
  Eye24Regular,
  ShieldCheckmark24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { ApiError } from "../api/client";
import type { PrivacyRequest, PrivacyRequestStatus } from "../api/types";
import { workflowApi } from "../api/workflowApi";
import { OperationFeedback } from "../components/OperationFeedback";
import { PageHeader } from "../components/PageHeader";
import { PaginationBar } from "../components/PaginationBar";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { APP_PATHS, navigate } from "../routing";
import { formatTimestamp } from "../utils/format";

const PAGE_SIZE = 20;

const requestTypeLabels: Record<string, string> = {
  access: "访问个人数据",
  correction: "更正个人数据",
  deletion: "删除个人数据",
  withdraw_consent: "撤回同意",
};

function PrivacyDrawer({
  request,
  onClose,
  onChanged,
}: {
  request: PrivacyRequest;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [current, setCurrent] = useState(request);
  const [status, setStatus] = useState<PrivacyRequestStatus>(request.status as PrivacyRequestStatus);
  const [verificationMethod, setVerificationMethod] = useState(request.verificationMethod || "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();

  const save = async () => {
    if (pending) return;
    setPending(true);
    setError(undefined);
    setNotice(undefined);
    try {
      const updated = await workflowApi.updatePrivacyRequest(current.id, {
        status,
        verificationMethod,
      });
      setCurrent(updated);
      setStatus(updated.status as PrivacyRequestStatus);
      setVerificationMethod(updated.verificationMethod || verificationMethod);
      setNotice("隐私请求处理状态已保存，审计证据保留在服务端。");
      onChanged();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError("处理隐私请求时发生未知错误。", {
              code: "UNKNOWN_ERROR",
            }),
      );
    } finally {
      setPending(false);
    }
  };

  return (
    <OverlayDrawer position="end" size="medium" open onOpenChange={(_, data) => !data.open && onClose()}>
      <DrawerHeader>
        <DrawerHeaderTitle
          action={
            <Button appearance="subtle" icon={<Dismiss24Regular />} aria-label="关闭隐私请求" onClick={onClose} />
          }
        >
          隐私请求处理
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody>
        <div className="drawer-command-bar"><StatusBadge status={current.status} /><code>{current.id}</code></div>
        <OperationFeedback notice={notice} error={error} onRetry={() => void save()} />
        <div className="drawer-section-stack">
          <section className="drawer-section">
            <h3>请求信息</h3>
            <dl className="detail-grid">
              <div><dt>请求类型</dt><dd>{requestTypeLabels[current.requestType] || current.requestType}</dd></div>
              <div><dt>访客 ID</dt><dd><code>{current.visitorId}</code></dd></div>
              <div><dt>创建时间</dt><dd>{formatTimestamp(current.createdAt)}</dd></div>
              <div><dt>完成时间</dt><dd>{formatTimestamp(current.completedAt)}</dd></div>
            </dl>
          </section>
          <section className="drawer-section">
            <h3>处理结果</h3>
            <div className="form-grid">
              <Field label="处理状态">
                <Select value={status} onChange={(_, data) => setStatus(data.value as PrivacyRequestStatus)}>
                  <option value="pending">待处理</option>
                  <option value="verified">已核验</option>
                  <option value="in_progress">处理中</option>
                  <option value="completed">已完成</option>
                  <option value="rejected">已拒绝</option>
                </Select>
              </Field>
              <Field label="身份核验方式" hint="例如：手机验证、邮箱回复、人工核对。">
                <Input value={verificationMethod} onChange={(_, data) => setVerificationMethod(data.value)} />
              </Field>
            </div>
            <div className="drawer-form-actions">
              <Button appearance="primary" icon={<ShieldCheckmark24Regular />} disabled={pending} onClick={() => void save()}>
                {pending ? "正在保存" : "保存处理结果"}
              </Button>
            </div>
          </section>
          {Object.keys(current.evidence).length > 0 && (
            <section className="drawer-section">
              <h3>审计证据</h3>
              <pre className="evidence-block">{JSON.stringify(current.evidence, null, 2)}</pre>
            </section>
          )}
        </div>
      </DrawerBody>
    </OverlayDrawer>
  );
}

export function PrivacyRequestsPage() {
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState<PrivacyRequestStatus | "">("pending");
  const [selected, setSelected] = useState<PrivacyRequest>();
  const resource = useResource(
    () => workflowApi.listPrivacyRequests({ limit: PAGE_SIZE, offset, status: status || undefined }),
    `${offset}:${status}`,
  );

  return (
    <main className="page-stack">
      <PageHeader
        title="隐私请求"
        description="这里处理具体隐私权利请求；长期访客画像授权与政策版本已拆到“数据与隐私”设置。"
        actions={
          <>
            <Button
              appearance="secondary"
              icon={<ArrowRight24Regular />}
              onClick={() => navigate(APP_PATHS.privacySettings)}
            >
              数据与隐私
            </Button>
            <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>刷新</Button>
          </>
        }
      />
      <section className="content-panel filter-panel" aria-label="隐私请求筛选">
        <Select
          aria-label="隐私请求状态"
          value={status}
          onChange={(_, data) => {
            setOffset(0);
            setStatus(data.value as PrivacyRequestStatus | "");
          }}
        >
          <option value="">全部状态</option>
          <option value="pending">待处理</option>
          <option value="verified">已核验</option>
          <option value="in_progress">处理中</option>
          <option value="completed">已完成</option>
          <option value="rejected">已拒绝</option>
        </Select>
      </section>
      <section className="content-panel data-panel">
        {resource.status === "ready" && resource.data ? (
          resource.data.items.length === 0 ? (
            <ResourceState status="empty" title="当前筛选下没有隐私请求" description="访客提交隐私权利请求后会显示在这里。" />
          ) : (
            <>
              <div className="table-scroll">
                <Table aria-label="隐私请求列表">
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>请求</TableHeaderCell>
                      <TableHeaderCell>状态</TableHeaderCell>
                      <TableHeaderCell>核验方式</TableHeaderCell>
                      <TableHeaderCell>创建时间</TableHeaderCell>
                      <TableHeaderCell />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resource.data.items.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell><div className="entity-title-cell compact-cell"><strong>{requestTypeLabels[item.requestType] || item.requestType}</strong><code>{item.visitorId}</code></div></TableCell>
                        <TableCell><StatusBadge status={item.status} /></TableCell>
                        <TableCell>{item.verificationMethod || "待核验"}</TableCell>
                        <TableCell className="updated-column">{formatTimestamp(item.createdAt)}</TableCell>
                        <TableCell className="actions-column"><Button appearance="subtle" size="small" icon={<Eye24Regular />} onClick={() => setSelected(item)}>处理</Button></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <PaginationBar total={resource.data.total} limit={resource.data.limit} offset={resource.data.offset} onOffsetChange={setOffset} />
            </>
          )
        ) : (
          <ResourceState status={resource.status === "ready" ? "empty" : resource.status} description={resource.error?.message} errorCode={resource.error?.code} requestId={resource.error?.requestId} onRetry={resource.status === "error" ? resource.reload : undefined} />
        )}
      </section>
      {selected && <PrivacyDrawer key={`${selected.id}:${selected.updatedAt}`} request={selected} onClose={() => setSelected(undefined)} onChanged={resource.reload} />}
    </main>
  );
}

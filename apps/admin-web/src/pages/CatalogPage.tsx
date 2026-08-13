import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  MessageBar,
  MessageBarBody,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import {
  Add24Regular,
  Archive24Regular,
  Delete24Regular,
  Edit24Regular,
  History24Regular,
  Send24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import {
  scheduledPublicationsApi,
  type ScheduledPublication,
  type ScheduledPublicationTargetType,
} from "../api/scheduledPublicationsApi";
import type { CaseStudy, Product, PublicationImpact, PublicationRevision } from "../api/types";
import { ActionConfirmDialog } from "../components/ActionConfirmDialog";
import { CaseStudyEditor, ProductEditor } from "../components/CatalogEditor";
import { ContentDistributionControl } from "../components/ContentDistributionControl";
import { ImportWorkbenchButton } from "../components/ImportWorkbenchButton";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import {
  ScheduledPublicationActions,
  ScheduledPublicationStatus,
} from "../components/ScheduledPublicationActions";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

type CatalogKind = "product" | "case";
type CatalogRecord = Product | CaseStudy;
type CatalogAction = "publish" | "archive" | "delete";

type PendingAction = {
  type: CatalogAction;
  target: CatalogRecord;
};

const contentConfig = {
  product: {
    pageTitle: "产品管理",
    description: "维护公开产品、服务边界和排序。发布与归档均受版本冲突保护。",
    createLabel: "新建产品",
    emptyTitle: "尚未创建产品",
    emptyDescription: "创建第一项产品后，可在这里编辑、发布或归档。",
    tableLabel: "产品列表",
  },
  case: {
    pageTitle: "案例管理",
    description: "维护项目背景、解决方案和成果。只有公开且已发布的案例会对访客展示。",
    createLabel: "新建案例",
    emptyTitle: "尚未创建案例",
    emptyDescription: "创建第一项案例后，可在这里编辑、发布或归档。",
    tableLabel: "案例列表",
  },
} as const;

function recordTitle(record: CatalogRecord): string {
  return "name" in record ? record.name : record.title;
}

function recordContext(record: CatalogRecord): string {
  if ("name" in record) {
    return [record.category, record.summary].filter(Boolean).join(" | ");
  }
  return [record.industry, record.clientDisplayName].filter(Boolean).join(" | ");
}

function actionCopy(action?: PendingAction) {
  if (!action) {
    return {
      title: "确认操作",
      description: "请确认是否继续。",
      confirmLabel: "确认",
      pendingLabel: "正在处理",
      destructive: false,
    };
  }
  const label = "name" in action.target ? "产品" : "案例";
  if (action.type === "publish") {
    return {
      title: `确认发布${label}`,
      description: `发布后，符合公开范围的${label}会立即进入访客可见状态。`,
      confirmLabel: "确认发布",
      pendingLabel: "正在发布",
      destructive: false,
    };
  }
  if (action.type === "archive") {
    return {
      title: `确认归档${label}`,
      description: `归档后，该${label}会立即从公开页面消失，但仍保留历史记录。`,
      confirmLabel: "确认归档",
      pendingLabel: "正在归档",
      destructive: true,
    };
  }
  return {
    title: `确认删除${label}`,
    description: `删除后，该${label}会被软删除并从管理列表及公开页面消失。`,
    confirmLabel: "确认删除",
    pendingLabel: "正在删除",
    destructive: true,
  };
}

export function CatalogPage({ kind }: { kind: CatalogKind }) {
  const config = contentConfig[kind];
  const scheduleTargetType: ScheduledPublicationTargetType =
    kind === "product" ? "product" : "case_study";
  const resource = useResource<CatalogRecord[]>(() =>
    kind === "product" ? adminApi.listProducts() : adminApi.listCaseStudies(),
  );
  const schedules = useResource<ScheduledPublication[]>(() =>
    scheduledPublicationsApi.list(scheduleTargetType),
  );
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<CatalogRecord>();
  const [action, setAction] = useState<PendingAction>();
  const [mutating, setMutating] = useState(false);
  const [actionError, setActionError] = useState<ApiError>();
  const [publicationImpact, setPublicationImpact] = useState<PublicationImpact>();
  const [historyTarget, setHistoryTarget] = useState<CatalogRecord>();
  const [revisions, setRevisions] = useState<PublicationRevision[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [rollbackRevision, setRollbackRevision] = useState<PublicationRevision>();
  const [rollbackImpact, setRollbackImpact] = useState<PublicationImpact>();
  const [rollbackError, setRollbackError] = useState<ApiError>();
  const [rollingBack, setRollingBack] = useState(false);
  const [notice, setNotice] = useState<string>();

  const openCreate = () => {
    setEditing(undefined);
    setEditorOpen(true);
    setNotice(undefined);
  };

  const openEdit = (record: CatalogRecord) => {
    setEditing(record);
    setEditorOpen(true);
    setNotice(undefined);
  };

  const saved = () => {
    setEditorOpen(false);
    setNotice(`${kind === "product" ? "产品" : "案例"}已由服务端确认保存。`);
    resource.reload();
  };

  const requestAction = (type: CatalogAction, target: CatalogRecord) => {
    setAction({ type, target });
    setActionError(undefined);
    setPublicationImpact(undefined);
    setNotice(undefined);
    if (type === "publish") {
      const preview = kind === "product"
        ? adminApi.previewProductPublication(target.id)
        : adminApi.previewCasePublication(target.id);
      void preview.then(setPublicationImpact).catch((caught) => {
        setActionError(caught instanceof ApiError ? caught : new ApiError("无法核对关联名片。", { code: "UNKNOWN_ERROR" }));
      });
    }
  };

  const executeAction = async () => {
    if (!action || mutating || (action.type === "publish" && !publicationImpact)) return;
    setMutating(true);
    setActionError(undefined);
    try {
      const { target, type } = action;
      if (kind === "product") {
        if (type === "publish") {
          await adminApi.publishProductConfirmed(target.id, target.version, publicationImpact!.impactDigest);
        } else if (type === "archive") {
          await adminApi.archiveProduct(target.id, target.version);
        } else {
          await adminApi.deleteProduct(target.id, target.version);
        }
      } else if (type === "publish") {
        await adminApi.publishCaseStudyConfirmed(target.id, target.version, publicationImpact!.impactDigest);
      } else if (type === "archive") {
        await adminApi.archiveCaseStudy(target.id, target.version);
      } else {
        await adminApi.deleteCaseStudy(target.id, target.version);
      }

      const label = kind === "product" ? "产品" : "案例";
      const verb = type === "publish" ? "发布" : type === "archive" ? "归档" : "删除";
      setNotice(`${label}已由服务端确认${verb}。`);
      setAction(undefined);
      resource.reload();
    } catch (caught) {
      setActionError(
        caught instanceof ApiError
          ? caught
          : new ApiError("执行目录操作时发生未知错误。", {
              code: "UNKNOWN_ERROR",
            }),
      );
    } finally {
      setMutating(false);
    }
  };

  const openHistory = async (target: CatalogRecord) => {
    setHistoryTarget(target);
    setRevisions([]);
    setHistoryLoading(true);
    try {
      setRevisions(kind === "product"
        ? await adminApi.listProductPublicationRevisions(target.id)
        : await adminApi.listCasePublicationRevisions(target.id));
    } catch (caught) {
      setRollbackError(caught instanceof ApiError ? caught : new ApiError("发布历史加载失败。", { code: "UNKNOWN_ERROR" }));
    } finally {
      setHistoryLoading(false);
    }
  };

  const requestRollback = async (revision: PublicationRevision) => {
    if (!historyTarget) return;
    setRollbackRevision(revision);
    setRollbackImpact(undefined);
    setRollbackError(undefined);
    try {
      setRollbackImpact(kind === "product"
        ? await adminApi.previewProductPublication(historyTarget.id)
        : await adminApi.previewCasePublication(historyTarget.id));
    } catch (caught) {
      setRollbackError(caught instanceof ApiError ? caught : new ApiError("无法核对回退影响。", { code: "UNKNOWN_ERROR" }));
    }
  };

  const executeRollback = async () => {
    if (!historyTarget || !rollbackRevision || !rollbackImpact || rollingBack) return;
    setRollingBack(true);
    setRollbackError(undefined);
    try {
      if (kind === "product") {
        await adminApi.rollbackProduct(historyTarget.id, historyTarget.version, rollbackRevision.id, rollbackImpact.impactDigest);
      } else {
        await adminApi.rollbackCaseStudy(historyTarget.id, historyTarget.version, rollbackRevision.id, rollbackImpact.impactDigest);
      }
      setNotice(`已回退到发布版本 ${rollbackRevision.revisionNumber}，并同步更新关联名片。`);
      setRollbackRevision(undefined);
      setHistoryTarget(undefined);
      resource.reload();
    } catch (caught) {
      setRollbackError(caught instanceof ApiError ? caught : new ApiError("回退失败。", { code: "UNKNOWN_ERROR" }));
    } finally {
      setRollingBack(false);
    }
  };

  const copy = actionCopy(action);
  const activeSchedule = (targetId: string) =>
    schedules.data?.find(
      (item) =>
        item.resourceId === targetId &&
        (["pending", "processing", "failed"] as string[]).includes(item.status),
    );
  const reloadAfterSchedule = (message: string) => {
    setNotice(message);
    schedules.reload();
  };

  return (
    <main className="page-stack">
      <PageHeader
        title={config.pageTitle}
        description={config.description}
        actions={
          resource.status === "permission" ? undefined : <>
            <ImportWorkbenchButton />
            <Button appearance="primary" icon={<Add24Regular />} onClick={openCreate}>{config.createLabel}</Button>
          </>
        }
      />

      {notice && (
        <MessageBar intent="success">
          <MessageBarBody>{notice}</MessageBarBody>
        </MessageBar>
      )}

      {schedules.status === "error" && (
        <MessageBar intent="error">
          <MessageBarBody>
            定时发布状态加载失败：{schedules.error?.message}
            <Button appearance="subtle" size="small" onClick={schedules.reload}>
              重试
            </Button>
          </MessageBarBody>
        </MessageBar>
      )}
      {schedules.status === "permission" && (
        <MessageBar intent="warning">
          <MessageBarBody>当前账号无权查看或管理定时发布任务。</MessageBarBody>
        </MessageBar>
      )}

      <section className="content-panel catalog-panel">
        {resource.status !== "ready" && (
          <ResourceState
            status={resource.status}
            title={resource.status === "empty" ? config.emptyTitle : undefined}
            description={
              resource.status === "empty"
                ? config.emptyDescription
                : resource.error?.message
            }
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
            emptyAction={
              <Button appearance="primary" icon={<Add24Regular />} onClick={openCreate}>
                {config.createLabel}
              </Button>
            }
          />
        )}

        {resource.status === "ready" && resource.data && (
          <div className="table-scroll">
            <Table aria-label={config.tableLabel} size="small">
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>名称与范围</TableHeaderCell>
                  <TableHeaderCell className="status-column">状态</TableHeaderCell>
                  <TableHeaderCell className="updated-column">更新时间</TableHeaderCell>
                  <TableHeaderCell className="catalog-actions-column">操作</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resource.data.map((record) => {
                  const schedule = activeSchedule(record.id);
                  return (
                  <TableRow key={record.id}>
                    <TableCell>
                      <div className="entity-title-cell">
                        <strong>{recordTitle(record) || "未命名内容"}</strong>
                        <span>{recordContext(record) || `链接标识：${record.slug}`}</span>
                      </div>
                    </TableCell>
                    <TableCell className="status-column">
                      <StatusBadge status={record.status} />
                      {record.hasUnpublishedChanges ? <span className="draft-change-note">有未发布修改</span> : null}
                      <ScheduledPublicationStatus publication={schedule} />
                    </TableCell>
                    <TableCell className="updated-column">
                      {formatTimestamp(record.updatedAt)}
                    </TableCell>
                    <TableCell className="catalog-actions-column">
                      <div className="row-actions catalog-row-actions">
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<Edit24Regular />}
                          onClick={() => openEdit(record)}
                        >
                          编辑
                        </Button>
                        <ContentDistributionControl
                          resourceType={kind === "product" ? "product" : "case_study"}
                          resourceId={record.id}
                          resourceLabel={recordTitle(record)}
                          sourceStatus={record.status}
                        />
                        {(record.status !== "published" || record.hasUnpublishedChanges) && !schedule && (
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<Send24Regular />}
                            onClick={() => requestAction("publish", record)}
                          >
                            发布
                          </Button>
                        )}
                        {record.publishedAt ? (
                          <Button appearance="subtle" size="small" icon={<History24Regular />} onClick={() => void openHistory(record)}>历史</Button>
                        ) : null}
                        {record.status !== "published" && (
                          <ScheduledPublicationActions
                            targetType={scheduleTargetType}
                            targetId={record.id}
                            targetVersion={record.version}
                            targetLabel={recordTitle(record) || "未命名内容"}
                            current={schedule}
                            disabled={schedules.status === "loading" || schedules.status === "permission"}
                            onChanged={reloadAfterSchedule}
                          />
                        )}
                        {record.status !== "archived" && (
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<Archive24Regular />}
                            onClick={() => requestAction("archive", record)}
                          >
                            归档
                          </Button>
                        )}
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<Delete24Regular />}
                          onClick={() => requestAction("delete", record)}
                        >
                          删除
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      {kind === "product" ? (
        <ProductEditor
          open={editorOpen}
          item={editing && "name" in editing ? editing : undefined}
          onClose={() => setEditorOpen(false)}
          onSaved={saved}
        />
      ) : (
        <CaseStudyEditor
          open={editorOpen}
          item={editing && "title" in editing ? editing : undefined}
          onClose={() => setEditorOpen(false)}
          onSaved={saved}
        />
      )}

      <ActionConfirmDialog
        key={action ? `${action.type}-${action.target.id}` : "catalog-action"}
        open={Boolean(action)}
        title={copy.title}
        description={copy.description}
        confirmLabel={copy.confirmLabel}
        pendingLabel={copy.pendingLabel}
        pending={mutating}
        error={actionError}
        destructive={copy.destructive}
        detail={
          action ? (
            <div className="publish-target">
              <strong>{recordTitle(action.target) || "未命名内容"}</strong>
              <span>当前版本：{action.target.version}</span>
              {action.type === "publish" ? (
                publicationImpact === undefined
                  ? <span>正在核对关联名片…</span>
                  : <div className="publication-impact-summary">
                      <strong>本次将更新 {publicationImpact.affectedCardCount} 张已发布名片</strong>
                      {publicationImpact.breakdown.filter((item) => item.cardCount > 0).map((item) => (
                        <span key={item.reason}>{item.label}：{item.cardCount} 张</span>
                      ))}
                      {publicationImpact.affectedCardCount === 0 && <span>当前没有已发布名片引用这条内容，发布只会更新内容库。</span>}
                    </div>
              ) : null}
            </div>
          ) : undefined
        }
        onCancel={() => {
          setAction(undefined);
          setActionError(undefined);
          setPublicationImpact(undefined);
        }}
        onConfirm={() => void executeAction()}
        onReload={() => {
          setAction(undefined);
          setActionError(undefined);
          setPublicationImpact(undefined);
          resource.reload();
        }}
      />

      <Dialog open={Boolean(historyTarget)} onOpenChange={(_, data) => { if (!data.open && !rollingBack) setHistoryTarget(undefined); }}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>发布历史</DialogTitle>
            <DialogContent>
              <p>{historyTarget ? recordTitle(historyTarget) : ""}</p>
              {historyLoading ? <p>正在加载历史版本…</p> : null}
              {!historyLoading && revisions.length === 0 ? <p>暂无可回退的发布版本。</p> : null}
              <div className="publication-history-list">
                {revisions.map((revision, index) => (
                  <div className="publication-history-row" key={revision.id}>
                    <div><strong>版本 {revision.revisionNumber}</strong><span>{formatTimestamp(revision.publishedAt)}</span></div>
                    <Button appearance="secondary" size="small" disabled={index === 0} onClick={() => void requestRollback(revision)}>{index === 0 ? "当前版本" : "回退到此版本"}</Button>
                  </div>
                ))}
              </div>
            </DialogContent>
            <DialogActions><Button appearance="secondary" onClick={() => setHistoryTarget(undefined)}>关闭</Button></DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      <ActionConfirmDialog
        open={Boolean(rollbackRevision)}
        title="确认回退发布版本"
        description="回退会生成一个新的发布版本，不会删除后续历史。"
        confirmLabel="确认回退并更新名片"
        pendingLabel="正在回退"
        pending={rollingBack}
        error={rollbackError}
        detail={rollbackRevision ? <div className="publish-target"><strong>版本 {rollbackRevision.revisionNumber}</strong><span>{rollbackImpact ? `将同步 ${rollbackImpact.affectedCardCount} 张已发布名片` : "正在核对关联名片…"}</span></div> : undefined}
        onCancel={() => { setRollbackRevision(undefined); setRollbackError(undefined); }}
        onConfirm={() => void executeRollback()}
      />
    </main>
  );
}

export function ProductsPage() {
  return <CatalogPage kind="product" />;
}

export function CaseStudiesPage() {
  return <CatalogPage kind="case" />;
}

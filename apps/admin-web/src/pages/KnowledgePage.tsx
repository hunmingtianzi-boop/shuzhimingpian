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
} from "../api/scheduledPublicationsApi";
import type { KnowledgeDocument, KnowledgeVersion, PublicationImpact } from "../api/types";
import { ActionConfirmDialog } from "../components/ActionConfirmDialog";
import { KnowledgeEditor } from "../components/KnowledgeEditor";
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

export function hasPublishableDraft(document: KnowledgeDocument): boolean {
  return document.latestVersion?.reviewStatus === "draft";
}

export function KnowledgePage() {
  const resource = useResource(() => adminApi.listKnowledgeDocuments());
  const schedules = useResource<ScheduledPublication[]>(() =>
    scheduledPublicationsApi.list("knowledge_document"),
  );
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<KnowledgeDocument>();
  const [publishTarget, setPublishTarget] = useState<KnowledgeDocument>();
  const [publishing, setPublishing] = useState(false);
  const [publishError, setPublishError] = useState<ApiError>();
  const [publicationImpact, setPublicationImpact] = useState<PublicationImpact>();
  const [publishVersionId, setPublishVersionId] = useState<string>();
  const [versionsTarget, setVersionsTarget] = useState<KnowledgeDocument>();
  const [versions, setVersions] = useState<KnowledgeVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeDocument>();
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();

  const openCreate = () => {
    setEditing(undefined);
    setEditorOpen(true);
    setNotice(undefined);
  };

  const openEdit = (document: KnowledgeDocument) => {
    setEditing(document);
    setEditorOpen(true);
    setNotice(undefined);
  };

  const saved = () => {
    setEditorOpen(false);
    setNotice(editing ? "知识草稿已由服务端确认更新。" : "知识草稿已由服务端确认创建。");
    resource.reload();
  };

  const publish = async () => {
    if (!publishTarget || publishing || !publicationImpact) return;
    setPublishing(true);
    setPublishError(undefined);
    try {
      await adminApi.publishKnowledgeDocument(
        publishTarget.id,
        publishVersionId,
        publicationImpact.impactDigest,
      );
      setNotice("发布请求已由服务端确认，索引状态请以后端结果为准。");
      setPublishTarget(undefined);
      setPublishVersionId(undefined);
      resource.reload();
    } catch (caught) {
      setPublishError(
        caught instanceof ApiError
          ? caught
          : new ApiError("发布知识内容时发生未知错误。", {
              code: "UNKNOWN_ERROR",
            }),
      );
    } finally {
      setPublishing(false);
    }
  };

  const requestPublish = async (document: KnowledgeDocument, versionId?: string) => {
    setPublishError(undefined);
    setPublishTarget(document);
    setPublishVersionId(versionId);
    setPublicationImpact(undefined);
    try {
      setPublicationImpact(await adminApi.previewKnowledgePublication(document.id));
    } catch (caught) {
      setPublishError(caught instanceof ApiError ? caught : new ApiError("无法核对关联名片。", { code: "UNKNOWN_ERROR" }));
    }
  };

  const openVersions = async (document: KnowledgeDocument) => {
    setVersionsTarget(document);
    setVersions([]);
    setVersionsLoading(true);
    try {
      setVersions(await adminApi.listKnowledgeVersions(document.id));
    } catch (caught) {
      setPublishError(caught instanceof ApiError ? caught : new ApiError("知识版本加载失败。", { code: "UNKNOWN_ERROR" }));
    } finally {
      setVersionsLoading(false);
    }
  };
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

  const requestDelete = (document: KnowledgeDocument) => {
    setDeleteTarget(document);
    setDeleteError(undefined);
    setNotice(undefined);
  };

  const remove = async () => {
    if (!deleteTarget || deleting || deleteTarget.version === undefined) return;
    setDeleting(true);
    setDeleteError(undefined);
    try {
      await adminApi.deleteKnowledgeDocument(deleteTarget.id, deleteTarget.version);
      setDeleteTarget(undefined);
      setNotice("知识内容已删除，AI 将不再检索该内容；历史导入批次仍保留用于追溯。");
      resource.reload();
      schedules.reload();
    } catch (caught) {
      setDeleteError(
        caught instanceof ApiError
          ? caught
          : new ApiError("删除知识内容时发生未知错误。", { code: "UNKNOWN_ERROR" }),
      );
    } finally {
      setDeleting(false);
    }
  };

  return (
    <main className="page-stack">
      <PageHeader
        title="知识 FAQ"
        description="维护 AI 问答使用的正式知识内容。草稿保存与发布均调用真实管理接口。"
        actions={
          resource.status === "permission" ? undefined : <>
            <ImportWorkbenchButton />
            <Button appearance="primary" icon={<Add24Regular />} onClick={openCreate}>新建 FAQ</Button>
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

      {deleteError && !deleteTarget ? (
        <MessageBar intent="error">
          <MessageBarBody>
            无法打开删除确认：{deleteError.message}
            {deleteError.requestId ? `（请求编号：${deleteError.requestId}）` : ""}
          </MessageBarBody>
        </MessageBar>
      ) : null}

      <section id="knowledge-documents" className="content-panel knowledge-panel">
        {resource.status !== "ready" && (
          <ResourceState
            status={resource.status}
            title={resource.status === "empty" ? "知识库中暂无 FAQ" : undefined}
            description={
              resource.status === "empty"
                ? "创建第一条 FAQ 后，服务端返回的内容会显示在这里。"
                : resource.error?.message
            }
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
            emptyAction={
              <Button appearance="primary" icon={<Add24Regular />} onClick={openCreate}>
                新建 FAQ
              </Button>
            }
          />
        )}

        {resource.status === "ready" && resource.data && (
          <div className="table-scroll">
            <Table aria-label="知识 FAQ 列表" size="small">
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>标题与问题</TableHeaderCell>
                  <TableHeaderCell className="status-column">状态</TableHeaderCell>
                  <TableHeaderCell className="updated-column">更新时间</TableHeaderCell>
                  <TableHeaderCell className="actions-column">操作</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resource.data.map((document) => {
                  const schedule = activeSchedule(document.id);
                  const targetVersion = document.version ?? document.latestVersion?.versionNumber;
                  return (
                  <TableRow key={document.id}>
                    <TableCell>
                      <div className="knowledge-title-cell">
                        <strong>{document.title || "未命名知识"}</strong>
                        <span>
                          {document.latestVersion
                            ? `最新版本：${document.latestVersion.versionNumber}，索引切片：${document.latestVersion.indexedChunkCount}/${document.latestVersion.chunkCount}`
                            : "尚无知识草稿版本"}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="status-column">
                      <StatusBadge status={document.status} />
                      <ScheduledPublicationStatus publication={schedule} />
                    </TableCell>
                    <TableCell className="updated-column">
                      {formatTimestamp(document.updatedAt)}
                    </TableCell>
                    <TableCell className="actions-column">
                      <div className="row-actions">
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<Edit24Regular />}
                          onClick={() => openEdit(document)}
                        >
                          编辑
                        </Button>
                        {hasPublishableDraft(document) && !schedule && (
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<Send24Regular />}
                            onClick={() => {
                              void requestPublish(document);
                            }}
                          >
                            发布
                          </Button>
                        )}
                        {document.latestVersion?.publishedAt || document.status === "published" ? (
                          <Button appearance="subtle" size="small" icon={<History24Regular />} onClick={() => void openVersions(document)}>历史</Button>
                        ) : null}
                        {hasPublishableDraft(document) && targetVersion !== undefined && (
                          <ScheduledPublicationActions
                            targetType="knowledge_document"
                            targetId={document.id}
                            targetVersion={targetVersion}
                            targetLabel={document.title || "未命名知识"}
                            knowledgeVersionId={document.latestVersion?.id}
                            current={schedule}
                            disabled={schedules.status === "loading" || schedules.status === "permission"}
                            onChanged={reloadAfterSchedule}
                          />
                        )}
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<Delete24Regular />}
                          disabled={document.version === undefined}
                          onClick={() => requestDelete(document)}
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

      <KnowledgeEditor
        open={editorOpen}
        document={editing}
        onClose={() => {
          setEditorOpen(false);
          resource.reload();
        }}
        onSaved={saved}
      />

      <Dialog
        open={Boolean(publishTarget)}
        onOpenChange={(_, data) => {
          if (!data.open && !publishing) {
            setPublishTarget(undefined);
            setPublishVersionId(undefined);
          }
        }}
      >
        <DialogSurface>
          <DialogBody>
            <DialogTitle>{publishVersionId ? "确认回退知识 FAQ" : "确认发布知识 FAQ"}</DialogTitle>
            <DialogContent>
              <p>
                {publishVersionId
                  ? "回退会把选中的历史版本重新发布为当前版本，完整历史不会被删除。"
                  : "发布后，服务端会进入审核与索引流程。只有服务端确认成功后，状态才会更新。"}
              </p>
              {publishTarget && (
                <div className="publish-target">
                  <strong>{publishTarget.title || "未命名知识"}</strong>
                  <span>
                    {publishTarget.latestVersion
                      ? `准备发布版本 ${publishTarget.latestVersion.versionNumber}`
                      : "服务端将选择可发布的最新草稿版本"}
                  </span>
                  {publicationImpact === undefined ? (
                    <span>正在核对关联名片…</span>
                  ) : (
                    <div className="publication-impact-summary">
                      <strong>本次将更新 {publicationImpact.affectedCardCount} 张已发布名片</strong>
                      {publicationImpact.breakdown.filter((item) => item.cardCount > 0).map((item) => (
                        <span key={item.reason}>{item.label}：{item.cardCount} 张</span>
                      ))}
                      {publicationImpact.affectedCardCount === 0 && (
                        <span>当前没有已发布名片引用这条 FAQ，发布只会更新知识库。</span>
                      )}
                      <span>确认后将一键同步；需要时可从发布历史回退。</span>
                    </div>
                  )}
                </div>
              )}
              {publishError && (
                <MessageBar intent="error">
                  <MessageBarBody>
                    <strong>发布失败</strong>
                    <div>{publishError.message}</div>
                    <div className="error-reference">
                      <span>错误代码：{publishError.code}</span>
                      {publishError.requestId && (
                        <span>请求编号：{publishError.requestId}</span>
                      )}
                    </div>
                  </MessageBarBody>
                </MessageBar>
              )}
            </DialogContent>
            <DialogActions>
              <Button
                appearance="secondary"
                onClick={() => { setPublishTarget(undefined); setPublishVersionId(undefined); }}
                disabled={publishing}
              >
                取消
              </Button>
              <Button
                appearance="primary"
                icon={<Send24Regular />}
                onClick={() => void publish()}
                disabled={publishing}
              >
                {publishing ? "正在处理" : publishVersionId ? "确认回退并更新名片" : "确认发布"}
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      <Dialog open={Boolean(versionsTarget)} onOpenChange={(_, data) => { if (!data.open && !publishing) setVersionsTarget(undefined); }}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>知识发布历史</DialogTitle>
            <DialogContent>
              <p>{versionsTarget?.title}</p>
              {versionsLoading ? <p>正在加载历史版本…</p> : null}
              <div className="publication-history-list">
                {versions.map((version) => (
                  <div className="publication-history-row" key={version.id}>
                    <div><strong>版本 {version.versionNumber}</strong><span>{formatTimestamp(version.publishedAt || version.createdAt)}</span></div>
                    <Button appearance="secondary" size="small" disabled={!version.publishedAt || version.id === versionsTarget?.latestVersion?.id} onClick={() => { if (versionsTarget) { setVersionsTarget(undefined); void requestPublish(versionsTarget, version.id); } }}>{version.id === versionsTarget?.latestVersion?.id ? "当前版本" : version.publishedAt ? "回退到此版本" : "未发布草稿"}</Button>
                  </div>
                ))}
              </div>
            </DialogContent>
            <DialogActions><Button appearance="secondary" onClick={() => setVersionsTarget(undefined)}>关闭</Button></DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      <ActionConfirmDialog
        open={Boolean(deleteTarget)}
        title="删除知识内容"
        description="删除后，这条内容会立即退出知识列表和 AI 检索范围；相关待发布任务也会取消。历史导入记录会保留，便于追溯。"
        confirmLabel="确认删除"
        pendingLabel="正在删除"
        pending={deleting}
        error={deleteError}
        destructive
        detail={deleteTarget ? (
          <div className="publish-target">
            <strong>{deleteTarget.title || "未命名知识"}</strong>
            <span>当前版本：{deleteTarget.version ?? "未知"}</span>
          </div>
        ) : undefined}
        onCancel={() => {
          setDeleteTarget(undefined);
          setDeleteError(undefined);
        }}
        onConfirm={() => void remove()}
        onReload={() => {
          setDeleteTarget(undefined);
          setDeleteError(undefined);
          resource.reload();
        }}
      />
    </main>
  );
}

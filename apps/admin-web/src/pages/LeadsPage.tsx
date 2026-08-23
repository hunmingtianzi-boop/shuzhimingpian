import {
  Badge,
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
  Textarea,
} from "@fluentui/react-components";
import {
  ArrowClockwise24Regular,
  Dismiss24Regular,
  Eye24Regular,
  Send24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { ApiError } from "../api/client";
import type {
  LeadDetail,
  LeadFollowupInput,
  LeadPriority,
  LeadStatus,
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

function asApiError(error: unknown, message: string): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError(message, { code: "UNKNOWN_ERROR" });
}

function ContactDetails({ lead }: { lead: LeadDetail }) {
  return (
    <dl className="detail-grid two-columns">
      <div>
        <dt>姓名</dt>
        <dd>{lead.name || "未提供"}</dd>
      </div>
      <div>
        <dt>公司</dt>
        <dd>{lead.companyName || "未提供"}</dd>
      </div>
      <div>
        <dt>手机</dt>
        <dd>{lead.mobile || "未提供"}</dd>
      </div>
      <div>
        <dt>邮箱</dt>
        <dd>{lead.email || "未提供"}</dd>
      </div>
      <div>
        <dt>微信</dt>
        <dd>{lead.wechat || "未提供"}</dd>
      </div>
      <div>
        <dt>归属名片</dt>
        <dd>{lead.cardDisplayName}</dd>
      </div>
    </dl>
  );
}

function LeadEditor({
  lead,
  canWrite,
  reload,
  onChanged,
}: {
  lead: LeadDetail;
  canWrite: boolean;
  reload: () => void;
  onChanged: () => void;
}) {
  const [status, setStatus] = useState<LeadStatus>(lead.status as LeadStatus);
  const [priority, setPriority] = useState<LeadPriority>(lead.priority as LeadPriority);
  const [followupType, setFollowupType] = useState<LeadFollowupInput["followupType"]>("note");
  const [content, setContent] = useState("");
  const [nextAt, setNextAt] = useState("");
  const [pendingAction, setPendingAction] = useState<"status" | "followup">();
  const [lastAction, setLastAction] = useState<"status" | "followup">("status");
  const [error, setError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();

  const updateStatus = async () => {
    if (pendingAction) return;
    setPendingAction("status");
    setLastAction("status");
    setError(undefined);
    setNotice(undefined);
    try {
      await workflowApi.updateLead(lead.id, lead.version, { status, priority });
      setNotice("线索状态和优先级已保存。");
      reload();
      onChanged();
    } catch (caught) {
      setError(asApiError(caught, "保存线索状态时发生未知错误。"));
    } finally {
      setPendingAction(undefined);
    }
  };

  const createFollowup = async () => {
    if (pendingAction || !content.trim()) return;
    setPendingAction("followup");
    setLastAction("followup");
    setError(undefined);
    setNotice(undefined);
    try {
      await workflowApi.createLeadFollowup(lead.id, {
        followupType,
        content,
        nextAt: nextAt ? new Date(nextAt).toISOString() : undefined,
      });
      setContent("");
      setNextAt("");
      setNotice("跟进记录已添加。");
      reload();
      onChanged();
    } catch (caught) {
      setError(asApiError(caught, "添加跟进记录时发生未知错误。"));
    } finally {
      setPendingAction(undefined);
    }
  };

  return (
    <div className="drawer-section-stack">
      <OperationFeedback
        notice={notice}
        error={error}
        onRetry={lastAction === "followup" ? () => void createFollowup() : () => void updateStatus()}
      />
      <section className="drawer-section">
        <h3>客户信息</h3>
        <ContactDetails lead={lead} />
        <div className="lead-demand">
          <strong>客户需求</strong>
          <p>{lead.demand || "未提供具体需求。"}</p>
        </div>
        {lead.interestTags.length > 0 && (
          <div className="tag-row">
            {lead.interestTags.map((tag) => <Badge key={tag} appearance="outline">{tag}</Badge>)}
          </div>
        )}
      </section>

      <section className="drawer-section">
        <h3>线索处理</h3>
        <div className="form-grid two-columns">
          <Field label="状态">
            <Select
              value={status}
              disabled={!canWrite}
              onChange={(_, data) => setStatus(data.value as LeadStatus)}
            >
              <option value="new">新线索</option>
              <option value="viewed">已查看</option>
              <option value="following">跟进中</option>
              <option value="won">已成交</option>
              <option value="lost">已失败</option>
              <option value="invalid">无效</option>
            </Select>
          </Field>
          <Field label="优先级">
            <Select
              value={priority}
              disabled={!canWrite}
              onChange={(_, data) => setPriority(data.value as LeadPriority)}
            >
              <option value="low">低</option>
              <option value="medium">中</option>
              <option value="high">高</option>
            </Select>
          </Field>
        </div>
        {canWrite && (
          <div className="drawer-form-actions">
            <Button
              appearance="primary"
              disabled={Boolean(pendingAction)}
              onClick={() => void updateStatus()}
            >
              {pendingAction === "status" ? "正在保存" : "保存状态"}
            </Button>
          </div>
        )}
      </section>

      {canWrite && (
        <section className="drawer-section">
          <h3>添加跟进</h3>
          <div className="form-grid two-columns">
            <Field label="跟进方式">
              <Select
                value={followupType}
                onChange={(_, data) =>
                  setFollowupType(data.value as LeadFollowupInput["followupType"])
                }
              >
                <option value="note">备注</option>
                <option value="call">电话</option>
                <option value="message">消息</option>
                <option value="meeting">会议</option>
                <option value="status_change">状态变更</option>
              </Select>
            </Field>
            <Field label="下次跟进时间">
              <Input type="datetime-local" value={nextAt} onChange={(_, data) => setNextAt(data.value)} />
            </Field>
          </div>
          <Field label="跟进内容" required>
            <Textarea
              resize="vertical"
              value={content}
              onChange={(_, data) => setContent(data.value)}
              placeholder="记录客户反馈、结论和下一步。"
            />
          </Field>
          <div className="drawer-form-actions">
            <Button
              appearance="primary"
              icon={<Send24Regular />}
              disabled={Boolean(pendingAction) || !content.trim()}
              onClick={() => void createFollowup()}
            >
              {pendingAction === "followup" ? "正在添加" : "添加跟进"}
            </Button>
          </div>
        </section>
      )}

      <section className="drawer-section">
        <h3>跟进记录</h3>
        {lead.followups.length === 0 ? (
          <ResourceState compact status="empty" title="尚无跟进记录" />
        ) : (
          <div className="followup-list">
            {lead.followups.map((followup) => (
              <article key={followup.id}>
                <header>
                  <strong>{followup.followupType}</strong>
                  <span>{formatTimestamp(followup.createdAt)}</span>
                </header>
                <p>{followup.content}</p>
                {followup.nextAt && <span>下次跟进：{formatTimestamp(followup.nextAt)}</span>}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function LeadDrawer({
  id,
  onClose,
  onChanged,
}: {
  id: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const auth = useAuth();
  const canWrite = hasPermission(auth.user, "leads.write", { allowCardOwner: true });
  const resource = useResource(() => workflowApi.getLead(id), id);
  return (
    <OverlayDrawer position="end" size="large" open onOpenChange={(_, data) => !data.open && onClose()}>
      <DrawerHeader>
        <DrawerHeaderTitle
          action={
            <Button appearance="subtle" icon={<Dismiss24Regular />} aria-label="关闭线索详情" onClick={onClose} />
          }
        >
          线索详情
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody>
        <div className="drawer-command-bar"><code>{id}</code></div>
        {resource.status === "ready" && resource.data ? (
          <LeadEditor
            key={`${resource.data.id}:${resource.data.version}:${resource.data.followups.length}`}
            lead={resource.data}
            canWrite={canWrite}
            reload={resource.reload}
            onChanged={onChanged}
          />
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

export function LeadsPage({
  initialLeadId,
}: {
  initialLeadId?: string;
} = {}) {
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState<LeadStatus | "">("");
  const [selectedId, setSelectedId] = useState<string | undefined>(initialLeadId);
  const resource = useResource(
    () => workflowApi.listLeads({ limit: PAGE_SIZE, offset, status: status || undefined }),
    `${offset}:${status}`,
  );

  return (
    <main className="page-stack">
      <PageHeader
        title="销售线索"
        description="查看客户联系方式和需求，设置优先级、更新阶段并保留跟进记录。"
        actions={
          <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>刷新</Button>
        }
      />
      <section className="content-panel filter-panel" aria-label="线索筛选">
        <Select
          aria-label="线索状态"
          value={status}
          onChange={(_, data) => {
            setOffset(0);
            setStatus(data.value as LeadStatus | "");
          }}
        >
          <option value="">全部状态</option>
          <option value="new">新线索</option>
          <option value="viewed">已查看</option>
          <option value="following">跟进中</option>
          <option value="won">已成交</option>
          <option value="lost">已失败</option>
          <option value="invalid">无效</option>
        </Select>
      </section>

      <section className="content-panel data-panel">
        {resource.status === "ready" && resource.data ? (
          resource.data.items.length === 0 ? (
            <ResourceState status="empty" title="没有匹配的线索" description="调整状态筛选，或等待访客提交联系信息。" />
          ) : (
            <>
              <div className="table-scroll">
                <Table aria-label="销售线索列表">
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>客户</TableHeaderCell>
                      <TableHeaderCell>状态</TableHeaderCell>
                      <TableHeaderCell>优先级</TableHeaderCell>
                      <TableHeaderCell>兴趣标签</TableHeaderCell>
                      <TableHeaderCell>更新时间</TableHeaderCell>
                      <TableHeaderCell />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resource.data.items.map((lead) => (
                      <TableRow key={lead.id}>
                        <TableCell>
                          <div className="entity-title-cell compact-cell">
                            <strong>{lead.maskedName}</strong>
                            <span>{[lead.maskedContact, lead.companyName].filter(Boolean).join(" | ")}</span>
                          </div>
                        </TableCell>
                        <TableCell><StatusBadge status={lead.status} /></TableCell>
                        <TableCell>{lead.priority === "high" ? "高" : lead.priority === "low" ? "低" : "中"}</TableCell>
                        <TableCell>{lead.interestTags.slice(0, 3).join("、") || "未标记"}</TableCell>
                        <TableCell className="updated-column">{formatTimestamp(lead.updatedAt)}</TableCell>
                        <TableCell className="actions-column">
                          <Button appearance="subtle" size="small" icon={<Eye24Regular />} onClick={() => setSelectedId(lead.id)}>详情</Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <PaginationBar total={resource.data.total} limit={resource.data.limit} offset={resource.data.offset} onOffsetChange={setOffset} />
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

      {selectedId && <LeadDrawer id={selectedId} onClose={() => setSelectedId(undefined)} onChanged={resource.reload} />}
    </main>
  );
}

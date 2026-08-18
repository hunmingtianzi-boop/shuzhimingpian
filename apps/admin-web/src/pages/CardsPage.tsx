import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  Field,
  Input,
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
  Copy24Regular,
  Edit24Regular,
  Open24Regular,
  QrCode24Regular,
  Send24Regular,
  Share24Regular,
  Settings24Regular,
  ToggleRight24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import { memberApi } from "../api/memberApi";
import type { EnterpriseTemplate, ManagedCard, ManagedCardInput } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ActionConfirmDialog } from "../components/ActionConfirmDialog";
import { CardEditor, syncEnterpriseLogo } from "../components/CardEditor";
import type { CardCreationDraft } from "../components/CardEditor";
import { EnterpriseTemplateEditor } from "../components/EnterpriseTemplateEditor";
import { CardContentOverridesDialog } from "../components/CardContentOverridesDialog";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

type CardAction = {
  type: "publish" | "deactivate";
  target: ManagedCard;
};

export async function copyManagedCardText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("copy failed");
}

type CardTableProps = {
  cards: ManagedCard[];
  kind: ManagedCard["cardKind"];
  onCreate?: () => void;
  onEdit: (card: ManagedCard) => void;
  onTemplate: (card: ManagedCard) => void;
  onShare: (card: ManagedCard) => void;
  onOverride: (card: ManagedCard) => void;
  onWeCom: (card: ManagedCard) => void;
  onAction: (type: CardAction["type"], card: ManagedCard) => void;
};

function CardTable({
  cards,
  kind,
  onCreate,
  onEdit,
  onTemplate,
  onShare,
  onOverride,
  onWeCom,
  onAction,
}: CardTableProps) {
  const enterprise = kind === "enterprise";
  if (cards.length === 0) {
    return (
      <div className="catalog-empty-inline">
        <p>
          {enterprise
            ? "尚未创建企业官方名片。它归企业所有，不需要选择员工。"
            : "尚未创建员工名片。员工名片需要绑定企业有效成员。"}
        </p>
        {onCreate && (
          <Button appearance={enterprise ? "primary" : "secondary"} onClick={onCreate}>
            {enterprise ? "创建企业名片" : "创建员工名片"}
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="table-scroll">
      <Table aria-label={enterprise ? "企业名片列表" : "员工名片列表"} size="small">
        <TableHeader>
          <TableRow>
            <TableHeaderCell>{enterprise ? "企业官方名片" : "员工名片"}</TableHeaderCell>
            <TableHeaderCell className="status-column">状态</TableHeaderCell>
            <TableHeaderCell className="updated-column">更新时间</TableHeaderCell>
            <TableHeaderCell className="catalog-actions-column">操作</TableHeaderCell>
          </TableRow>
        </TableHeader>
        <TableBody>
          {cards.map((card) => (
            <TableRow key={card.id}>
              <TableCell>
                <div className="entity-title-cell">
                  <strong>{card.displayName || (enterprise ? "未命名企业" : "未命名员工")}</strong>
                  <span>
                    {card.title || (enterprise ? "业务定位未填写" : "职务未填写")}
                  </span>
                </div>
              </TableCell>
              <TableCell className="status-column">
                <StatusBadge status={card.status} />
              </TableCell>
              <TableCell className="updated-column">
                {formatTimestamp(card.updatedAt)}
              </TableCell>
              <TableCell className="catalog-actions-column">
                <div className="row-actions catalog-row-actions">
                  <Button
                    appearance="subtle"
                    size="small"
                    icon={<Edit24Regular />}
                    onClick={() => onEdit(card)}
                  >
                    编辑
                  </Button>
                  {true && (
                    <Button appearance="subtle" size="small" onClick={() => onTemplate(card)}>
                      编辑内容
                    </Button>
                  )}
                  {!enterprise && (
                    <Button
                      appearance="subtle"
                      size="small"
                      icon={<QrCode24Regular />}
                      onClick={() => onWeCom(card)}
                    >
                      企微联系入口
                    </Button>
                  )}
                  {card.status === "published" && (
                    <>
                      <Button
                        as="a"
                        appearance="primary"
                        size="small"
                        icon={<Open24Regular />}
                        href={card.shareUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        打开公开页
                      </Button>
                      <Button
                        appearance="subtle"
                        size="small"
                        icon={<Share24Regular />}
                        onClick={() => onShare(card)}
                      >
                        分享
                      </Button>
                    </>
                  )}
                  <Button
                    appearance="subtle"
                    size="small"
                    icon={<Settings24Regular />}
                    onClick={() => onOverride(card)}
                  >
                    内容覆盖
                  </Button>
                  {card.status !== "published" ? (
                    <Button
                      appearance="subtle"
                      size="small"
                      icon={<Send24Regular />}
                      onClick={() => onAction("publish", card)}
                    >
                      发布
                    </Button>
                  ) : (
                    <Button
                      appearance="subtle"
                      size="small"
                      icon={<ToggleRight24Regular />}
                      onClick={() => onAction("deactivate", card)}
                    >
                      停用
                    </Button>
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function CardsPage() {
  const auth = useAuth();
  const resource = useResource(() => adminApi.listManagedCards());
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<ManagedCard>();
  const [creationDraft, setCreationDraft] = useState<CardCreationDraft>();
  const [creatingFromComposer, setCreatingFromComposer] = useState(false);
  const [templateTarget, setTemplateTarget] = useState<ManagedCard>();
  const [defaultTemplateKind, setDefaultTemplateKind] = useState<ManagedCard["cardKind"]>();
  const [createKind, setCreateKind] = useState<ManagedCard["cardKind"]>("enterprise");
  const [shareTarget, setShareTarget] = useState<ManagedCard>();
  const [overrideTarget, setOverrideTarget] = useState<ManagedCard>();
  const [copyNotice, setCopyNotice] = useState<string>();
  const [copyError, setCopyError] = useState<string>();
  const [action, setAction] = useState<CardAction>();
  const [mutating, setMutating] = useState(false);
  const [actionError, setActionError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();
  const [wecomPendingId, setWecomPendingId] = useState<string>();

  const openCreate = (kind: ManagedCard["cardKind"]) => {
    setCreateKind(kind);
    setEditing(undefined);
    setEditorOpen(true);
    setCreationDraft(undefined);
    setNotice(undefined);
    setActionError(undefined);
  };

  const saved = () => {
    setEditorOpen(false);
    setNotice(editing ? "名片已由服务端确认保存。" : "名片已创建，安全链接已由服务端生成。");
    resource.reload();
  };

  const openCreationComposer = (draft: CardCreationDraft) => {
    setEditorOpen(false);
    setCreationDraft(draft);
    setActionError(undefined);
    setNotice(undefined);
  };

  const createFromComposer = async (
    document: EnterpriseTemplate["draft"],
    identity: Pick<ManagedCardInput, "identityTitles" | "contactFields">,
  ) => {
    if (!creationDraft || creatingFromComposer) return;
    setCreatingFromComposer(true);
    setActionError(undefined);
    try {
      const uploaded = creationDraft.imageFile
        ? await adminApi.uploadCardAsset(creationDraft.imageFile)
        : undefined;
      const canonicalAvatarUrl = uploaded?.url ?? creationDraft.canonicalAvatarUrl;
      if (creationDraft.input.cardKind === "enterprise" && creationDraft.avatarChanged) {
        await syncEnterpriseLogo(canonicalAvatarUrl);
      }
      if (
        creationDraft.input.cardKind === "employee"
        && creationDraft.avatarChanged
        && creationDraft.employeeMembershipId
      ) {
        if (
          auth.user?.role !== "company_admin"
          && creationDraft.employeeUserId !== auth.user?.id
        ) {
          throw new ApiError("只能修改自己的员工头像。", {
            code: "EMPLOYEE_AVATAR_PERMISSION_DENIED",
          });
        }
        if (auth.user?.role === "company_admin") {
          await memberApi.updateMember(creationDraft.employeeMembershipId, {
            avatarUrl: canonicalAvatarUrl,
          });
        } else {
          await memberApi.updateMyProfile({ avatarUrl: canonicalAvatarUrl });
        }
      }
      const input: ManagedCardInput = {
        ...creationDraft.input,
        avatarUrl: creationDraft.input.cardKind === "employee" ? "" : canonicalAvatarUrl,
        templateSourceCardId: undefined,
        composerMode: "default",
        templateDocument: document,
        identityTitles: identity.identityTitles,
        contactFields: identity.contactFields,
      };
      await adminApi.createManagedCard(input);
      setCreationDraft(undefined);
      setNotice("名片已按当前页面设计创建，安全链接已由服务端生成。");
      resource.reload();
    } catch (caught) {
      const apiError = caught instanceof ApiError
        ? caught
        : new ApiError("按当前页面设计创建名片时发生未知错误。", {
            code: "UNKNOWN_ERROR",
          });
      setActionError(apiError);
      throw apiError;
    } finally {
      setCreatingFromComposer(false);
    }
  };

  const requestAction = (type: CardAction["type"], target: ManagedCard) => {
    setAction({ type, target });
    setActionError(undefined);
    setNotice(undefined);
  };

  const executeAction = async () => {
    if (!action || mutating) return;
    setMutating(true);
    setActionError(undefined);
    try {
      if (action.type === "publish") {
        await adminApi.publishManagedCard(action.target.id, action.target.version);
        setNotice("名片已由服务端确认发布。公开链接现在可访问。");
      } else {
        await adminApi.deactivateManagedCard(action.target.id, action.target.version);
        setNotice("名片已停用，公开访问会立即失效。");
      }
      setAction(undefined);
      resource.reload();
    } catch (caught) {
      setActionError(
        caught instanceof ApiError
          ? caught
          : new ApiError("执行名片操作时发生未知错误。", {
              code: "UNKNOWN_ERROR",
            }),
      );
    } finally {
      setMutating(false);
    }
  };

  const copy = async (value: string, label: string) => {
    setCopyNotice(undefined);
    setCopyError(undefined);
    try {
      await copyManagedCardText(value);
      setCopyNotice(`${label}已复制。`);
    } catch {
      setCopyError("浏览器未允许自动复制，请手动选择文本。");
    }
  };

  const deactivating = action?.type === "deactivate";
  const canManageEnterpriseCards = auth.user?.role === "company_admin";
  const enterpriseCards = resource.data?.filter((card) => card.cardKind === "enterprise") ?? [];
  const employeeCards = resource.data?.filter((card) => card.cardKind === "employee") ?? [];

  const edit = (card: ManagedCard) => {
    setEditing(card);
    setEditorOpen(true);
    setNotice(undefined);
  };

  const share = (card: ManagedCard) => {
    setShareTarget(card);
    setCopyNotice(undefined);
    setCopyError(undefined);
  };

  const provisionWeCom = async (card: ManagedCard) => {
    if (wecomPendingId) return;
    setWecomPendingId(card.id);
    setActionError(undefined);
    setNotice(undefined);
    try {
      const contact = await adminApi.provisionWeComCardContactWay(card.id);
      setNotice(
        contact.qrCodeUrl
          ? `“${card.displayName}”的企微联系入口已启用，公开名片会自动展示。`
          : `“${card.displayName}”已绑定企微，但企业微信未返回二维码。`,
      );
    } catch (caught) {
      setActionError(
        caught instanceof ApiError
          ? caught
          : new ApiError("生成企微联系入口时发生未知错误。", {
              code: "UNKNOWN_ERROR",
            }),
      );
    } finally {
      setWecomPendingId(undefined);
    }
  };

  return (
    <main className="page-stack">
      <PageHeader
        title="企业与员工名片"
        description="企业官方名片归企业所有并可独立发布；员工名片绑定具体成员。两类名片共享同一安全公开页合同。"
        actions={
          resource.status === "permission" ? undefined : (
            <div className="row-actions">
              {auth.wecomBind && (
                <Button
                  appearance="secondary"
                  icon={<QrCode24Regular />}
                  disabled={auth.loginPending}
                  onClick={() => void auth.wecomBind?.()}
                >
                  {auth.loginPending ? "正在连接企微" : "绑定我的企业微信"}
                </Button>
              )}
              {canManageEnterpriseCards && (
                <Button
                  appearance="primary"
                  icon={<Add24Regular />}
                  onClick={() => openCreate("enterprise")}
                >
                  新建企业名片
                </Button>
              )}
              <Button
                appearance={canManageEnterpriseCards ? "secondary" : "primary"}
                icon={<Add24Regular />}
                onClick={() => openCreate("employee")}
              >
                新建员工名片
              </Button>
              <Button appearance="secondary" onClick={() => setDefaultTemplateKind("employee")}>
                员工默认配置
              </Button>
              {canManageEnterpriseCards && (
                <Button appearance="secondary" onClick={() => setDefaultTemplateKind("enterprise")}>
                  企业默认配置
                </Button>
              )}
            </div>
          )
        }
      />

      {notice && (
        <MessageBar intent="success">
          <MessageBarBody>{notice}</MessageBarBody>
        </MessageBar>
      )}
      {actionError && !action && (
        <MessageBar intent="error">
          <MessageBarBody>
            {actionError.message}
            {actionError.requestId ? `（请求 ${actionError.requestId}）` : ""}
          </MessageBarBody>
        </MessageBar>
      )}

      {resource.status !== "ready" && (
        <section className="content-panel catalog-panel">
          <ResourceState
            status={resource.status}
            title={resource.status === "empty" ? "尚未创建名片" : undefined}
            description={
              resource.status === "empty"
                ? "企业管理员可先创建企业官方名片；员工名片在绑定成员后单独管理。"
                : resource.error?.message
            }
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
            emptyAction={
              <div className="row-actions">
                {canManageEnterpriseCards && (
                  <Button
                    appearance="primary"
                    icon={<Add24Regular />}
                    onClick={() => openCreate("enterprise")}
                  >
                    创建企业名片
                  </Button>
                )}
                <Button
                  appearance={canManageEnterpriseCards ? "secondary" : "primary"}
                  icon={<Add24Regular />}
                  onClick={() => openCreate("employee")}
                >
                  创建员工名片
                </Button>
              </div>
            }
          />
        </section>
      )}

      {resource.status === "ready" && (
        <>
          <section
            className="content-panel catalog-panel catalog-section-panel"
            aria-labelledby="enterprise-card-title"
          >
            <div className="section-heading-row">
              <div>
                <h2 id="enterprise-card-title">企业官方名片</h2>
                <p>企业官方公开主页，不绑定员工，可由企业管理员独立发布。</p>
              </div>
            </div>
            <CardTable
              cards={enterpriseCards}
              kind="enterprise"
              onCreate={canManageEnterpriseCards ? () => openCreate("enterprise") : undefined}
              onEdit={edit}
              onTemplate={setTemplateTarget}
              onShare={share}
              onOverride={setOverrideTarget}
              onWeCom={provisionWeCom}
              onAction={requestAction}
            />
          </section>

          <section
            className="content-panel catalog-panel catalog-section-panel"
            aria-labelledby="employee-card-title"
          >
            <div className="section-heading-row">
              <div>
                <h2 id="employee-card-title">员工名片</h2>
                <p>绑定具体企业成员，用于个人对外展示与客户跟进。</p>
              </div>
            </div>
            <CardTable
              cards={employeeCards}
              kind="employee"
              onCreate={() => openCreate("employee")}
              onEdit={edit}
              onTemplate={setTemplateTarget}
              onShare={share}
              onOverride={setOverrideTarget}
              onWeCom={provisionWeCom}
              onAction={requestAction}
            />
          </section>
        </>
      )}

      <EnterpriseTemplateEditor
        card={templateTarget}
        defaultKind={defaultTemplateKind}
        creationDraft={creationDraft ? {
          cardKind: creationDraft.input.cardKind,
          identityPreview: creationDraft.identityPreview,
        } : undefined}
        open={Boolean(templateTarget || defaultTemplateKind || creationDraft) && !editorOpen}
        onClose={() => {
          if (creatingFromComposer) return;
          setTemplateTarget(undefined);
          setDefaultTemplateKind(undefined);
          setCreationDraft(undefined);
        }}
        onDraftConfirm={createFromComposer}
        onEditBasicSettings={(card) => {
          setDefaultTemplateKind(undefined);
          edit(card);
        }}
        onRequestPublish={(card) => {
          setTemplateTarget(undefined);
          setDefaultTemplateKind(undefined);
          requestAction("publish", card);
        }}
        onSaved={(card) => {
          if (card) setTemplateTarget(card);
          setNotice(card ? "名片内容草稿已保存；公开页仍保持上一次发布内容。" : "默认配置已保存；之后新建的同类名片会自动使用它。");
          resource.reload();
        }}
      />
      <CardEditor
        open={editorOpen}
        item={editing}
        createKind={createKind}
        onClose={() => setEditorOpen(false)}
        onSaved={saved}
        onCustomize={openCreationComposer}
      />
      <CardContentOverridesDialog
        card={overrideTarget}
        open={Boolean(overrideTarget)}
        onClose={() => setOverrideTarget(undefined)}
      />

      <ActionConfirmDialog
        open={Boolean(action)}
        title={deactivating ? "确认停用名片" : "确认发布名片"}
        description={
          deactivating
            ? "停用后，公开链接会立即失效。后台配置和历史数据仍会保留。"
            : "发布后，名片公开链接会立即生效，请确认展示内容和政策版本已复核。"
        }
        confirmLabel={deactivating ? "确认停用" : "确认发布"}
        pendingLabel={deactivating ? "正在停用" : "正在发布"}
        pending={mutating}
        error={actionError}
        destructive={deactivating}
        detail={
          action ? (
            <div className="publish-target">
              <strong>{action.target.displayName || "未命名名片"}</strong>
              <span>当前版本：{action.target.version}</span>
              {action.type === "publish" && action.target.cardKind === "enterprise" ? (
                <ul className="publish-checklist-summary">
                  <li>企业名称、业务定位和 Logo 已复核</li>
                  <li>模板草稿中的区块、图片、视频和案例将冻结为公开快照</li>
                  <li>公开页不会读取后续未发布草稿</li>
                </ul>
              ) : null}
            </div>
          ) : undefined
        }
        onCancel={() => {
          setAction(undefined);
          setActionError(undefined);
        }}
        onConfirm={() => void executeAction()}
        onReload={() => {
          setAction(undefined);
          setActionError(undefined);
          resource.reload();
        }}
      />

      <Dialog
        open={Boolean(shareTarget)}
        onOpenChange={(_, data) => {
          if (!data.open) setShareTarget(undefined);
        }}
      >
        <DialogSurface>
          <DialogBody>
            <DialogTitle>分享名片</DialogTitle>
            <DialogContent className="share-dialog-content">
              <p>分享链接和二维码内容均由服务端返回，不在浏览器中拼接。</p>
              {shareTarget && (
                <div className="share-fields">
                  <Field label="分享链接">
                    <div className="copy-field">
                      <Input value={shareTarget.shareUrl} readOnly />
                      <Button
                        icon={<Copy24Regular />}
                        aria-label="复制分享链接"
                        onClick={() => void copy(shareTarget.shareUrl, "分享链接")}
                      />
                    </div>
                  </Field>
                  <Field
                    label="二维码内容"
                    hint="将以下 URL 交给受信任的二维码工具编码。"
                  >
                    <div className="copy-field">
                      <Input value={shareTarget.qrUrl} readOnly />
                      <Button
                        icon={<QrCode24Regular />}
                        aria-label="复制二维码内容"
                        onClick={() => void copy(shareTarget.qrUrl, "二维码内容")}
                      />
                    </div>
                  </Field>
                  <a
                    className="share-open-link"
                    href={shareTarget.shareUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    打开公开名片
                  </a>
                </div>
              )}
              {copyNotice && (
                <MessageBar intent="success">
                  <MessageBarBody>{copyNotice}</MessageBarBody>
                </MessageBar>
              )}
              {copyError && (
                <MessageBar intent="error">
                  <MessageBarBody>{copyError}</MessageBarBody>
                </MessageBar>
              )}
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setShareTarget(undefined)}>
                关闭
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </main>
  );
}

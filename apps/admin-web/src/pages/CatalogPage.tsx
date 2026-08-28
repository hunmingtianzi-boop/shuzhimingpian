import {
  Button,
  Field,
  Input,
  MessageBar,
  MessageBarBody,
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
  Add24Regular,
  Archive24Regular,
  ArrowClockwise24Regular,
  ArrowLeft24Regular,
  Delete24Regular,
  Edit24Regular,
  Search24Regular,
  Send24Regular,
} from "@fluentui/react-icons";
import { useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import {
  scheduledPublicationsApi,
  type ScheduledPublication,
  type ScheduledPublicationTargetType,
} from "../api/scheduledPublicationsApi";
import type {
  CaseStudy,
  ContentVisibility,
  Product,
  ProductInput,
  PublicationImpact,
  PublicationRevision,
} from "../api/types";
import { ActionConfirmDialog } from "../components/ActionConfirmDialog";
import { CaseStudyEditor, ProductEditor } from "../components/CatalogEditor";
import { ContentDistributionControl } from "../components/ContentDistributionControl";
import { FormFeedback } from "../components/FormFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import {
  ScheduledPublicationActions,
  ScheduledPublicationStatus,
} from "../components/ScheduledPublicationActions";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { appHref, productDetailPath } from "../routing";
import { formatTimestamp } from "../utils/format";

type CatalogKind = "product" | "case";
type CatalogAction = "publish" | "archive" | "delete";
type InlineCatalogItem = Product | CaseStudy;

type PendingProductAction = {
  type: CatalogAction;
  product: Product;
};

const emptyProduct: ProductInput = {
  slug: "",
  name: "",
  category: "",
  summary: "",
  detail: "",
  audience: "",
  priceBoundary: "",
  imageUrl: "",
  visibility: "public",
  sortOrder: 0,
  settings: {},
};

const slugPattern = /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/;

function toApiError(error: unknown, fallback: string) {
  return error instanceof ApiError
    ? error
    : new ApiError(fallback, { code: "UNKNOWN_ERROR" });
}

function productValid(form: ProductInput) {
  return Boolean(form.name.trim() && slugPattern.test(form.slug) && form.summary.trim());
}

function navigateRawPath(path: string) {
  window.history.pushState({}, "", appHref(path));
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function actionCopy(action?: PendingProductAction) {
  if (!action) {
    return {
      title: "确认操作",
      description: "请确认是否继续。",
      confirmLabel: "确认",
      pendingLabel: "正在处理",
      destructive: false,
    };
  }
  if (action.type === "publish") {
    return {
      title: "确认发布产品",
      description: "发布后，符合公开范围的产品会立即进入访客可见状态。",
      confirmLabel: "确认发布",
      pendingLabel: "正在发布",
      destructive: false,
    };
  }
  if (action.type === "archive") {
    return {
      title: "确认归档产品",
      description: "归档后，该产品会立即从公开页面消失，但仍保留历史记录。",
      confirmLabel: "确认归档",
      pendingLabel: "正在归档",
      destructive: true,
    };
  }
  return {
    title: "确认删除产品",
    description: "删除后，该产品会被软删除并从管理列表及公开页面消失。",
    confirmLabel: "确认删除",
    pendingLabel: "正在删除",
    destructive: true,
  };
}

function InlineCatalogActions({ kind, item, activeSchedule, schedulesStatus, onEdit, onChanged, showDetails = false }: {
  kind: CatalogKind;
  item: InlineCatalogItem;
  activeSchedule?: ScheduledPublication;
  schedulesStatus?: string;
  onEdit: () => void;
  onChanged: (notice: string) => void;
  showDetails?: boolean;
}) {
  const [action, setAction] = useState<CatalogAction>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError>();
  const [impact, setImpact] = useState<PublicationImpact>();
  const label = kind === "product" ? (item as Product).name : (item as CaseStudy).title;
  const noun = kind === "product" ? "产品" : "案例";

  const requestAction = (next: CatalogAction) => {
    setAction(next);
    setError(undefined);
    setImpact(undefined);
    if (next === "publish") {
      const preview = kind === "product" ? adminApi.previewProductPublication(item.id) : adminApi.previewCasePublication(item.id);
      void preview.then(setImpact, (caught) => setError(toApiError(caught, "无法核对关联名片。")));
    }
  };

  const execute = async () => {
    if (!action || pending || (action === "publish" && !impact)) return;
    setPending(true);
    setError(undefined);
    try {
      if (kind === "product") {
        if (action === "publish") await adminApi.publishProductConfirmed(item.id, item.version, impact!.impactDigest);
        else if (action === "archive") await adminApi.archiveProduct(item.id, item.version);
        else await adminApi.deleteProduct(item.id, item.version);
      } else {
        if (action === "publish") await adminApi.publishCaseStudyConfirmed(item.id, item.version, impact!.impactDigest);
        else if (action === "archive") await adminApi.archiveCaseStudy(item.id, item.version);
        else await adminApi.deleteCaseStudy(item.id, item.version);
      }
      setAction(undefined);
      const notice = action === "publish"
        ? `${noun}已由服务端确认发布。`
        : action === "archive"
          ? `${noun}“${label}”已归档。`
          : `${noun}“${label}”已删除。`;
      onChanged(notice);
    } catch (caught) {
      setError(toApiError(caught, `操作${noun}时发生未知错误。`));
    } finally {
      setPending(false);
    }
  };

  const title = action === "publish" ? `确认发布${noun}` : action === "archive" ? `确认归档${noun}` : `确认删除${noun}`;
  const description = action === "publish" ? `发布后，符合公开范围的${noun}会立即进入访客可见状态。` : action === "archive" ? `归档后，该${noun}会从公开页面消失，但保留历史记录。` : `删除后，该${noun}会从管理列表和公开页面消失。`;

  return <>
    <div className="row-actions catalog-row-actions catalog-inline-actions">
      <Button appearance="subtle" size="small" icon={<Edit24Regular />} onClick={onEdit}>编辑</Button>
      {(item.status !== "published" || item.hasUnpublishedChanges) && !activeSchedule ? <Button appearance="subtle" size="small" icon={<Send24Regular />} onClick={() => requestAction("publish")}>发布</Button> : null}
      {item.status !== "published" ? <ScheduledPublicationActions targetType={kind === "product" ? "product" : "case_study"} targetId={item.id} targetVersion={item.version} targetLabel={label} current={activeSchedule} disabled={schedulesStatus === "loading" || schedulesStatus === "permission"} onChanged={onChanged} /> : null}
      {item.status !== "archived" ? <Button appearance="subtle" size="small" icon={<Archive24Regular />} onClick={() => requestAction("archive")}>归档</Button> : null}
      <Button appearance="subtle" size="small" icon={<Delete24Regular />} onClick={() => requestAction("delete")}>删除</Button>
      {showDetails ? <a className="catalog-detail-link" href={appHref(productDetailPath(item.id))}>查看详情</a> : null}
    </div>
    <ActionConfirmDialog open={Boolean(action)} title={title} description={description} confirmLabel={action === "publish" ? "确认发布" : action === "archive" ? "确认归档" : "确认删除"} pendingLabel="正在处理" pending={pending} error={error} destructive={action === "archive" || action === "delete"} onCancel={() => { setAction(undefined); setError(undefined); }} onConfirm={() => void execute()} detail={action === "publish" && impact ? <div className="publish-target"><strong>本次将更新 {impact.affectedCardCount} 张已发布名片</strong>{impact.breakdown.map((entry) => <span key={entry.reason}>{entry.label}：{entry.cardCount} 张</span>)}<span>确认后同步公开内容</span></div> : undefined} />
  </>;
}

function ProductFormFields({
  form,
  setForm,
  saving,
  attempted,
}: {
  form: ProductInput;
  setForm: Dispatch<SetStateAction<ProductInput>>;
  saving: boolean;
  attempted: boolean;
}) {
  const update = <K extends keyof ProductInput>(field: K, value: ProductInput[K]) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  return (
    <>
      <section className="content-panel form-panel">
        <div className="form-section-heading">
          <div>
            <h2>基础内容</h2>
            <p>这里维护产品名称、链接标识与核心介绍，列表页只做搜索和状态承载。</p>
          </div>
        </div>
        <div className="form-grid two-columns">
          <Field
            label="产品名称"
            required
            validationState={attempted && !form.name.trim() ? "error" : "none"}
            validationMessage={attempted && !form.name.trim() ? "请输入产品名称。" : undefined}
          >
            <Input value={form.name} onChange={(_, data) => update("name", data.value)} disabled={saving} />
          </Field>
          <Field
            label="链接标识"
            required
            validationState={attempted && !slugPattern.test(form.slug) ? "error" : "none"}
            validationMessage={attempted && !slugPattern.test(form.slug) ? "请输入有效的链接标识。" : undefined}
            hint="使用小写字母、数字和连字符，至少 3 个字符。"
          >
            <Input value={form.slug} onChange={(_, data) => update("slug", data.value.toLowerCase())} disabled={saving} />
          </Field>
          <Field label="产品分类">
            <Input value={form.category} onChange={(_, data) => update("category", data.value)} disabled={saving} />
          </Field>
          <Field label="排序值" hint="数字越小越靠前。">
            <Input
              type="number"
              min={0}
              value={String(form.sortOrder)}
              onChange={(_, data) => update("sortOrder", Number(data.value || 0))}
              disabled={saving}
            />
          </Field>
        </div>
      </section>

      <section className="content-panel form-panel">
        <div className="form-section-heading">
          <div>
            <h2>对外展示</h2>
            <p>公开页面展示什么、面向谁、价格怎么描述，都在这里完成。</p>
          </div>
        </div>
        <div className="form-grid two-columns">
          <Field label="受众">
            <Input value={form.audience} onChange={(_, data) => update("audience", data.value)} disabled={saving} />
          </Field>
          <Field label="价格范围">
            <Input value={form.priceBoundary} onChange={(_, data) => update("priceBoundary", data.value)} disabled={saving} />
          </Field>
          <Field label="封面图地址">
            <Input value={form.imageUrl} onChange={(_, data) => update("imageUrl", data.value)} disabled={saving} />
          </Field>
          <Field label="可见范围">
            <Select value={form.visibility} onChange={(_, data) => update("visibility", data.value as ContentVisibility)} disabled={saving}>
              <option value="public">公开</option>
              <option value="authenticated">登录后</option>
              <option value="internal">内部</option>
            </Select>
          </Field>
        </div>
        <Field
          label="摘要"
          required
          validationState={attempted && !form.summary.trim() ? "error" : "none"}
          validationMessage={attempted && !form.summary.trim() ? "请输入摘要。" : undefined}
        >
          <Textarea value={form.summary} onChange={(_, data) => update("summary", data.value)} resize="vertical" rows={4} disabled={saving} />
        </Field>
        <Field label="详情介绍">
          <Textarea value={form.detail} onChange={(_, data) => update("detail", data.value)} resize="vertical" rows={8} disabled={saving} />
        </Field>
      </section>
    </>
  );
}

export function ProductDetailPage({
  productId,
}: {
  productId?: string;
}) {
  const createMode = !productId;
  const listResource = useResource<Product[]>(() => adminApi.listProducts(), productId ?? "new");
  const schedules = useResource<ScheduledPublication[]>(() => scheduledPublicationsApi.list("product"), productId ?? "new");
  const [form, setForm] = useState<ProductInput>(emptyProduct);
  const [currentProduct, setCurrentProduct] = useState<Product>();
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string>();
  const [error, setError] = useState<ApiError>();
  const [action, setAction] = useState<PendingProductAction>();
  const [mutating, setMutating] = useState(false);
  const [actionError, setActionError] = useState<ApiError>();
  const [publicationImpact, setPublicationImpact] = useState<PublicationImpact>();
  const [revisions, setRevisions] = useState<PublicationRevision[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [rollbackRevision, setRollbackRevision] = useState<PublicationRevision>();
  const [rollbackImpact, setRollbackImpact] = useState<PublicationImpact>();
  const [rollingBack, setRollingBack] = useState(false);
  const [rollbackError, setRollbackError] = useState<ApiError>();

  useEffect(() => {
    if (createMode || listResource.status !== "ready" || !listResource.data) return;
    const found = listResource.data.find((item) => item.id === productId);
    if (found) {
      setCurrentProduct(found);
      setForm({
        slug: found.slug,
        name: found.name,
        category: found.category,
        summary: found.summary,
        detail: found.detail,
        audience: found.audience,
        priceBoundary: found.priceBoundary,
        imageUrl: found.imageUrl,
        visibility: found.visibility,
        sortOrder: found.sortOrder,
        settings: found.settings,
      });
    }
  }, [createMode, listResource.data, listResource.status, productId]);

  const activeSchedule = currentProduct
    ? schedules.data?.find(
        (item) =>
          item.resourceId === currentProduct.id &&
          (["pending", "processing", "failed"] as string[]).includes(item.status),
      )
    : undefined;

  const save = async () => {
    setAttempted(true);
    setError(undefined);
    setNotice(undefined);
    if (!productValid(form) || saving) return;
    setSaving(true);
    try {
      if (createMode) {
        const created = await adminApi.createProduct(form);
        setCurrentProduct(created);
        setNotice("产品已创建，当前页面已切换到详情态。");
        navigateRawPath(productDetailPath(created.id));
        listResource.reload();
      } else if (currentProduct) {
        const updated = await adminApi.updateProduct(currentProduct.id, currentProduct.version, form);
        setCurrentProduct(updated);
        setNotice("产品已由服务端确认保存。");
        listResource.reload();
      }
    } catch (caught) {
      setError(toApiError(caught, "保存产品时发生未知错误。"));
    } finally {
      setSaving(false);
    }
  };

  const requestAction = (type: CatalogAction) => {
    if (!currentProduct) return;
    setAction({ type, product: currentProduct });
    setActionError(undefined);
    setPublicationImpact(undefined);
    if (type === "publish") {
      void adminApi.previewProductPublication(currentProduct.id).then(
        setPublicationImpact,
        (caught) => setActionError(toApiError(caught, "无法核对关联名片。")),
      );
    }
  };

  const executeAction = async () => {
    if (!action || !currentProduct || mutating || (action.type === "publish" && !publicationImpact)) return;
    setMutating(true);
    setActionError(undefined);
    try {
      if (action.type === "publish") {
        const updated = await adminApi.publishProductConfirmed(currentProduct.id, currentProduct.version, publicationImpact!.impactDigest);
        setCurrentProduct(updated);
        setNotice("产品已由服务端确认发布。");
      } else if (action.type === "archive") {
        const updated = await adminApi.archiveProduct(currentProduct.id, currentProduct.version);
        setCurrentProduct(updated);
        setNotice("产品已由服务端确认归档。");
      } else {
        await adminApi.deleteProduct(currentProduct.id, currentProduct.version);
        setNotice("产品已删除。");
        navigateRawPath("/products");
      }
      setAction(undefined);
      listResource.reload();
    } catch (caught) {
      setActionError(toApiError(caught, "执行目录操作时发生未知错误。"));
    } finally {
      setMutating(false);
    }
  };

  const openHistory = async () => {
    if (!currentProduct) return;
    setHistoryLoading(true);
    try {
      setRevisions(await adminApi.listProductPublicationRevisions(currentProduct.id));
    } catch (caught) {
      setRollbackError(toApiError(caught, "发布历史加载失败。"));
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (currentProduct?.publishedAt) {
      void openHistory();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentProduct?.id, currentProduct?.publishedAt]);

  const requestRollback = async (revision: PublicationRevision) => {
    if (!currentProduct) return;
    setRollbackRevision(revision);
    setRollbackImpact(undefined);
    setRollbackError(undefined);
    try {
      setRollbackImpact(await adminApi.previewProductPublication(currentProduct.id));
    } catch (caught) {
      setRollbackError(toApiError(caught, "无法核对回退影响。"));
    }
  };

  const executeRollback = async () => {
    if (!currentProduct || !rollbackRevision || !rollbackImpact || rollingBack) return;
    setRollingBack(true);
    setRollbackError(undefined);
    try {
      const updated = await adminApi.rollbackProduct(
        currentProduct.id,
        currentProduct.version,
        rollbackRevision.id,
        rollbackImpact.impactDigest,
      );
      setCurrentProduct(updated);
      setNotice(`已回退到发布版本 ${rollbackRevision.revisionNumber}。`);
      setRollbackRevision(undefined);
      listResource.reload();
    } catch (caught) {
      setRollbackError(toApiError(caught, "回退失败。"));
    } finally {
      setRollingBack(false);
    }
  };

  const copy = actionCopy(action);

  if (!createMode && listResource.status === "ready" && !currentProduct) {
    return (
      <main className="page-stack">
        <section className="content-panel">
          <ResourceState status="empty" title="未找到该产品" description="请返回产品列表重新选择。" />
        </section>
      </main>
    );
  }

  return (
    <main className="page-stack">
      <PageHeader
        title={createMode ? "新建产品" : currentProduct?.name || "产品详情"}
        description={createMode ? "这是路由化的新建页面；保存后将进入产品详情。" : "详情页承载产品基础内容、对外展示、分发策略与版本历史。"}
        actions={
          <>
            <Button appearance="secondary" icon={<ArrowLeft24Regular />} onClick={() => navigateRawPath("/products")}>
              返回产品列表
            </Button>
            {!createMode && currentProduct ? (
              <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={listResource.reload}>
                刷新
              </Button>
            ) : null}
          </>
        }
      />

      {(listResource.status !== "ready" && !createMode) ? (
        <section className="content-panel">
          <ResourceState
            status={listResource.status}
            description={listResource.error?.message}
            errorCode={listResource.error?.code}
            requestId={listResource.error?.requestId}
            onRetry={listResource.status === "error" ? listResource.reload : undefined}
          />
        </section>
      ) : (
        <>
          {notice && (
            <MessageBar intent="success">
              <MessageBarBody>{notice}</MessageBarBody>
            </MessageBar>
          )}
          <FormFeedback error={error} />

          {!createMode && currentProduct ? (
            <section className="content-panel">
              <div className="panel-footer-row">
                <div className="entity-title-cell">
                  <strong>{currentProduct.name}</strong>
                  <span>{currentProduct.slug} · {currentProduct.category || "未分类"}</span>
                </div>
                <StatusBadge status={currentProduct.status} />
              </div>
            </section>
          ) : null}

          <ProductFormFields form={form} setForm={setForm} saving={saving} attempted={attempted} />

          <section className="content-panel">
            <div className="panel-footer-row">
              <Button appearance="primary" icon={<Edit24Regular />} disabled={saving} onClick={() => void save()}>
                {saving ? "正在保存" : createMode ? "保存产品" : "保存修改"}
              </Button>
              {!createMode && currentProduct ? (
                <div className="row-actions catalog-row-actions">
                  <ContentDistributionControl
                    resourceType="product"
                    resourceId={currentProduct.id}
                    resourceLabel={currentProduct.name}
                    sourceStatus={currentProduct.status}
                  />
                  {(currentProduct.status !== "published" || currentProduct.hasUnpublishedChanges) && !activeSchedule ? (
                    <Button appearance="secondary" icon={<Send24Regular />} onClick={() => requestAction("publish")}>
                      发布
                    </Button>
                  ) : null}
                  {currentProduct.status !== "published" ? (
                    <ScheduledPublicationActions
                      targetType={"product" as ScheduledPublicationTargetType}
                      targetId={currentProduct.id}
                      targetVersion={currentProduct.version}
                      targetLabel={currentProduct.name}
                      current={activeSchedule}
                      disabled={schedules.status === "loading" || schedules.status === "permission"}
                      onChanged={(message) => {
                        setNotice(message);
                        schedules.reload();
                      }}
                    />
                  ) : null}
                  {currentProduct.status !== "archived" ? (
                    <Button appearance="secondary" icon={<Archive24Regular />} onClick={() => requestAction("archive")}>
                      归档
                    </Button>
                  ) : null}
                  <Button appearance="secondary" icon={<Delete24Regular />} onClick={() => requestAction("delete")}>
                    删除
                  </Button>
                </div>
              ) : null}
            </div>
          </section>

          {!createMode && currentProduct ? (
            <section className="content-panel">
              <div className="form-section-heading">
                <div>
                  <h2>版本与历史</h2>
                  <p>发布历史与回退都在详情页处理，列表页不再承载这些动作。</p>
                </div>
                {activeSchedule ? <ScheduledPublicationStatus publication={activeSchedule} /> : null}
              </div>
              {historyLoading ? <p>正在加载发布历史…</p> : null}
              {!historyLoading && revisions.length === 0 ? <p>暂无可回退的发布版本。</p> : null}
              <div className="publication-history-list">
                {revisions.map((revision, index) => (
                  <div className="publication-history-row" key={revision.id}>
                    <div>
                      <strong>版本 {revision.revisionNumber}</strong>
                      <span>{formatTimestamp(revision.publishedAt)}</span>
                    </div>
                    <Button appearance="secondary" size="small" disabled={index === 0} onClick={() => void requestRollback(revision)}>
                      {index === 0 ? "当前版本" : "回退到此版本"}
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </>
      )}

      <ActionConfirmDialog
        key={action ? `${action.type}-${action.product.id}` : "product-action"}
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
              <strong>{action.product.name || "未命名产品"}</strong>
              <span>当前版本：{action.product.version}</span>
              {action.type === "publish" ? (
                publicationImpact === undefined ? (
                  <span>正在核对关联名片…</span>
                ) : (
                  <div className="publication-impact-summary">
                    <strong>本次将更新 {publicationImpact.affectedCardCount} 张已发布名片</strong>
                    {publicationImpact.breakdown.filter((item) => item.cardCount > 0).map((item) => (
                      <span key={item.reason}>{item.label}：{item.cardCount} 张</span>
                    ))}
                  </div>
                )
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
      />

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
  const resource = useResource<Product[]>(() => adminApi.listProducts());
  const schedules = useResource<ScheduledPublication[]>(() => scheduledPublicationsApi.list("product"), "product-list");
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<string>();
  const [editing, setEditing] = useState<Product>();
  const filtered = useMemo(() => {
    if (resource.status !== "ready" || !resource.data) return [];
    const keyword = query.trim().toLocaleLowerCase();
    return resource.data.filter((item) =>
      `${item.name} ${item.category} ${item.slug} ${item.status}`.toLocaleLowerCase().includes(keyword),
    );
  }, [query, resource.data, resource.status]);

  return (
    <main className="page-stack">
      <PageHeader
        title="产品管理"
        description="列表页只承担搜索和状态观察；基础内容、对外展示、分发策略与历史都进入产品详情页处理。"
        actions={
          <Button appearance="primary" icon={<Add24Regular />} onClick={() => navigateRawPath("/products/new")}>
            新建产品
          </Button>
        }
      />
      {notice ? <MessageBar intent="success"><MessageBarBody>{notice}</MessageBarBody></MessageBar> : null}
      <section className="content-panel filter-panel" aria-label="产品筛选">
        <Input
          aria-label="搜索产品"
          contentBefore={<Search24Regular />}
          placeholder="按产品名称、分类或标识搜索"
          value={query}
          onChange={(_, data) => setQuery(data.value)}
        />
      </section>
      <section className="content-panel catalog-panel">
        {resource.status !== "ready" ? (
          <ResourceState
            status={resource.status}
            title={resource.status === "empty" ? "尚未创建产品" : undefined}
            description={resource.status === "empty" ? "创建第一项产品后，可在这里观察状态并进入详情页。" : resource.error?.message}
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
          />
        ) : filtered.length === 0 ? (
          <ResourceState status="empty" title={query ? "没有匹配的产品" : "尚未创建产品"} description={query ? "调整搜索条件后重试。" : "创建第一项产品后，可在这里观察状态并进入详情页。"} />
        ) : (
          <div className="table-scroll">
            <Table aria-label="产品列表" size="small">
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>名称与范围</TableHeaderCell>
                  <TableHeaderCell className="status-column">状态</TableHeaderCell>
                  <TableHeaderCell className="updated-column">更新时间</TableHeaderCell>
                  <TableHeaderCell className="catalog-actions-column">操作</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((record) => (
                  <TableRow key={record.id}>
                    <TableCell>
                      <div className="entity-title-cell">
                        <strong>{record.name}</strong>
                        <span>{record.category || "未分类"} | {record.slug}</span>
                      </div>
                    </TableCell>
                    <TableCell className="status-column">
                      <StatusBadge status={record.status} />
                      {record.hasUnpublishedChanges ? <span className="draft-change-note">有未发布修改</span> : null}
                    </TableCell>
                    <TableCell className="updated-column">{formatTimestamp(record.updatedAt)}</TableCell>
                    <TableCell className="catalog-actions-column">
                      <InlineCatalogActions
                        kind="product"
                        item={record}
                        activeSchedule={schedules.data?.find((entry) => entry.resourceId === record.id && ["pending", "processing", "failed"].includes(entry.status))}
                        schedulesStatus={schedules.status}
                        onEdit={() => setEditing(record)}
                        showDetails
                        onChanged={(message) => { setNotice(message); resource.reload(); schedules.reload(); }}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
      <ProductEditor item={editing} open={Boolean(editing)} onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); resource.reload(); }} />
    </main>
  );
}

export function CatalogPage({ kind }: { kind: CatalogKind }) {
  const resource = useResource<CaseStudy[]>(() => adminApi.listCaseStudies(), kind);
  const schedules = useResource<ScheduledPublication[]>(() => scheduledPublicationsApi.list("case_study"), "case-list");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<CaseStudy>();
  const [notice, setNotice] = useState<string>();

  if (kind === "product") return <ProductsPage />;

  return (
    <main className="page-stack">
      <PageHeader
        title="案例管理"
        description="维护项目背景、解决方案和成果。只有公开且已发布的案例会对访客展示。"
        actions={<Button appearance="primary" icon={<Add24Regular />} onClick={() => setEditorOpen(true)}>新建案例</Button>}
      />
      {notice ? <MessageBar intent="success"><MessageBarBody>{notice}</MessageBarBody></MessageBar> : null}
      <section className="content-panel catalog-panel">
        {resource.status !== "ready" ? (
          <ResourceState
            status={resource.status}
            title={resource.status === "empty" ? "尚未创建案例" : undefined}
            description={resource.status === "empty" ? "创建第一项案例后，可在这里维护。" : resource.error?.message}
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
          />
        ) : (
          <div className="table-scroll">
            <Table aria-label="案例列表" size="small">
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>案例</TableHeaderCell>
                  <TableHeaderCell>状态</TableHeaderCell>
                  <TableHeaderCell>更新时间</TableHeaderCell>
                  <TableHeaderCell className="catalog-actions-column">操作</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(resource.data ?? []).map((record) => (
                  <TableRow key={record.id}>
                    <TableCell>
                      <div className="entity-title-cell">
                        <strong>{record.title}</strong>
                        <span>{record.clientDisplayName || "未填写客户"} | {record.slug}</span>
                      </div>
                    </TableCell>
                    <TableCell><StatusBadge status={record.status} /></TableCell>
                    <TableCell>{formatTimestamp(record.updatedAt)}</TableCell>
                    <TableCell className="catalog-actions-column">
                      <InlineCatalogActions
                        kind="case"
                        item={record}
                        activeSchedule={schedules.data?.find((entry) => entry.resourceId === record.id && ["pending", "processing", "failed"].includes(entry.status))}
                        schedulesStatus={schedules.status}
                        onEdit={() => { setEditing(record); setEditorOpen(true); }}
                        onChanged={(message) => { setNotice(message); resource.reload(); schedules.reload(); }}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
      <CaseStudyEditor item={editing} open={editorOpen} onClose={() => { setEditorOpen(false); setEditing(undefined); }} onSaved={() => { setEditorOpen(false); setEditing(undefined); resource.reload(); }} />
    </main>
  );
}

export function CaseStudiesPage() {
  return <CatalogPage kind="case" />;
}

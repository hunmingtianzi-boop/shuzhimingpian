import {
  Badge,
  Button,
  Checkbox,
  Input,
  MessageBar,
  MessageBarBody,
  ProgressBar,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Textarea,
} from "@fluentui/react-components";
import { ArrowClockwise24Regular, ArrowUpload24Regular, Delete24Regular } from "@fluentui/react-icons";
import { useContext, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import {
  knowledgeImportsApi,
  contentImportsApi,
  type ContentImportCandidate,
  type ContentImportCategory,
  type ContentImportRun,
  type KnowledgeImportBatch,
  type KnowledgeImportBatchStatus,
  type KnowledgeImportItemStatus,
  type KnowledgeImportStageStatus,
} from "../api/knowledgeImportsApi";
import { AuthContext } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { OperationFeedback } from "./OperationFeedback";
import { ResourceState } from "./ResourceState";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

export const KNOWLEDGE_IMPORT_MAX_FILES = 5;
export const KNOWLEDGE_IMPORT_MAX_FILE_BYTES = 10 * 1024 * 1024;
export const KNOWLEDGE_IMPORT_MAX_BATCH_BYTES = 25 * 1024 * 1024;
const allowedExtensions = new Set([
  "pdf", "docx", "pptx", "xlsx", "csv", "txt", "md", "html", "htm",
  "png", "jpg", "jpeg", "webp", "tiff", "bmp",
]);

const batchLabels: Record<KnowledgeImportBatchStatus, string> = {
  pending: "等待处理",
  processing: "处理中",
  completed: "已完成",
  completed_with_errors: "部分完成",
  failed: "批次失败",
  dead_letter: "处理终止",
};
const itemLabels: Record<KnowledgeImportItemStatus, string> = {
  pending: "等待处理",
  processing: "处理中",
  completed: "草稿已创建",
  failed: "失败",
  dead_letter: "处理终止",
};
const stageLabels: Record<KnowledgeImportStageStatus, string> = {
  pending: "等待",
  processing: "处理中",
  completed: "完成",
  failed: "失败",
  skipped: "跳过",
};

const categoryLabels: Record<ContentImportCategory, string> = {
  enterprise_profile: "企业资料",
  products: "核心业务",
  case_studies: "案例",
  faqs: "常见问题",
  unclassified: "待人工分类",
};
const fieldLabels: Record<string, string> = {
  company_name: "企业名称", summary: "摘要", industry: "行业", region: "地区", website: "官网",
  name: "业务名称", category: "分类", detail: "详细介绍", audience: "适用对象", price_boundary: "价格说明",
  title: "案例标题", client_display_name: "客户名称", background: "项目背景", solution: "解决方案", result: "项目成果",
  question: "问题", answer: "答案", text: "原始内容", reason: "待分类原因",
};
const payloadDefaults: Record<ContentImportCategory, Record<string, string>> = {
  enterprise_profile: { company_name: "", summary: "", industry: "", region: "", website: "" },
  products: { name: "", category: "", summary: "", detail: "", audience: "", price_boundary: "" },
  case_studies: { title: "", industry: "", client_display_name: "", background: "", solution: "", result: "" },
  faqs: { question: "", answer: "" },
  unclassified: { text: "", reason: "" },
};

function stageCopy(label: string, status: KnowledgeImportStageStatus | undefined): string {
  return status ? `${label}：${stageLabels[status]}` : `${label}：等待服务端回执`;
}

export function validateKnowledgeImportFiles(files: File[]): string | undefined {
  if (files.length === 0) return "请选择要导入的文件。";
  if (files.length > KNOWLEDGE_IMPORT_MAX_FILES) return "每批最多选择 5 个文件。";
  for (const file of files) {
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!allowedExtensions.has(extension)) {
      return `不支持文件“${file.name}”。可上传 PDF、Word、PPT、Excel、CSV、TXT/MD/HTML 或 PNG/JPG/WEBP/TIFF/BMP 图片。`;
    }
    if (file.size > KNOWLEDGE_IMPORT_MAX_FILE_BYTES) {
      return `文件“${file.name}”超过 10 MiB。`;
    }
  }
  if (files.reduce((sum, file) => sum + file.size, 0) > KNOWLEDGE_IMPORT_MAX_BATCH_BYTES) {
    return "本批文件总大小超过 25 MiB。";
  }
  return undefined;
}

function asApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("创建知识导入批次时发生未知错误。", { code: "UNKNOWN_ERROR" });
}

function isActive(batch: KnowledgeImportBatch): boolean {
  return batch.status === "pending" || batch.status === "processing";
}

function ImportDetail({
  batch,
  onRequestDeleteDocument,
}: {
  batch: KnowledgeImportBatch;
  onRequestDeleteDocument?: (documentId: string) => void;
}) {
  const completed = batch.succeededItems + batch.failedItems;
  const progress = batch.totalItems > 0 ? completed / batch.totalItems : 0;
  return (
    <div className="knowledge-import-detail">
      <div className="knowledge-import-progress-copy">
        <strong>{batchLabels[batch.status]}</strong>
        <span>{completed}/{batch.totalItems} 项已处理</span>
      </div>
      <ProgressBar value={progress} aria-label="导入批次进度" />
      <div className="table-scroll">
        <Table aria-label="知识导入逐文件结果" size="small">
          <TableHeader><TableRow>
            <TableHeaderCell>文件</TableHeaderCell><TableHeaderCell>类型</TableHeaderCell>
            <TableHeaderCell>处理状态</TableHeaderCell><TableHeaderCell>解析 / 索引 / 发布</TableHeaderCell><TableHeaderCell>结果</TableHeaderCell>
          </TableRow></TableHeader>
          <TableBody>
            {batch.items.map((item) => (
              <TableRow key={item.id}>
                <TableCell>{item.fileName}{item.rowNumber ? ` · 第 ${item.rowNumber} 行` : ""}</TableCell>
                <TableCell>{item.sourceType.toUpperCase()}</TableCell>
                <TableCell><Badge appearance="tint" color={item.status === "completed" ? "success" : item.status === "failed" || item.status === "dead_letter" ? "danger" : "informative"}>{itemLabels[item.status]}</Badge></TableCell>
                <TableCell>
                  <div className="knowledge-import-stages">
                    <span>{stageCopy("解析", item.parseStatus)}</span>
                    <span>{item.indexStatus ? stageCopy("索引", item.indexStatus) : "索引：随发布流程确认"}</span>
                    <span>{stageCopy("发布", item.publishStatus)}</span>
                  </div>
                </TableCell>
                <TableCell>{item.errorCode ? `错误码：${item.errorCode}` : item.documentId ? (
                  <div className="row-actions">
                    {item.publishStatus === "completed" ? <span>已更新并发布</span> : <a href="#knowledge-documents">已生成待审核草稿，去审核</a>}
                    {onRequestDeleteDocument ? (
                      <Button
                        appearance="subtle"
                        size="small"
                        icon={<Delete24Regular />}
                        onClick={() => onRequestDeleteDocument(item.documentId!)}
                      >删除内容</Button>
                    ) : null}
                  </div>
                ) : "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

const classificationFailureLabels: Record<string, string> = {
  classification_provider_output_truncated: "模型输出被截断，系统已尝试缩小分片；仍未完成的内容需要重试。",
  classification_provider_timeout: "模型响应超时，请稍后重试。",
  classification_provider_rate_limit: "模型当前请求过多，请稍后重试。",
  classification_interrupted: "上次整理被服务重启或网络中断打断，可以安全重试。",
  classification_internal_error: "整理过程发生内部错误，任务已经安全结束，可以重试。",
};

function classificationFailureMessage(code?: string) {
  if (!code) return "模型结果未通过证据硬门，请核对资料后重试。";
  if (code.startsWith("classification_partial:")) {
    return "部分资料已生成候选，另有分片未能完成；现有候选可以继续核对。";
  }
  return classificationFailureLabels[code] ?? "模型结果未通过证据硬门，请核对资料或模型配置后重试。";
}

function ContentImportReview({ batch }: { batch: KnowledgeImportBatch }) {
  const [run, setRun] = useState<ContentImportRun>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();
  const [drafts, setDrafts] = useState<Record<string, ContentImportCandidate>>({});
  const [applyFields, setApplyFields] = useState<Record<string, string[]>>({});

  useEffect(() => {
    void contentImportsApi.list().then((runs) => {
      const existing = runs.find((item) => item.batchId === batch.id);
      if (existing) {
        setRun(existing);
        setDrafts(Object.fromEntries(existing.candidates.map((item) => [item.id, item])));
      }
    }, (caught) => setError(asApiError(caught)));
  }, [batch.id]);

  useEffect(() => {
    if (run?.status !== "processing") return undefined;
    const timer = window.setInterval(() => {
      void contentImportsApi.get(run.id).then((updated) => {
        setRun(updated);
        setDrafts(Object.fromEntries(updated.candidates.map((item) => [item.id, item])));
      }, (caught) => setError(asApiError(caught)));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [run?.id, run?.status]);

  const generate = async (retry = false) => {
    setBusy(true); setError(undefined); setNotice(undefined);
    try {
      const created = await contentImportsApi.generate(batch.id, { retry });
      setRun(created);
      setDrafts(Object.fromEntries(created.candidates.map((item) => [item.id, item])));
      setNotice(created.status === "manual_required"
        ? classificationFailureMessage(created.failureCode)
        : `已生成 ${created.candidates.length} 条候选。请逐条核对原文后再接受。`);
    } catch (caught) { setError(asApiError(caught)); } finally { setBusy(false); }
  };

  const replaceCandidate = (candidate: ContentImportCandidate) => {
    setDrafts((current) => ({ ...current, [candidate.id]: candidate }));
    setRun((current) => current ? {
      ...current,
      candidates: current.candidates.map((item) => item.id === candidate.id ? candidate : item),
    } : current);
  };

  const act = async (candidate: ContentImportCandidate, action: "save" | "accept" | "ignore") => {
    setBusy(true); setError(undefined); setNotice(undefined);
    try {
      const updated = action === "save"
        ? await contentImportsApi.update(candidate)
        : action === "accept"
          ? await contentImportsApi.accept(candidate, applyFields[candidate.id] ?? [])
          : await contentImportsApi.ignore(candidate);
      replaceCandidate(updated);
      setNotice(action === "accept" ? "已写入对应工作台草稿，仍需人工发布。" : action === "ignore" ? "已忽略该候选。" : "候选修改已保存。");
    } catch (caught) { setError(asApiError(caught)); } finally { setBusy(false); }
  };

  if (!(batch.status === "completed" || batch.status === "completed_with_errors")) return null;
  return (
    <section className="content-import-review" aria-labelledby="content-import-review-title">
      <div className="content-import-review-heading">
        <div><h3 id="content-import-review-title">智能整理为工作台内容</h3><p>DeepSeek 只生成候选；服务端核验字段和逐字原文。接受后写入草稿，不会自动发布。</p></div>
        {!run && <Button appearance="primary" disabled={busy} onClick={() => void generate()}>{busy ? "正在识别" : "开始智能整理"}</Button>}
      </div>
      <OperationFeedback notice={notice} error={error} onRetry={!run ? () => void generate() : undefined} />
      {run?.status === "processing" && <ResourceState status="loading" title="正在分段整理资料" description="系统会逐段识别并合并重复候选。刷新页面不会重复创建任务。" compact />}
      {run?.status === "manual_required" && <div className="content-import-manual-state">
        <ResourceState status="error" title="本次整理未完成" description={classificationFailureMessage(run.failureCode)} compact />
        <Button disabled={busy} onClick={() => void generate(true)}>{busy ? "正在重试" : "安全重试"}</Button>
      </div>}
      {run?.status === "review" && run.failureCode?.startsWith("classification_partial:") && <div className="content-import-manual-state">
        <ResourceState status="error" title="部分分片需要重试" description={classificationFailureMessage(run.failureCode)} compact />
        <Button disabled={busy} onClick={() => void generate(true)}>{busy ? "正在重新整理" : "重新整理未完成内容"}</Button>
      </div>}
      {run?.status === "review" && (
        <div className="content-import-candidate-list">
          {run.candidates.map((original) => {
            const candidate = drafts[original.id] ?? original;
            const accepted = candidate.status === "accepted";
            const ignored = candidate.status === "ignored";
            return <article className="content-import-candidate" key={candidate.id}>
              <div className="content-import-candidate-head">
                <select
                  aria-label="候选分类"
                  disabled={accepted || ignored || busy}
                  value={candidate.category}
                  onChange={(event) => {
                    const category = event.target.value as ContentImportCategory;
                    replaceCandidate({ ...candidate, category, payload: { ...payloadDefaults[category] } });
                  }}
                >{Object.entries(categoryLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                <Badge appearance="tint" color={accepted ? "success" : ignored ? "subtle" : "informative"}>{accepted ? "已写入草稿" : ignored ? "已忽略" : `${Math.round(candidate.confidence * 100)}% · 待复核`}</Badge>
              </div>
              <div className="content-import-fields">
                {Object.entries(candidate.payload).map(([field, value]) => {
                  const multiline = ["summary", "detail", "background", "solution", "result", "answer", "text", "reason"].includes(field);
                  const update = (next: string) => replaceCandidate({ ...candidate, payload: { ...candidate.payload, [field]: next } });
                  return <label key={field}><span>{fieldLabels[field] ?? field}</span>{multiline
                    ? <Textarea disabled={accepted || ignored || busy} value={value} onChange={(_, data) => update(data.value)} resize="vertical" />
                    : <Input disabled={accepted || ignored || busy} value={value} onChange={(_, data) => update(data.value)} />}</label>;
                })}
              </div>
              <details className="content-import-evidence"><summary>查看原文证据</summary><blockquote>{candidate.sourceText}</blockquote></details>
              {candidate.category === "enterprise_profile" && !accepted && !ignored && (
                <fieldset className="content-import-apply-fields"><legend>只更新勾选字段</legend>
                  {Object.keys(candidate.payload).map((field) => <Checkbox key={field} label={fieldLabels[field] ?? field} checked={(applyFields[candidate.id] ?? Object.keys(candidate.payload)).includes(field)} onChange={(_, data) => setApplyFields((current) => {
                    const selected = current[candidate.id] ?? Object.keys(candidate.payload);
                    return { ...current, [candidate.id]: data.checked ? [...new Set([...selected, field])] : selected.filter((item) => item !== field) };
                  })} />)}
                </fieldset>
              )}
              {!accepted && !ignored && <div className="row-actions">
                <Button disabled={busy} onClick={() => void act(candidate, "save")}>保存修改</Button>
                <Button appearance="primary" disabled={busy || candidate.category === "unclassified"} onClick={() => void act(candidate, "accept")}>接受并写入草稿</Button>
                <Button appearance="subtle" disabled={busy} onClick={() => void act(candidate, "ignore")}>忽略</Button>
              </div>}
            </article>;
          })}
        </div>
      )}
    </section>
  );
}

export function KnowledgeImportPanel({
  onRequestDeleteDocument,
}: {
  onRequestDeleteDocument?: (documentId: string) => void;
} = {}) {
  const auth = useContext(AuthContext);
  const canImport = auth?.user
    ? hasPermission(auth.user, "knowledge.write")
    : true;
  const canAutoPublish = auth?.user
    ? auth.user.role === "company_admin" || auth.user.role === "platform_admin"
    : true;
  const inputRef = useRef<HTMLInputElement>(null);
  const resource = useResource(() => knowledgeImportsApi.list());
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [selectedBatch, setSelectedBatch] = useState<KnowledgeImportBatch>();
  const [uploading, setUploading] = useState(false);
  const [autoPublish, setAutoPublish] = useState(false);
  const [validationError, setValidationError] = useState<string>();
  const [operationError, setOperationError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();

  useEffect(() => {
    const active = resource.data?.items.some(isActive) || (selectedBatch && isActive(selectedBatch));
    if (!active) return undefined;
    const timer = window.setInterval(() => {
      resource.reload();
      if (selectedBatch && isActive(selectedBatch)) {
        void knowledgeImportsApi.get(selectedBatch.id).then(setSelectedBatch, () => undefined);
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [resource.data, resource.reload, selectedBatch]);

  const chooseFiles = (files: File[]) => {
    const error = validateKnowledgeImportFiles(files);
    setSelectedFiles(error ? [] : files);
    setValidationError(error);
    setOperationError(undefined);
    setNotice(undefined);
  };

  const upload = async () => {
    const error = validateKnowledgeImportFiles(selectedFiles);
    if (error || uploading) {
      setValidationError(error);
      return;
    }
    setUploading(true);
    setOperationError(undefined);
    setNotice(undefined);
    try {
      const batch = autoPublish
        ? await knowledgeImportsApi.create(selectedFiles, { autoPublish: true })
        : await knowledgeImportsApi.create(selectedFiles);
      setSelectedBatch(batch);
      setSelectedFiles([]);
      if (inputRef.current) inputRef.current.value = "";
      setNotice(
        autoPublish
          ? "导入批次已创建。服务端会解析、建立索引并尝试发布；仅在自动发布成功后，AI 问答才会使用更新后的知识。失败内容会保留为草稿或可重试状态。"
          : "导入批次已创建。内容只会生成草稿，仍需人工审核并发布。",
      );
      resource.reload();
    } catch (caught) {
      setOperationError(asApiError(caught));
    } finally {
      setUploading(false);
    }
  };

  const openBatch = async (batch: KnowledgeImportBatch) => {
    setOperationError(undefined);
    try {
      setSelectedBatch(await knowledgeImportsApi.get(batch.id));
    } catch (caught) {
      setOperationError(asApiError(caught));
    }
  };

  return (
    <section className="content-panel knowledge-import-panel" aria-labelledby="knowledge-import-title">
      <div className="knowledge-import-heading">
        <div><h2 id="knowledge-import-title">文件与批量导入</h2><p>支持 PDF、Word、PPT、Excel、CSV、文本/网页和常见图片。系统会异步解析并建立知识草稿；默认须人工审核后发布。</p></div>
        <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>刷新批次</Button>
      </div>

      {!canImport ? (
        <ResourceState status="permission" description="当前账号没有知识写入权限，无法创建导入批次。" compact />
      ) : (
        <div className="knowledge-import-picker">
          <input ref={inputRef} aria-label="选择知识文件" type="file" accept=".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.html,.htm,.png,.jpg,.jpeg,.webp,.tiff,.bmp" multiple disabled={uploading} onChange={(event) => chooseFiles(Array.from(event.target.files ?? []))} />
          <span>{selectedFiles.length > 0 ? `已选择 ${selectedFiles.length} 个文件` : "每批 1–5 个；单文件不超过 10 MiB，批次不超过 25 MiB。"}</span>
          {canAutoPublish && (
            <div className="knowledge-import-autopublish">
              <Switch
                checked={autoPublish}
                disabled={uploading}
                label="解析完成后自动更新并发布到知识库"
                onChange={(_, data) => setAutoPublish(data.checked)}
              />
              <span>仅在自动发布与索引成功后，AI 问答才会使用更新内容；失败时保留草稿或可重试状态。请仅用于已审核、可公开的企业材料。</span>
            </div>
          )}
          <Button appearance="primary" icon={<ArrowUpload24Regular />} disabled={uploading || selectedFiles.length === 0} onClick={() => void upload()}>{uploading ? "正在上传" : "创建导入批次"}</Button>
        </div>
      )}
      {validationError && <MessageBar intent="error"><MessageBarBody>{validationError}</MessageBarBody></MessageBar>}
      <OperationFeedback
        notice={notice}
        error={operationError}
        onRetry={selectedFiles.length > 0 ? () => void upload() : resource.reload}
      />
      {selectedBatch && (
        <>
          <ImportDetail batch={selectedBatch} onRequestDeleteDocument={canImport ? onRequestDeleteDocument : undefined} />
          {canImport && <ContentImportReview batch={selectedBatch} />}
        </>
      )}

      {resource.status !== "ready" ? (
        <ResourceState status={resource.status} title={resource.status === "empty" ? "尚无导入批次" : undefined} description={resource.status === "empty" ? "选择文件后创建第一个异步导入批次。" : resource.error?.message} errorCode={resource.error?.code} requestId={resource.error?.requestId} onRetry={resource.status === "error" ? resource.reload : undefined} compact />
      ) : resource.data && resource.data.items.length === 0 ? (
        <ResourceState status="empty" title="尚无导入批次" description="选择文件后创建第一个异步导入批次。" compact />
      ) : resource.data ? (
        <div className="table-scroll"><Table aria-label="知识导入批次列表" size="small">
          <TableHeader><TableRow><TableHeaderCell>批次</TableHeaderCell><TableHeaderCell>状态</TableHeaderCell><TableHeaderCell>进度</TableHeaderCell><TableHeaderCell>创建时间</TableHeaderCell><TableHeaderCell /></TableRow></TableHeader>
          <TableBody>{resource.data.items.map((batch) => <TableRow key={batch.id}>
            <TableCell><code>{batch.id}</code></TableCell><TableCell>{batchLabels[batch.status]}</TableCell>
            <TableCell>{batch.succeededItems} 成功 / {batch.failedItems} 失败 / {batch.pendingItems} 待处理</TableCell>
            <TableCell>{formatTimestamp(batch.createdAt)}</TableCell><TableCell><Button appearance="subtle" size="small" onClick={() => void openBatch(batch)}>查看结果</Button></TableCell>
          </TableRow>)}</TableBody>
        </Table></div>
      ) : null}
    </section>
  );
}

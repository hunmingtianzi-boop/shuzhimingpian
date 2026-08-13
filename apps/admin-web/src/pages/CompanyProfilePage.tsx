import {
  Button,
  Field,
  Input,
  Textarea,
} from "@fluentui/react-components";
import { Save24Regular } from "@fluentui/react-icons";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { CompanyProfileInput } from "../api/types";
import { FormFeedback } from "../components/FormFeedback";
import { ImportWorkbenchButton } from "../components/ImportWorkbenchButton";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

const emptyProfile: CompanyProfileInput = {
  name: "",
  summary: "",
  industry: "",
  region: "",
  website: "",
  logoUrl: "",
  profilePersonalizationPolicyVersion: "profile-personalization-v1",
  version: undefined,
};

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("保存企业资料时发生未知错误。", {
        code: "UNKNOWN_ERROR",
      });
}

export function CompanyProfilePage() {
  const resource = useResource(() => adminApi.getCompanyProfile());
  const [form, setForm] = useState<CompanyProfileInput>(emptyProfile);
  const [saving, setSaving] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [saveError, setSaveError] = useState<ApiError>();
  const [success, setSuccess] = useState<string>();

  useEffect(() => {
    if (resource.status !== "ready" || !resource.data) return;
    const { id: _id, updatedAt: _updatedAt, ...input } = resource.data;
    setForm(input);
  }, [resource.data, resource.status]);

  const update = (field: keyof CompanyProfileInput, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setSuccess(undefined);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    setSaveError(undefined);
    setSuccess(undefined);
    if (!form.name.trim() || form.version === undefined || saving) return;

    setSaving(true);
    try {
      await adminApi.updateCompanyProfile(form);
      setSuccess("企业资料已由服务端确认保存。");
      resource.reload();
    } catch (error) {
      setSaveError(toApiError(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="page-stack">
      <PageHeader
        title="企业资料"
        description="维护企业公开资料。保存时使用服务端版本号进行并发冲突保护。"
        actions={<ImportWorkbenchButton />}
      />

      {resource.status !== "ready" && (
        <section className="content-panel">
          <ResourceState
            status={resource.status}
            title={resource.status === "empty" ? "企业资料为空" : undefined}
            description={
              resource.status === "empty"
                ? "服务端没有返回企业资料，请联系平台管理员。"
                : resource.error?.message
            }
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
          />
        </section>
      )}

      {resource.status === "ready" && (
        <form className="content-panel form-panel" onSubmit={submit} noValidate>
          <div className="form-section-heading">
            <div>
              <h2>企业公开资料</h2>
              <p>空白可选字段会按 null 提交，不会填充默认内容。</p>
            </div>
            {resource.data?.updatedAt && (
              <span>上次更新：{formatTimestamp(resource.data.updatedAt)}</span>
            )}
          </div>

          <FormFeedback success={success} error={saveError} />

          <div className="form-grid two-columns">
            <Field
              label="企业名称"
              required
              validationState={attempted && !form.name.trim() ? "error" : "none"}
              validationMessage={
                attempted && !form.name.trim() ? "请输入企业名称。" : undefined
              }
            >
              <Input
                value={form.name}
                onChange={(_, data) => update("name", data.value)}
                disabled={saving}
              />
            </Field>

            <Field label="所属行业">
              <Input
                value={form.industry}
                onChange={(_, data) => update("industry", data.value)}
                disabled={saving}
              />
            </Field>

            <Field label="所在地区">
              <Input
                value={form.region}
                onChange={(_, data) => update("region", data.value)}
                disabled={saving}
              />
            </Field>

            <Field label="官方网站">
              <Input
                type="url"
                value={form.website}
                onChange={(_, data) => update("website", data.value)}
                placeholder="https://"
                disabled={saving}
              />
            </Field>
          </div>

          <Field label="企业标识图片地址">
            <Input
              type="url"
              value={form.logoUrl}
              onChange={(_, data) => update("logoUrl", data.value)}
              placeholder="https://"
              disabled={saving}
            />
          </Field>

          <Field label="企业简介">
            <Textarea
              value={form.summary}
              onChange={(_, data) => update("summary", data.value)}
              resize="vertical"
              rows={7}
              disabled={saving}
            />
          </Field>

          <Field
            label="长期访客画像政策版本"
            hint="修改版本后，旧同意与旧关联令牌立即失效，访客需要按新版本重新明确同意。"
            required
            validationState={
              attempted && !form.profilePersonalizationPolicyVersion.trim()
                ? "error"
                : "none"
            }
            validationMessage={
              attempted && !form.profilePersonalizationPolicyVersion.trim()
                ? "请输入政策版本。"
                : undefined
            }
          >
            <Input
              value={form.profilePersonalizationPolicyVersion}
              onChange={(_, data) =>
                update("profilePersonalizationPolicyVersion", data.value)
              }
              maxLength={64}
              disabled={saving}
            />
          </Field>

          <div className="form-actions">
            <Button
              type="submit"
              appearance="primary"
              icon={<Save24Regular />}
              disabled={
                saving ||
                !form.name.trim() ||
                !form.profilePersonalizationPolicyVersion.trim() ||
                form.version === undefined
              }
            >
              {saving ? "正在保存" : "保存企业资料"}
            </Button>
          </div>
        </form>
      )}
    </main>
  );
}

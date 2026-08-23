import {
  Button,
  Field,
  Input,
} from "@fluentui/react-components";
import { ArrowRight24Regular, Save24Regular } from "@fluentui/react-icons";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { CompanyPrivacySettings } from "../api/types";
import { FormFeedback } from "../components/FormFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { APP_PATHS, navigate } from "../routing";
import { useResource } from "../hooks/useResource";

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("保存数据与隐私设置时发生未知错误。", {
        code: "UNKNOWN_ERROR",
      });
}

export function PrivacySettingsPage() {
  const resource = useResource(() => adminApi.getPrivacySettings());
  const [form, setForm] = useState<CompanyPrivacySettings>();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<ApiError>();
  const [success, setSuccess] = useState<string>();

  useEffect(() => {
    if (resource.status === "ready" && resource.data) {
      setForm(resource.data);
    }
  }, [resource.data, resource.status]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form || saving) return;
    setSaving(true);
    setSaveError(undefined);
    setSuccess(undefined);
    try {
      const updated = await adminApi.updatePrivacySettings(form);
      setForm(updated);
      setSuccess("数据与隐私设置已由服务端确认保存。");
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
        title="数据与隐私"
        description="这里维护长期访客画像授权边界；具体的隐私权利请求仍在“隐私请求”页面处理。"
        actions={
          <>
            <Button
              appearance="secondary"
              icon={<ArrowRight24Regular />}
              onClick={() => navigate(APP_PATHS.privacyRequests)}
            >
              隐私请求
            </Button>
            <Button
              appearance="secondary"
              icon={<ArrowRight24Regular />}
              onClick={() => navigate(APP_PATHS.company)}
            >
              企业资料
            </Button>
          </>
        }
      />

      {resource.status !== "ready" || !form ? (
        <section className="content-panel">
          <ResourceState
            status={resource.status === "ready" ? "empty" : resource.status}
            title={resource.status === "empty" ? "数据与隐私设置暂不可用" : undefined}
            description={resource.error?.message}
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
          />
        </section>
      ) : (
        <form className="content-panel form-panel" onSubmit={submit} noValidate>
          <div className="form-section-heading">
            <div>
              <h2>长期访客画像授权</h2>
              <p>修改政策版本后，旧同意与旧关联令牌立即失效，访客需要按新版本重新明确同意。</p>
            </div>
          </div>

          <FormFeedback success={success} error={saveError} />

          <Field
            label="访客画像政策版本"
            required
            hint="修改版本后，旧同意需要按新版本重新确认。"
          >
            <Input
              value={form.profilePersonalizationPolicyVersion}
              onChange={(_, data) =>
                setForm((current) =>
                  current
                    ? { ...current, profilePersonalizationPolicyVersion: data.value }
                    : current,
                )
              }
              maxLength={64}
              disabled={saving}
            />
          </Field>

          <Field label="访客画像留存期限（天）" hint="允许 1–730 天，保存后只影响本企业后续画像留存。">
            <Input
              type="number"
              min={1}
              max={730}
              value={String(form.visitorProfileRetentionDays)}
              onChange={(_, data) =>
                setForm((current) =>
                  current
                    ? { ...current, visitorProfileRetentionDays: Number(data.value) }
                    : current,
                )
              }
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
                !form.profilePersonalizationPolicyVersion.trim() ||
                form.visitorProfileRetentionDays < 1 ||
                form.visitorProfileRetentionDays > 730
              }
            >
              {saving ? "正在保存" : "保存数据与隐私设置"}
            </Button>
          </div>
        </form>
      )}
    </main>
  );
}

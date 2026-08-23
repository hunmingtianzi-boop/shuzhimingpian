import {
  Button,
  Field,
  Radio,
  RadioGroup,
  Switch,
} from "@fluentui/react-components";
import { ArrowRight24Regular, Save24Regular } from "@fluentui/react-icons";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { CompanyNotificationSettings } from "../api/types";
import { FormFeedback } from "../components/FormFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { APP_PATHS, navigate } from "../routing";
import { useResource } from "../hooks/useResource";

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("保存通知设置时发生未知错误。", {
        code: "UNKNOWN_ERROR",
      });
}

export function NotificationSettingsPage() {
  const resource = useResource(() => adminApi.getNotificationSettings());
  const [form, setForm] = useState<CompanyNotificationSettings>();
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
      const updated = await adminApi.updateNotificationSettings(form);
      setForm(updated);
      setSuccess("通知设置已由服务端确认保存。");
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
        title="通知设置"
        description="默认仅实时推送留资或高意向提醒，普通访问按日汇总，避免把消息中心变成噪声流。"
        actions={
          <Button
            appearance="secondary"
            icon={<ArrowRight24Regular />}
            onClick={() => navigate(APP_PATHS.notifications)}
          >
            返回消息中心
          </Button>
        }
      />

      {resource.status !== "ready" || !form ? (
        <section className="content-panel">
          <ResourceState
            status={resource.status === "ready" ? "empty" : resource.status}
            title={resource.status === "empty" ? "通知设置暂不可用" : undefined}
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
              <h2>提醒节奏</h2>
              <p>留资和高意向可实时提醒；普通访问按日汇总，避免逐次打扰。</p>
            </div>
          </div>

          <FormFeedback success={success} error={saveError} />

          <Switch
            checked={form.visitNotificationsEnabled}
            label="实时推送留资或高意向提醒"
            onChange={(_, data) =>
              setForm((current) =>
                current ? { ...current, visitNotificationsEnabled: data.checked } : current,
              )
            }
            disabled={saving}
          />
          <Switch
            checked={form.visitReportNotificationsEnabled}
            label="高意向访问结束后实时发送行为报告"
            onChange={(_, data) =>
              setForm((current) =>
                current
                  ? { ...current, visitReportNotificationsEnabled: data.checked }
                  : current,
              )
            }
            disabled={saving || !form.visitNotificationsEnabled}
          />
          <Switch
            checked={form.ordinaryVisitDigestEnabled}
            label="普通访问按日汇总"
            onChange={(_, data) =>
              setForm((current) =>
                current ? { ...current, ordinaryVisitDigestEnabled: data.checked } : current,
              )
            }
            disabled={saving}
          />

          <div className="form-grid two-columns">
            <Switch
              checked={form.visitNotificationInAppEnabled}
              label="后台站内通知"
              onChange={(_, data) =>
                setForm((current) =>
                  current
                    ? { ...current, visitNotificationInAppEnabled: data.checked }
                    : current,
                )
              }
              disabled={saving || !form.visitNotificationsEnabled}
            />
            <Switch
              checked={form.visitNotificationWecomEnabled}
              label="企业微信应用消息"
              onChange={(_, data) =>
                setForm((current) =>
                  current
                    ? { ...current, visitNotificationWecomEnabled: data.checked }
                    : current,
                )
              }
              disabled={saving || !form.visitNotificationsEnabled}
            />
          </div>

          <Field label="通知接收人" hint="名片负责人适用于员工名片；企业名片由负责人或企业管理员接收。">
            <RadioGroup
              value={form.visitNotificationRecipientScope}
              onChange={(_, data) =>
                setForm((current) =>
                  current
                    ? {
                        ...current,
                        visitNotificationRecipientScope:
                          data.value as CompanyNotificationSettings["visitNotificationRecipientScope"],
                      }
                    : current,
                )
              }
              disabled={saving || !form.visitNotificationsEnabled}
            >
              <Radio value="admins" label="所有企业管理员" />
              <Radio value="responsible" label="仅名片负责人" />
              <Radio value="both" label="名片负责人和企业管理员" />
            </RadioGroup>
          </Field>

          <div className="form-actions">
            <Button
              type="submit"
              appearance="primary"
              icon={<Save24Regular />}
              disabled={saving}
            >
              {saving ? "正在保存" : "保存通知设置"}
            </Button>
          </div>
        </form>
      )}
    </main>
  );
}

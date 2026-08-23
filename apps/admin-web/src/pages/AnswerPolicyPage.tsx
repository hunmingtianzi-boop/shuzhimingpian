import {
  Button,
  Field,
  Radio,
  RadioGroup,
  Slider,
} from "@fluentui/react-components";
import { ArrowRight24Regular, Save24Regular } from "@fluentui/react-icons";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { CompanyAnswerPolicy } from "../api/types";
import { FormFeedback } from "../components/FormFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { APP_PATHS, navigate } from "../routing";
import { useResource } from "../hooks/useResource";

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("保存回答策略时发生未知错误。", {
        code: "UNKNOWN_ERROR",
      });
}

export function AnswerPolicyPage() {
  const resource = useResource(() => adminApi.getAnswerPolicy());
  const [form, setForm] = useState<CompanyAnswerPolicy>();
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
      const updated = await adminApi.updateAnswerPolicy(form);
      setForm(updated);
      setSuccess("回答策略已由服务端确认保存。");
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
        title="回答策略"
        description="这里只管理企业 AI 助手的回答边界，不包含模型接入、API Key 或套餐额度。"
        actions={
          <Button
            appearance="secondary"
            icon={<ArrowRight24Regular />}
            onClick={() => navigate(APP_PATHS.company)}
          >
            企业资料
          </Button>
        }
      />

      {resource.status !== "ready" || !form ? (
        <section className="content-panel">
          <ResourceState
            status={resource.status === "ready" ? "empty" : resource.status}
            title={resource.status === "empty" ? "回答策略暂不可用" : undefined}
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
              <h2>企业 AI 助手回答边界</h2>
              <p>这项设置只控制与本企业无关的普通问题，不会放宽价格、敏感信息和企业知识来源等安全限制。</p>
            </div>
          </div>

          <FormFeedback success={success} error={saveError} />

          <RadioGroup
            value={form.aiOffTopicAnswerMode}
            aria-label="无关问题回答尺度"
            onChange={(_, data) =>
              setForm((current) =>
                current
                  ? {
                      ...current,
                      aiOffTopicAnswerMode: data.value as CompanyAnswerPolicy["aiOffTopicAnswerMode"],
                    }
                  : current,
              )
            }
            disabled={saving}
          >
            <Radio
              value="blocked"
              label="完全不回答——从第 1 个企业无关问题起拒答"
            />
            <Radio
              value="limited"
              label="限量回答——达到自定义次数后拒答"
            />
            <Radio
              value="unlimited"
              label="完全允许——不按次数限制普通无关问题"
            />
          </RadioGroup>

          {form.aiOffTopicAnswerMode === "limited" && (
            <Field
              label={`每段对话最多回答 ${form.aiOffTopicQuestionLimit} 个无关问题`}
              hint="达到上限后，后续无关问题会被拒答；企业相关问题和普通问候仍可继续。"
            >
              <Slider
                min={1}
                max={10}
                step={1}
                value={form.aiOffTopicQuestionLimit}
                aria-label="无关问题回答上限"
                onChange={(_, data) =>
                  setForm((current) =>
                    current
                      ? { ...current, aiOffTopicQuestionLimit: Number(data.value) }
                      : current,
                  )
                }
                disabled={saving}
              />
            </Field>
          )}

          <div className="form-actions">
            <Button
              type="submit"
              appearance="primary"
              icon={<Save24Regular />}
              disabled={saving}
            >
              {saving ? "正在保存" : "保存回答策略"}
            </Button>
          </div>
        </form>
      )}
    </main>
  );
}

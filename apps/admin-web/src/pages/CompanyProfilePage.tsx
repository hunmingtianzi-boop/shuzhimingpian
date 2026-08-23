import {
  Button,
  Field,
  Input,
  Select,
  Textarea,
} from "@fluentui/react-components";
import {
  ArrowRight24Regular,
  Save24Regular,
} from "@fluentui/react-icons";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type {
  CompanyIdentityProfile,
  CompanyIdentityProfileInput,
  CompanySubjectType,
  IdentityProfileFact,
} from "../api/types";
import { FormFeedback } from "../components/FormFeedback";
import { IdentityTitlesEditor } from "../components/IdentityTitlesEditor";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import { APP_PATHS, navigate } from "../routing";
import { formatTimestamp } from "../utils/format";

type CompanyIdentityDraft = CompanyIdentityProfileInput & {
  version?: number;
};

const emptyProfile: CompanyIdentityDraft = {
  legalName: "",
  shortName: "",
  subjectType: "pending_registration",
  socialCreditCode: "",
  industry: "",
  region: "",
  website: "",
  logoUrl: "",
  positioning: "",
  profileFacts: [],
  profileTags: [],
  summary: "",
  version: undefined,
};

const subjectTypeOptions: Array<{ value: CompanySubjectType; label: string }> = [
  { value: "domestic_enterprise", label: "国内企业" },
  { value: "association", label: "协会 / 商会" },
  { value: "overseas", label: "境外主体" },
  { value: "pending_registration", label: "筹备中 / 待注册" },
];

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("保存企业资料时发生未知错误。", {
        code: "UNKNOWN_ERROR",
      });
}

function toDraft(profile: CompanyIdentityProfile): CompanyIdentityDraft {
  return {
    legalName: profile.legalName,
    shortName: profile.shortName ?? "",
    subjectType: profile.subjectType,
    socialCreditCode: profile.socialCreditCode ?? "",
    industry: profile.industry,
    region: profile.region,
    website: profile.website,
    logoUrl: profile.logoUrl,
    positioning: profile.positioning ?? "",
    profileFacts: profile.profileFacts ?? [],
    profileTags: profile.profileTags ?? [],
    summary: profile.summary,
    version: profile.version,
  };
}

function moveFact(facts: IdentityProfileFact[], index: number, direction: -1 | 1) {
  const target = index + direction;
  if (target < 0 || target >= facts.length) return facts;
  const next = [...facts];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export function CompanyProfilePage() {
  const resource = useResource(() => adminApi.getCompanyIdentity());
  const [form, setForm] = useState<CompanyIdentityDraft>(emptyProfile);
  const [saving, setSaving] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [saveError, setSaveError] = useState<ApiError>();
  const [success, setSuccess] = useState<string>();

  useEffect(() => {
    if (resource.status !== "ready" || !resource.data) return;
    setForm(toDraft(resource.data));
  }, [resource.data, resource.status]);

  const update = <FieldName extends keyof CompanyIdentityDraft>(
    field: FieldName,
    value: CompanyIdentityDraft[FieldName],
  ) => {
    setForm((current) => ({ ...current, [field]: value }));
    setSuccess(undefined);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    setSaveError(undefined);
    setSuccess(undefined);
    if (!form.legalName.trim() || form.version === undefined || saving) return;

    setSaving(true);
    try {
      await adminApi.updateCompanyIdentity({
        legalName: form.legalName,
        shortName: form.shortName,
        subjectType: form.subjectType,
        socialCreditCode: form.socialCreditCode,
        industry: form.industry,
        region: form.region,
        website: form.website,
        logoUrl: form.logoUrl,
        positioning: form.positioning,
        profileFacts: form.profileFacts,
        profileTags: form.profileTags,
        summary: form.summary,
        version: form.version,
      });
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
        description="当前页面完全基于企业身份接口，负责主体身份与对外展示。回答策略、通知偏好和数据隐私已经拆到独立设置页。"
        actions={
          <>
            <Button
              appearance="secondary"
              icon={<ArrowRight24Regular />}
              onClick={() => navigate(APP_PATHS.answerPolicy)}
            >
              回答策略
            </Button>
            <Button
              appearance="secondary"
              icon={<ArrowRight24Regular />}
              onClick={() => navigate(APP_PATHS.notificationSettings)}
            >
              通知设置
            </Button>
            <Button
              appearance="secondary"
              icon={<ArrowRight24Regular />}
              onClick={() => navigate(APP_PATHS.privacySettings)}
            >
              数据与隐私
            </Button>
          </>
        }
      />

      {resource.status !== "ready" && (
        <section className="content-panel">
          <ResourceState
            status={resource.status}
            title={resource.status === "empty" ? "企业资料为空" : undefined}
            description={
              resource.status === "empty"
                ? "服务端没有返回企业身份资料，请联系平台管理员。"
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
              <h2>企业身份与对外展示</h2>
              <p>正式名称、简称、主体类型与信用代码属于企业身份；定位、信息项、标签和简介属于对外展示。</p>
            </div>
            {resource.data?.updatedAt && (
              <span>上次更新：{formatTimestamp(resource.data.updatedAt)}</span>
            )}
          </div>

          <FormFeedback success={success} error={saveError} />

          <div className="form-grid two-columns">
            <Field
              label="企业正式名称"
              required
              validationState={attempted && !form.legalName.trim() ? "error" : "none"}
              validationMessage={
                attempted && !form.legalName.trim() ? "请输入企业正式名称。" : undefined
              }
            >
              <Input
                value={form.legalName}
                onChange={(_, data) => update("legalName", data.value)}
                disabled={saving}
              />
            </Field>

            <Field label="企业简称">
              <Input
                value={form.shortName ?? ""}
                onChange={(_, data) => update("shortName", data.value)}
                disabled={saving}
              />
            </Field>

            <Field label="主体类型">
              <Select
                value={form.subjectType}
                onChange={(_, data) => update("subjectType", data.value as CompanySubjectType)}
                disabled={saving}
              >
                {subjectTypeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>

            <Field
              label="统一社会信用代码"
              hint={form.subjectType === "domestic_enterprise" ? "国内企业建议完整填写 18 位信用代码。" : "非国内企业可留空。"}
            >
              <Input
                value={form.socialCreditCode ?? ""}
                onChange={(_, data) => update("socialCreditCode", data.value.toUpperCase())}
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

            <Field label="地址 / 地区">
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

            <Field label="Logo / 品牌展示图">
              <Input
                type="url"
                value={form.logoUrl}
                onChange={(_, data) => update("logoUrl", data.value)}
                placeholder="https://"
                disabled={saving}
              />
            </Field>
          </div>

          <Field label="对外展示定位" hint="显示在企业名称下方，适合填写一句简短的业务定位。">
            <Input
              value={form.positioning ?? ""}
              maxLength={240}
              onChange={(_, data) => update("positioning", data.value)}
              disabled={saving}
            />
          </Field>

          <Field label="企业信息项" hint="对外展示的补充信息，最多 4 项。">
            <div className="profile-fact-editor">
              {form.profileFacts?.map((fact, index) => (
                <div className="profile-fact-row" key={fact.id}>
                  <div className="profile-fact-order">
                    <Button
                      type="button"
                      appearance="subtle"
                      size="small"
                      aria-label={`上移企业信息项${index + 1}`}
                      disabled={saving || index === 0}
                      onClick={() =>
                        setForm((current) => ({
                          ...current,
                          profileFacts: moveFact(current.profileFacts ?? [], index, -1),
                        }))
                      }
                    >
                      上移
                    </Button>
                    <Button
                      type="button"
                      appearance="subtle"
                      size="small"
                      aria-label={`下移企业信息项${index + 1}`}
                      disabled={saving || index === (form.profileFacts?.length ?? 0) - 1}
                      onClick={() =>
                        setForm((current) => ({
                          ...current,
                          profileFacts: moveFact(current.profileFacts ?? [], index, 1),
                        }))
                      }
                    >
                      下移
                    </Button>
                  </div>
                  <Input
                    aria-label={`企业信息项${index + 1}小标题`}
                    value={fact.label}
                    maxLength={8}
                    disabled={saving}
                    onChange={(_, data) =>
                      setForm((current) => ({
                        ...current,
                        profileFacts: (current.profileFacts ?? []).map((value) =>
                          value.id === fact.id ? { ...value, label: data.value } : value,
                        ),
                      }))
                    }
                  />
                  <Input
                    aria-label={`企业信息项${index + 1}内容`}
                    value={fact.value}
                    maxLength={24}
                    disabled={saving}
                    onChange={(_, data) =>
                      setForm((current) => ({
                        ...current,
                        profileFacts: (current.profileFacts ?? []).map((value) =>
                          value.id === fact.id ? { ...value, value: data.value } : value,
                        ),
                      }))
                    }
                  />
                  <Button
                    type="button"
                    appearance="subtle"
                    aria-label={`删除企业信息项${index + 1}`}
                    disabled={saving}
                    onClick={() =>
                      setForm((current) => ({
                        ...current,
                        profileFacts: (current.profileFacts ?? []).filter((value) => value.id !== fact.id),
                      }))
                    }
                  >
                    删除
                  </Button>
                </div>
              ))}
              <Button
                type="button"
                appearance="secondary"
                disabled={saving || (form.profileFacts?.length ?? 0) >= 4}
                onClick={() =>
                  setForm((current) => ({
                    ...current,
                    profileFacts: [
                      ...(current.profileFacts ?? []),
                      { id: `fact-${Date.now()}`, label: "新信息", value: "待填写" },
                    ],
                  }))
                }
              >
                添加信息项
              </Button>
            </div>
          </Field>

          <Field label="企业标签" hint="对外展示时最多展示 3 个短标签。">
            <IdentityTitlesEditor
              values={form.profileTags ?? []}
              kind="enterprise"
              maxItems={3}
              maxItemLength={40}
              disabled={saving}
              onChange={(profileTags) => setForm((current) => ({ ...current, profileTags }))}
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

          <div className="form-actions">
            <Button
              type="submit"
              appearance="primary"
              icon={<Save24Regular />}
              disabled={saving || !form.legalName.trim() || form.version === undefined}
            >
              {saving ? "正在保存" : "保存企业资料"}
            </Button>
          </div>
        </form>
      )}
    </main>
  );
}

import {
  Button,
  Field,
  Input,
  Textarea,
} from "@fluentui/react-components";
import {
  ArrowLeft24Regular,
  ArrowRight24Regular,
  Building24Regular,
  Checkmark24Regular,
  CheckmarkCircle24Regular,
  ContactCard24Regular,
  Open24Regular,
  Sparkle24Regular,
} from "@fluentui/react-icons";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type {
  CardSettingsInput,
  CompanyProfileInput,
} from "../api/types";
import { FormFeedback } from "../components/FormFeedback";
import { ResourceState } from "../components/ResourceState";
import { APP_PATHS, appHref, navigate } from "../routing";

type SetupStep = 1 | 2 | 3;

type SetupData = {
  company: CompanyProfileInput;
  card: CardSettingsInput;
  completed: boolean;
};

const slugPattern = /^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$/;

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("保存开通资料时发生未知错误。", {
        code: "UNKNOWN_ERROR",
      });
}

function publicCardUrl(slug: string): string {
  return new URL(`/c/${encodeURIComponent(slug)}`, window.location.origin).toString();
}

export function CompanySetupPage() {
  const [step, setStep] = useState<SetupStep>(1);
  const [data, setData] = useState<SetupData>();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<ApiError>();
  const [saveError, setSaveError] = useState<ApiError>();
  const [saving, setSaving] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [questionsText, setQuestionsText] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(undefined);
    try {
      const [companyProfile, cardProfile] = await Promise.all([
        adminApi.getCompanyProfile(),
        adminApi.getCard(),
      ]);
      const {
        id: _companyId,
        updatedAt: _companyUpdatedAt,
        onboardingStatus: companyOnboarding,
        ...company
      } = companyProfile;
      const {
        id: _cardId,
        status: _cardStatus,
        updatedAt: _cardUpdatedAt,
        onboardingStatus: cardOnboarding,
        ...card
      } = cardProfile;
      setData({
        company,
        card,
        completed:
          companyOnboarding === "completed" &&
          cardOnboarding === "completed" &&
          cardProfile.status === "published",
      });
      setQuestionsText(card.suggestedQuestions.join("\n"));
    } catch (error) {
      setLoadError(toApiError(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [step]);

  const questions = useMemo(
    () =>
      questionsText
        .split(/\r?\n/)
        .map((value) => value.trim())
        .filter(Boolean),
    [questionsText],
  );
  const companyValid = Boolean(
    data?.company.name.trim() && data.company.summary.trim(),
  );
  const cardValid = Boolean(
    data?.card.displayName.trim() &&
      data.card.title.trim() &&
      slugPattern.test(data.card.slug) &&
      questions.length <= 6 &&
      questions.every((value) => value.length <= 200),
  );

  const updateCompany = (field: keyof CompanyProfileInput, value: string) => {
    setData((current) =>
      current
        ? {
            ...current,
            completed: false,
            company: { ...current.company, [field]: value },
          }
        : current,
    );
    setSaveError(undefined);
  };

  const updateCard = (field: keyof CardSettingsInput, value: string) => {
    setData((current) =>
      current
        ? {
            ...current,
            completed: false,
            card: { ...current.card, [field]: value },
          }
        : current,
    );
    setSaveError(undefined);
  };

  const next = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (step === 1 && companyValid) {
      setAttempted(false);
      setStep(2);
    } else if (step === 2 && cardValid) {
      setAttempted(false);
      setStep(3);
    }
  };

  const publish = async () => {
    if (!data || !companyValid || !cardValid || saving) return;
    setSaving(true);
    setSaveError(undefined);
    try {
      await adminApi.updateCompanyProfile(data.company);
      await adminApi.updateCard({
        ...data.card,
        suggestedQuestions: questions,
      });
      await adminApi.completeEnterpriseSetup();
      setData((current) =>
        current ? { ...current, completed: true } : current,
      );
    } catch (error) {
      setSaveError(toApiError(error));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <main className="setup-page">
        <section className="setup-shell">
          <ResourceState status="loading" />
        </section>
      </main>
    );
  }

  if (loadError || !data) {
    return (
      <main className="setup-page">
        <section className="setup-shell">
          <ResourceState
            status="error"
            title="暂时无法读取开通资料"
            description={loadError?.message}
            errorCode={loadError?.code}
            requestId={loadError?.requestId}
            onRetry={load}
          />
        </section>
      </main>
    );
  }

  return (
    <main className="setup-page">
      <section className="setup-shell" aria-labelledby="setup-title">
        <header className="setup-header">
          <div className="setup-brand-mark" aria-hidden="true">
            <Sparkle24Regular />
          </div>
          <div>
            <span>企业微信名片工作台</span>
            <h1 id="setup-title">完善企业数智名片</h1>
            <p>只需三步，资料将同步到企业展示页与 AI 助手。</p>
          </div>
        </header>

        <ol className="setup-progress" aria-label="开通进度">
          {([
            [1, "企业"],
            [2, "名片与 AI"],
            [3, "发布"],
          ] as const).map(([number, label]) => (
            <li
              key={number}
              className={step === number ? "active" : step > number ? "done" : ""}
              aria-current={step === number ? "step" : undefined}
            >
              <span>{step > number ? <Checkmark24Regular /> : number}</span>
              <b>{label}</b>
            </li>
          ))}
        </ol>

        {step === 1 && (
          <form className="setup-form" onSubmit={next} noValidate>
            <div className="setup-section-heading">
              <Building24Regular />
              <div>
                <h2>企业公开资料</h2>
                <p>这些信息会用于名片首页和 AI 回答中的企业身份。</p>
              </div>
            </div>
            <Field
              label="企业名称"
              required
              validationState={attempted && !data.company.name.trim() ? "error" : "none"}
              validationMessage={attempted && !data.company.name.trim() ? "请输入企业名称。" : undefined}
            >
              <Input
                size="large"
                value={data.company.name}
                onChange={(_, value) => updateCompany("name", value.value)}
              />
            </Field>
            <Field
              label="企业简介"
              required
              hint="建议用 2–4 句说清业务、客户和核心价值。"
              validationState={attempted && !data.company.summary.trim() ? "error" : "none"}
              validationMessage={attempted && !data.company.summary.trim() ? "请输入企业简介。" : undefined}
            >
              <Textarea
                value={data.company.summary}
                onChange={(_, value) => updateCompany("summary", value.value)}
                rows={5}
                resize="vertical"
              />
            </Field>
            <div className="setup-grid">
              <Field label="所属行业">
                <Input value={data.company.industry} onChange={(_, value) => updateCompany("industry", value.value)} />
              </Field>
              <Field label="所在地区">
                <Input value={data.company.region} onChange={(_, value) => updateCompany("region", value.value)} />
              </Field>
            </div>
            <Field label="企业官网">
              <Input type="url" placeholder="https://" value={data.company.website} onChange={(_, value) => updateCompany("website", value.value)} />
            </Field>
            <Field label="Logo 图片地址" hint="可先留空，后续在企业资料中补充。">
              <Input type="url" placeholder="https://" value={data.company.logoUrl} onChange={(_, value) => updateCompany("logoUrl", value.value)} />
            </Field>
            <div className="setup-actions">
              <Button type="submit" appearance="primary" size="large" icon={<ArrowRight24Regular />} iconPosition="after">
                下一步
              </Button>
            </div>
          </form>
        )}

        {step === 2 && (
          <form className="setup-form" onSubmit={next} noValidate>
            <div className="setup-section-heading">
              <ContactCard24Regular />
              <div>
                <h2>名片与 AI 助手</h2>
                <p>设置访客看到的身份，以及 AI 首次对话的引导内容。</p>
              </div>
            </div>
            <div className="setup-grid">
              <Field label="展示姓名" required validationState={attempted && !data.card.displayName.trim() ? "error" : "none"}>
                <Input size="large" value={data.card.displayName} onChange={(_, value) => updateCard("displayName", value.value)} />
              </Field>
              <Field label="职务" required validationState={attempted && !data.card.title.trim() ? "error" : "none"}>
                <Input size="large" value={data.card.title} onChange={(_, value) => updateCard("title", value.value)} />
              </Field>
            </div>
            <Field
              label="名片公开标识"
              required
              hint="用于 /c/后的地址，仅允许小写字母、数字和连字符。"
              validationState={attempted && !slugPattern.test(data.card.slug) ? "error" : "none"}
              validationMessage={attempted && !slugPattern.test(data.card.slug) ? "请输入 3–96 位有效标识。" : undefined}
            >
              <Input value={data.card.slug} onChange={(_, value) => updateCard("slug", value.value.toLowerCase().replace(/\s+/g, "-"))} />
            </Field>
            <Field label="个人头像地址" hint="可使用企业微信授权头像，也可后续在名片管理中上传。">
              <Input type="url" placeholder="https://" value={data.card.avatarUrl} onChange={(_, value) => updateCard("avatarUrl", value.value)} />
            </Field>
            <Field label="AI 助手名称">
              <Input value={data.card.assistantName} onChange={(_, value) => updateCard("assistantName", value.value)} />
            </Field>
            <Field label="AI 欢迎语">
              <Textarea value={data.card.welcomeMessage} onChange={(_, value) => updateCard("welcomeMessage", value.value)} rows={4} resize="vertical" />
            </Field>
            <Field
              label="访客推荐问题"
              hint="每行一个，最多 6 个。AI 仍可回答其他问题。"
              validationState={attempted && !cardValid ? "error" : "none"}
            >
              <Textarea value={questionsText} onChange={(_, value) => setQuestionsText(value.value)} rows={5} resize="vertical" />
            </Field>
            <div className="setup-actions split">
              <Button type="button" size="large" icon={<ArrowLeft24Regular />} onClick={() => { setAttempted(false); setStep(1); }}>上一步</Button>
              <Button type="submit" appearance="primary" size="large" icon={<ArrowRight24Regular />} iconPosition="after">预览发布</Button>
            </div>
          </form>
        )}

        {step === 3 && (
          <section className="setup-review">
            <div className="setup-section-heading">
              <CheckmarkCircle24Regular />
              <div>
                <h2>{data.completed ? "名片已完成开通" : "确认后即可发布"}</h2>
                <p>{data.completed ? "资料已写入企业工作台，可继续完善内容或分享名片。" : "请检查企业身份与公开地址，发布后仍可修改。"}</p>
              </div>
            </div>

            <div className="setup-review-card">
              <div className="setup-review-brand">
                <span>{data.company.logoUrl ? <img src={data.company.logoUrl} alt="" /> : <Building24Regular />}</span>
                <div>
                  <small>企业数智名片</small>
                  <h3>{data.company.name}</h3>
                  <p>{data.company.industry || "行业待补充"}{data.company.region ? ` · ${data.company.region}` : ""}</p>
                </div>
              </div>
              <p className="setup-review-summary">{data.company.summary}</p>
              <dl>
                <div><dt>名片人</dt><dd>{data.card.displayName} · {data.card.title}</dd></div>
                <div><dt>AI 助手</dt><dd>{data.card.assistantName || "企业 AI 助手"}</dd></div>
                <div><dt>公开地址</dt><dd>/c/{data.card.slug}</dd></div>
              </dl>
            </div>

            <FormFeedback
              success={data.completed ? "企业资料和名片已完成发布。" : undefined}
              error={saveError}
            />

            <div className="setup-actions split">
              {!data.completed && (
                <Button type="button" size="large" icon={<ArrowLeft24Regular />} onClick={() => setStep(2)} disabled={saving}>返回修改</Button>
              )}
              {data.completed ? (
                <>
                  <Button size="large" onClick={() => navigate(APP_PATHS.knowledge)}>补充知识库</Button>
                  <Button as="a" appearance="primary" size="large" icon={<Open24Regular />} href={publicCardUrl(data.card.slug)} target="_blank">打开名片</Button>
                </>
              ) : (
                <Button appearance="primary" size="large" icon={<CheckmarkCircle24Regular />} onClick={() => void publish()} disabled={saving}>
                  {saving ? "正在发布" : "确认并发布"}
                </Button>
              )}
            </div>
            {data.completed && (
              <a className="setup-dashboard-link" href={appHref(APP_PATHS.overview)}>进入业务概览</a>
            )}
          </section>
        )}
      </section>
    </main>
  );
}

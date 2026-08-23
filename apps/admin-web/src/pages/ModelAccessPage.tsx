import {
  Button,
  Dropdown,
  Field,
  Input,
  Option,
  Radio,
  RadioGroup,
  Switch,
} from "@fluentui/react-components";
import { Save24Regular } from "@fluentui/react-icons";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { EnterpriseLlmAccess, EnterpriseLlmProfileOption } from "../api/types";
import { FormFeedback } from "../components/FormFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";

type FormState = EnterpriseLlmAccess & { apiKey: string };

export function ModelAccessPage() {
  const [access, setAccess] = useState<FormState>();
  const [options, setOptions] = useState<EnterpriseLlmProfileOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<ApiError>();
  const [success, setSuccess] = useState<string>();

  const load = async () => {
    setLoading(true);
    setError(undefined);
    try {
      const [nextAccess, nextOptions] = await Promise.all([
        adminApi.getEnterpriseLlmAccess(),
        adminApi.listEnterpriseLlmOptions(),
      ]);
      setAccess({ ...nextAccess, apiKey: "" });
      setOptions(nextOptions);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("模型接入设置加载失败。", { code: "UNKNOWN_ERROR" }));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);
  const selected = useMemo(
    () => options.find((option) => option.id === access?.platformProfileId),
    [access?.platformProfileId, options],
  );

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!access || saving) return;
    setSaving(true); setError(undefined); setSuccess(undefined);
    try {
      const updated = await adminApi.updateEnterpriseLlmAccess({
        platformProfileId: access.platformProfileId,
        mode: access.mode,
        dailyBudgetCny: access.dailyBudgetCny,
        expectedVersion: access.version,
        apiKey: access.apiKey || undefined,
        enabled: access.enabled,
      });
      setAccess({ ...updated, apiKey: "" });
      setSuccess("模型接入设置已保存，新的请求会直接采用该配置。 ");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("模型接入设置保存失败。", { code: "UNKNOWN_ERROR" }));
    } finally { setSaving(false); }
  };

  const test = async () => {
    if (!access || testing) return;
    setTesting(true); setError(undefined); setSuccess(undefined);
    try {
      const result = await adminApi.testEnterpriseLlmAccess(access.apiKey || undefined);
      setSuccess(result.status === "succeeded" ? `连接成功，耗时 ${result.latencyMs} ms。` : `连接失败：${result.errorCode ?? "上游不可用"}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("模型连接测试失败。", { code: "UNKNOWN_ERROR" }));
    } finally { setTesting(false); }
  };

  return (
    <main className="page-stack">
      <PageHeader title="模型接入" description="选择平台批准的模型；可以使用平台托管额度，也可以仅替换为本企业加密保存的 API Key。回答边界仍在“回答策略”中管理。" />
      {loading || !access ? (
        <section className="content-panel"><ResourceState status={loading ? "loading" : "error"} title={error?.message} errorCode={error?.code} onRetry={() => void load()} /></section>
      ) : (
        <form className="content-panel form-panel" onSubmit={submit}>
          <div className="form-section-heading"><div><h2>企业模型来源</h2><p>平台控制 Provider、模型白名单和预算上限；企业不能填写任意 Base URL。</p></div></div>
          <FormFeedback success={success} error={error} />
          <Field label="平台批准的模型" hint={selected ? `${selected.provider} · ${selected.model} · 每日上限 ¥${selected.dailyBudgetCeilingCny}` : undefined}>
            <Dropdown value={selected?.name ?? ""} selectedOptions={[access.platformProfileId]} onOptionSelect={(_, data) => {
              const profile = options.find((option) => option.id === data.optionValue);
              if (profile) setAccess((current) => current ? { ...current, platformProfileId: profile.id, profileName: profile.name, provider: profile.provider, baseUrl: profile.baseUrl, model: profile.model, platformBudgetCeilingCny: profile.dailyBudgetCeilingCny, dailyBudgetCny: Math.min(current.dailyBudgetCny, profile.dailyBudgetCeilingCny) } : current);
            }}>
              {options.map((option) => {
                const label = `${option.name}${option.isDefault ? "（平台默认）" : ""}`;
                return <Option key={option.id} value={option.id} text={label}>{label}</Option>;
              })}
            </Dropdown>
          </Field>
          <Field label="使用方式">
            <RadioGroup value={access.mode} onChange={(_, data) => setAccess((current) => current ? { ...current, mode: data.value as EnterpriseLlmAccess["mode"] } : current)}>
              <Radio value="platform_managed" label="平台托管额度——使用平台已保存的密钥" />
              <Radio value="byok" label="企业自有 API Key——密钥加密保存，平台不回显" />
            </RadioGroup>
          </Field>
          {access.mode === "byok" && <Field label="企业 API Key" hint={access.keyConfigured ? `已配置 ${access.keyHint ?? "加密密钥"}；留空表示保留原密钥。` : "首次启用必须填写。"}><Input type="password" autoComplete="new-password" value={access.apiKey} onChange={(_, data) => setAccess((current) => current ? { ...current, apiKey: data.value } : current)} /></Field>}
          <Field label="每日预算（人民币）" hint={`不能超过平台上限 ¥${access.platformBudgetCeilingCny}`}><Input type="number" min={0} max={access.platformBudgetCeilingCny} value={String(access.dailyBudgetCny)} onChange={(_, data) => setAccess((current) => current ? { ...current, dailyBudgetCny: Number(data.value) } : current)} /></Field>
          <Switch checked={access.enabled} label="启用企业模型接入" onChange={(_, data) => setAccess((current) => current ? { ...current, enabled: data.checked } : current)} />
          <div className="form-actions"><Button type="button" onClick={() => void test()} disabled={testing}>{testing ? "正在测试" : "测试连接"}</Button><Button type="submit" appearance="primary" icon={<Save24Regular />} disabled={saving}>{saving ? "正在保存" : "保存模型接入"}</Button></div>
        </form>
      )}
    </main>
  );
}

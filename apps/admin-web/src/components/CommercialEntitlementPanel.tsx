import {
  Button,
  Field,
  Input,
  MessageBar,
  MessageBarBody,
  Select,
  Spinner,
  Switch,
} from "@fluentui/react-components";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../api/client";
import { platformApi } from "../api/platformApi";
import type {
  CommercialBillingCycle,
  CommercialPlanCode,
} from "../api/types";
import { useResource } from "../hooks/useResource";
import styles from "../pages/PlatformEnterpriseDrawer.module.css";

const planRank: Record<CommercialPlanCode, number> = {
  starter: 10,
  professional: 20,
  enterprise: 30,
};

export function CommercialEntitlementPanel({
  companyId,
  onChanged,
}: {
  companyId: string;
  onChanged?: () => void;
}) {
  const resource = useResource(
    () => platformApi.getEnterpriseEntitlements(companyId),
    companyId,
  );
  const [planCode, setPlanCode] = useState<CommercialPlanCode>("starter");
  const [billingCycle, setBillingCycle] = useState<CommercialBillingCycle>("contract");
  const [price, setPrice] = useState("");
  const [overrides, setOverrides] = useState<Record<string, boolean>>({});
  const [limitOverrides, setLimitOverrides] = useState<Record<string, number | null>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError>();

  useEffect(() => {
    const value = resource.data;
    if (!value) return;
    setPlanCode(value.planCode);
    setBillingCycle(value.billingCycle);
    setPrice(value.contractPriceCny === undefined ? "" : String(value.contractPriceCny));
    setOverrides(value.featureOverrides);
    setLimitOverrides(value.limitOverrides);
  }, [resource.data]);

  const groups = useMemo(() => {
    const values = resource.data?.featureCatalog ?? [];
    return Array.from(new Set(values.map((feature) => feature.group))).map((group) => ({
      group,
      features: values.filter((feature) => feature.group === group),
    }));
  }, [resource.data]);

  const isEnabled = (
    featureId: string,
    minimumPlan: CommercialPlanCode,
    overrideable: boolean,
  ) => {
    if (!overrideable) return true;
    return overrides[featureId] ?? planRank[planCode] >= planRank[minimumPlan];
  };

  const save = async () => {
    const current = resource.data;
    if (!current || saving) return;
    const parsedPrice = price.trim() === "" ? undefined : Number(price);
    if (parsedPrice !== undefined && (!Number.isFinite(parsedPrice) || parsedPrice < 0)) {
      setError(new ApiError("合同价格必须是大于等于 0 的数字。", { code: "VALIDATION_ERROR" }));
      return;
    }
    setSaving(true);
    setError(undefined);
    try {
      const updated = await platformApi.updateEnterpriseEntitlements(companyId, {
        expectedVersion: current.companyVersion,
        planCode,
        billingCycle,
        contractPriceCny: parsedPrice,
        featureOverrides: overrides,
        limitOverrides,
      });
      setPlanCode(updated.planCode);
      setBillingCycle(updated.billingCycle);
      setPrice(updated.contractPriceCny === undefined ? "" : String(updated.contractPriceCny));
      setOverrides(updated.featureOverrides);
      setLimitOverrides(updated.limitOverrides);
      resource.reload();
      onChanged?.();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError("企业商业授权保存失败。", { code: "UNKNOWN_ERROR" }),
      );
    } finally {
      setSaving(false);
    }
  };

  if (resource.status === "loading") {
    return <Spinner size="tiny" label="正在读取套餐授权" />;
  }
  if (resource.status !== "ready" || !resource.data) {
    return (
      <MessageBar intent="error">
        <MessageBarBody>{resource.error?.message ?? "商业授权暂不可用。"}</MessageBarBody>
      </MessageBar>
    );
  }
  const entitlement = resource.data;

  return (
    <div className={styles.entitlementPanel}>
      {error ? (
        <MessageBar intent="error">
          <MessageBarBody>{error.message}</MessageBarBody>
        </MessageBar>
      ) : null}
      <div className={styles.entitlementFields}>
        <Field label="套餐版本">
          <Select
            value={planCode}
            onChange={(event) => setPlanCode(event.target.value as CommercialPlanCode)}
          >
            {entitlement.plans.map((plan) => (
              <option key={plan.code} value={plan.code}>{plan.name} · {plan.description}</option>
            ))}
          </Select>
        </Field>
        <Field label="计费周期">
          <Select
            value={billingCycle}
            onChange={(event) => setBillingCycle(event.target.value as CommercialBillingCycle)}
          >
            <option value="contract">按合同</option>
            <option value="monthly">按月</option>
            <option value="yearly">按年</option>
          </Select>
        </Field>
        <Field label="合同价格（元）" hint="留空表示由外部合同或账单系统管理。">
          <Input
            type="number"
            min="0"
            step="0.01"
            value={price}
            onChange={(_, data) => setPrice(data.value)}
          />
        </Field>
      </div>

      <div className={styles.entitlementGroups}>
        <div className={styles.entitlementSectionHeading}>
          <div><h3>功能授权</h3><p>套餐提供默认值，企业覆盖可单独打开或关闭。</p></div>
          <span>{entitlement.featureCatalog.length} 项能力</span>
        </div>
        {groups.map(({ group, features }) => (
          <div className={styles.entitlementGroup} key={group}>
            <h4>{group}</h4>
            {features.map((feature) => {
              const enabled = isEnabled(
                feature.id,
                feature.minimumPlan,
                feature.overrideable,
              );
              const overridden = Object.prototype.hasOwnProperty.call(overrides, feature.id);
              return (
                <div className={styles.entitlementFeature} key={feature.id}>
                  <div>
                    <strong>{feature.name}</strong>
                    <p>{feature.description}</p>
                    <small>
                      {feature.overrideable
                        ? overridden ? "企业单独覆盖" : "跟随套餐"
                        : "系统必需能力"}
                    </small>
                  </div>
                  <div className={styles.entitlementControl}>
                    {overridden ? (
                      <Button
                        size="small"
                        appearance="transparent"
                        onClick={() => {
                          const next = { ...overrides };
                          delete next[feature.id];
                          setOverrides(next);
                        }}
                      >
                        跟随套餐
                      </Button>
                    ) : null}
                    <Switch
                      checked={enabled}
                      disabled={!feature.overrideable || saving}
                      aria-label={`${enabled ? "关闭" : "打开"}${feature.name}`}
                      onChange={(_, data) => setOverrides((current) => ({
                        ...current,
                        [feature.id]: data.checked,
                      }))}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <div className={styles.entitlementGroups}>
        <div className={styles.entitlementSectionHeading}>
          <div><h3>套餐额度</h3><p>可跟随套餐、设为不限，或为签约企业配置专属额度。</p></div>
          <span>{entitlement.limitCatalog.length} 项指标</span>
        </div>
        {Array.from(new Set(entitlement.limitCatalog.map((limit) => limit.group))).map((group) => (
          <div className={styles.entitlementGroup} key={group}>
            <h4>{group}</h4>
            {entitlement.limitCatalog.filter((limit) => limit.group === group).map((limit) => {
              const overridden = Object.prototype.hasOwnProperty.call(limitOverrides, limit.id);
              const override = limitOverrides[limit.id];
              const planDefault = limit.planDefaults[planCode];
              const effective = overridden ? override : planDefault;
              const mode = !overridden ? "plan" : override === null ? "unlimited" : "custom";
              return (
                <div className={styles.entitlementFeature} key={limit.id}>
                  <div>
                    <strong>{limit.name}</strong>
                    <p>{limit.description}</p>
                    <small>当前生效：{effective === null ? "不限" : `${effective.toLocaleString()} ${limit.unit}`}</small>
                  </div>
                  <div className={styles.entitlementLimitControl}>
                    <Select
                      aria-label={`${limit.name}额度模式`}
                      value={mode}
                      disabled={saving}
                      onChange={(event) => {
                        const nextMode = event.target.value;
                        if (nextMode === "plan") {
                          setLimitOverrides((current) => {
                            const next = { ...current };
                            delete next[limit.id];
                            return next;
                          });
                        } else if (nextMode === "unlimited") {
                          setLimitOverrides((current) => ({ ...current, [limit.id]: null }));
                        } else {
                          setLimitOverrides((current) => ({
                            ...current,
                            [limit.id]: typeof current[limit.id] === "number"
                              ? current[limit.id]
                              : planDefault ?? 0,
                          }));
                        }
                      }}
                    >
                      <option value="plan">跟随套餐</option>
                      <option value="custom">自定义</option>
                      <option value="unlimited">不限</option>
                    </Select>
                    {mode === "custom" ? (
                      <Input
                        className={styles.entitlementLimitInput}
                        type="number"
                        min="0"
                        step="1"
                        aria-label={`${limit.name}自定义额度`}
                        value={String(override ?? 0)}
                        onChange={(_, data) => {
                          const parsed = Number(data.value);
                          if (Number.isInteger(parsed) && parsed >= 0) {
                            setLimitOverrides((current) => ({ ...current, [limit.id]: parsed }));
                          }
                        }}
                      />
                    ) : null}
                    <span>{limit.unit}</span>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <div className={styles.entitlementActions}>
        <span>保存后功能开关立即生效；额度将作为企业资源与用量控制基准。</span>
        <Button appearance="primary" disabled={saving} onClick={() => void save()}>
          {saving ? "正在保存" : "保存全部商业授权"}
        </Button>
      </div>
    </div>
  );
}

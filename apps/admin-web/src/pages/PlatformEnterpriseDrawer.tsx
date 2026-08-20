import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  DrawerBody,
  DrawerHeader,
  DrawerHeaderTitle,
  OverlayDrawer,
  ProgressBar,
  Field,
  Textarea,
} from "@fluentui/react-components";
import { Dismiss24Regular, Open24Regular } from "@fluentui/react-icons";
import { useState } from "react";
import type { RefObject } from "react";

import { ApiError } from "../api/client";
import { platformApi } from "../api/platformApi";
import type { PlatformCardProjection } from "../api/types";
import { FormFeedback } from "../components/FormFeedback";
import { CommercialEntitlementPanel } from "../components/CommercialEntitlementPanel";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";
import styles from "./PlatformEnterpriseDrawer.module.css";

type PlatformEnterpriseDrawerProps = {
  companyId: string;
  onClose: () => void;
  onChanged?: () => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
};

function onboardingLabel(status: string): string {
  if (["completed", "active"].includes(status)) return "已完成入驻";
  if (status === "content_pending") return "待完善资料";
  if (status === "initialized") return "空间已初始化";
  return status;
}

const businessProfileLabels: Record<string, string> = {
  business_positioning: "业务定位",
  products_services: "产品与服务",
  target_customers: "目标客户与场景",
  customer_pain_points: "客户痛点",
  core_capabilities: "核心能力",
  business_model: "业务与交付模式",
  differentiators: "可验证差异点",
  business_directions: "明确业务方向",
  sales_opening: "建议业务开场",
  evidence_conflicts: "资料冲突与待确认项",
  missing_information: "待补资料",
};

function PlatformCardGroup({
  label,
  cards,
}: {
  label: string;
  cards: PlatformCardProjection[];
}) {
  return (
    <div className={styles.cardGroup}>
      <div className={styles.cardGroupHeader}>
        <strong>{label}</strong>
        <span>{cards.length} 张</span>
      </div>
      {cards.length > 0 ? (
        <div className={styles.cardList}>
          {cards.map((card) => (
            <article className={styles.cardItem} key={card.id}>
              <div className={styles.cardCopy}>
                <h4>{card.displayName}</h4>
                <p>
                  {card.title ||
                    (card.cardKind === "enterprise" ? "未填写业务定位" : "未填写职务")}
                </p>
                <div className={styles.cardMeta}>
                  <StatusBadge status={card.status} />
                  <span>{formatTimestamp(card.updatedAt)}</span>
                </div>
              </div>
              {card.status === "published" && card.shareUrl ? (
                <Button
                  as="a"
                  href={card.shareUrl}
                  target="_blank"
                  rel="noreferrer"
                  appearance="secondary"
                  icon={<Open24Regular />}
                  aria-label={`打开${card.displayName}${
                    card.cardKind === "enterprise" ? "企业" : "员工"
                  }名片`}
                >
                  打开名片
                </Button>
              ) : (
                <span className={styles.noLink}>发布后可访问</span>
              )}
            </article>
          ))}
        </div>
      ) : (
        <p className={styles.noLink}>暂无{label}。</p>
      )}
    </div>
  );
}

export function PlatformEnterpriseDrawer({
  companyId,
  onClose,
  onChanged,
  returnFocusRef,
}: PlatformEnterpriseDrawerProps) {
  const resource = useResource(
    () => platformApi.getEnterpriseDetail(companyId),
    companyId,
  );
  const [lifecycleOpen, setLifecycleOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [lifecycleError, setLifecycleError] = useState<ApiError>();

  const close = () => {
    onClose();
    globalThis.setTimeout(() => returnFocusRef?.current?.focus(), 0);
  };

  const detail = resource.data;
  const targetStatus = detail?.status === "active" ? "suspended" : "active";
  const lifecycleLabel = targetStatus === "suspended" ? "暂停企业" : "恢复企业";
  const transition = async () => {
    if (!detail || saving || reason.trim().length < 3) return;
    setSaving(true);
    setLifecycleError(undefined);
    try {
      await platformApi.transitionEnterprise(detail.companyId, {
        expectedVersion: detail.version,
        targetStatus,
        reason,
      });
      setLifecycleOpen(false);
      setReason("");
      resource.reload();
      onChanged?.();
    } catch (caught) {
      setLifecycleError(
        caught instanceof ApiError
          ? caught
          : new ApiError("企业状态变更失败。", { code: "UNKNOWN_ERROR" }),
      );
    } finally {
      setSaving(false);
    }
  };
  const metrics = detail
    ? [
        ["企业成员", detail.employeeCount],
        ["全部名片", detail.cardCount],
        ["已发布名片", detail.publishedCardCount],
        ["近 30 天访问", detail.visits30d],
        ["近 30 天对话", detail.conversations30d],
        ["近 30 天线索", detail.leads30d],
      ] as const
    : [];
  const enterpriseCards = detail?.cards.filter((card) => card.cardKind === "enterprise") ?? [];
  const employeeCards = detail?.cards.filter((card) => card.cardKind === "employee") ?? [];

  return (
    <OverlayDrawer
      className={styles.drawer}
      position="end"
      size="large"
      open
      aria-label="企业运营详情"
      onOpenChange={(_, data) => !data.open && close()}
    >
      <DrawerHeader>
        <DrawerHeaderTitle
          action={
            <Button
              appearance="subtle"
              icon={<Dismiss24Regular />}
              aria-label="关闭企业详情"
              onClick={close}
            />
          }
        >
          企业详情
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody className={styles.body}>
        {resource.status === "ready" && detail ? (
          <>
            <section className={styles.identity} aria-labelledby="enterprise-detail-name">
              <div className={styles.identityMeta}>
                <StatusBadge status={detail.status} />
                <span>{onboardingLabel(detail.onboardingStatus)}</span>
              </div>
              <h2 id="enterprise-detail-name">{detail.companyName}</h2>
              <p>
                {detail.tenantName} · {detail.tenantSlug}
              </p>
              <div className={styles.identityMeta}>
                <span>开通于 {formatTimestamp(detail.createdAt)}</span>
                <span>更新于 {formatTimestamp(detail.updatedAt)}</span>
              </div>
            </section>

            <section className={styles.section} aria-labelledby="profile-progress-title">
              <div className={styles.sectionHeader}>
                <h3 id="profile-progress-title">资料完善度</h3>
                <strong>{detail.profileCompletion}%</strong>
              </div>
              <ProgressBar
                value={detail.profileCompletion / 100}
                aria-label={`资料完善度 ${detail.profileCompletion}%`}
              />
            </section>

            <section className={styles.section} aria-labelledby="enterprise-metrics-title">
              <div className={styles.sectionHeader}>
                <h3 id="enterprise-metrics-title">运营聚合</h3>
              </div>
              <dl className={styles.metrics}>
                {metrics.map(([label, value]) => (
                  <div className={styles.metric} key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </section>

            <section className={styles.section} aria-labelledby="enterprise-entitlements-title">
              <div className={styles.sectionHeader}>
                <div>
                  <h3 id="enterprise-entitlements-title">套餐与功能授权</h3>
                  <p>套餐提供默认能力；单功能开关可针对该企业覆盖。</p>
                </div>
              </div>
              <CommercialEntitlementPanel
                companyId={detail.companyId}
                onChanged={() => {
                  resource.reload();
                  onChanged?.();
                }}
              />
            </section>

            <section className={styles.section} aria-labelledby="enterprise-business-title">
              <div className={styles.sectionHeader}>
                <div>
                  <h3 id="enterprise-business-title">资料归纳业务画像</h3>
                  <p>来自建企资料的待审核归纳，不代表已发布业务承诺。</p>
                </div>
                <span>{detail.businessProfile.length} 项</span>
              </div>
              {detail.businessProfile.length > 0 ? (
                <div className={styles.profileList}>
                  {detail.businessProfile.map((item, index) => (
                    <article key={`${item.field}-${index}`}>
                      <div>
                        <strong>{businessProfileLabels[item.field] ?? item.field}</strong>
                        <span>{item.confidence === undefined ? "待核验" : `${Math.round(item.confidence * 100)}% 置信`}</span>
                      </div>
                      <p>{item.value}</p>
                      <small>来源：{item.sources.map((source) => source.fileName).join("、") || "未标注"}</small>
                    </article>
                  ))}
                </div>
              ) : (
                <p className={styles.noLink}>该企业尚未通过资料辅助建企生成业务画像。</p>
              )}
            </section>

            <section className={styles.section} aria-labelledby="enterprise-cards-title">
              <div className={styles.sectionHeader}>
                <div>
                  <h3 id="enterprise-cards-title">名片发布情况</h3>
                  <p>企业官方名片与员工名片分开查看。</p>
                </div>
                <span>{detail.publishedCardCount} 张已发布</span>
              </div>
              {detail.cards.length > 0 ? (
                <div className={styles.cardGroups}>
                  <PlatformCardGroup label="企业官方名片" cards={enterpriseCards} />
                  <PlatformCardGroup label="员工名片" cards={employeeCards} />
                </div>
              ) : (
                <p>该企业还没有名片。</p>
              )}
            </section>

            {detail.status !== "disabled" && (
              <section className={styles.section} aria-labelledby="enterprise-lifecycle-title">
                <div className={styles.sectionHeader}>
                  <div>
                    <h3 id="enterprise-lifecycle-title">企业状态</h3>
                    <p>
                      暂停后企业账号立即无法登录；恢复不会改动企业资料、名片或导入记录。
                    </p>
                  </div>
                  <Button
                    appearance="secondary"
                    onClick={() => {
                      setLifecycleError(undefined);
                      setLifecycleOpen(true);
                    }}
                  >
                    {lifecycleLabel}
                  </Button>
                </div>
              </section>
            )}
          </>
        ) : (
          <ResourceState
            status={resource.status === "ready" ? "empty" : resource.status}
            title={resource.status === "empty" ? "企业详情暂不可用" : undefined}
            description={resource.error?.message}
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
          />
        )}
      </DrawerBody>
      <Dialog
        open={lifecycleOpen}
        onOpenChange={(_, data) => !saving && setLifecycleOpen(data.open)}
      >
        <DialogSurface>
          <DialogBody>
            <DialogTitle>{lifecycleLabel}</DialogTitle>
            <DialogContent>
              <FormFeedback error={lifecycleError} />
              <p>
                将 {detail?.companyName} 变更为
                {targetStatus === "suspended" ? "暂停" : "正常运营"}状态。
              </p>
              <Field
                label="操作原因"
                required
                validationState={reason.length > 0 && reason.trim().length < 3 ? "error" : "none"}
                validationMessage={
                  reason.length > 0 && reason.trim().length < 3
                    ? "请至少填写 3 个字符。"
                    : undefined
                }
              >
                <Textarea
                  value={reason}
                  maxLength={500}
                  resize="vertical"
                  onChange={(_, data) => setReason(data.value)}
                />
              </Field>
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" disabled={saving} onClick={() => setLifecycleOpen(false)}>
                取消
              </Button>
              <Button
                appearance="primary"
                disabled={saving || reason.trim().length < 3}
                onClick={() => void transition()}
              >
                {saving ? "正在提交" : `确认${lifecycleLabel}`}
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </OverlayDrawer>
  );
}

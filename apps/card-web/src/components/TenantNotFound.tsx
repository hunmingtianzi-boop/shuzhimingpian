import { Buildings, ShieldCheck } from "@phosphor-icons/react";

export type TenantErrorKind = "missing" | "invalid" | "runtime" | "load";

const messages: Record<TenantErrorKind, { title: string; description: string }> = {
  missing: {
    title: "未找到企业名片",
    description: "请检查企业访问地址或 tenant 参数。该企业可能尚未注册、尚未发布，或内容包已下线。",
  },
  invalid: {
    title: "企业内容包未通过校验",
    description: "该企业名片暂时不能安全展示。平台已阻止不完整或冲突的数据进入页面。",
  },
  runtime: {
    title: "页面暂时无法显示",
    description: "加载企业名片时发生异常。你可以重新加载页面，若问题持续出现，请联系平台维护人员。",
  },
  load: {
    title: "名片暂时无法加载",
    description: "公开名片服务暂时不可用。请重新加载页面，若问题持续出现，请稍后再试。",
  },
};

export function TenantNotFound({
  kind = "missing",
  onRetry,
}: {
  kind?: TenantErrorKind;
  onRetry?: () => void;
}) {
  const message = messages[kind];

  return (
    <main className="tenant-error" aria-labelledby="tenant-error-title">
      <div className="tenant-error-panel">
        <span className="tenant-error-icon" aria-hidden="true">
          <Buildings size={30} weight="duotone" />
        </span>
        <p>创非凡数智名片</p>
        <h1 id="tenant-error-title">{message.title}</h1>
        <p className="tenant-error-description">{message.description}</p>
        <div className="tenant-error-safety">
          <ShieldCheck size={19} weight="duotone" aria-hidden="true" />
          <span>系统不会回退到其他企业内容，避免品牌与知识跨租户混用。</span>
        </div>
        {onRetry && (
          <button className="button button-secondary tenant-error-retry" type="button" onClick={onRetry}>
            重新加载
          </button>
        )}
      </div>
    </main>
  );
}

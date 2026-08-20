import { Button, MessageBar, MessageBarBody, Spinner } from "@fluentui/react-components";
import { useState } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { CardPluginCatalog } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useResource } from "../hooks/useResource";

function pluginLabel(pluginId: string) {
  return ({
    "cf.system.identity": "基础名片",
    "cf.card.faq": "常见问题",
    "cf.card.actions": "快捷入口",
  } as Record<string, string>)[pluginId] || pluginId;
}

export function CardPluginPanel() {
  const auth = useAuth();
  const resource = useResource(() => adminApi.listCardPlugins());
  const [pending, setPending] = useState<string>();
  const [error, setError] = useState<ApiError>();

  const update = async (
    catalog: CardPluginCatalog,
    pluginId: string,
    enabled: boolean,
    grants: string[],
  ) => {
    if (pending) return;
    setPending(pluginId);
    setError(undefined);
    try {
      await adminApi.updateCardPlugin(pluginId, catalog.companyVersion, {
        enabled,
        grants: enabled ? grants : [],
      });
      resource.reload();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("更新插件状态失败。"));
    } finally {
      setPending(undefined);
    }
  };

  if (resource.status === "loading") {
    return <section className="content-panel"><Spinner size="tiny" label="正在读取名片插件" /></section>;
  }
  if (resource.status !== "ready" || !resource.data) return null;
  const catalog = resource.data;
  const installations = new Map(
    catalog.installations.map((installation) => [installation.pluginId, installation]),
  );
  return (
    <section className="content-panel catalog-panel" aria-labelledby="card-plugin-title">
      <div className="section-heading-row">
        <div>
          <h2 id="card-plugin-title">名片插件</h2>
          <p>插件按企业启停；已发布快照不会因普通停用被静默改写。</p>
        </div>
      </div>
      {error ? <MessageBar intent="error"><MessageBarBody>{error.message}</MessageBarBody></MessageBar> : null}
      <div className="card-plugin-grid">
        {catalog.releases.map((release) => {
          const installation = installations.get(release.id);
          const enabled = installation?.enabled === true;
          const entitled = auth.entitlements?.features[release.commercialFeatureId] !== false;
          const disabled = release.required || release.status === "killed" || !entitled || Boolean(pending);
          return (
            <article className="card-plugin-item" key={`${release.id}@${release.version}`}>
              <div>
                <strong>{pluginLabel(release.id)}</strong>
                <span>{release.id} · v{release.version}</span>
                <small>
                  {release.required ? "系统插件，不可停用" : release.status === "killed" ? "平台已紧急停用" : !entitled ? "当前套餐未开通" : enabled ? "已启用" : "已停用"}
                </small>
              </div>
              <Button
                appearance={enabled ? "secondary" : "primary"}
                disabled={disabled}
                onClick={() => void update(catalog, release.id, !enabled, release.permissions)}
              >
                {pending === release.id ? "处理中" : enabled ? "停用" : "启用"}
              </Button>
            </article>
          );
        })}
      </div>
    </section>
  );
}

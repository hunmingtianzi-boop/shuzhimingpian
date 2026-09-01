import { Button, MessageBar, MessageBarBody } from "@fluentui/react-components";
import { Add24Regular } from "@fluentui/react-icons";
import { useState } from "react";

import type { EnterpriseTemplateThemeKey, ManagedCard } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { CardTemplateLibraryPanel } from "../pages/CardsPage";

export function StandaloneCardsManagement() {
  const [selection, setSelection] = useState<string>();

  const selectTemplate = (
    kind: ManagedCard["cardKind"],
    themeKey: EnterpriseTemplateThemeKey,
  ) => {
    setSelection(`${kind === "employee" ? "员工" : "企业"}默认配置已选择 ${themeKey === "executive" ? "黑金商务名片" : "当前模板"}`);
  };

  return (
    <main className="page-stack standalone-card-management-preview">
      <PageHeader
        title="企业与员工名片"
        description="创建、设计、发布与分享企业官方名片和员工名片。"
        actions={(
          <div className="row-actions">
            <Button appearance="primary" icon={<Add24Regular />}>新建企业名片</Button>
            <Button appearance="secondary" icon={<Add24Regular />}>新建员工名片</Button>
          </div>
        )}
      />

      {selection ? (
        <MessageBar intent="success">
          <MessageBarBody>{selection}</MessageBarBody>
        </MessageBar>
      ) : null}

      <CardTemplateLibraryPanel canManageEnterpriseCards onSelect={selectTemplate} />

      <section className="content-panel catalog-panel catalog-section-panel">
        <div className="section-heading-row">
          <div>
            <h2>企业官方名片</h2>
            <p>企业官方公开主页，可由企业管理员独立发布。</p>
          </div>
        </div>
        <div className="catalog-empty-inline">
          <p>选择上方模板后，可继续创建企业名片或设置默认页面。</p>
        </div>
      </section>

      <section className="content-panel catalog-panel catalog-section-panel">
        <div className="section-heading-row">
          <div>
            <h2>员工名片</h2>
            <p>绑定具体企业成员，用于个人对外展示与客户跟进。</p>
          </div>
        </div>
        <div className="catalog-empty-inline">
          <p>黑金商务名片适合作为高管与商务负责人的默认模板。</p>
        </div>
      </section>
    </main>
  );
}

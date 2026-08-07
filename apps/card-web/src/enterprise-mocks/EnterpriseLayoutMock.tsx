import { lazy, Suspense } from "react";

import type { EnterpriseCardConfig } from "../domain/card";
import type { PublicCardData } from "../lib/publicCardApi";
import "./enterprise-mock-base.css";
import {
  type EnterpriseMockLayout,
  useEnterpriseMockContent,
} from "./model";

const SummaryEnterpriseMock = lazy(() =>
  import("./SummaryEnterpriseMock").then((module) => ({
    default: module.SummaryEnterpriseMock,
  })),
);
const AccordionEnterpriseMock = lazy(() =>
  import("./AccordionEnterpriseMock").then((module) => ({
    default: module.AccordionEnterpriseMock,
  })),
);
const IntentEnterpriseMock = lazy(() =>
  import("./IntentEnterpriseMock").then((module) => ({
    default: module.IntentEnterpriseMock,
  })),
);

const layoutLabels: Record<EnterpriseMockLayout, string> = {
  summary: "名片首页与详情层",
  accordion: "单页折叠导航",
  intent: "访客意图分流",
};

export function EnterpriseLayoutMock({
  layout,
  tenant,
  card,
  onAssistant,
  onLead,
}: {
  layout: EnterpriseMockLayout;
  tenant: EnterpriseCardConfig;
  card?: PublicCardData;
  onAssistant: (question?: string) => void;
  onLead: () => void;
}) {
  const content = useEnterpriseMockContent(tenant, card);
  const props = { content, onAssistant, onLead };

  return (
    <Suspense
      fallback={
        <main className="em-site em-loading" aria-busy="true">
          正在打开“{layoutLabels[layout]}”模拟方案…
        </main>
      }
    >
      {layout === "summary" && <SummaryEnterpriseMock {...props} />}
      {layout === "accordion" && <AccordionEnterpriseMock {...props} />}
      {layout === "intent" && <IntentEnterpriseMock {...props} />}
    </Suspense>
  );
}

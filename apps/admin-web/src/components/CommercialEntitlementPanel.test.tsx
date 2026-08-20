import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { platformApi } from "../api/platformApi";
import type { CommercialEntitlements } from "../api/types";
import { CommercialEntitlementPanel } from "./CommercialEntitlementPanel";

const entitlement: CommercialEntitlements = {
  companyId: "company-1",
  companyVersion: 7,
  planCode: "professional",
  billingCycle: "contract",
  featureOverrides: {},
  features: { "card.core": true, "data.exports": false },
  limitOverrides: {},
  limits: { "members.max": 50 },
  plans: [
    { code: "starter", name: "基础版", description: "基础能力" },
    { code: "professional", name: "专业版", description: "AI 与知识" },
    { code: "enterprise", name: "企业版", description: "高级经营" },
  ],
  featureCatalog: [
    {
      id: "card.core",
      name: "数智名片",
      group: "名片与内容",
      description: "基础身份展示",
      minimumPlan: "starter",
      overrideable: false,
    },
    {
      id: "data.exports",
      name: "数据导出",
      group: "客户经营",
      description: "访问和线索数据导出",
      minimumPlan: "enterprise",
      overrideable: true,
    },
  ],
  limitCatalog: [
    {
      id: "members.max",
      name: "员工账号数",
      group: "账号与内容",
      description: "企业内可启用的员工账号上限",
      unit: "人",
      planDefaults: { starter: 5, professional: 50, enterprise: null },
    },
  ],
};

afterEach(() => vi.restoreAllMocks());

describe("CommercialEntitlementPanel", () => {
  it("lets platform operators override an individual paid feature", async () => {
    const user = userEvent.setup();
    vi.spyOn(platformApi, "getEnterpriseEntitlements").mockResolvedValue(entitlement);
    const update = vi.spyOn(platformApi, "updateEnterpriseEntitlements").mockResolvedValue({
      ...entitlement,
      companyVersion: 8,
      featureOverrides: { "data.exports": true },
      features: { ...entitlement.features, "data.exports": true },
    });

    render(<CommercialEntitlementPanel companyId="company-1" />);

    await user.click(await screen.findByRole("switch", { name: "打开数据导出" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "员工账号数额度模式" }), "custom");
    await user.clear(screen.getByRole("spinbutton", { name: "员工账号数自定义额度" }));
    await user.type(screen.getByRole("spinbutton", { name: "员工账号数自定义额度" }), "80");
    await user.click(screen.getByRole("button", { name: "保存全部商业授权" }));

    await waitFor(() => {
      expect(update).toHaveBeenCalledWith("company-1", {
        expectedVersion: 7,
        planCode: "professional",
        billingCycle: "contract",
        contractPriceCny: undefined,
        featureOverrides: { "data.exports": true },
        limitOverrides: { "members.max": 80 },
      });
    });
  });
});

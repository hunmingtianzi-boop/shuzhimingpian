import { FluentProvider } from "@fluentui/react-components";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { exportsApi } from "../api/exportsApi";
import { AuthContext } from "../auth/AuthContext";
import { adminLightTheme } from "../theme";
import { ExportsPage } from "./ExportsPage";

const item = {
  id: "export-1",
  exportType: "leads" as const,
  status: "completed" as const,
  includeSensitive: false,
  rowCount: 2,
  fileName: "leads.csv",
  createdAt: "2026-07-12T00:00:00Z",
  completedAt: "2026-07-12T00:01:00Z",
  expiresAt: "2026-07-13T00:01:00Z",
};

function renderPage(role = "company_admin", permissions: string[] = []) {
  return render(
    <FluentProvider theme={adminLightTheme}>
      <AuthContext.Provider value={{
        status: "authenticated",
        user: {
          id: "user-1", displayName: "管理员", membershipId: "membership-1",
          tenantId: "tenant-1", companyId: "company-1", role, permissions,
        },
        loginPending: false,
        apiConfigured: true,
        login: vi.fn(),
        logout: vi.fn(),
      }}>
        <ExportsPage />
      </AuthContext.Provider>
    </FluentProvider>,
  );
}

describe("ExportsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function mockAvailability(
    availability = { visitors: 42, leads: 0, conversations: 42 },
  ) {
    vi.spyOn(exportsApi, "availability").mockResolvedValue({
      ...availability,
      generatedAt: "2026-07-25T00:00:00Z",
    });
  }

  it("creates and downloads a sensitive administrator export with one click", async () => {
    const user = userEvent.setup();
    mockAvailability({ visitors: 42, leads: 2, conversations: 42 });
    vi.spyOn(exportsApi, "list").mockResolvedValue({ items: [item], total: 1, limit: 50, offset: 0 });
    const create = vi.spyOn(exportsApi, "create").mockResolvedValue({
      ...item, id: "export-2", status: "completed",
    });
    const download = vi.spyOn(exportsApi, "download").mockResolvedValue({
      blob: new Blob(["id\r\nlead-1\r\n"], { type: "text/csv" }),
      fileName: "线索.csv",
    });
    const createObjectURL = vi.fn(() => "blob:export-test");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectURL,
    });
    renderPage();

    await screen.findByText("可下载");
    await user.click(screen.getByRole("checkbox", { name: "包含未脱敏联系方式" }));
    await user.click(screen.getByRole("button", { name: "导出线索数据，共 2 条" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith("leads", true));
    await waitFor(() => expect(download).toHaveBeenCalledWith("export-2", "leads.csv"));
    expect(await screen.findByText(/线索 CSV 已生成，下载已开始/)).toBeInTheDocument();
    expect(createObjectURL).toHaveBeenCalled();
  });

  it("disables sensitive export for a card owner", async () => {
    mockAvailability();
    vi.spyOn(exportsApi, "list").mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
    renderPage("card_owner");
    expect(await screen.findByRole("checkbox", { name: "包含未脱敏联系方式" })).toBeDisabled();
  });

  it("shows a permission state when no dataset can be read", async () => {
    mockAvailability({ visitors: 0, leads: 0, conversations: 0 });
    renderPage("auditor");
    expect(await screen.findByText("没有访问权限")).toBeInTheDocument();
  });

  it("makes populated data directly exportable and disables an empty type", async () => {
    mockAvailability({ visitors: 42, leads: 0, conversations: 42 });
    vi.spyOn(exportsApi, "list").mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
    const { container } = renderPage();

    await screen.findByText("当前暂无数据");
    const availabilityButtons = container.querySelectorAll(".export-availability-item");
    expect(availabilityButtons).toHaveLength(3);
    expect(screen.getByRole("button", { name: "导出访客数据，共 42 条" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "导出对话数据，共 42 条" })).toBeEnabled();
    expect(availabilityButtons[1]).toBeDisabled();
    expect(screen.getByRole("button", { name: "线索当前暂无数据" })).toBeDisabled();
  });
});

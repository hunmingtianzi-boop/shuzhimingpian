import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { memberApi } from "../api/memberApi";
import type { AdminUser, CompanyMember } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { adminLightTheme } from "../theme";
import { MembersPage } from "./MembersPage";

vi.mock("../auth/AuthContext", () => ({ useAuth: vi.fn() }));

const admin: AdminUser = {
  id: "user-admin", displayName: "管理员", membershipId: "membership-admin",
  tenantId: "tenant-1", companyId: "company-1", role: "company_admin", permissions: [],
};
const adminMember: CompanyMember = {
  membershipId: "membership-admin", userId: "user-admin", account: "admin@example.test",
  displayName: "管理员", role: "company_admin", permissions: [], status: "active",
  credentialEnabled: true, createdAt: "2026-07-11T00:00:00Z", updatedAt: "2026-07-11T00:00:00Z",
};
const cardOwner: CompanyMember = {
  ...adminMember, membershipId: "membership-member", userId: "user-member",
  account: "member@example.test", displayName: "张三", role: "card_owner", permissions: ["card.read"],
};

function renderPage() {
  return render(<FluentProvider theme={adminLightTheme}><MembersPage /></FluentProvider>);
}

describe("MembersPage", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({ user: admin } as ReturnType<typeof useAuth>);
    vi.spyOn(memberApi, "listMembers").mockResolvedValue({ items: [adminMember, cardOwner], total: 2, limit: 50, offset: 0 });
  });

  afterEach(() => vi.restoreAllMocks());

  it("renders loading then the member list", async () => {
    renderPage();
    expect(screen.getByRole("status", { name: "正在加载" })).toBeInTheDocument();
    expect(await screen.findByText("member@example.test")).toBeInTheDocument();
    expect(screen.getByText("用户总数").nextSibling).toHaveTextContent("2");
  });

  it("shows empty, error and permission states", async () => {
    vi.mocked(memberApi.listMembers).mockResolvedValueOnce({ items: [], total: 0, limit: 50, offset: 0 });
    const empty = renderPage();
    expect(await screen.findByText("尚未创建企业用户")).toBeInTheDocument();
    empty.unmount();

    vi.mocked(memberApi.listMembers).mockRejectedValueOnce(new ApiError("服务离线", { code: "NETWORK_ERROR" }));
    const failed = renderPage();
    expect(await screen.findByText("服务离线")).toBeInTheDocument();
    failed.unmount();

    vi.mocked(useAuth).mockReturnValue({ user: { ...admin, role: "card_owner", permissions: [] } } as unknown as ReturnType<typeof useAuth>);
    renderPage();
    expect(await screen.findByText("没有企业用户管理权限")).toBeInTheDocument();
  });

  it("creates a member with validated form values", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(memberApi, "createMember").mockResolvedValue(cardOwner);
    renderPage();
    await screen.findByText("member@example.test");
    await user.click(screen.getAllByRole("button", { name: "创建用户" }).at(-1)!);
    fireEvent.change(screen.getByRole("textbox", { name: /登录账号/ }), { target: { value: "member2@example.test" } });
    fireEvent.change(screen.getByRole("textbox", { name: /显示姓名/ }), { target: { value: "李四" } });
    fireEvent.change(screen.getByLabelText(/初始密码/), { target: { value: "SecurePassword!2026" } });
    await user.click(screen.getAllByRole("button", { name: "创建用户" }).at(-1)!);
    await waitFor(() => expect(create).toHaveBeenCalledWith(expect.objectContaining({ account: "member2@example.test", displayName: "李四", password: "SecurePassword!2026" })));
  });

  it("confirms an administrator downgrade exactly once and saves it", async () => {
    const user = userEvent.setup();
    const update = vi.spyOn(memberApi, "updateMember").mockResolvedValue({ ...adminMember, role: "card_owner" });
    renderPage();
    await screen.findByText("admin@example.test");
    await user.click(screen.getAllByRole("button", { name: "编辑" })[0]);
    const editor = await screen.findByRole("dialog", { name: "编辑企业用户" });
    const role = within(editor).getByRole("combobox", { name: "角色" });
    await user.selectOptions(role, "card_owner");
    await waitFor(() => expect(role).toHaveValue("card_owner"));
    await user.click(within(editor).getByRole("button", { name: "保存用户" }));
    expect(update).not.toHaveBeenCalled();
    const confirmation = await screen.findByRole("dialog", {
      name: "移除企业管理员角色",
    });
    await user.click(
      within(confirmation).getByRole("button", { name: "确认调整角色" }),
    );
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(update).toHaveBeenCalledWith("membership-admin", expect.objectContaining({ role: "card_owner" }));
  });

  it("confirms status changes and resets passwords with session feedback", async () => {
    const user = userEvent.setup();
    const setStatus = vi.spyOn(memberApi, "setStatus").mockResolvedValue({ ...cardOwner, status: "disabled" });
    const reset = vi.spyOn(memberApi, "resetPassword").mockResolvedValue({ membershipId: "membership-member", passwordChangedAt: "2026-07-12T00:00:00Z", sessionsRevoked: 3 });
    renderPage();
    await screen.findByText("member@example.test");

    await user.click(screen.getAllByRole("button", { name: "停用" })[1]);
    await user.click(screen.getByRole("button", { name: "确认停用" }));
    await waitFor(() => expect(setStatus).toHaveBeenCalledWith("membership-member", "disabled"));
    await screen.findByText("member@example.test");

    await user.click(screen.getAllByRole("button", { name: "重置密码" })[1]);
    fireEvent.change(screen.getByLabelText(/新密码/), { target: { value: "AnotherSecure!2026" } });
    await user.click(screen.getByRole("button", { name: "确认重置" }));
    await waitFor(() => expect(reset).toHaveBeenCalledWith("membership-member", "AnotherSecure!2026"));
    expect(await screen.findByText(/撤销 3 个会话/)).toBeInTheDocument();
  });

  it("imports CSV and renders every row outcome", async () => {
    const user = userEvent.setup();
    vi.spyOn(memberApi, "bulkCsv").mockResolvedValue({
      batchId: "batch-1",
      summary: { total: 2, succeeded: 1, created: 1, updated: 0, unchanged: 0, duplicated: 0, failed: 1 },
      rows: [
        { rowNumber: 1, account: "ok@example.test", outcome: "created", member: cardOwner },
        { rowNumber: 2, account: "bad", outcome: "failed", error: { code: "ROW_INVALID", message: "密码过短", fields: ["password"] } },
      ],
    });
    renderPage();
    await screen.findByText("member@example.test");
    await user.click(screen.getByRole("button", { name: "批量导入" }));
    fireEvent.change(screen.getByRole("textbox", { name: "CSV 文本" }), { target: { value: "account,display_name,password\nok@example.test,张三,SecurePassword!2026" } });
    await user.click(screen.getByRole("button", { name: "开始导入" }));
    expect(await screen.findByText("逐行导入结果")).toBeInTheDocument();
    expect(screen.getByText(/密码过短/)).toHaveTextContent("字段：password");
  });
});

import { FluentProvider } from "@fluentui/react-components";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { adminLightTheme } from "../theme";
import { LoginForm } from "./LoginPage";

describe("LoginForm", () => {
  it("blocks login and explains when the API is not configured", () => {
    render(
      <FluentProvider theme={adminLightTheme}>
        <LoginForm
          pending={false}
          apiConfigured={false}
          onLogin={async () => undefined}
        />
      </FluentProvider>,
    );

    expect(screen.getByText(/尚未配置 VITE_API_BASE_URL/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登录" })).toBeDisabled();
  });

  it("submits credentials only after both fields are entered", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn().mockResolvedValue(undefined);
    render(
      <FluentProvider theme={adminLightTheme}>
        <LoginForm pending={false} apiConfigured onLogin={onLogin} />
      </FluentProvider>,
    );

    await user.type(screen.getByRole("textbox", { name: /账号/ }), "admin@example.test");
    await user.type(screen.getByLabelText(/密码/), "safe-password");
    await user.click(screen.getByRole("button", { name: "登录" }));

    expect(onLogin).toHaveBeenCalledWith({
      account: "admin@example.test",
      credential: "safe-password",
    });
  });

  it("offers enterprise WeChat login when the connector action is available", async () => {
    const user = userEvent.setup();
    const onWeComLogin = vi.fn().mockResolvedValue(undefined);
    render(
      <FluentProvider theme={adminLightTheme}>
        <LoginForm
          pending={false}
          apiConfigured
          onLogin={async () => undefined}
          onWeComLogin={onWeComLogin}
        />
      </FluentProvider>,
    );

    await user.click(screen.getByRole("button", { name: "企业微信登录" }));
    expect(onWeComLogin).toHaveBeenCalledTimes(1);
  });
});

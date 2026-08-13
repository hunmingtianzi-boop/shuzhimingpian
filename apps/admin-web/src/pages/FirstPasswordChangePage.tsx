import { Button, Field, Input, MessageBar, MessageBarBody } from "@fluentui/react-components";
import { LockClosed24Regular } from "@fluentui/react-icons";
import { type FormEvent, useState } from "react";

import { useAuth } from "../auth/AuthContext";

export function FirstPasswordChangePage() {
  const auth = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const valid = newPassword.length >= 12 && newPassword === confirmation;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (currentPassword && valid && !auth.loginPending) {
      void auth.changePassword(currentPassword, newPassword);
    }
  };

  return (
    <main className="login-page first-password-page">
      <section className="login-context" aria-label="账号安全说明">
        <div className="login-context-content">
          <span className="product-name">创非凡数智名片</span>
          <h2>企业账号已安全交付。</h2>
          <p>临时密码只用于验证交付对象。设置正式密码后，才能进入企业工作台。</p>
        </div>
      </section>
      <section className="login-panel">
        <form className="login-form" onSubmit={submit}>
          <div className="login-heading">
            <div className="login-mark" aria-hidden><LockClosed24Regular /></div>
            <div>
              <p className="eyebrow">企业账号首次登录</p>
              <h1 id="first-password-change-title">设置正式密码</h1>
              <p>完成这一步即可进入企业工作台。</p>
            </div>
          </div>
          {auth.error && (
            <MessageBar intent="error">
              <MessageBarBody>{auth.error.message}</MessageBarBody>
            </MessageBar>
          )}
          <Field label="当前临时密码" required>
            <Input type="password" value={currentPassword} onChange={(_, data) => setCurrentPassword(data.value)} />
          </Field>
          <Field label="新密码" hint="至少 12 个字符" required>
            <Input type="password" value={newPassword} onChange={(_, data) => setNewPassword(data.value)} />
          </Field>
          <Field
            label="再次输入新密码"
            required
            validationState={confirmation && confirmation !== newPassword ? "error" : "none"}
            validationMessage={confirmation && confirmation !== newPassword ? "两次输入不一致" : undefined}
          >
            <Input type="password" value={confirmation} onChange={(_, data) => setConfirmation(data.value)} />
          </Field>
          <Button appearance="primary" type="submit" disabled={!currentPassword || !valid || auth.loginPending}>
            {auth.loginPending ? "正在保存" : "修改密码并进入工作台"}
          </Button>
        </form>
      </section>
    </main>
  );
}

import {
  Button,
  Field,
  Input,
  MessageBar,
  MessageBarBody,
} from "@fluentui/react-components";
import {
  Building24Regular,
  Chat24Regular,
  LockClosed24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";
import type { FormEvent } from "react";

import type { ApiError } from "../api/client";
import type { LoginInput } from "../api/types";
import { useAuth } from "../auth/AuthContext";

export type LoginFormProps = {
  pending: boolean;
  apiConfigured: boolean;
  error?: ApiError;
  onLogin: (input: LoginInput) => Promise<void>;
  onWeComLogin?: () => Promise<void>;
};

export function LoginForm({
  pending,
  apiConfigured,
  error,
  onLogin,
  onWeComLogin,
}: LoginFormProps) {
  const [account, setAccount] = useState("");
  const [credential, setCredential] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!account.trim() || !credential || pending || !apiConfigured) return;
    await onLogin({ account, credential }).catch(() => undefined);
  };

  return (
    <form className="login-form" onSubmit={submit} noValidate>
      <div className="login-heading">
        <div className="login-mark" aria-hidden>
          <Building24Regular />
        </div>
        <div>
          <h1>企业管理工作台</h1>
          <p>使用企业管理员账号登录。</p>
        </div>
      </div>

      {!apiConfigured && (
        <MessageBar intent="warning">
          <MessageBarBody>
            尚未配置 VITE_API_BASE_URL，认证服务当前不可用。
          </MessageBarBody>
        </MessageBar>
      )}

      {error && (
        <MessageBar intent="error">
          <MessageBarBody>
            <strong>登录失败</strong>
            <div>{error.message}</div>
            {(error.code || error.requestId) && (
              <div className="error-reference">
                <span>错误代码：{error.code}</span>
                {error.requestId && <span>请求编号：{error.requestId}</span>}
              </div>
            )}
          </MessageBarBody>
        </MessageBar>
      )}

      <Field label="账号" required>
        <Input
          type="text"
          name="account"
          value={account}
          onChange={(_, data) => setAccount(data.value)}
          autoComplete="username"
          placeholder="请输入管理员账号"
          disabled={pending}
        />
      </Field>

      <Field label="密码" required>
        <Input
          type="password"
          name="credential"
          value={credential}
          onChange={(_, data) => setCredential(data.value)}
          autoComplete="current-password"
          disabled={pending}
        />
      </Field>

      <Button
        type="submit"
        appearance="primary"
        size="large"
        icon={<LockClosed24Regular />}
        disabled={!apiConfigured || pending || !account.trim() || !credential}
      >
        {pending ? "正在登录" : "登录"}
      </Button>

      {onWeComLogin && (
        <>
          <div className="login-divider" role="separator">
            <span>或</span>
          </div>
          <Button
            type="button"
            appearance="outline"
            size="large"
            icon={<Chat24Regular />}
            disabled={!apiConfigured || pending}
            onClick={() => void onWeComLogin().catch(() => undefined)}
          >
            企业微信登录
          </Button>
        </>
      )}
    </form>
  );
}

export function LoginPage() {
  const auth = useAuth();
  return (
    <main className="login-page">
      <section className="login-context" aria-label="工作台说明">
        <div className="login-context-content">
          <span className="product-name">创非凡数智名片</span>
          <h2>统一管理企业资料、名片与 AI 知识内容。</h2>
          <p>
            所有管理操作以真实服务响应为准。未连接的接口会显示明确错误，不会填充演示数据。
          </p>
        </div>
      </section>
      <section className="login-panel">
        <LoginForm
          pending={auth.loginPending}
          apiConfigured={auth.apiConfigured}
          error={auth.error}
          onLogin={auth.login}
          onWeComLogin={auth.wecomLogin}
        />
      </section>
    </main>
  );
}

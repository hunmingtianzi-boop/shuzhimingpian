import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";

import { adminApi } from "../api/adminApi";
import {
  ADMIN_AUTH_EXPIRED_EVENT,
  apiClient,
  ApiError,
} from "../api/client";
import type { AdminUser, LoginInput } from "../api/types";
import {
  APP_PATHS,
  appHref,
  appPathFromBrowser,
  wecomEntryReturnTo,
  WECOM_CALLBACK_PATH,
  WECOM_ENTRY_PATH,
} from "../routing";

type AuthStatus = "bootstrapping" | "unauthenticated" | "authenticated";

export type AuthContextValue = {
  status: AuthStatus;
  user?: AdminUser;
  error?: ApiError;
  loginPending: boolean;
  apiConfigured: boolean;
  login: (input: LoginInput) => Promise<void>;
  wecomLogin?: () => Promise<void>;
  wecomBind?: () => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

type AuthProviderProps = {
  children: ReactNode;
  externalRedirect?: (url: string) => void;
};

function assignExternalLocation(url: string): void {
  globalThis.location.assign(url);
}

function asApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("登录过程中发生未知错误。", { code: "UNKNOWN_ERROR" });
}

export function AuthProvider({
  children,
  externalRedirect = assignExternalLocation,
}: AuthProviderProps) {
  const [status, setStatus] = useState<AuthStatus>("bootstrapping");
  const [user, setUser] = useState<AdminUser>();
  const [error, setError] = useState<ApiError>();
  const [loginPending, setLoginPending] = useState(false);

  const beginWeComLogin = useCallback(
    async (returnTo: string) => {
      setLoginPending(true);
      setError(undefined);
      try {
        const authorizeUrl = await apiClient.createWeComLoginUrl(returnTo);
        externalRedirect(authorizeUrl);
      } catch (caught) {
        const apiError = asApiError(caught);
        setError(apiError);
        setStatus("unauthenticated");
        throw apiError;
      } finally {
        setLoginPending(false);
      }
    },
    [externalRedirect],
  );

  useEffect(() => {
    let active = true;
    const handleExpired = () => {
      setUser(undefined);
      setStatus("unauthenticated");
    };
    globalThis.addEventListener(ADMIN_AUTH_EXPIRED_EVENT, handleExpired);

    const bootstrap = async () => {
      if (!apiClient.isConfigured()) {
        if (active) setStatus("unauthenticated");
        return;
      }

      try {
        const appPath = appPathFromBrowser(globalThis.location.pathname);
        const query = new URLSearchParams(globalThis.location.search);
        const code = query.get("code");
        const state = query.get("state");
        const isWeComCallback = appPath === WECOM_CALLBACK_PATH;
        if (isWeComCallback && (!code || !state)) {
          throw new ApiError("企业微信没有返回完整的登录凭证，请重新进入应用。", {
            code: "WECOM_OAUTH_CALLBACK_INVALID",
          });
        }
        if (isWeComCallback && code && state) {
          const flow = apiClient.consumeWeComFlow();
          if (flow === "bind") {
            await apiClient.refreshSession();
            await apiClient.bindWithWeCom(code, state);
          } else {
            await apiClient.loginWithWeCom(code, state);
          }
          globalThis.history.replaceState(
            {},
            "",
            apiClient.consumeWeComReturnTo(),
          );
        } else {
          await apiClient.refreshSession();
        }
        const currentUser = await adminApi.me();
        if (!active) return;
        setUser(currentUser);
        setStatus("authenticated");
      } catch (caught) {
        apiClient.clearSession();
        if (!active) return;
        const appPath = appPathFromBrowser(globalThis.location.pathname);
        if (appPath === WECOM_ENTRY_PATH) {
          // The dedicated workbench URL is intentionally login-only. Keeping
          // this state on the boot screen avoids flashing the password form
          // between the session probe and the WeCom authorization redirect.
          setStatus("bootstrapping");
          await beginWeComLogin(
            wecomEntryReturnTo(globalThis.location.search),
          ).catch(() => undefined);
          return;
        }
        if (appPath === WECOM_CALLBACK_PATH) {
          setError(asApiError(caught));
        }
        setStatus("unauthenticated");
      }
    };

    void bootstrap();
    return () => {
      active = false;
      globalThis.removeEventListener(ADMIN_AUTH_EXPIRED_EVENT, handleExpired);
    };
  }, [beginWeComLogin]);

  const login = useCallback(async ({ account, credential }: LoginInput) => {
    setLoginPending(true);
    setError(undefined);
    try {
      await apiClient.login(account.trim(), credential);
      const currentUser = await adminApi.me();
      setUser(currentUser);
      setStatus("authenticated");
    } catch (caught) {
      apiClient.clearSession();
      const apiError = asApiError(caught);
      setError(apiError);
      setStatus("unauthenticated");
      throw apiError;
    } finally {
      setLoginPending(false);
    }
  }, []);

  const logout = useCallback(async () => {
    setError(undefined);
    try {
      await apiClient.logout();
    } catch (caught) {
      setError(asApiError(caught));
    } finally {
      setUser(undefined);
      setStatus("unauthenticated");
    }
  }, []);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    setLoginPending(true);
    setError(undefined);
    try {
      await adminApi.changePassword(currentPassword, newPassword);
      await apiClient.refreshSession();
      setUser(await adminApi.me());
    } catch (caught) {
      const apiError = asApiError(caught);
      setError(apiError);
      throw apiError;
    } finally {
      setLoginPending(false);
    }
  }, []);

  const wecomLogin = useCallback(
    () => beginWeComLogin(appHref(APP_PATHS.setup)),
    [beginWeComLogin],
  );

  const wecomBind = useCallback(async () => {
    setLoginPending(true);
    setError(undefined);
    try {
      const authorizeUrl = await apiClient.createWeComBindingUrl(appHref("/cards"));
      globalThis.location.assign(authorizeUrl);
    } catch (caught) {
      const apiError = asApiError(caught);
      setError(apiError);
      throw apiError;
    } finally {
      setLoginPending(false);
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      error,
      loginPending,
      apiConfigured: apiClient.isConfigured(),
      login,
      wecomLogin,
      wecomBind,
      logout,
      changePassword,
    }),
    [changePassword, error, login, loginPending, logout, status, user, wecomBind, wecomLogin],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

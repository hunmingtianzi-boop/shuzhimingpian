import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";

export type ResourceStatus =
  | "loading"
  | "ready"
  | "empty"
  | "error"
  | "permission";

export type ResourceState<T> = {
  status: ResourceStatus;
  data?: T;
  error?: ApiError;
  reload: () => void;
};

type ResourceRefreshOptions = {
  refreshIntervalMs?: number;
  refreshOnVisible?: boolean;
};

function isEmpty(value: unknown): boolean {
  return value === null || (Array.isArray(value) && value.length === 0);
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError("加载数据时发生未知错误。", { code: "UNKNOWN_ERROR" });
}

export function useResource<T>(
  loader: () => Promise<T>,
  dependencyKey?: string | number | boolean,
  refreshOptions: ResourceRefreshOptions = {},
): ResourceState<T> {
  const loaderRef = useRef(loader);
  const [reloadKey, setReloadKey] = useState(0);
  const [state, setState] = useState<Omit<ResourceState<T>, "reload">>({
    status: "loading",
  });

  loaderRef.current = loader;

  const reload = useCallback(() => {
    setReloadKey((value) => value + 1);
  }, []);

  useEffect(() => {
    let active = true;
    setState({ status: "loading" });

    void loaderRef.current().then(
      (data) => {
        if (!active) return;
        setState({ status: isEmpty(data) ? "empty" : "ready", data });
      },
      (error: unknown) => {
        if (!active) return;
        const apiError = asApiError(error);
        setState({
          status: apiError.status === 403 ? "permission" : "error",
          error: apiError,
        });
      },
    );

    return () => {
      active = false;
    };
  }, [dependencyKey, reloadKey]);

  useEffect(() => {
    const intervalMs = refreshOptions.refreshIntervalMs;
    const refreshOnVisible = refreshOptions.refreshOnVisible ?? false;
    if (!intervalMs && !refreshOnVisible) return undefined;

    let active = true;
    const refreshSilently = () => {
      void loaderRef.current().then(
        (data) => {
          if (!active) return;
          setState({ status: isEmpty(data) ? "empty" : "ready", data });
        },
        () => {
          // Keep the last successful result during background refresh errors.
        },
      );
    };
    const visibilityChanged = () => {
      if (refreshOnVisible && document.visibilityState === "visible") {
        refreshSilently();
      }
    };
    const intervalId = intervalMs
      ? window.setInterval(refreshSilently, intervalMs)
      : undefined;
    if (refreshOnVisible) {
      document.addEventListener("visibilitychange", visibilityChanged);
    }
    return () => {
      active = false;
      if (intervalId !== undefined) window.clearInterval(intervalId);
      if (refreshOnVisible) {
        document.removeEventListener("visibilitychange", visibilityChanged);
      }
    };
  }, [dependencyKey, reloadKey, refreshOptions.refreshIntervalMs, refreshOptions.refreshOnVisible]);

  return { ...state, reload };
}

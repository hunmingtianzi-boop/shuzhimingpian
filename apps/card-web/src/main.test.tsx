import "@testing-library/jest-dom/vitest";

import {
  Children,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EnterpriseCardConfig } from "./domain/card";
import type { PublicCardData } from "./lib/publicCardApi";
import { templateTenant } from "./tenants/template/tenant";

const mocks = vi.hoisted(() => {
  const rootRender = vi.fn();
  return {
    app: vi.fn(() => null),
    applyTenantRuntime: vi.fn(),
    createRoot: vi.fn(() => ({ render: rootRender })),
    fetchPublicCard: vi.fn(),
    loadTenant: vi.fn(),
    mergePublishedCard: vi.fn(),
    resolveTenantSlug: vi.fn(),
    rootRender,
    validateTenantConfig: vi.fn(),
  };
});

vi.mock("react-dom/client", () => ({ createRoot: mocks.createRoot }));
vi.mock("./App", () => ({ default: mocks.app }));
vi.mock("./lib/publicCardApi", () => ({
  fetchPublicCard: mocks.fetchPublicCard,
}));
vi.mock("./lib/publicCard", () => ({
  mergePublishedCard: mocks.mergePublishedCard,
}));
vi.mock("./lib/tenantRuntime", () => ({
  applyTenantRuntime: mocks.applyTenantRuntime,
}));
vi.mock("./lib/validateTenantConfig", () => ({
  validateTenantConfig: mocks.validateTenantConfig,
}));
vi.mock("./tenants", () => ({
  loadTenant: mocks.loadTenant,
  resolveTenantSlug: mocks.resolveTenantSlug,
}));

const publishedCard: PublicCardData = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "tuotu",
  display_name: "公开名片",
  title: "解决方案顾问",
  contact_fields: [],
  company: {
    id: "22222222-2222-2222-2222-222222222222",
    name: "公开企业",
    summary: "已发布的企业介绍。",
  },
  featured_products: [],
  featured_cases: [],
  faq_items: [],
  ai_assistant: {
    available: true,
    display_name: "企业助手",
    disclosure: "回答由 AI 生成",
    welcome_message: "你好",
    suggested_questions: [],
  },
  policy_versions: {
    privacy: "privacy-v1",
    chat_notice: "chat-v1",
    lead_consent: "lead-v1",
    profile_personalization: "profile-v1",
  },
};

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function findElementByType(
  node: ReactNode,
  type: unknown,
): ReactElement<Record<string, unknown>> | undefined {
  if (!isValidElement(node)) return undefined;
  if (node.type === type) {
    return node as ReactElement<Record<string, unknown>>;
  }
  const children = (node.props as { children?: ReactNode }).children;
  for (const child of Children.toArray(children)) {
    const result = findElementByType(child, type);
    if (result) return result;
  }
  return undefined;
}

function finalAppProps() {
  const finalTree = mocks.rootRender.mock.calls.at(-1)?.[0] as ReactNode;
  return findElementByType(finalTree, mocks.app)?.props;
}

async function waitForRenderCount(expectedCount: number) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (mocks.rootRender.mock.calls.length === expectedCount) return;
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  }
  expect(mocks.rootRender).toHaveBeenCalledTimes(expectedCount);
}

describe("card tenant bootstrap", () => {
  beforeEach(() => {
    vi.resetModules();
    mocks.rootRender.mockReset();
    mocks.app.mockClear();
    mocks.createRoot.mockClear();
    mocks.fetchPublicCard.mockReset();
    mocks.loadTenant.mockReset();
    mocks.mergePublishedCard.mockReset();
    mocks.resolveTenantSlug.mockReset();
    mocks.applyTenantRuntime.mockReset();
    mocks.validateTenantConfig.mockReset();
    mocks.resolveTenantSlug.mockReturnValue("tuotu");
    mocks.validateTenantConfig.mockReturnValue({ valid: true, errors: [] });
    window.history.replaceState({}, "", "/");
    document.body.innerHTML = '<div id="root"></div>';
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it(
    "keeps the loading screen until local and published data are both resolved",
    async () => {
      const remote = deferred<PublicCardData | undefined>();
      mocks.loadTenant.mockResolvedValue(templateTenant);
      mocks.fetchPublicCard.mockReturnValue(remote.promise);

      await import("./main");
      await Promise.resolve();

      expect(mocks.rootRender).toHaveBeenCalledTimes(1);
      expect(mocks.applyTenantRuntime).not.toHaveBeenCalled();

      remote.resolve(undefined);
      await waitForRenderCount(2);

      expect(finalAppProps()).toMatchObject({
        tenant: templateTenant,
        publishedCard: undefined,
      });
      expect(mocks.applyTenantRuntime).toHaveBeenCalledOnce();
    },
    15_000,
  );

  it("renders the merged published tenant once without exposing the local draft first", async () => {
    const mergedTenant: EnterpriseCardConfig = {
      ...templateTenant,
      id: "merged-published-tenant",
    };
    mocks.loadTenant.mockResolvedValue(templateTenant);
    mocks.fetchPublicCard.mockResolvedValue(publishedCard);
    mocks.mergePublishedCard.mockReturnValue(mergedTenant);

    await import("./main");
    await waitForRenderCount(2);

    expect(mocks.mergePublishedCard).toHaveBeenCalledWith(
      publishedCard,
      templateTenant,
      templateTenant,
    );
    expect(finalAppProps()).toMatchObject({
      tenant: mergedTenant,
      publishedCard,
    });
    expect(mocks.applyTenantRuntime).toHaveBeenCalledTimes(1);
    expect(mocks.applyTenantRuntime).toHaveBeenCalledWith(mergedTenant);
  });

  it("safely falls back to the local tenant when the public API fails", async () => {
    const remote = deferred<PublicCardData | undefined>();
    mocks.loadTenant.mockResolvedValue(templateTenant);
    mocks.fetchPublicCard.mockReturnValue(remote.promise);

    await import("./main");
    await Promise.resolve();
    expect(mocks.rootRender).toHaveBeenCalledTimes(1);

    remote.reject(new Error("public API unavailable"));
    await waitForRenderCount(2);

    expect(finalAppProps()).toMatchObject({
      tenant: templateTenant,
      publishedCard: undefined,
    });
    expect(mocks.applyTenantRuntime).toHaveBeenCalledTimes(1);
  });

  it("shows an explicit load error for a real card route when the public API fails", async () => {
    window.history.replaceState({}, "", "/c/tuotu");
    const remote = deferred<PublicCardData | undefined>();
    mocks.loadTenant.mockResolvedValue(templateTenant);
    mocks.fetchPublicCard.mockReturnValue(remote.promise);

    await import("./main");
    await Promise.resolve();
    remote.reject(new Error("public API unavailable"));
    await waitForRenderCount(2);

    const finalTree = mocks.rootRender.mock.calls.at(-1)?.[0] as ReactNode;
    render(finalTree);

    expect(screen.getByRole("heading", { name: "名片暂时无法加载" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新加载" })).toBeInTheDocument();
    expect(document.querySelector(".bp-person-head")).not.toBeInTheDocument();
    expect(screen.queryByText("拓浙 AI")).not.toBeInTheDocument();
    expect(finalAppProps()).toBeUndefined();
    expect(mocks.applyTenantRuntime).not.toHaveBeenCalled();
  }, 15_000);

  it("does not leave a registered tenant on the loading screen when the public API hangs", async () => {
    vi.useFakeTimers();
    mocks.loadTenant.mockResolvedValue(templateTenant);
    mocks.fetchPublicCard.mockReturnValue(new Promise(() => undefined));

    await import("./main");
    await Promise.resolve();
    expect(mocks.rootRender).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(5_000);
    await Promise.resolve();

    expect(finalAppProps()).toMatchObject({
      tenant: templateTenant,
      publishedCard: undefined,
    });
    expect(mocks.applyTenantRuntime).toHaveBeenCalledOnce();
  });
});

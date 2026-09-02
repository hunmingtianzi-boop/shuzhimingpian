import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./styles.css";

import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { TenantLoading } from "./components/TenantLoading";
import { TenantNotFound } from "./components/TenantNotFound";
import type { EnterpriseCardConfig } from "./domain/card";
import {
  fetchPublicCard,
  type PublicCardData,
} from "./lib/publicCardApi";
import { applyTenantRuntime } from "./lib/tenantRuntime";
import { validateTenantConfig } from "./lib/validateTenantConfig";
import { loadTenant, resolveTenantSlug } from "./tenants";

const tenantSlug = resolveTenantSlug(window.location);
const root = createRoot(document.getElementById("root")!);
const PUBLIC_CARD_BOOTSTRAP_TIMEOUT_MS = 5_000;
const isExplicitCardMock = new URLSearchParams(window.location.search).has("mock-card");
const requiresPublishedCard = /(?:^|\/)c\/[^/]+\/?$/.test(window.location.pathname)
  && !isExplicitCardMock;

async function fetchPublishedCard(slug: string) {
  const controller = new AbortController();
  let timeoutId: number | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = window.setTimeout(() => {
      controller.abort();
      reject(new Error("Public card bootstrap timed out"));
    }, PUBLIC_CARD_BOOTSTRAP_TIMEOUT_MS);
  });

  try {
    return await Promise.race([fetchPublicCard(slug, controller.signal), timeout]);
  } finally {
    if (timeoutId !== undefined) window.clearTimeout(timeoutId);
  }
}

type AppComponent = typeof import("./App").default;

function renderTenant(
  App: AppComponent,
  tenant: EnterpriseCardConfig,
  publishedCard?: PublicCardData,
) {
  const validation = validateTenantConfig(tenant);
  if (!validation.valid) {
    console.error("Tenant config validation failed", validation.errors);
    root.render(
      <StrictMode>
        <TenantNotFound kind="invalid" onRetry={() => window.location.reload()} />
      </StrictMode>,
    );
    return false;
  }

  applyTenantRuntime(tenant);
  root.render(
    <StrictMode>
      <AppErrorBoundary>
        <App tenant={tenant} publishedCard={publishedCard} />
      </AppErrorBoundary>
    </StrictMode>,
  );
  return true;
}

if (tenantSlug) {
  root.render(
    <StrictMode>
      <TenantLoading />
    </StrictMode>,
  );
} else {
  root.render(
    <StrictMode>
      <TenantNotFound />
    </StrictMode>,
  );
}

async function bootstrapTenant() {
  if (!tenantSlug) return;
  // Start every critical public-card dependency together. The public card
  // request may already be in flight from early-card-bootstrap.js, so the
  // renderer, merge logic and fallback template should never form a serial
  // waterfall behind it.
  const appModulePromise = import("./App");
  const mergeModulePromise = import("./lib/publicCard");
  const fallbackTenantPromise = loadTenant("template");
  const registeredTenantPromise = loadTenant(tenantSlug)
    .then((tenant) => ({ tenant, error: undefined }))
    .catch((error: unknown) => ({ tenant: undefined, error }));
  const publishedCardPromise = fetchPublishedCard(tenantSlug)
    .then((card) => ({ card, error: undefined }))
    .catch((error: unknown) => ({ card: undefined, error }));

  const [registeredResult, publishedResult] = await Promise.all([
    registeredTenantPromise,
    publishedCardPromise,
  ]);
  const registeredTenant = registeredResult.tenant;

  if (registeredResult.error) {
    console.error("Registered tenant loading failed", {
      errorType:
        registeredResult.error instanceof Error
          ? registeredResult.error.name
          : typeof registeredResult.error,
    });
  }

  try {
    if (publishedResult.error) throw publishedResult.error;
    const [{ default: App }, { mergePublishedCard }, fallbackTemplate] =
      await Promise.all([
        appModulePromise,
        mergeModulePromise,
        fallbackTenantPromise,
      ]);
    const publishedCard = publishedResult.card;
    if (publishedCard) {
      const fallbackTenant = registeredTenant ?? fallbackTemplate;
      if (!fallbackTenant) throw new Error("Generic tenant template is unavailable");
      renderTenant(
        App,
        mergePublishedCard(publishedCard, registeredTenant, fallbackTenant),
        publishedCard,
      );
      return;
    }
    if (requiresPublishedCard) {
      root.render(
        <StrictMode>
          <TenantNotFound />
        </StrictMode>,
      );
      return;
    }
    if (registeredTenant) {
      renderTenant(App, registeredTenant);
      return;
    }

    root.render(
      <StrictMode>
        <TenantNotFound />
      </StrictMode>,
    );
  } catch (error) {
    console.error("Published tenant loading failed", {
      errorType: error instanceof Error ? error.name : typeof error,
    });
    if (registeredTenant && !requiresPublishedCard) {
      try {
        const { default: App } = await appModulePromise;
        renderTenant(App, registeredTenant);
        return;
      } catch (runtimeError) {
        console.error("Registered tenant runtime loading failed", {
          errorType: runtimeError instanceof Error ? runtimeError.name : typeof runtimeError,
        });
      }
    }

    root.render(
      <StrictMode>
        <TenantNotFound
          kind={requiresPublishedCard ? "load" : "runtime"}
          onRetry={() => window.location.reload()}
        />
      </StrictMode>,
    );
  }
}

void bootstrapTenant();

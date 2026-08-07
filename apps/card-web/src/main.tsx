import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
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

function renderTenant(tenant: EnterpriseCardConfig, publishedCard?: PublicCardData) {
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
    const publishedCard = publishedResult.card;
    if (publishedCard) {
      const { mergePublishedCard } = await import("./lib/publicCard");
      const fallbackTenant = registeredTenant ?? (await loadTenant("template"));
      if (!fallbackTenant) throw new Error("Generic tenant template is unavailable");
      renderTenant(
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
      renderTenant(registeredTenant);
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
      renderTenant(registeredTenant);
      return;
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

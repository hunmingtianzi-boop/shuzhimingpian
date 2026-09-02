import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchPublicCard } from "./publicCardApi";

describe("public card bootstrap request", () => {
  afterEach(() => {
    delete window.__CF_PUBLIC_CARD_BOOTSTRAP__;
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("reuses the request started by the document bootstrap", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "/api/v1");
    const networkFetch = vi.spyOn(window, "fetch");
    const slug = "early-card";
    const endpoint = new URL(
      `/api/v1/public/cards/${slug}`,
      window.location.origin,
    ).href;
    window.__CF_PUBLIC_CARD_BOOTSTRAP__ = {
      endpoint,
      slug,
      promise: Promise.resolve({ ok: false, payload: {}, status: 404 }),
    };

    await expect(fetchPublicCard(slug)).resolves.toBeUndefined();

    expect(networkFetch).not.toHaveBeenCalled();
    expect(window.__CF_PUBLIC_CARD_BOOTSTRAP__).toBeUndefined();
  });

  it("does not reuse a bootstrap request for another card", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "/api/v1");
    const networkFetch = vi.spyOn(window, "fetch").mockResolvedValue(
      new Response("{}", {
        headers: { "Content-Type": "application/json" },
        status: 404,
      }),
    );
    window.__CF_PUBLIC_CARD_BOOTSTRAP__ = {
      endpoint: new URL(
        "/api/v1/public/cards/another-card",
        window.location.origin,
      ).href,
      slug: "another-card",
      promise: Promise.resolve({ ok: false, payload: {}, status: 404 }),
    };

    await expect(fetchPublicCard("requested-card")).resolves.toBeUndefined();

    expect(networkFetch).toHaveBeenCalledOnce();
  });
});

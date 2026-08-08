import { afterEach, describe, expect, it, vi } from "vitest";

import { resolveApiResourceUrl } from "./resourceUrl";

describe("resolveApiResourceUrl", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("routes API-owned relative assets through the configured API origin", () => {
    vi.stubEnv("VITE_API_BASE_URL", "http://127.0.0.1:38100/api/v1");

    expect(resolveApiResourceUrl("/api/v1/public/card-assets/company/logo.webp")).toBe(
      "http://127.0.0.1:38100/api/v1/public/card-assets/company/logo.webp",
    );
  });

  it("preserves a deployment prefix from a relative API base URL", () => {
    vi.stubEnv("VITE_API_BASE_URL", "/c/api/v1");

    expect(resolveApiResourceUrl("/api/v1/public/card-assets/company/logo.webp")).toBe(
      new URL(
        "/c/api/v1/public/card-assets/company/logo.webp",
        globalThis.location.origin,
      ).toString(),
    );
  });

  it("keeps public HTTPS resources unchanged", () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1");

    expect(resolveApiResourceUrl("https://cdn.example.test/logo.webp")).toBe(
      "https://cdn.example.test/logo.webp",
    );
  });
});
